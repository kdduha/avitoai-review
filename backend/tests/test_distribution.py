"""Распределение: кому какая работа и почему именно ему.

Главная опасность здесь не «неоптимально», а «тихо». Потерянная работа выглядит
как отсутствие работы, и координатор узнаёт о ней от студента через неделю.
Поэтому половина тестов — про полноту отчёта, а не про качество раскладки.
"""

from __future__ import annotations

import json
import random
from datetime import timedelta
from pathlib import Path

import pytest
from factories import NOW, item, reviewer, work_profile
from pydantic import ValidationError

from avito_reviewer.distribution import (
    DistributionItem,
    ReviewerStore,
    TermName,
    Tov,
    UnassignedReason,
    Weights,
    distribute,
    validate_reviewer,
)
from avito_reviewer.ingest.identity import author_hash

REVIEWERS = Path(__file__).resolve().parents[1] / "reviewers"


# --------------------------------------------------------------------------- #
# каталог
# --------------------------------------------------------------------------- #

def test_the_catalogue_loads_reviewers_from_disk():
    store = ReviewerStore(REVIEWERS)

    assert "c-kruglov" in store.ids
    assert store.get("c-kruglov").capacity_minutes > 0
    assert len(store.all()) == len(store.ids)


def test_a_broken_file_does_not_take_down_the_roster(tmp_path):
    (tmp_path / "good.json").write_text(
        reviewer("good").model_dump_json(), encoding="utf-8"
    )
    (tmp_path / "broken.json").write_text("{не json", encoding="utf-8")

    assert ReviewerStore(tmp_path).ids == ["good"]


def test_a_missing_directory_is_survivable():
    """Приложение обязано подниматься без данных — иначе чистый запуск выглядит поломкой."""
    assert ReviewerStore("нет такого каталога").ids == []


def test_a_roster_file_cannot_carry_a_live_load(tmp_path):
    """Занятость меняется каждый час: замороженная в файле — это враньё назавтра."""
    card = json.loads(reviewer("stale").model_dump_json())
    card["committed_minutes"] = 300
    (tmp_path / "stale.json").write_text(json.dumps(card), encoding="utf-8")

    assert ReviewerStore(tmp_path).ids == []


def test_an_id_that_cannot_be_a_filename_is_refused():
    assert validate_reviewer(reviewer("../etc/passwd"))
    assert validate_reviewer(reviewer("ok")) == []


def test_zero_items_is_not_how_you_bench_a_reviewer():
    problems = validate_reviewer(reviewer("c", max_items=0))
    assert any("active" in p for p in problems)


# --------------------------------------------------------------------------- #
# жёсткие ограничения
# --------------------------------------------------------------------------- #

def test_a_co_author_never_gets_the_work():
    """Проверять работу, которую сам коммитил, нельзя ни при какой загрузке."""
    author = reviewer("c-author", github_handle="octocat")
    other = reviewer("c-other", name="Мария Ерёмина")
    work = item(author_hashes=[author_hash("octocat")])

    plan = distribute([work], [author, other])

    assert plan.allocations[0].reviewer_id == "c-other"
    blocked = [b for b in plan.allocations if b.reviewer_id == "c-author"]
    assert blocked == []


def test_a_conflict_alone_leaves_the_work_unassigned():
    author = reviewer("c-author", github_handle="octocat")
    work = item(author_hashes=[author_hash("octocat")])

    plan = distribute([work], [author])

    assert plan.allocations == []
    assert plan.unassigned[0].reason is UnassignedReason.CONFLICT
    assert "соавтор" in plan.unassigned[0].blocked_by[0].detail


def test_a_work_that_does_not_fit_the_week_is_not_squeezed_in():
    tight = reviewer("c-tight", capacity_minutes=60)

    plan = distribute([item(est_review_minutes=70)], [tight])

    assert plan.allocations == []
    assert plan.unassigned[0].reason is UnassignedReason.CAPACITY
    assert "свободно 60" in plan.unassigned[0].blocked_by[0].detail


