# Бэкенд: состояние и как его воспроизвести

Что работает, как это запустить и на чём здесь спотыкаются.

## Что работает

Конвейер собран целиком и проверен на живой модели:

```
ссылка на PR
   → ingest          SubmissionBundle: диффы, карта репозитория, история ревизий
   → ai/content      тексты артефактов: excerpt | дозагрузка по content_ref | дифф
   → ai/gate         формальные проверки рубрики, без единого токена
   → ai/review       вердикты по критериям с цитатами; балл считает агрегатор
   → ai/detection    четыре сигнала ГенИИ, вывод рекомендательный
```

Рядом — Rubric Compiler: условие задания → черновик рубрики → подтверждение
методистом.

```
POST /auth/login → JWT      RBAC: student < reviewer < methodist < admin
        │
POST /review [assignment_id | rubric_id] → Submission (Postgres): очередь
        │                          ревьюера, карточка, правка балла с
        │                          авторством, утверждение, переназначение
        ▼
POST .../review/rerun → Redis/arq → worker: та же логика ai.review(),
                          без повторного похода за PR
        │
POST .../chat → SSE: разбор с моделью, тулы read-only +
                          propose_review_patch — применяет ревьюер сам
```

Учебный контур: курс, поток, задание, зачисление.

```
методист:  POST /courses → /streams → /assignments (рубрика + срок)
студент:   GET /me/assignments → POST /me/submissions (ссылка на PR)
                  │ разбор готовится сразу, ревьюер не назначен
руководитель: POST /streams/{id}/reviewers → /streams/{id}/distribute
                  │ солвер раскладывает и пишет reviewer_id в базу
ревьюер:   GET /me/queue → правка → approve
студент:   GET /me/submissions → балл и отзыв появляются после approve
```

Замеры на живой модели (`deepseek-v4-flash`, записанные сдачи из
`backend/scripts/fixtures/`):

| Работа | Балл | Цитаты подтверждены | Стоимость |
|---|---|---|---|
| Go, код | 9/10 | 9 из 10 | 0.43 ₽ |
| System design, текст | 4.5/6 | 9 из 9 | 0.69 ₽ |
| Компиляция рубрики (`gpt-5.6-luna-pro`) | — | 100% критериев | ~2 ₽ один раз на задание |

Изменилось с прошлой ревизии документа:

- **Гейт не останавливает разбор.** Статуса `blocked` нет. Проверки остались
  все, их результат уходит в модель фактом и ревьюеру строкой; уровень
  `blocking` сохранён — по нему отличают дословное требование условия от
  пожелания.
- **У черновика есть отзыв словами** — `ReviewDraft.summary`, отдельный шаг
  после оценки критериев. Файлов работы ему не показывают: он пересказывает уже
  подтверждённые цитатами вердикты. Не собралось — `None`, заглушки нет. Прогон
  стоит на один вызов дороже.
- **Ролей четыре.** `methodist` владеет рубриками, описаниями заданий и сроками.
  Правка дедлайна задним числом молча пересчитывает штраф за просрочку на всех
  сданных работах потока.

532 теста, `uv run pytest` из `backend/` — на SQLite (`aiosqlite`), Postgres не
нужен: `conftest.py` подставляет файловый `DB_DSN` на каждый прогон.

## Запуск

```bash
cd backend
uv sync --group dev
uv run pytest                                           # тесты, ключи не нужны
uv run uvicorn avito_reviewer.app.main:app --reload     # http://localhost:8000/docs

docker compose up --build          # из корня: postgres, redis, backend, worker
```

Без docker-compose локально нужен свой Postgres (`DB_DSN`) и, для
`review/rerun`, Redis (`QUEUE_REDIS_DSN`) — воркер отдельным процессом:
`uv run arq avito_reviewer.queue.WorkerSettings`.

Без ключей поднимается провайдер `fake`: конвейер проходится целиком, черновик
приходит с пометкой «оценить вручную». Готовый черновик без ключа показывает демо:

