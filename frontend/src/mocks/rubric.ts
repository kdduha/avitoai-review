import type { Rubric } from '@/lib/backend'

/** Снимок `backend/rubrics/go-task1.json` для демо без бэкенда.
 *  Живой прогон берёт рубрику с сервера через `GET /rubrics/{id}` —
 *  этот файл нужен только чтобы демо открывалось на пустом окружении. */
export const DEMO_RUBRIC = {
  "assignment_id": "go-task1",
  "title": "Создание boilerplate сервиса, поднятие веб-сервера",
  "course": "Разработка микросервисов на Go",
  "stage": "task1",
  "source_note": "Скомпилировано из GO/task1.md. В условии баллов нет — шкала задана методистом, веса равные.",
  "ai_policy": "declare_required",
  "scale": {
    "total_max": 10,
    "pass_threshold": 6,
    "step": 0.5
  },
  "late_policy": {
    "grace_days": 1,
    "penalty_per_grace_day": 1,
    "after_grace": "zero"
  },
  "format_gate": [
    {
      "check": "required_paths",
      "level": "warning",
      "params": {
        "paths": [
          "cmd/",
          "internal/"
        ]
      },
      "note": "«Разделите код на логические директории (cmd/, internal/, pkg/)»"
    },
    {
      "check": "code_contains",
      "level": "blocking",
      "params": {
        "pattern": "Shutting down service-courier",
        "label": "Сообщение о завершении работы в логе",
        "expected": "строка «Shutting down service-courier»",
        "in": [
          ".go"
        ]
      },
      "note": "Условие задаёт текст сообщения буквально"
    },
    {
      "check": "code_contains",
      "level": "warning",
      "params": {
        "pattern": "\"port\"|--port|PORT",
        "label": "Переопределение порта флагом командной строки",
        "expected": "обработка флага --port",
        "in": [
          ".go"
        ]
      },
      "note": "«go run cmd/main.go --port 3000»"
    },
    {
      "check": "code_contains",
      "level": "warning",
      "params": {
        "pattern": "/ping",
        "label": "Эндпоинт GET /ping",
        "expected": "маршрут /ping",
        "in": [
          ".go"
        ]
      }
    },
    {
      "check": "code_contains",
      "level": "warning",
      "params": {
        "pattern": "healthcheck",
        "label": "Эндпоинт HEAD /healthcheck",
        "expected": "маршрут /healthcheck",
        "in": [
          ".go"
        ]
      }
    },
    {
      "check": "code_contains",
      "level": "warning",
      "params": {
        "pattern": "signal\\.Notify|SIGTERM|SIGINT",
        "label": "Обработка сигналов завершения",
        "expected": "signal.Notify с SIGINT/SIGTERM",
        "in": [
          ".go"
        ]
      }
    },
    {
      "check": "required_paths",
      "level": "warning",
      "params": {
        "paths": [
          ".env.example"
        ]
      },
      "note": "Параметры сервера читаются из .env — пример файла должен быть в репозитории"
    },
    {
      "check": "forbidden_paths",
      "level": "warning",
      "params": {
        "paths": [
          ".env"
        ],
        "label": "Реальный .env не закоммичен"
      },
      "note": "Закоммиченный .env — и нарушение гигиены, и потенциальная утечка секретов"
    },
    {
      "check": "token_budget",
      "level": "info",
      "params": {
        "max_tokens": 40000
      }
    }
  ],
  "criteria": [
    {
      "id": "c1",
      "title": "Структура проекта по golang-standards/project-layout",
      "max_score": 2,
      "min_score_for_pass": 1,
      "auto_verifiable": true,
      "checks": [
        "код разделён на cmd/ и internal/",
        "точка входа лежит в cmd/",
        "внутренние пакеты не вынесены в корень"
      ],
      "anchors": {
        "0": "плоская структура, весь код в одном файле",
        "1": "разделение есть, но границы пакетов размыты",
        "2": "структура соответствует рекомендации, границы пакетов осмысленны"
      }
    },
    {
      "id": "c2",
      "title": "Веб-сервер и конфигурация из .env с переопределением флагами",
      "max_score": 2,
      "min_score_for_pass": 1,
      "auto_verifiable": true,
      "checks": [
        "сервер поднимается через net/http",
        "PORT читается из .env",
        "флаг --port переопределяет значение окружения"
      ]
    },
    {
      "id": "c3",
      "title": "Тестовые эндпоинты /ping и /healthcheck",
      "max_score": 2,
      "min_score_for_pass": 1,
      "auto_verifiable": true,
      "checks": [
        "GET /ping возвращает 200 и {\"message\":\"pong\"}",
        "HEAD /healthcheck возвращает 204 без тела"
      ]
    },
    {
      "id": "c4",
      "title": "Корректное завершение по SIGINT/SIGTERM",
      "max_score": 2,
      "min_score_for_pass": 1,
      "auto_verifiable": true,
      "checks": [
        "используются context и signal",
        "сервер завершается через Shutdown, а не по os.Exit",
        "в stdout пишется «Shutting down service-courier»"
      ]
    },
    {
      "id": "c5",
      "title": "Читаемость и чистота кода",
      "max_score": 2,
      "description": "Условие отдельно просит обратить внимание на читаемость, поскольку сервис будет расти в следующих заданиях.",
      "checks": [
        "нет закомментированного и мёртвого кода",
        "ошибки обрабатываются, а не глушатся",
        "именование пакетов и функций осмысленно"
      ],
      "ai_sensitive": true
    }
  ]
} as unknown as Rubric