def test_capacity_is_counted_in_minutes_not_in_works():
    """Работа на Go и ноутбук по ML — это не «две работы»."""
    tight = reviewer("c-tight", capacity_minutes=60)
    small = [item(f"s{n}", est_review_minutes=20) for n in range(3)]

    assert len(distribute(small, [tight]).allocations) == 3
    assert distribute([item(est_review_minutes=70)], [tight]).allocations == []


def test_an_inactive_reviewer_is_out_of_the_pool():
    plan = distribute([item()], [reviewer("c-sick", active=False)])

    assert plan.allocations == []
    assert plan.unassigned[0].blocked_by[0].detail == "не в строю"


def test_a_reviewer_of_another_course_is_not_offered_the_work():
    plan = distribute([item(course_id="qa")], [reviewer("c-go", course_ids=["go"])])

    assert plan.unassigned[0].reason is UnassignedReason.NOT_ELIGIBLE
    assert "не ведёт курс qa" in plan.unassigned[0].blocked_by[0].detail


def test_an_excluded_reviewer_is_skipped():
    plan = distribute([item(excluded_reviewer_ids=["c-one"])], [reviewer("c-one")])

    assert plan.unassigned[0].reason is UnassignedReason.EXCLUDED


# --------------------------------------------------------------------------- #
# нераспределённое
# --------------------------------------------------------------------------- #

def test_every_work_is_either_allocated_or_explained():
    """Инвариант, ради которого написан весь отчёт: работа не может пропасть."""
    works = [item(f"s{n}", est_review_minutes=50) for n in range(10)]
    plan = distribute(works, [reviewer("c-one", capacity_minutes=120)])

    assert len(plan.allocations) + len(plan.unassigned) == len(works) == plan.items


def test_the_report_names_who_refused_the_work_and_why():
    pool = [
        reviewer("c-full", capacity_minutes=10),
        reviewer("c-other-course", course_ids=["qa"]),
        reviewer("c-sick", active=False),
    ]
    plan = distribute([item(est_review_minutes=60)], pool)

    named = {b.reviewer_id for b in plan.unassigned[0].blocked_by}
    assert named == {"c-full", "c-other-course", "c-sick"}


def test_capacity_shortage_and_conflict_are_told_apart():
    """Нехватку ёмкости координатор чинит, конфликт — нет. Причина должна вести к действию."""
    author = reviewer("c-author", github_handle="octocat")
    tight = reviewer("c-tight", capacity_minutes=10)
    work = item(est_review_minutes=60, author_hashes=[author_hash("octocat")])

    assert distribute([work], [author, tight]).unassigned[0].reason is UnassignedReason.CAPACITY
    assert distribute([work], [author]).unassigned[0].reason is UnassignedReason.CONFLICT


def test_an_empty_pool_says_so_rather_than_returning_nothing():
    plan = distribute([item()], [])

    assert plan.unassigned[0].reason is UnassignedReason.NO_REVIEWERS
    assert plan.allocations == []


# --------------------------------------------------------------------------- #
# скор и объяснение
# --------------------------------------------------------------------------- #

def test_every_allocation_carries_its_terms():
    plan = distribute([item()], [reviewer()])

    assert plan.allocations[0].explain
    assert all(term.label for term in plan.allocations[0].explain)


def test_the_card_adds_up_to_the_headline_number():
    """Карточка, строки которой не сходятся с итогом, хуже отсутствующей."""
    plan = distribute([item(profile=work_profile())], [reviewer()])
    allocation = plan.allocations[0]

    assert sum(t.contribution for t in allocation.explain) == pytest.approx(
        allocation.score, abs=1e-6
    )
    assert -1.0 <= allocation.score <= 1.0


def test_a_term_without_data_is_disabled_not_zeroed():
    """Обнулённый терм в отчёте неотличим от посчитанного и давшего ноль."""
    plan = distribute([item()], [reviewer()])

    disabled = {d.term for d in plan.disabled_terms}
    assert TermName.SKILLS in disabled
    assert TermName.ONBOARDING in disabled
    assert TermName.SKILLS not in {t.term for t in plan.allocations[0].explain}


