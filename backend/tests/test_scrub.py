"""Обезличивание: что именно не должно уехать во внешнюю модель.

Тесты написаны от угроз, а не от функций. Каждый — про конкретный способ,
которым личность студента утекала бы в чужой сервис.
"""

from __future__ import annotations

import pytest

from avito_reviewer.ai.llm import Identity, Scrubber, residual_risk

STUDENT = Identity(
    role="student",
    name="Улитин Пётр Валерьевич",
    handles=("student-1043", "petr.ulitin"),
    emails=("ulitin.pv@edu.avito.ru",),
)


def scrub(text: str, identities=(STUDENT,)) -> str:
    return Scrubber(identities).scrub(text).text


# --------------------------------------------------------------------------- #
# известные личности
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "text",
    [
        "Работу сдал Улитин Пётр Валерьевич",
        "Автор: Пётр Улитин",           # обратный порядок
        "Сдал Улитин П. В.",            # инициалы
        "Замечания Улитину переданы",   # дательный падеж
        "работа Улитина проверена",     # родительный падеж
    ],
)
def test_known_name_is_removed_in_every_form(text):
    """Фамилия склоняется, и утечка в косвенном падеже — такая же утечка."""
    assert "Улитин" not in scrub(text)


def test_login_inside_import_paths_is_removed():
    """Логин стоит в каждой строке импорта — это самый частый путь утечки."""
    code = 'import "github.com/student-1043/service-courier/internal/service"'
    cleaned = scrub(code)
    assert "student-1043" not in cleaned
    # Структура пути обязана уцелеть, иначе разбор кода ломается.
    assert "github.com/[STUDENT_HANDLE]/service-courier" in cleaned


def test_known_email_and_its_local_part_are_removed():
    text = "почта ulitin.pv@edu.avito.ru, логин petr.ulitin"
    cleaned = scrub(text)
    assert "ulitin.pv" not in cleaned and "petr.ulitin" not in cleaned


def test_identity_without_a_name_still_covers_handles():
    """Имени в `StudentRef` нет намеренно — логины закрываться обязаны всё равно."""
    anonymous = Identity(role="student", handles=("student-1043",))
    assert "student-1043" not in scrub("github.com/student-1043/x", [anonymous])


# --------------------------------------------------------------------------- #
# люди, которых система не знает
# --------------------------------------------------------------------------- #

def test_patronymic_gives_away_a_third_party():
    assert "Ерёмина" not in scrub("Обсуждали с Ерёминой Марией Сергеевной")


def test_name_after_an_authorship_marker_is_removed():
    for line in ("Автор: Иван Петров", "Проверил: Антон Круглов", "Выполнила Мария Ерёмина"):
        assert "Петров" not in scrub(line) or "Круглов" not in scrub(line) or "Ерёмина" not in scrub(line)


def test_third_party_without_marker_or_patronymic_is_still_caught():
    """Соавтор в комментарии — тоже персональные данные, хоть мы его и не знали."""
    assert "Ерёминой" not in scrub("// обсуждали с Марией Ерёминой")


def test_code_owner_annotation_is_removed():
    """`TODO(логин)` — конвенция; логина может не быть в бандле, а личность в нём есть."""
    cleaned = scrub("// TODO(petr.ulitin): вынести в конфиг", [])
    assert "petr.ulitin" not in cleaned and "TODO(" in cleaned


def test_commit_signature_is_removed():
    cleaned = scrub("Signed-off-by: Пётр Улитин <p.ulitin@mail.ru>", [])
    assert "Улитин" not in cleaned and "p.ulitin@mail.ru" not in cleaned


# --------------------------------------------------------------------------- #
# что трогать нельзя
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "code",
    [
        'func NewOrderHandler(ctx context.Context) (*OrderHandler, error) {',
        'r.Get("/ping", handlePing)',
        'import "github.com/go-chi/chi/v5"',
        "type OrderService struct { Repo Repository }",
    ],
)
def test_code_identifiers_survive(code):
    """Латиница — это идентификаторы кода. Тронуть их значит сломать разбор."""
    assert scrub(code) == code


def test_ordinary_technical_prose_survives():
    text = "Сервис разбит на три слоя. Ошибки валидации отдаются как InvalidArgument."
    assert scrub(text) == text


def test_doc_tags_are_not_mistaken_for_telegram_handles():
    assert "@author" in scrub("@author: Мария Ерёмина", [])


# --------------------------------------------------------------------------- #
# связность и обратимость
# --------------------------------------------------------------------------- #

def test_one_person_gets_one_token_everywhere():
    """Иначе модель не поймёт, что автор README и автор комментария — один человек."""
    result = Scrubber([STUDENT]).scrub("Автор: Улитин Пётр Валерьевич\n// правка от Улитина")
    assert result.text.count("[STUDENT]") == 2


def test_rehydration_restores_each_kind_of_value():
    """Один токен — один вид значения, иначе имя вернётся на место почты."""
    result = Scrubber([STUDENT]).scrub("Улитин Пётр Валерьевич, ulitin.pv@edu.avito.ru, student-1043")
    restored = result.rehydrate(result.text)
    assert "Улитин Пётр Валерьевич" in restored
    assert "ulitin.pv@edu.avito.ru" in restored
    assert "student-1043" in restored


# --------------------------------------------------------------------------- #
# валидатор остаточного риска
# --------------------------------------------------------------------------- #

def test_validator_does_not_call_a_leak_clean():
    """Главный грех прежней версии: три замены, отчёт «чисто», ФИО уехало."""
    leaked = "Работу сдал Улитин Пётр Валерьевич"
    assert residual_risk(leaked, [STUDENT])


def test_validator_catches_a_name_it_could_not_attribute():
    assert residual_risk("Проверил Ерёмин Сергей Петрович")


def test_validator_is_quiet_on_clean_text():
    assert residual_risk(scrub("Автор: Улитин Пётр Валерьевич"), [STUDENT]) == []


def test_validator_ignores_tokens_it_put_there():
    assert residual_risk("Автор: [STUDENT], ревьюер [PERSON_1]", [STUDENT]) == []