/** Снимок `backend/rubrics/sysdesign-lab1.json` — вторая шкала для демо: шесть
 *  баллов с порогом четыре, у критериев дробные максимумы. */
export const DEMO_RUBRIC_SYSDESIGN = {
  "assignment_id": "sysdesign-lab1",
  "title": "Проектирование системы: декомпозиция и архитектурное описание",
  "course": "Системный дизайн",
  "stage": "lab1",
  "source_note": "Форма взята из архитектуры (§6.0–6.1): 9 критериев, максимум 6 баллов, дробный шаг 0.5, зачёт с 4, у части критериев обязательный минимум. Критерии c1 и c5 перенесены из примера дословно, остальные семь скомпилированы под ту же шкалу и подлежат сверке с исходным условием курса.",
  "ai_policy": "declare_required",
  "scale": {
    "total_max": 6,
    "pass_threshold": 4,
    "step": 0.5
  },
  "late_policy": {
    "grace_days": 1,
    "penalty_per_grace_day": 1,
    "after_grace": "zero"
  },
  "format_gate": [
    {
      "check": "required_paths",
      "level": "blocking",
      "params": {
        "paths": [
          "README.md"
        ],
        "label": "Документ с решением на месте"
      },
      "note": "Работа сдаётся текстом в репозитории; без документа проверять нечего"
    },
    {
      "check": "code_contains",
      "level": "warning",
      "params": {
        "pattern": "(?i)C4|контекстн\\w+ диаграмм|компонентн\\w+ диаграмм",
        "label": "Диаграмма C4 упомянута в тексте",
        "expected": "раздел с диаграммой C4",
        "in": [
          ".md"
        ]
      }
    },
    {
      "check": "code_contains",
      "level": "warning",
      "params": {
        "pattern": "(?i)```mermaid|!\\[|\\.drawio|\\.png|plantuml",
        "label": "В работе есть хотя бы одна диаграмма",
        "expected": "встроенная диаграмма или изображение",
        "in": [
          ".md"
        ]
      }
    },
    {
      "check": "code_contains",
      "level": "info",
      "params": {
        "pattern": "(?i)\\b(SLI|SLO|RPS|latency|p9[59]|перцентил)",
        "label": "Нефункциональные требования названы числами",
        "expected": "SLI/SLO или числовые требования",
        "in": [
          ".md"
        ]
      }
    },
    {
      "check": "token_budget",
      "level": "warning",
      "params": {
        "max_tokens": 6000,
        "label": "Объём работы (аналог «не более 3 страниц»)"
      },
      "note": "Условие ограничивает объём; в git страниц нет, поэтому считаем токены"
    },
    {
      "check": "revision_history_visible",
      "level": "blocking",
      "params": {
        "label": "Видна история изменений документа"
      },
      "note": "Требование условия для сдачи через Google Docs. В git-канале не исполняется — уходит ревьюеру как непроверенное"
    },
    {
      "check": "font",
      "level": "warning",
      "params": {
        "family": "Arial",
        "size_pt": 11,
        "label": "Шрифт Arial 11, таблицы 10"
      },
      "note": "Проверяется только для .docx / Google Docs"
    }
  ],
  "criteria": [
    {
      "id": "c1",
      "title": "Выполнена декомпозиция по двум и более признакам",
      "max_score": 1,
      "min_score_for_pass": 1,
      "evidence_required": true,
      "checks": [
        "названы минимум два признака декомпозиции",
        "для каждого признака показан результат разбиения"
      ],
      "anchors": {
        "0": "признак один или не назван",
        "1": "два и более, с результатом разбиения"
      }
    },
    {
      "id": "c2",
      "title": "Определены границы системы и внешние акторы",
      "max_score": 0.5,
      "evidence_required": true,
      "checks": [
        "перечислены внешние системы и пользователи",
        "сказано, что остаётся за границей системы"
      ],
      "anchors": {
        "0": "границы не заданы",
        "0.5": "границы и акторы названы явно"
      }
    },
    {
      "id": "c3",
      "title": "Заданы контракты между компонентами",
      "max_score": 0.5,
      "evidence_required": true,
      "checks": [
        "для каждой связи указан способ взаимодействия (синхронный вызов, событие, очередь)",
        "названы форматы или протоколы"
      ],
      "anchors": {
        "0": "связи без контрактов",
        "0.5": "контракты названы и обоснованы"
      }
    },
    {
      "id": "c4",
      "title": "Описана модель данных и её обоснование",
      "max_score": 0.5,
      "evidence_required": true,
      "checks": [
        "названы основные сущности и их связи",
        "выбор хранилища обоснован характером нагрузки"
      ],
      "anchors": {
        "0": "данные не описаны",
        "0.5": "модель и выбор хранилища обоснованы"
      }
    },
    {
      "id": "c5",
      "title": "Построена диаграмма C4 (контекстная и компонентная)",
      "max_score": 1,
      "min_score_for_pass": 1,
      "evidence_required": true,
      "auto_verifiable": true,
      "checks": [
        "есть контекстная диаграмма",
        "есть компонентная диаграмма одного контейнера"
      ],
      "anchors": {
        "0": "диаграмм нет или уровень один",
        "1": "оба уровня присутствуют и согласованы с текстом"
      }
    },
    {
      "id": "c6",
      "title": "Нефункциональные требования выражены числами",
      "max_score": 0.5,
      "evidence_required": true,
      "checks": [
        "названы целевые значения (RPS, latency, доступность)",
        "требования привязаны к конкретным сценариям"
      ],
      "anchors": {
        "0": "только качественные формулировки",
        "0.5": "есть числа и сценарии"
      }
    },
    {
      "id": "c7",
      "title": "Продуманы отказоустойчивость и деградация",
      "max_score": 0.5,
      "evidence_required": true,
      "checks": [
        "названы точки отказа",
        "описано поведение системы при отказе каждой из них"
      ],
      "anchors": {
        "0": "отказы не рассмотрены",
        "0.5": "точки отказа и деградация описаны"
      }
    },
    {
      "id": "c8",
      "title": "Названо узкое место и способ масштабирования",
      "max_score": 0.5,
      "evidence_required": true,
      "checks": [
        "указан компонент, который упрётся первым",
        "предложен способ масштабирования именно для него"
      ],
      "anchors": {
        "0": "узкое место не названо",
        "0.5": "названо и обосновано"
      }
    },
    {
      "id": "c9",
      "title": "Решения обоснованы, компромиссы названы",
      "max_score": 1,
      "evidence_required": true,
      "ai_sensitive": true,
      "checks": [
        "для ключевых решений показана альтернатива и причина отказа от неё",
        "названы слабые места собственного решения"
      ],
      "anchors": {
        "0": "решения перечислены без обоснования",
        "0.5": "обоснование есть, но альтернативы не рассмотрены",
        "1": "альтернативы и компромиссы названы явно"
      }
    }
  ]
} as unknown as Rubric