def test_topic_similarity_is_reported_as_not_built():
    plan = distribute([item(profile=work_profile())], [reviewer()])

    topics = next(d for d in plan.disabled_terms if d.term is TermName.TOPICS)
    assert "эмбеддинг" in topics.reason
    assert TermName.TOPICS not in plan.enabled_terms


def test_a_declared_number_is_marked_as_declared():
    """Через месяц ничто, кроме этой пометки, не помешает счесть анкету фактом."""
    plan = distribute([item(profile=work_profile())], [reviewer()])

    bases = {t.term: t.basis for t in plan.allocations[0].explain}
    assert bases[TermName.SKILLS] == "declared"
    assert bases[TermName.LOAD] == "given"
    assert "measured" not in set(bases.values())


def test_a_partially_profiled_batch_disables_the_term_for_everyone():
    """Иначе работы с профилем и без него стоят на разных шкалах внутри одной матрицы."""
    works = [item("s1", profile=work_profile()), item("s2")]

    plan = distribute(works, [reviewer()])

    assert TermName.SKILLS not in plan.enabled_terms
    assert any("несопоставим" in line for line in plan.limitations)


def test_the_alternatives_show_the_runner_up():
    pool = [reviewer("c-one"), reviewer("c-two", name="Вторая"), reviewer("c-three", name="Третий")]

    plan = distribute([item()], pool)
    allocation = plan.allocations[0]

    assert len(allocation.alternatives) == 2
    assert all(a.score <= allocation.score for a in allocation.alternatives)
    assert allocation.reviewer_id not in {a.reviewer_id for a in allocation.alternatives}


# --------------------------------------------------------------------------- #
# поведение солвера
# --------------------------------------------------------------------------- #

def test_a_specialist_gets_the_work_that_needs_the_skill():
    generalist = reviewer("c-general", skills=["go"])
    specialist = reviewer("c-mlflow", name="Алиса Штейн", skills=["mlflow", "llm"])
    work = item(profile=work_profile(special_needs=["MLflow"], topics=[], stack=[]))

    plan = distribute([work], [generalist, specialist])

    assert plan.allocations[0].reviewer_id == "c-mlflow"


def test_a_newcomer_does_not_get_the_hardest_work():
    rookie = reviewer("c-rookie", onboarding=True)
    veteran = reviewer("c-veteran", name="Ветеран")
    hard = item("s1", profile=work_profile(complexity=0.95))

    plan = distribute([hard], [rookie, veteran])

    assert plan.allocations[0].reviewer_id == "c-veteran"


def test_nobody_hoovers_the_batch():
    """Раунд — одна работа на ревьюера, поэтому сильнейший не забирает поток целиком."""
    strong = reviewer("c-strong", capacity_minutes=600, skills=["go", "docker"])
    weak = reviewer("c-weak", name="Слабее", capacity_minutes=600, skills=[])
    works = [
        item(f"s{n}", est_review_minutes=100, profile=work_profile(special_needs=["go"]))
        for n in range(6)
    ]

    plan = distribute(works, [strong, weak])
    per_reviewer = {load.reviewer_id: load.items for load in plan.loads}

    assert per_reviewer == {"c-strong": 3, "c-weak": 3}
    assert plan.rounds == 3
    assert next(load for load in plan.loads if load.reviewer_id == "c-strong").load_ratio_after == 0.5


def test_the_batch_beats_first_come_first_served():
    """Довод §9.3 за венгерский: глобальный оптимум вместо разбора в порядке поступления.

    Универсал тянет обе работы, но его хватает ровно на одну. Кто разбирает пакет
    по одной, отдаёт ему первую попавшуюся — и вторая, которую больше некому
    сделать хорошо, достаётся тому, кто её не тянет.

    Сравнивать суммы скоров двух прогонов нельзя: `load` и `fairness` зависят от
    состояния, и число получилось бы про разные пулы. Сравнивается покрытие
    навыками — величина, которая от порядка раскладки не зависит.
    """
    universal = reviewer("c-universal", capacity_minutes=30, skills=["go", "ml", "mlflow"])
    narrow = reviewer("c-narrow", name="Узкий", capacity_minutes=600, skills=["ml"])
    pool = [universal, narrow]
    works = [
        item("s1-ml", profile=work_profile(special_needs=["ml", "mlflow"])),
        item("s2-go", profile=work_profile(special_needs=["go"])),
    ]

    batch = distribute(works, pool)

    assert {a.item_id: a.reviewer_id for a in batch.allocations} == {
        "s1-ml": "c-narrow",
        "s2-go": "c-universal",
    }
    assert _coverage(batch.allocations) > _coverage(_one_at_a_time(works, pool))


