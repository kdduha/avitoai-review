"""Контракты распределения: кому какая работа и почему именно ему.

Домен называется `distribution`, а не `assignment`, потому что слово
«assignment» в этом коде уже занято заданием: `Rubric.assignment_id` — строка
вида `go-task1`, `SubmissionBundle.assignment_id` — UUID. Второй смысл под тем
же словом сделал бы обе сущности нечитаемыми.

Здесь нет ни одного вычисления. Схемы отделены намеренно: солвер должен
собираться и тестироваться без шлюза, без сети и без конфига, а `profile.py` —
единственное место домена, которое ходит к модели.

**Заявленное отделено от измеренного.** Ёмкость, навыки и медиана в карточке
ревьюера — то, что человек написал о себе, а не то, что кто-то замерил. §9.2
хочет фактическую скорость по истории ревью; истории нет. Поэтому у каждого
слагаемого скора есть `basis`, и сегодня в `measured` не попадает ничего. Через
месяц это единственное, что помешает принять анкетную цифру за факт.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Tov(StrEnum):
    """Тон обратной связи. Значения — дословно из §9.2."""

    STRICT = "строгий"
    SUPPORTIVE = "поддерживающий"
    TALKATIVE = "разговорный"


class Reviewer(BaseModel):
    """Карточка ревьюера: то, что о нём известно до всякого распределения.

    Не `ReviewerProfile`: в §9.2 профиль — вычисляемый по истории ревью объект с
    датой пересчёта и вектором сильных тем. Это анкета. Имя профиля держим
    свободным, чтобы, когда история появится, их не спутали.

    `extra="forbid"` здесь несёт смысл, а не строгость ради строгости: текущая
    занятость меняется каждый час и приходит в запросе. Карточка, в которой
    завелась `committed_minutes`, не разберётся и будет пропущена каталогом с
    записью в лог — это дешевле, чем договорённость, что так писать не надо.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    """Совпадает с именем файла: каталог ведёт человек."""
    name: str
    initials: str = ""
    email: str = ""
    source: str = ""
    """Откуда взяты цифры: «анкета куратора, 02.2026». Заявленное должно быть подписано."""

    skills: list[str] = Field(default_factory=list)
    capacity_minutes: int = 0
    """Минут разбора в неделю. Нагрузка считается в минутах, а не в работах:
    работа на Go и ноутбук по ML — это не «две работы»."""
    median_minutes_per_work: float = 0.0
    onboarding: bool = False
    tov: Tov | None = None

    course_ids: list[str] = Field(default_factory=list)
    stream_ids: list[str] = Field(default_factory=list)
    assignment_ids: list[str] = Field(default_factory=list)
    """Пространство рубрик (`go-task1`). Пусто — ограничения по заданию нет."""

    github_handle: str = ""
    """Логин, а не готовый хеш: `sha256(соль:логин)` человек руками не посчитает.
    Хеширует код той же солью, что ingest, иначе конфликт интересов молча не сработает."""
    conflict_student_ids: list[str] = Field(default_factory=list)

    max_items: int | None = None
    active: bool = True
    """Больничный снимается флагом, а не удалением файла: удалённую карточку не вернуть."""


class WorkProfile(BaseModel):
    """Что это за работа и во сколько она обойдётся ревьюеру. Строит модель (§9.2).

    Вектора тем здесь нет намеренно. §9.3 хочет косинус между сильными темами
    ревьюера и темами работы, но провайдера эмбеддингов в системе не существует,
    а поле `list[float]`, которое всегда пустое, хуже отсутствующего: его
    начинают считать заполненным.
    """

    submission_id: UUID | None = None
    origin_url: str = ""

    topics: list[str] = Field(default_factory=list)
    stack: list[str] = Field(default_factory=list)
    complexity: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_criteria: list[str] = Field(default_factory=list)
    """Идентификаторы критериев рубрики, по которым работа пограничная."""
    special_needs: list[str] = Field(default_factory=list)
    est_review_minutes: int = 0
    rationale: str = ""

    warnings: list[str] = Field(default_factory=list)
    """Что код поправил за моделью. Обрезанная оценка обязана быть видна."""

    tokens_in: int = 0
    tokens_out: int = 0
    cost_rub: float = 0.0


class DistributionItem(BaseModel):
    """Одна работа, которую надо кому-то отдать."""

    item_id: str
    """Ключ вызывающего. Обычно `str(submission_id)`, но домен в это не верит."""
    assignment_id: str = ""
    course_id: str = ""
    stream_id: str = ""
    student_internal_id: str = ""

    author_hashes: list[str] = Field(default_factory=list)
    """`Revision.author_hash` из бандла — единственная улика соавторства."""

    est_review_minutes: int | None = None
    profile: WorkProfile | None = None

    last_reviewer_id: str | None = None
    preferred_tov: Tov | None = None
    due_at: datetime | None = None

    pinned_reviewer_id: str | None = None
    excluded_reviewer_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _has_a_duration(self) -> DistributionItem:
        if self.minutes <= 0:
            raise ValueError(
                f"{self.item_id}: укажите est_review_minutes или profile — "
                "сколько стоит разбор, по ссылке не угадать"
            )
        return self

    @property
    def minutes(self) -> int:
        if self.est_review_minutes:
            return self.est_review_minutes
        return self.profile.est_review_minutes if self.profile else 0


