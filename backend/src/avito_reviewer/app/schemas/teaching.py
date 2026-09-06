"""Курс, поток, задание, зачисление — то, что настраивает методист.

Граница проходит здесь: **рубрика — это требования, задание — расписание**.
Рубрика лежит файлом в каталоге и говорит, за что ставится балл; задание
говорит, какому потоку она выдана и до какого числа. Одна рубрика служит
нескольким потокам, у которых сроки разные, поэтому дата в рубрику не влезает
физически — пришлось бы копировать её на каждый поток.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

_KEY = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")


class CourseIn(BaseModel):
    key: str = _KEY
    """`go`, `system-design` — то же слово, что ревьюеры перечисляют в
    `course_ids` своих карточек. Совпадение не проверяется: карточки лежат
    файлами и правятся отдельно."""
    title: str = Field(min_length=1, max_length=200)


class CourseOut(BaseModel):
    id: UUID
    key: str
    title: str
    streams: int = 0
    """Сколько потоков заведено — чтобы список курсов был читаем без второго
    запроса на каждый ряд."""


class CoursePatch(BaseModel):
    """Только название. `key` — то слово, которым курс назван в карточках
    ревьюеров (`course_ids`), и переименование ключа молча отвязало бы их."""

    title: str = Field(min_length=1, max_length=200)


class StreamIn(BaseModel):
    course_id: UUID
    key: str = _KEY
    """Уникален внутри курса, не глобально: `a` у двух курсов — это нормально."""
    title: str = Field(default="", max_length=200)


class StreamOut(BaseModel):
    id: UUID
    course_id: UUID
    course_key: str
    key: str
    title: str
    assignments: int = 0
    students: int = 0


class StreamPatch(BaseModel):
    """Не переданное поле не трогается."""

    key: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    title: str | None = Field(default=None, max_length=200)


class StreamStudentRow(BaseModel):
    id: UUID
    username: str
    display_name: str


class AssignmentIn(BaseModel):
    """Рубрика, выданная потоку в срок."""

    stream_id: UUID
    rubric_key: str = Field(min_length=1, max_length=128)
    """Ключ каталога рубрик. Существование проверяет роутер — рубрики лежат
    файлами, и сослаться на несуществующую значит завести задание, которое
    нечем проверить."""
    title: str = Field(default="", max_length=200)
    """Пусто — показываем название рубрики."""
    description: str = ""
    """Что методист говорит студентам сверх рубрики. В модель не уходит."""
    opens_at: datetime | None = None
    deadline_at: datetime | None = None
    """`None` — срока нет, и просрочки не бывает. Это не «не заполнили»: у
    большинства курсов сроков в условиях нет вовсе."""


class AssignmentPatch(BaseModel):
    """Правка задания. Не переданное поле не трогается.

    `deadline_at` при этом надо уметь стереть, а `None` здесь неотличим от
    «не передавали» — поэтому дату снимают отдельным флагом `clear_deadline`.
    """

    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    opens_at: datetime | None = None
    deadline_at: datetime | None = None
    clear_deadline: bool = False


class AssignmentOut(BaseModel):
    id: UUID
    stream_id: UUID
    stream_key: str
    course_key: str
    rubric_key: str
    title: str
    """Название задания: своё, если поток дал ему своё, иначе из рубрики."""
    description: str
    opens_at: datetime | None
    deadline_at: datetime | None

    rubric_title: str = ""
    max_score: float = 0.0
    criteria: int = 0
    """Сведения из рубрики — чтобы выбирающий задание видел, во что он целится,
    не открывая каталог рубрик отдельно."""

    submissions: int = 0


class EnrollIn(BaseModel):
    usernames: list[str] = Field(min_length=1)
    """Логины уже заведённых аккаунтов. Заводит аккаунты `POST /users` —
    зачисление не создаёт людей, оно связывает их с потоком."""