```bash
uv run python scripts/demo.py review     # записанная сдача
uv run python scripts/demo.py detect
uv run python scripts/demo.py review --repo путь/к/каталогу
uv run python scripts/demo.py review --link https://github.com/owner/repo/pull/1
```

## Конфигурация

`pydantic-settings`, см. `backend/src/avito_reviewer/config.py`.

```bash
INGEST_GITHUB__TOKEN=ghp_...              # без него 60 запросов в час на всё
AI_LLM__PROVIDER=external                 # fake | local | external
AI_LLM__BASE_URL=https://api.aitunnel.ru/v1
AI_LLM__MODEL=deepseek-v4-flash
AI_LLM__API_KEY=...
AI_LLM__TASK_MODELS={"compile": "gpt-5.6-luna-pro"}   # матрица роутинга
AI_LLM__FORCE_LOCAL=false                 # аварийный тумблер: наружу не ходим
AI_RUBRICS_DIR=rubrics

DB_DSN=postgresql+asyncpg://avito:avito@localhost:5432/avito_reviewer
QUEUE_REDIS_DSN=redis://localhost:6379/0  # нужен только для review/rerun
AUTH_JWT_SECRET=...                       # обязательно сменить в проде
AUTH_SEED_PASSWORD=avito2026
```

**Почему матрица моделей, а не одна модель.** Ревью идёт потоком — там решает
стоимость. Rubric Compiler считается один раз на задание, его результат
подтверждает человек, а ошибка тиражируется на весь поток — там решает
устойчивость. Замер на одном условии: `deepseek-v4-flash` дважды дал разный
результат и один раз вернул ноль критериев, `gpt-5.6-luna-pro` — шесть критериев
со стопроцентным подтверждением цитатами.

## Ручки

Всё, кроме `/health`, `/init` и `/auth/login`, требует `Authorization: Bearer
<token>`. RBAC — лестница `student < reviewer < methodist < admin`, в таблице
указан минимум: методист умеет всё, что умеет ревьюер.