def _coverage(allocations) -> float:
    """Сколько названных работой требований закрыто навыками того, кто её получил."""
    return sum(
        term.value
        for allocation in allocations
        for term in allocation.explain
        if term.term is TermName.SKILLS
    )


def _one_at_a_time(works, pool):
    """Разбор в порядке поступления тем же скором — база для сравнения."""
    committed: dict[str, int] = {}
    chosen = []
    for work in works:
        plan = distribute([work], pool, committed_minutes=committed)
        if not plan.allocations:
            continue
        allocation = plan.allocations[0]
        chosen.append(allocation)
        committed[allocation.reviewer_id] = (
            committed.get(allocation.reviewer_id, 0) + allocation.est_review_minutes
        )
    return chosen


def test_a_pinned_reviewer_keeps_the_work():
    pinned = reviewer("c-pinned", capacity_minutes=600)
    other = reviewer("c-other", name="Другой", capacity_minutes=600, skills=["go", "docker"])

    plan = distribute([item(pinned_reviewer_id="c-pinned")], [pinned, other])

    assert plan.allocations[0].reviewer_id == "c-pinned"
    assert plan.allocations[0].pinned is True
    assert next(load for load in plan.loads if load.reviewer_id == "c-pinned").items == 1


def test_a_pin_that_hides_a_conflict_is_refused():
    """Закрепление — это удобство координатора, а не обход правил."""
    author = reviewer("c-author", github_handle="octocat")
    work = item(pinned_reviewer_id="c-author", author_hashes=[author_hash("octocat")])

    plan = distribute([work], [author])

    assert plan.allocations == []
    assert plan.unassigned[0].reason is UnassignedReason.PIN_INFEASIBLE


# --------------------------------------------------------------------------- #
# воспроизводимость
# --------------------------------------------------------------------------- #

def test_the_same_pool_gives_the_same_plan():
    """§9.5: разные ответы в 10:00 и в 10:05 — и системой перестают пользоваться."""
    works = [item(f"s{n}", est_review_minutes=40) for n in range(8)]
    pool = [reviewer(f"c{n}", name=f"Р{n}", capacity_minutes=200) for n in range(3)]

    first = distribute(works, pool)
    second = distribute(works, pool)

    assert first.model_dump_json() == second.model_dump_json()


def test_the_order_of_the_input_does_not_change_the_plan():
    works = [item(f"s{n}", est_review_minutes=40) for n in range(8)]
    pool = [reviewer(f"c{n}", name=f"Р{n}", capacity_minutes=200) for n in range(3)]

    straight = distribute(works, pool)
    shuffled = distribute(list(reversed(works)), list(reversed(pool)))

    assert straight.model_dump_json() == shuffled.model_dump_json()


def test_the_plan_carries_no_clock():
    """Поле с часами сделало бы требование §9.5 буквально невыполнимым."""
    works = [item("s1", est_review_minutes=40)]
    pool = [reviewer("c1")]

    early = distribute(works, pool, now=NOW)
    late = distribute(works, pool, now=NOW + timedelta(hours=5))

    assert early.model_dump_json() == late.model_dump_json()


# --------------------------------------------------------------------------- #
# деградация
# --------------------------------------------------------------------------- #

def test_distribution_works_without_a_single_profile():
    """Раскладка не должна стоить ни одного токена, если оценка пришла с платформы."""
    works = [item(f"s{n}", est_review_minutes=30) for n in range(4)]

    plan = distribute(works, [reviewer(capacity_minutes=600)])

    assert len(plan.allocations) == 4
    assert TermName.LOAD in plan.enabled_terms