class TermName(StrEnum):
    TOPICS = "topic_affinity"
    """Косинус по темам (§9.3, вес 1.0). Не считается: эмбеддингов нет."""
    SKILLS = "skills_cover"
    CONTINUITY = "continuity"
    TOV = "tov_fit"
    LOAD = "load_ratio"
    DEADLINE = "deadline_risk"
    FAIRNESS = "fairness_bonus"
    ONBOARDING = "onboarding_penalty"


class Basis(StrEnum):
    """На чём держится слагаемое."""

    MEASURED = "measured"
    """Замерено системой. Сегодня сюда не попадает ничего — и это видно."""
    DECLARED = "declared"
    """Из анкеты ревьюера: навыки, ёмкость, медиана, онбординг."""
    GIVEN = "given"
    """Из запроса: текущая занятость, прошлый ревьюер, срок."""


class Weights(BaseModel):
    """Веса слагаемых из §9.3.

    `skills_cover` сознательно не наследует вес 1.0 мёртвого косинуса: это
    лексическое пересечение множеств, а не семантическая близость, и притворяться
    сильным сигналом ему нечем. Появится провайдер эмбеддингов — `topic_affinity`
    встанет на своё место, знаменатель перенормируется, формула не изменится.
    """

    topics: float = 1.0
    skills: float = 0.6
    continuity: float = 0.4
    tov: float = 0.3
    load: float = -0.8
    deadline: float = -0.5
    fairness: float = 0.2
    onboarding: float = -0.7

    def of(self, term: TermName) -> float:
        return float(getattr(self, _WEIGHT_FIELD[term]))


_WEIGHT_FIELD: dict[TermName, str] = {
    TermName.TOPICS: "topics",
    TermName.SKILLS: "skills",
    TermName.CONTINUITY: "continuity",
    TermName.TOV: "tov",
    TermName.LOAD: "load",
    TermName.DEADLINE: "deadline",
    TermName.FAIRNESS: "fairness",
    TermName.ONBOARDING: "onboarding",
}


class ScoreTerm(BaseModel):
    """Одно слагаемое скора — строка карточки «почему так»."""

    term: TermName
    label: str
    weight: float
    value: float
    contribution: float
    """Уже перенормированный вклад. Сумма вкладов равна итоговому скору:
    карточка, строки которой не сходятся с заголовком, хуже отсутствующей."""
    basis: Basis
    note: str = ""


class DisabledTerm(BaseModel):
    term: TermName
    label: str
    reason: str


class Alternative(BaseModel):
    reviewer_id: str
    reviewer_name: str
    score: float


class Allocation(BaseModel):
    item_id: str
    reviewer_id: str
    reviewer_name: str
    est_review_minutes: int
    score: float
    explain: list[ScoreTerm] = Field(default_factory=list)
    """§9.5: карточка «почему так» обязана открываться без повторного вызова модели."""
    alternatives: list[Alternative] = Field(default_factory=list)
    round: int = 1
    pinned: bool = False


class UnassignedReason(StrEnum):
    NO_REVIEWERS = "no_reviewers"
    CONFLICT = "conflict"
    CAPACITY = "capacity"
    NOT_ELIGIBLE = "not_eligible"
    EXCLUDED = "excluded"
    PIN_INFEASIBLE = "pin_infeasible"


class Blocked(BaseModel):
    reviewer_id: str
    reason: UnassignedReason
    detail: str


class Unassigned(BaseModel):
    """Работа, которую не взял никто, — с поимённым списком отказавших.

    Тихо потерянная работа — худший из возможных исходов распределения:
    координатор узнает о ней от студента через неделю. Поэтому
    `len(allocations) + len(unassigned)` всегда равно числу поданных работ.
    """

    item_id: str
    est_review_minutes: int
    reason: UnassignedReason
    detail: str
    blocked_by: list[Blocked] = Field(default_factory=list)


class ReviewerLoad(BaseModel):
    reviewer_id: str
    name: str
    onboarding: bool
    capacity_minutes: int
    committed_before: int
    items: int
    minutes_assigned: int
    load_ratio_before: float
    load_ratio_after: float
    remaining_minutes: int
    tight: bool = False
    """Ревьюер у верхней границы ёмкости. Порог считает сервер: у клиента он
    иначе оказывается размазан по экранам, и три копии расходятся молча."""


class DistributionPlan(BaseModel):
    """План распределения.

    Что гарантируется: детерминированность, соблюдение жёстких ограничений,
    полнота отчёта и глобальный оптимум **внутри каждого раунда**. Что не
    гарантируется: оптимальность плана целиком — задача с бюджетом в минутах
    NP-трудна, а `load_ratio` и `fairness_bonus` меняются по ходу раскладки,
    поэтому оптимум одной большой матрицы был бы оптимумом не той функции.

    Времени генерации здесь нет намеренно: §9.5 требует, чтобы один и тот же пул
    в 10:00 и в 10:05 давал один и тот же ответ, а поле с часами сделало бы это
    требование буквально невыполнимым.
    """

    allocations: list[Allocation] = Field(default_factory=list)
    unassigned: list[Unassigned] = Field(default_factory=list)
    loads: list[ReviewerLoad] = Field(default_factory=list)

    enabled_terms: list[TermName] = Field(default_factory=list)
    disabled_terms: list[DisabledTerm] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    rounds: int = 0
    items: int = 0
    reviewers: int = 0