| Ручка | Роль | Что делает |
|---|---|---|
| `GET /health`, `GET /init` | — | живость и состав бутстрапа |
| `POST /auth/login`, `GET /me` | — / любая | сеяный логин → JWT; кто владеет токеном |
| `GET /users`, `POST /users` | admin | список аккаунтов; завести новый |
| `GET/PATCH/DELETE /users/{id}` | admin | карточка, правка роли/пароля, удаление (`409` — за пользователем числятся сдачи) |
| `POST /ingest` | reviewer | ссылка → `SubmissionBundle` |
| `POST /review` | reviewer | сдача + рубрика → черновик, **сохраняет `Submission`**; `with_detection` — заодно детектор на тех же bundle/texts. `assignment_id` вместо `rubric_id`: рубрику и срок берёт задание, указать оба сразу нельзя |
| `POST /detect` | reviewer | сдача → отчёт о признаках ГенИИ; ничего не сохраняет |
| `GET /rubrics`, `GET /rubrics/{id}` | reviewer | каталог рубрик |
| `POST /rubrics/compile`, `POST /rubrics` | methodist | условие → черновик → подтверждение |
| `DELETE /rubrics/{id}` | methodist | снять рубрику из каталога |
| `GET /cost`, `GET /audit/llm-calls` | admin | журнал шлюза: сводка / построчно |
| `POST /work-profile` | reviewer | сдача → `{profile, item}`: о чём работа и во сколько обойдётся её проверка; единственный вызов модели во всём распределении |
| `POST /distribute` | reviewer | `{items, reviewers? \| reviewer_ids?, committed_minutes?, now?}` → план назначений с объяснением по слагаемым и списком отказавших; к модели не ходит |
| `GET /me/queue` | reviewer | своя очередь; `?all=true` — весь поток (admin) |
| `GET /submissions/{id}`, `.../artifacts/{path}` | reviewer* | карточка сдачи, текст файла |
| `GET/PATCH /submissions/{id}/review` | reviewer* | черновик; правка балла/вердикта с пересчётом и авторством |
| `POST .../review/approve` | reviewer* | утвердить (`409` — уже утверждена) |
| `POST .../review/rerun` | reviewer* | в очередь на Redis/arq (`503` — очередь недоступна) |
| `GET .../ai-detection`, `POST .../{span_id}/verdict` | reviewer* | отчёт детектора; подтвердить/отклонить спан (advisory — работает и после утверждения) |
| `GET/POST /submissions/{id}/chat` | reviewer* | история разговора с моделью; ход — SSE |
| `POST /submissions/{id}/reassign` | admin | передать сдачу другому ревьюеру |
| `DELETE /submissions/{id}` | admin | удалить сдачу (каскад — ревизии, чат) |
| `GET /courses`, `GET /streams`, `GET /assignments` | reviewer | учебный каталог |
| `POST /courses`, `POST /streams` | methodist | завести курс, поток |
| `PATCH /courses/{id}` | methodist | переименовать; `key` неизменяем — им курс назван в карточках ревьюеров |
| `DELETE /courses/{id}` | admin | убрать курс (`409` — есть потоки) |
| `PATCH /streams/{id}` | methodist | ключ и название (`409` — ключ у курса занят) |
| `DELETE /streams/{id}` | admin | убрать поток (`409` — есть задания или студенты; назначения ревьюеров уходят с ним) |
| `POST /assignments`, `PATCH`, `DELETE` | methodist | выдать рубрику потоку со сроком; правка срока; снять (`409` — по заданию есть сдачи) |
| `POST /streams/{id}/students` | methodist | зачислить студентов (только роль `student`) |
| `GET /streams/{id}/students` | reviewer | состав потока |
| `DELETE /streams/{id}/students/{username}` | methodist | отчислить; сданные работы остаются |
| `GET /me/assignments` | любая | задания моих потоков |
| `POST /me/submissions` | любая | сдать работу ссылкой; ревьюер не назначается |
| `GET /me/submissions`, `GET /me/submissions/{id}` | любая | свои сдачи; балл и отзыв — только у утверждённых |
| `GET /stats/streams/{id}`, `GET /stats/assignments/{id}` | reviewer | числа по сданным работам |
| `GET/POST /streams/{id}/reviewers`, `DELETE .../{username}` | reviewer / admin | кто проверяет поток; назначить, снять |
| `POST /streams/{id}/distribute` | admin | разложить работы без ревьюера и **записать `reviewer_id`** |

\* reviewer — только свои сдачи; admin — все. Чужая сдача даёт 404, а не 403:
существование чужой работы — тоже сведение о ней. Черновик студенту не
показывают до утверждения.

`/review` и `/detect` сами тянут сдачу по ссылке. `review/rerun` переиспользует
`Submission.bundle`, сохранённый первым `/review`, и к источнику не ходит.

## Решения, которые не надо пересматривать наугад

**Балл считает код, а не модель.** Модель отвечает по одному критерию и обязана
приложить цитату; цитата сверяется с текстом файла программно; сумму считает
`review/aggregate.py`.

**Единственный выход к моделям — `PrivacyGateway`.** Скраб ПДн, проверка
остаточного риска, маршрут, аудит. Правило проверяется тестом
`test_llm_calls_leave_only_through_the_gateway`: SDK моделей вне `ai/llm`
запрещены, сетевые вызовы разрешены ещё и в `ingest`.

**Неполнота видна на всём пути.** Полного текста файла может не быть: ingest
инлайнит `excerpt` только в пределах бюджета. Такие файлы помечены `partial`, и
это тянется в промпт, в цитаты, в черновик и в ограничения детектора. Вердикт
«в работе нет обработки ошибок», сделанный по одному ханку, некорректен.

**Рубрика проверяется кодом перед принятием.** Недостижимый порог зачёта,
минимум выше максимума критерия, повторяющиеся идентификаторы ломают подсчёт не
на одной работе, а на каждой до конца курса.