/** Снимок `backend/rubrics/backend-task1.json` — третья программа с разбором. */
export const DEMO_RUBRIC_BACKEND = {
  "assignment_id": "backend-task1",
  "title": "Основы веб-разработки: обработчик predict и тесты",
  "course": "Основы backend-разработки",
  "stage": "task1",
  "source_note": "Скомпилировано из условия «ДЗ 1. Основы веб-разработки» курса «Основы backend-разработки». Баллы, веса и градации взяты из условия дословно: семь критериев, сумма 10, у критерия «Прохождение тестов» есть промежуточная градация 0.5.",
  "ai_policy": "not_specified",
  "scale": {
    "total_max": 10,
    "pass_threshold": 6,
    "step": 0.5
  },
  "late_policy": {
    "grace_days": 1,
    "penalty_per_grace_day": 1,
    "after_grace": "zero"
  },
  "format_gate": [
    {
      "check": "code_contains",
      "level": "blocking",
      "params": {
        "pattern": "def predict|async def predict|\"/predict\"|'/predict'",
        "label": "Обработчик predict",
        "expected": "единственный обработчик predict",
        "in": [
          ".py"
        ]
      },
      "note": "«Сервис должен иметь один обработчик predict»"
    },
    {
      "check": "code_contains",
      "level": "warning",
      "params": {
        "pattern": "from fastapi import|import fastapi",
        "label": "Сервис на FastAPI",
        "expected": "импорт fastapi",
        "in": [
          ".py"
        ]
      },
      "note": "«Сервис разрабатываем на Python с использованием фреймворка FastAPI»"
    },
    {
      "check": "code_contains",
      "level": "warning",
      "params": {
        "pattern": "is_verified_seller",
        "label": "Поле is_verified_seller во входной модели",
        "expected": "поле is_verified_seller",
        "in": [
          ".py"
        ]
      },
      "note": "Условие перечисляет семь входных полей поимённо"
    },
    {
      "check": "code_contains",
      "level": "warning",
      "params": {
        "pattern": "images_qty",
        "label": "Поле images_qty во входной модели",
        "expected": "поле images_qty",
        "in": [
          ".py"
        ]
      },
      "note": "От него зависит вся заданная бизнес-логика"
    },
    {
      "check": "required_paths",
      "level": "warning",
      "params": {
        "paths": [
          "tests/"
        ]
      },
      "note": "Условие требует четыре тест-сценария; без каталога тестов проверять нечего"
    },
    {
      "check": "code_contains",
      "level": "warning",
      "params": {
        "pattern": "parametrize",
        "label": "Параметризация в тестах",
        "expected": "pytest.mark.parametrize",
        "in": [
          ".py"
        ]
      },
      "note": "Третий балл за тесты условие даёт именно за параметризацию"
    },
    {
      "check": "code_absent",
      "level": "warning",
      "params": {
        "pattern": "__pycache__|\\.pyc$",
        "label": "Скомпилированные файлы не закоммичены"
      },
      "note": "Гигиена репозитория: .pyc в индексе — след отсутствующего .gitignore"
    },
    {
      "check": "token_budget",
      "level": "info",
      "params": {
        "max_tokens": 40000
      }
    }
  ],
  "criteria": [
    {
      "id": "c1",
      "title": "Корректный обработчик",
      "max_score": 2,
      "min_score_for_pass": 1,
      "auto_verifiable": true,
      "checks": [
        "обработчик соответствует заданному API",
        "входящие аргументы валидируются",
        "возвращается значение заданного типа"
      ],
      "anchors": {
        "0": "обработчик не соответствует заданному API",
        "1": "обработчик соответствует заданному API",
        "2": "обработчик имеет валидацию входящих аргументов и возвращает значение заданного типа"
      }
    },
    {
      "id": "c2",
      "title": "Правильная логика валидации объявления",
      "max_score": 1,
      "min_score_for_pass": null,
      "auto_verifiable": true,
      "checks": [
        "подтверждённый продавец публикует без нарушений всегда",
        "неподтверждённый — только при наличии изображений"
      ],
      "anchors": {
        "0": "логика не соответствует условию или инвертирована",
        "1": "логика в точности как в условии"
      }
    },
    {
      "id": "c3",
      "title": "Соответствие принципам чистой архитектуры",
      "max_score": 1,
      "min_score_for_pass": null,
      "auto_verifiable": true,
      "checks": [
        "выделены уровни routes и services",
        "бизнес-логика не смешана с роутами"
      ],
      "anchors": {
        "0": "код монолитный, бизнес-логика смешана с роутами",
        "1": "выделены уровни routes и services"
      }
    },
    {
      "id": "c4",
      "title": "Локальный запуск без ошибок",
      "max_score": 1,
      "min_score_for_pass": null,
      "auto_verifiable": true,
      "checks": [
        "проект разворачивается и запускается через fastapi dev"
      ],
      "anchors": {
        "0": "запуск падает или требует ручных правок",
        "1": "проект запускается локально без ошибок через fastapi dev"
      }
    },
    {
      "id": "c5",
      "title": "Тесты",
      "max_score": 3,
      "min_score_for_pass": 1,
      "auto_verifiable": false,
      "checks": [
        "есть тесты на позитивные и негативные сценарии",
        "покрыты corner-cases",
        "для corner-cases использована параметризация"
      ],
      "anchors": {
        "0": "тестов нет",
        "1": "есть тесты на позитивные и негативные сценарии, но нет обработки corner-cases",
        "2": "тесты покрывают все возможные corner-cases",
        "3": "в тестах используется параметризация, чтобы уменьшить дублирование кода"
      }
    },
    {
      "id": "c6",
      "title": "Прохождение тестов",
      "max_score": 1,
      "min_score_for_pass": null,
      "auto_verifiable": true,
      "checks": [
        "тесты запускаются",
        "все тесты проходят"
      ],
      "anchors": {
        "0": "часть тестов падает или не запускается",
        "0.5": "тесты запускаются, но не все проходят",
        "1": "все тесты проходят успешно"
      }
    },
    {
      "id": "c7",
      "title": "Предсказуемые статусы ответа",
      "max_score": 1,
      "min_score_for_pass": null,
      "auto_verifiable": true,
      "checks": [
        "ошибка валидации отдаёт 400",
        "неизвестная ошибка бизнес-логики отдаёт 500",
        "сообщения об ошибках понятны"
      ],
      "anchors": {
        "0": "статусы произвольные или ошибки не обрабатываются",
        "1": "ошибка валидации — 400, неизвестная ошибка бизнес-логики — 500, сообщения понятны"
      }
    }
  ]
} as unknown as Rubric