def test_a_work_without_a_duration_is_refused():
    """Цифры по умолчанию здесь быть не может: она молча съест ёмкость потока."""
    with pytest.raises(ValidationError):
        DistributionItem(item_id="s1")


def test_a_reviewer_at_the_edge_of_capacity_is_named():
    """Порог загрузки считает сервер: у клиента он расползается по экранам."""
    loaded = reviewer("c-loaded", capacity_minutes=600)
    roomy = reviewer("c-roomy", name="Свободнее", capacity_minutes=600)
    works = [item(f"s{n}", est_review_minutes=40) for n in range(2)]

    plan = distribute(works, [loaded, roomy], committed_minutes={"c-loaded": 520})
    tight = {load.reviewer_id for load in plan.loads if load.tight}

    assert tight == {"c-loaded"}
    assert any("верхней границы" in line for line in plan.limitations)


def test_an_unsalted_conflict_check_says_it_is_weaker_than_it_looks():
    author = reviewer("c-author", github_handle="octocat")
    work = item(author_hashes=[author_hash("octocat")])

    plan = distribute([work], [author, reviewer("c-other", name="Другой")])

    assert any("Соль" in line for line in plan.limitations)


def test_a_deadline_is_used_only_when_every_work_has_one():
    dated = [item(f"s{n}", due_at=NOW + timedelta(days=1)) for n in range(2)]
    mixed = [item("s1", due_at=NOW + timedelta(days=1)), item("s2")]

    assert TermName.DEADLINE in distribute(dated, [reviewer()], now=NOW).enabled_terms
    assert TermName.DEADLINE not in distribute(mixed, [reviewer()], now=NOW).enabled_terms


def test_continuity_counts_a_first_work_as_a_fact_not_as_missing_data():
    """Отсутствие прошлого ревьюера — это «работа первая», а не «мы не знаем»."""
    works = [item("s1", last_reviewer_id="c-one"), item("s2")]

    plan = distribute(works, [reviewer("c-one"), reviewer("c-two", name="Вторая")])
    first = next(a for a in plan.allocations if a.item_id == "s2")

    assert TermName.CONTINUITY in plan.enabled_terms
    note = next(t.note for t in first.explain if t.term is TermName.CONTINUITY)
    assert "первая работа" in note


def test_a_preferred_tone_is_honoured_when_asked():
    strict = reviewer("c-strict", tov=Tov.STRICT)
    warm = reviewer("c-warm", name="Тёплая", tov=Tov.SUPPORTIVE)

    plan = distribute([item(preferred_tov=Tov.SUPPORTIVE)], [strict, warm])

    assert plan.allocations[0].reviewer_id == "c-warm"


# --------------------------------------------------------------------------- #
# устойчивость к тому, что приходит снаружи
# --------------------------------------------------------------------------- #

def test_two_works_under_one_key_are_two_works():
    """`item_id` даёт вызывающий: слить два пакета или повторить запрос — его право.

    Раньше очередь чистилась по ключу, и одно назначение выносило из неё обе
    работы — вторая пропадала бесследно, ровно тем отказом, против которого
    написан весь отчёт.
    """
    works = [item("A", est_review_minutes=30), item("A", est_review_minutes=30)]

    plan = distribute(works, [reviewer("c-one", capacity_minutes=30)])

    assert len(plan.allocations) + len(plan.unassigned) == plan.items == 2
    assert len(plan.allocations) == 1
    assert plan.unassigned[0].reason is UnassignedReason.CAPACITY


def test_a_naive_deadline_does_not_take_the_request_down():
    """Тело запроса приходит и без смещения; сравнение с осведомлённым временем роняло разбор."""
    naive = item("s1", due_at=NOW.replace(tzinfo=None) + timedelta(days=1))

    plan = distribute([naive], [reviewer()], now=NOW)

    assert len(plan.allocations) == 1


def test_a_naive_now_does_not_take_the_request_down():
    plan = distribute([item("s1", due_at=NOW + timedelta(days=1))], [reviewer()],
                      now=NOW.replace(tzinfo=None))

    assert len(plan.allocations) == 1