**Сдача помнит свою рубрику, а не ссылку на каталог.** `Submission.rubric_snapshot`
— полный `Rubric` на момент разбора. `PATCH .../review` и `review/rerun` считают
против него, а не против `rubrics/<id>.json`: правка файла задним числом не
должна молча пересчитывать уже выставленные баллы.

## Грабли, на которые уже наступали

**Рассуждающие модели тратят на `reasoning` тот же бюджет, что и на ответ.** При
`max_tokens=3000` JSON обрывался на середине. Обрыв виден по `finish_reason`,
лечится повтором с удвоенным бюджетом (потолок — четыре исходных), а не
ремонтным запросом. Пустой ответ — того же происхождения.

**Тройные кавычки внутри значения JSON.** Работа по системному дизайну состоит
из блоков ```` ```mermaid ````; поиск ограды по всему тексту вырезал содержимое
диаграммы вместо ответа. Ограда снимается, только если обрамляет ответ целиком.

**Ответ шлюза неизвестной формы.** `"usage": null` встречается; разбор «в лоб»
давал AttributeError, и один странный ответ превращался в пятисотку на весь
запрос. Разбор не верит форме ответа и поднимает `LLMError`, который переживается
потерей одного батча.

**Лимит GitHub без токена — 60 запросов в час**, а один `/review` тратит
несколько. Штатная политика githubkit пережидает лимит `sleep`-ом до часа;
отключена, лимит всплывает сразу как 502.

**Тестовые двойники должны совпадать с настоящими провайдерами.** `fake_gateway`
ставил провайдера и внешним, и локальным, а `gateway_from_config` — нет;
`FakeProvider` отвечал своей моделью вместо запрошенной. Оба случая закрыты
тестами.

**`~/.zshrc` не читается неинтерактивной оболочкой.** Если ключ живёт там,
скриптам нужен явный `source ~/.zshrc`.

**Мутация JSON-колонки на месте не сохраняется без `flag_modified`.** SQLAlchemy
сравнивает новое значение со старым по той же ссылке и не кладёт колонку в
`UPDATE`. На SQLite тест зелёный, на Postgres правка исчезает после перезагрузки
карточки. Лечится `flag_modified(obj, "draft")` сразу после присваивания.
Тест обязан перечитывать через отдельный `GET`, а не проверять ответ той же
ручки — только так он ловит эту ошибку.

**Postgres не примет tz-aware `datetime` в `TIMESTAMP WITHOUT TIME ZONE`.**
`SubmissionBundle.submitted_at` приходит от GitHub с `tzinfo`; asyncpg падает на
первой же настоящей работе, а SQLite типы не проверяет и в тестах молчит. Все
datetime-колонки `db/models.py` объявлены `DateTime(timezone=True)` поэтому.

**`arq.WorkerSettings.redis_settings` должен быть значением, не методом.** `arq`
читает `__dict__` класса настроек напрямую; `@staticmethod` падает
`AttributeError` при старте воркера. Присваивайте
`redis_settings = RedisSettings.from_dsn(...)` в теле класса.

**`redis.exceptions.ConnectionError` не наследуется от builtin `ConnectionError`.**
`except (ConnectionError, OSError)` вокруг `arq.create_pool` не ловит отказ
Redis — нужен `redis.exceptions.RedisError`. Вдобавок `arq` без
`retry=0`/`conn_retries=0` на недоступном Redis виснет секунд на пять на
дефолтных повторах; ручке, которая должна быстро вернуть `503`, нужен свой
`RedisSettings(conn_retries=0)`.

**`User.role` — колонка `String`, а не SQLAlchemy `Enum`.** Значение из базы
(`session.get(User, id)`) приходит как `str`: `user.role is Role.ADMIN` всегда
`False`. Идиом — `Role(user.role) is Role.ADMIN`. Свежесозданный в этом же
запросе объект ловушки не несёт: `body.role` уже `Role` из Pydantic-схемы. На
этом `_require_another_admin` тихо не срабатывала и позволила удалить последний
`admin`-аккаунт.

**Можно удалить или разжаловать последнего `admin`.** `seed_users` заполняет
только пустую таблицу `users` — рестарт контейнера удалённый аккаунт не вернёт.
`DELETE /users/{id}` и `PATCH .../role` проверяют это через
`_require_another_admin` (`app/routers/users.py`) и возвращают `409`.
Восстановление — только прямой INSERT в БД (`happy-path.md`, сценарий 7).

**Advisory-сигнал не должен уметь топить основной ответ.** Первая версия
`with_detection` звала `ai.detect()` без `try/except`, и падение детектора
возвращало 500 вместе с уже посчитанным черновиком. Детектор обёрнут в
`try/except Exception`, при отказе `detection` — `None`. Проверено тестом,
подменяющим `AIService.detect` на бросающую функцию.

## Чего нет

- Format Gate знает только git-канал: шрифт и число страниц живут в Google Docs.
  Историю ревизий он закрывает — для pull request'а это коммиты бандла.
  Нереализованная проверка уходит ревьюеру как непроверенная.
- Перплексия не подключена как сигнал: `LogprobScorer` объявлен и не
  конструируется нигде в `src/`, поэтому `AI_LLM__PROVIDER=local` её не включит.
  Ансамбль сегодня — три сигнала из четырёх.
- Пороги детектора не калиброваны: нужны вердикты ревьюеров, схема готова.
- NER на локальной модели поверх регулярок скраба: `TaskKind.NER` заперт в
  локальный маршрут, самой модели нет. Имя без отчества и без маркера авторства
  остаётся риском, и `residual_risk` о нём сообщает.
- Рубрики лежат файлами, не в БД: добавить курс значит положить JSON рядом.
- Профили ревьюера и студента (§9 архитектуры) не построены: пересчёт по истории
  ревью не сделан, косинус по темам ждёт эмбеддингов. Экспорт в Sheets и
  комментарий в PR тоже не сделаны.
- Парсеры docx/xlsx/pdf. Их отсутствие ограничивает не гейт, а то, какие рубрики
  он умеет исполнять: проверки вида «21 тест-кейс», «не более 3 страниц»,
  «шрифт Arial 11» читаются только из таблицы или документа. Таких рубрик в
  каталоге пока нет.
- GitHub webhook: сейчас только явный `POST /review` по ссылке.
- Учёта расхода по людям нет. `AuditRecord` пишет провайдера, модель, задачу,
  токены и цену, но без `user_id` и `submission_id`, и живёт в памяти процесса:
  рестарт обнуляет `/cost` и `/audit/llm-calls`. Воркер строит свой `AIService`
  со своим журналом, поэтому токены `rerun` не видны, а чат не обёрнут в
  `audit.collect()`. Дешёвый первый шаг — помечать применённый из чата патч как
  `AuthorType.AI_ASSISTED`: значение объявлено и не используется ни разу.
- Оценка трудоёмкости для распределения — заглушка: `POST /streams/{id}/distribute`
  берёт число критериев рубрики, потому что настоящая оценка (`POST /work-profile`)
  стоит вызова модели на каждую работу.
- Дедупликации сдач нет: `POST /review` создаёт новую строку на каждый вызов.
- `DataClass` пишется в аудит, но маршрут не меняет.
- Mermaid и блоки кода не исключаются из статистических сигналов: гранулярность
  исключения — по путям файлов, не по фрагментам внутри файла.

## Демо и ручные скрипты

`scripts/` — ручные примеры и утилиты, не тесты и не часть пакета. По умолчанию
`scripts/demo.py` берёт `scripts/fixtures/go-task1-pr42.json`; флаги (до
подкоманды) переключают источник:

```bash
uv run python scripts/demo.py --repo "homework_examples/GO/Хорошее решение 1-3" review
uv run python scripts/demo.py --link https://github.com/owner/repo/pull/1 review
```

`scripts/local_bundle.py` собирает из каталога тот же `SubmissionBundle`, что
отдал бы провайдер — не оформлен провайдером намеренно: заглушек под
нереализованные источники не держим. `scripts/ingest_pr_example.py` прогоняет
`ingest` на реальном PR и печатает `SubmissionBundle` целиком.

## Структура

```
src/avito_reviewer/
  config.py              AppConfig: IngestConfig / AIConfig / DatabaseConfig / AuthConfig / QueueConfig
  queue.py               review/rerun: arq-задача + WorkerSettings; тоже прогоняет миграции
  db/                     users, submissions, review_revisions, chat_messages — SQLAlchemy 2 (async)
    migrate.py            run_migrations(): alembic upgrade head, вызывается в lifespan
  app/                    HTTP-слой
    main.py               create_app(): lifespan (миграции+ingest+seed), роутеры
    auth.py               JWT + RBAC: seed_users, get_current_user, require_role
    routers/              APIRouter по доменам; schemas/ — Pydantic-модели, по файлу на роутер
  ingest/                 ссылка → SubmissionBundle
    service.py            IngestService: SubmissionSource → провайдер; резолвер content_ref
    models.py             SubmissionBundle и связанные модели — контракт для слоёв ниже
    providers/github.py   единственный провайдер, клиент — githubkit
  ai/
    content.py            тексты артефактов: excerpt | дозагрузка | дифф, флаг partial; strip_notebook
    rubric.py             схема рубрики, разбор JSON, реестр каталога
    compiler.py           условие задания → черновик рубрики с цитатами
    gate.py               формальные проверки рубрики без единого токена
    chat.py               ReAct-цикл чата ревьюера с моделью
    llm/                  PrivacyGateway — единственный выход к моделям
    review/               промпт из рубрики, валидатор цитат, агрегатор баллов
    detection/            ансамбль сигналов ГенИИ + signals/
  distribution/           раскладка работ по ревьюерам; hungarian.py — солвер без зависимостей
rubrics/                  рубрики как данные: добавить курс = добавить JSON
reviewers/                ревьюеры как данные; занятость туда не пишут
migrations/               Alembic (async шаблон); env.py берёт DSN из DatabaseConfig
scripts/fixtures/         записанные сдачи и условия для прогонов без сети
```

### Границы

`ai` работает только с `SubmissionBundle` и `Rubric` — про источник сдачи не
знает; схемы `content_ref` разбирает только `ingest`, а `ai` ходит за телами
файлов через протокол `ContentResolver`, которому `IngestService` удовлетворяет
структурно. Наружу к моделям ходит один `PrivacyGateway`.

### Чего в `SubmissionBundle` нет

**Полного текста файла может не быть.** Крупные файлы едут diff-only.
`ai/content.py` сводит `excerpt`, дозагрузку по `content_ref` и дифф к одному
объекту и помечает неполные флагом `partial`. Дифф файла, добавленного этой
сдачей, — весь файл, и фрагментом не считается. Дальше: в промпте такой файл
помечен и системная инструкция запрещает утверждать по нему, что чего-то нет;
валидатор цитат говорит «не найдено в доступной части», не «такого текста нет»;
стилометрия и перплексия такие файлы пропускают; список уходит в
`partial_artifacts` черновика.

**История не хранит списка файлов.** `Revision` несёт время и объём коммита, но
не пути — GitHub отдаёт их отдельным запросом на каждый коммит. Форензика
поэтому не обещает «эта строка из того коммита», а подсвечивает крупные файлы,
добавленные сдачей, и пишет в обосновании, что связь косвенная.

## Как расширять

- **Новый роутер** — `app/routers/<name>.py` + `app/schemas/<name>.py`,
  `include_router` в `main.py`.
- **Новый провайдер ingest** — `SubmissionProvider` в `ingest/providers/<name>.py`,
  запись в словарь `IngestService`, конфиг в `config.py`, значение в
  `SubmissionSource`.
- **Новый домен** — пакет рядом с `ingest`/`ai`; на входе только
  `SubmissionBundle`, наружу — сервисный класс, который зовёт роутер.