def test_negative_load_cannot_buy_extra_capacity():
    """Отрицательная занятость из тела запроса пробивала жёсткое ограничение."""
    works = [item(f"s{n}", est_review_minutes=120) for n in range(8)]

    plan = distribute(works, [reviewer("c-one", capacity_minutes=600)],
                      committed_minutes={"c-one": -1000})
    load = plan.loads[0]

    assert load.minutes_assigned <= load.capacity_minutes


def test_a_reviewer_named_twice_is_one_reviewer():
    """Иначе клиент, суммирующий loads, видит вдвое больше работы, чем есть."""
    twice = [reviewer("c-one"), reviewer("c-one")]

    plan = distribute([item("s1", est_review_minutes=40)], twice)

    assert plan.reviewers == 1
    assert [load.reviewer_id for load in plan.loads] == ["c-one"]
    assert sum(load.minutes_assigned for load in plan.loads) == 40


def test_an_exhausted_pool_does_not_claim_to_be_empty():
    """«Ревьюеров нет» при непустом пуле отправило бы координатора искать не то."""
    works = [item(f"s{n}", est_review_minutes=50) for n in range(3)]

    plan = distribute(works, [reviewer("c-one", capacity_minutes=60)])

    assert plan.unassigned
    assert plan.unassigned[0].reason is UnassignedReason.CAPACITY


def test_the_invariant_holds_on_pools_nobody_thought_about():
    """Одиночные случаи ловят известное. Этот — неизвестное.

    Проверяются разом три обещания: работа не пропадает, ёмкость не пробивается,
    соавтор работу не получает.
    """
    rng = random.Random(20260905)
    for _ in range(300):
        pool = [
            reviewer(
                f"c{n}",
                name=f"Р{n}",
                capacity_minutes=rng.choice([0, 30, 120, 600]),
                active=rng.random() > 0.15,
                github_handle=f"h{n}",
                max_items=rng.choice([None, 1, 3]),
            )
            for n in range(rng.randint(1, 5))
        ]
        works = [
            item(
                f"s{n}",
                est_review_minutes=rng.choice([15, 40, 90, 200]),
                author_hashes=[author_hash(f"h{rng.randint(0, 4)}")] if rng.random() > 0.7 else [],
                due_at=NOW + timedelta(days=1) if rng.random() > 0.5 else None,
            )
            for n in range(rng.randint(0, 8))
        ]
        committed = {r.id: rng.choice([0, 100, 400]) for r in pool}

        plan = distribute(works, pool, committed_minutes=committed, now=NOW)
        by_id = {r.id: r for r in pool}

        assert len(plan.allocations) + len(plan.unassigned) == len(works)
        for load in plan.loads:
            # Прийти перегруженным ревьюер может — это состояние платформы.
            # Нельзя другое: чтобы движок добавил ему работы сверх ёмкости.
            if load.items:
                assert load.committed_before + load.minutes_assigned <= load.capacity_minutes
        for allocation in plan.allocations:
            got = by_id[allocation.reviewer_id]
            assert got.active
            source = next(w for w in works if w.item_id == allocation.item_id)
            assert author_hash(got.github_handle) not in source.author_hashes


def test_a_weight_that_is_not_a_number_is_refused():
    """NaN доезжал до round() и превращался в пятисотку."""
    with pytest.raises(ValidationError):
        Weights(load=float("nan"))
    with pytest.raises(ValidationError):
        Weights(load=float("inf"))


# --------------------------------------------------------------------------- #
# архитектурное правило
# --------------------------------------------------------------------------- #

def test_the_solver_does_not_reach_for_the_model_layer():
    """Детерминированная половина остаётся детерминированной по правилу, а не по намерению."""
    package = Path(__file__).resolve().parents[1] / "src" / "avito_reviewer" / "distribution"
    deterministic = ["schema.py", "roster.py", "hungarian.py", "score.py", "solver.py"]

    for name in deterministic:
        source = (package / name).read_text(encoding="utf-8")
        assert "avito_reviewer.ai" not in source, f"{name} тянется к слою модели"
        assert "llm" not in source.lower(), f"{name} упоминает LLM"
