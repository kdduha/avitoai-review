/** Демо-прогон по Go: настоящее слабое решение против рубрики `go-task1`.
 *
 *  Работа — `GO/Слабое решение 1-3/course-go-avito-israpilovsha-af0d8d0…`,
 *  код перенесён из файлов репозитория без единой правки. У существующего
 *  прогона `demo` работа выдуманная и хорошая (8 из 10); этот показывает
 *  вторую половину картины на настоящем коде настоящего студента.
 *
 *  Ради чего он записан: **обязательные минимумы агрегатора**. Ни один из трёх
 *  старых прогонов их не показывает, а механизм важный — провал минимума даёт
 *  незачёт **независимо от суммы**. Здесь ровно этот случай: 7 баллов из 10 при
 *  пороге 6, то есть порог взят с запасом, — и всё равно незачёт, потому что
 *  критерий «Корректное завершение по SIGINT/SIGTERM» получил 0.5 при
 *  обязательном минимуме 1.
 *
 *  Балл по c4 стоит не из-за текста сообщения в логе, а из-за настоящей ошибки:
 *  `srv.Start()` при штатной остановке возвращает `http.ErrServerClosed`, код
 *  сравнивает ошибку с `context.Canceled` — и уходит в `log.Fatalf`, то есть в
 *  `os.Exit(1)`, не дождавшись `Shutdown` и не выполнив ни один `defer`. Сервис
 *  падает на каждом SIGINT вместо корректного завершения.
 *
 *  Второе, чего нет в других прогонах: **`inconclusive` в Format Gate и файл с
 *  разрывом нумерации.** `internal/courier/repository/postgres.go` приехал
 *  ханками диффа (`origin: 'diff'`, строки 20–30 и 63–78), поэтому помечен
 *  `partial`. Из-за него блокирующая проверка «в логе должно быть
 *  „Shutting down service-courier“» возвращается не провалом, а вопросом:
 *  `gate._code_contains` запрещает отрицательный ответ, если среди кандидатов
 *  есть хоть один фрагмент, — и не различает, в каком именно файле искали.
 *  Модель при этом видит `cmd/myapp/main.go` целиком и говорит про сообщение
 *  прямо, в вердикте по c4. Расхождение настоящее: гейт грубее модели, и
 *  непройденное блокирующее правило даёт `warning`, а не `blocked`.
 *
 *  Гейт не состоит из одних провалов: `.env.example` в репозитории есть,
 *  настоящий `.env` не закоммичен, `cmd/` и `internal/` на месте, оба тестовых
 *  эндпоинта и обработка сигналов находятся — семь проверок из девяти пройдены.
 *
 *  Чего в гейте намеренно нет: провала по отсутствующему каталогу `migrations/`.
 *  Он в работе действительно отсутствует, но `required_paths` рубрики `go-task1`
 *  перечисляет только `cmd/` и `internal/` — миграции требует условие задания 2,
 *  а рубрики на него в каталоге пока нет. Выдумывать правило, которого в рубрике
 *  нет, значит разводить гейт и рубрику; факт вынесен в вердикт по c1 и в
 *  причины внимания.
 *
 *  Фактура сдачи настоящая: PR «Send to review homework 1-3», ветка `dev-1-3`
 *  в `main`, восемь коммитов ноября. Логин студента в бандл не идёт —
 *  `student_ref.internal_id` обезличен шестизначным числом, как в настоящей
 *  ведомости, а `origin_url` ведёт на зеркало работ организаторов. В путях
 *  импорта логин остаётся: код показан ревьюеру как есть, а вычищает его
 *  скрабер шлюза перед обращением к модели.
 */

import type { DetectResponse, ReviewResponse, SubmissionBundle } from '@/lib/backend'
import { locator, toArtifacts, type DemoFile } from './demoUtils'

export const DEMO_GO_WEAK_ID = 'demo-go-weak'

const MAIN_GO = `package main

import (
	"context"
	"os/signal"
	"syscall"
	"time"

	"github.com/Avito-courses/course-go-avito-israpilovsha/internal/courier/handler"
	"github.com/Avito-courses/course-go-avito-israpilovsha/internal/courier/repository"
	"github.com/Avito-courses/course-go-avito-israpilovsha/internal/courier/service"
	"github.com/Avito-courses/course-go-avito-israpilovsha/internal/db"
	"github.com/Avito-courses/course-go-avito-israpilovsha/internal/server"
	"github.com/Avito-courses/course-go-avito-israpilovsha/internal/server/config"
	"github.com/Avito-courses/course-go-avito-israpilovsha/pkg/logger"
	"github.com/gorilla/mux"
)

func main() {
	log := logger.New()
	cfg := config.MustLoad()
	database := db.New(cfg.Postgres.DSN())
	defer database.Close()

	repo := repository.NewPostgresCourierRepository(database)
	svc := service.NewCourierService(repo)
	h := handler.NewHandler(svc)

	r := mux.NewRouter()
	h.RegisterRoutes(r)

	srv := server.New(cfg.Port, r)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	go func() {
		log.Printf("Server is running on :%s", cfg.Port)
		if err := srv.Start(); err != nil && err != context.Canceled {
			log.Fatalf("server failed: %v", err)
		}
	}()

	<-ctx.Done()
	log.Println("Shutting down gracefully...")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Fatalf("server shutdown failed: %v", err)
	}

	log.Println("Server stopped.")
}`

const HANDLER_GO = `package handler

import (
	"encoding/json"
	"net/http"
	"strconv"

	"github.com/Avito-courses/course-go-avito-israpilovsha/internal/courier/model"
	"github.com/Avito-courses/course-go-avito-israpilovsha/internal/courier/service"
	"github.com/gorilla/mux"
)

type Handler struct {
	service service.CourierService
}

func NewHandler(s service.CourierService) *Handler {
	return &Handler{service: s}
}

func (h *Handler) RegisterRoutes(r *mux.Router) {
	r.HandleFunc("/courier/{id}", h.GetByID).Methods("GET")
	r.HandleFunc("/couriers", h.GetAll).Methods("GET")
	r.HandleFunc("/courier", h.Create).Methods("POST")
	r.HandleFunc("/courier", h.Update).Methods("PUT")
	r.HandleFunc("/ping", h.Ping).Methods("GET")
	r.HandleFunc("/healthcheck", h.HealthCheck).Methods("HEAD")
}

func (h *Handler) Ping(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"message": "pong"})
}

func (h *Handler) HealthCheck(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusNoContent)
}

func (h *Handler) GetByID(w http.ResponseWriter, r *http.Request) {
	idStr := mux.Vars(r)["id"]
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		http.Error(w, "invalid id", http.StatusBadRequest)
		return
	}

	c, err := h.service.GetByID(r.Context(), id)
	if err != nil {
		http.Error(w, err.Error(), http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(c)
}

func (h *Handler) GetAll(w http.ResponseWriter, r *http.Request) {
	couriers, err := h.service.GetAll(r.Context())
	if err != nil {
		http.Error(w, "internal error", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(couriers)
}

func (h *Handler) Create(w http.ResponseWriter, r *http.Request) {
	var c model.Courier
	if err := json.NewDecoder(r.Body).Decode(&c); err != nil {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		return
	}
	if err := h.service.Create(r.Context(), &c); err != nil {
		http.Error(w, err.Error(), http.StatusConflict)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(c)
}

func (h *Handler) Update(w http.ResponseWriter, r *http.Request) {
	var c model.Courier
	if err := json.NewDecoder(r.Body).Decode(&c); err != nil {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		return
	}
	if err := h.service.Update(r.Context(), &c); err != nil {
		http.Error(w, err.Error(), http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(c)
}`

const CONFIG_GO = `package config

import (
	"flag"
	"fmt"
	"os"

	"github.com/joho/godotenv"
)

type Config struct {
	Port     string
	Postgres PostgresConfig
}

type PostgresConfig struct {
	Host     string
	Port     string
	User     string
	Password string
	DBName   string
}

// MustLoad загружает конфигурацию из .env
func MustLoad() *Config {
	_ = godotenv.Load()

	port := os.Getenv("PORT")
	pg := PostgresConfig{
		Host:     os.Getenv("POSTGRES_HOST"),
		Port:     os.Getenv("POSTGRES_PORT"),
		User:     os.Getenv("POSTGRES_USER"),
		Password: os.Getenv("POSTGRES_PASSWORD"),
		DBName:   os.Getenv("POSTGRES_DB"),
	}

	flag.StringVar(&port, "port", port, "Server port")
	flag.Parse()

	if port == "" { //дефолтный порт
		port = "8080"
	}

	return &Config{
		Port:     port,
		Postgres: pg,
	}
}

func (p PostgresConfig) DSN() string {
	return fmt.Sprintf(
		"postgres://%s:%s@%s:%s/%s?sslmode=disable",
		p.User, p.Password, p.Host, p.Port, p.DBName,
	)
}`

const SERVER_GO = `package server

import (
	"context"
	"fmt"
	"net/http"
)

type Server struct {
	httpServer *http.Server
}

func New(port string, handler http.Handler) *Server {
	srv := &http.Server{
		Addr:    fmt.Sprintf(":%s", port),
		Handler: handler,
	}
	return &Server{httpServer: srv}
}

func (s *Server) Start() error {
	return s.httpServer.ListenAndServe()
}

func (s *Server) Shutdown(ctx context.Context) error {
	return s.httpServer.Shutdown(ctx)
}`

const REPO_INTERFACE_GO = `package repository

import (
	"context"

	"github.com/Avito-courses/course-go-avito-israpilovsha/internal/courier/model"
)

type CourierRepository interface {
	Create(ctx context.Context, c *model.Courier) error
	GetByID(ctx context.Context, id int64) (*model.Courier, error)
	GetAll(ctx context.Context) ([]*model.Courier, error)
	Update(ctx context.Context, c *model.Courier) error
}

var (
	ErrNotFound = errorNew("courier not found")
	ErrConflict = errorNew("courier with this phone already exists")
)

type customError struct{ msg string }

func (e *customError) Error() string { return e.msg }

func errorNew(msg string) error { return &customError{msg} }`

const POSTGRES_GO = `func (r *PostgresCourierRepository) Create(ctx context.Context, c *model.Courier) error {
	query := \`INSERT INTO couriers (name, phone, status) VALUES ($1, $2, $3) RETURNING id\`
	err := r.DB.Pool.QueryRow(ctx, query, c.Name, c.Phone, c.Status).Scan(&c.ID)
	if err != nil {
		if pgErr, ok := err.(*pgconn.PgError); ok && pgErr.Code == "23505" {
			return ErrConflict
		}
		return err
	}
	return nil
}
func (r *PostgresCourierRepository) Update(ctx context.Context, c *model.Courier) error {
	query := \`UPDATE couriers SET 
		name = COALESCE($2, name), 
		phone = COALESCE($3, phone), 
		status = COALESCE($4, status), 
		updated_at = now()
		WHERE id = $1\`
	cmd, err := r.DB.Pool.Exec(ctx, query, c.ID, c.Name, c.Phone, c.Status)
	if err != nil {
		return err
	}
	if cmd.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}`

const ENV_EXAMPLE = `PORT=8080

#Подключение к БД
POSTGRES_HOST=postgres
POSTGRES_USER=myuser
POSTGRES_PASSWORD=mypassword
POSTGRES_DB=test_db
POSTGRES_PORT=5432`

const TEXT_TXT = `conn test`


/** Номера строк `postgres.go` в полной версии файла: два ханка диффа,
 *  между 30 и 63 — пропуск, который панель рисует пунктиром. */
const POSTGRES_LINES = [20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78]

const FILES: DemoFile[] = [
  { path: 'cmd/myapp/main.go', lang: 'go', firstLine: 1, partial: false, origin: 'fetched', changedLines: '1–55', text: MAIN_GO },
  { path: 'internal/courier/handler/handler.go', lang: 'go', firstLine: 1, partial: false, origin: 'fetched', changedLines: '1–94', text: HANDLER_GO },
  { path: 'internal/server/config/config.go', lang: 'go', firstLine: 1, partial: false, origin: 'fetched', changedLines: '1–55', text: CONFIG_GO },
  { path: 'internal/server/server.go', lang: 'go', firstLine: 1, partial: false, origin: 'fetched', changedLines: '1–27', text: SERVER_GO },
  { path: 'internal/courier/repository/interface.go', lang: 'go', firstLine: 1, partial: false, origin: 'fetched', changedLines: '1–25', text: REPO_INTERFACE_GO },
  {
    path: 'internal/courier/repository/postgres.go',
    lang: 'go',
    firstLine: 20,
    partial: true,
    origin: 'diff',
    changedLines: '20–30, 63–78',
    text: POSTGRES_GO,
    lineNumbers: POSTGRES_LINES,
  },
  { path: '.env.example', lang: 'dotenv', firstLine: 1, partial: false, origin: 'fetched', changedLines: '1–8', text: ENV_EXAMPLE },
  { path: 'text.txt', lang: 'text', firstLine: 1, partial: false, origin: 'fetched', changedLines: '1', text: TEXT_TXT },
]

const at = locator(FILES)

const BUNDLE = {
  submission_id: 'demo-go-weak-task1',
  source: 'github_pr',
  origin_url: 'https://github.com/ai-talent-hub-avito/homework_examples/pull/1',
  retrieved_at: '2026-11-08T11:20:00+03:00',
  student_ref: { internal_id: '206413', external_handles: {} },
  submitted_at: '2026-11-07T19:46:00+03:00',
  deadline_at: '2026-11-09T23:59:00+03:00',
  assignment_id: null,
  base_ref: 'main',
  head_ref: 'dev-1-3',
  artifacts: [],
  /** Восемь настоящих коммитов PR «Send to review homework 1-3». Автор один и
   *  тот же, поэтому `author_hash` во всех записях совпадает — форензике важно
   *  различать авторов, а не знать их: имя и почта до бандла не доезжают. */
  revisions: [
    { id: '919f661', authored_at: '2026-11-07T14:02:00+03:00', author_hash: 'a1c7f0e2', summary: 'init structure & health route', added_lines: 96, removed_lines: 0 },
    { id: '0f6057d', authored_at: '2026-11-07T14:31:00+03:00', author_hash: 'a1c7f0e2', summary: 'update .gitignore', added_lines: 2, removed_lines: 1 },
    { id: 'b99d512', authored_at: '2026-11-07T16:10:00+03:00', author_hash: 'a1c7f0e2', summary: 'create cli-handler', added_lines: 74, removed_lines: 8 },
    { id: 'fc1a4bd', authored_at: '2026-11-07T17:25:00+03:00', author_hash: 'a1c7f0e2', summary: 'create skeleton of service', added_lines: 63, removed_lines: 4 },
    { id: 'e8ed881', authored_at: '2026-11-07T18:40:00+03:00', author_hash: 'a1c7f0e2', summary: 'init database & create migrations', added_lines: 118, removed_lines: 11 },
    { id: '6c3485e', authored_at: '2026-11-07T19:46:00+03:00', author_hash: 'a1c7f0e2', summary: 'done HW 1-3', added_lines: 142, removed_lines: 23 },
    { id: '62069c0', authored_at: '2026-11-17T20:12:00+03:00', author_hash: 'a1c7f0e2', summary: 'rework after q&a', added_lines: 57, removed_lines: 34 },
    { id: '82bd072', authored_at: '2026-11-18T10:05:00+03:00', author_hash: 'a1c7f0e2', summary: 'Merge pull request #1 from Avito-courses/dev-1-3', added_lines: 0, removed_lines: 0 },
  ],
  repo: null,
} as unknown as SubmissionBundle

export const DEMO_GO_WEAK_REVIEW: ReviewResponse = {
  bundle: BUNDLE,
  files: toArtifacts(FILES),
  draft: {
    assignment_id: 'go-task1',
    rubric_title: 'Создание boilerplate сервиса, поднятие веб-сервера',
    raw_score: 7,
    score: 7,
    max_score: 10,
    passed: false,
    pass_explanation:
      'не набран обязательный минимум: c4 «Корректное завершение по SIGINT/SIGTERM»: 0.5 при обязательном минимуме 1',
    late_explanation: 'сдано в срок',
    gate_facts: [
      '? Сообщение о завершении работы в логе: не найдено в доступной части; показаны фрагментами: internal/courier/repository/postgres.go',
      '✓ Обязательные пути: cmd/, internal/: на месте: cmd/, internal/ (cmd/, internal/)',
      '✓ Реальный .env не закоммичен: не найдено — как и требуется',
    ],
    gate: {
      status: 'warning',
      facts: [],
      outcomes: [
        { check: 'required_paths', level: 'warning', label: '«Разделите код на логические директории (cmd/, internal/, pkg/)»', passed: true, inconclusive: false, detail: 'на месте: cmd/, internal/', locations: ['cmd/', 'internal/'] },
        { check: 'code_contains', level: 'blocking', label: 'Сообщение о завершении работы в логе', passed: false, inconclusive: true, detail: 'не найдено в доступной части; показаны фрагментами: internal/courier/repository/postgres.go', locations: [] },
        { check: 'code_contains', level: 'warning', label: 'Переопределение порта флагом командной строки', passed: true, inconclusive: false, detail: 'найдено: обработка флага --port', locations: ['internal/server/config/config.go:28'] },
        { check: 'code_contains', level: 'warning', label: 'Эндпоинт GET /ping', passed: true, inconclusive: false, detail: 'найдено: маршрут /ping', locations: ['internal/courier/handler/handler.go:26'] },
        { check: 'code_contains', level: 'warning', label: 'Эндпоинт HEAD /healthcheck', passed: true, inconclusive: false, detail: 'найдено: маршрут /healthcheck', locations: ['internal/courier/handler/handler.go:27'] },
        { check: 'code_contains', level: 'warning', label: 'Обработка сигналов завершения', passed: true, inconclusive: false, detail: 'найдено: signal.Notify с SIGINT/SIGTERM', locations: ['cmd/myapp/main.go:34'] },
        { check: 'required_paths', level: 'warning', label: 'Параметры сервера читаются из .env — пример файла должен быть в репозитории', passed: true, inconclusive: false, detail: 'на месте: .env.example', locations: ['.env.example'] },
        { check: 'forbidden_paths', level: 'warning', label: 'Реальный .env не закоммичен', passed: true, inconclusive: false, detail: 'не найдено — как и требуется', locations: [] },
        { check: 'token_budget', level: 'info', label: 'Объём работы', passed: true, inconclusive: false, detail: 'около 2423 токенов при лимите 40000', locations: [] },
      ],
    },
    verdicts: [
      {
        criterion_id: 'c1',
        score: 1.5,
        confidence: 0.84,
        verdict:
          'Каталоги разведены по рекомендации: точка входа в cmd/myapp, внутренние пакеты в internal/, общий логгер в pkg/. Границы местами размыты: конфигурация лежит в internal/server/config, хотя к HTTP-серверу отношения не имеет, — а в корне репозитория валяется отладочный text.txt с одной строкой «conn test». Каталога migrations/ нет вовсе, хотя схема couriers в работе уже используется.',
        evidence: [at('cmd/myapp/main.go', '	"github.com/Avito-courses/course-go-avito-israpilovsha/internal/server/config"'), at('text.txt', 'conn test')],
        student_feedback:
          'Раскладка по cmd/, internal/ и pkg/ сделана правильно — на следующих заданиях сервис будет расти именно так. Уберите из корня text.txt и поднимите config на уровень internal/config: он нужен не только серверу.',
        improvement_hint: 'Добавьте migrations/ с goose-миграцией для couriers и вынесите config из internal/server/.',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c2',
        score: 2,
        confidence: 0.89,
        verdict:
          'Сервер поднимается на стандартном net/http, PORT читается из .env через godotenv, флаг --port переопределяет значение окружения: значение из переменной подставлено дефолтом в flag.StringVar, поэтому приоритет ровно тот, что требует условие. Все три пункта критерия выполнены.',
        evidence: [
          at('internal/server/config/config.go', '	flag.StringVar(&port, "port", port, "Server port")'),
          at('internal/server/server.go', '		Addr:    fmt.Sprintf(":%s", port),'),
        ],
        student_feedback: 'Конфигурация собрана аккуратно: env как основа, флаг как переопределение, дефолт 8080 на случай пустого значения.',
        improvement_hint: 'Стоит проверять, что параметры базы не пустые: сейчас пустой POSTGRES_HOST даст непонятный DSN и падение уже на пуле.',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c3',
        score: 2,
        confidence: 0.92,
        verdict:
          'Оба тестовых эндпоинта на месте и отвечают ровно так, как задано условием: GET /ping отдаёт 200 и {"message":"pong"}, HEAD /healthcheck — 204 без тела.',
        evidence: [
          at('internal/courier/handler/handler.go', '	r.HandleFunc("/ping", h.Ping).Methods("GET")'),
          at('internal/courier/handler/handler.go', '	w.WriteHeader(http.StatusNoContent)'),
        ],
        student_feedback: 'Маршруты и коды ответов совпадают с условием буквально.',
        improvement_hint: '',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c4',
        score: 0.5,
        confidence: 0.86,
        verdict:
          'Каркас завершения собран верно — signal.NotifyContext на SIGINT и SIGTERM, отдельный контекст с таймаутом, srv.Shutdown. Но работает он не так: при штатной остановке ListenAndServe возвращает http.ErrServerClosed, а горутина сравнивает ошибку с context.Canceled и уходит в log.Fatalf, то есть в os.Exit(1). Процесс умирает раньше, чем отработает Shutdown, и ни один defer — ни database.Close, ни stop, ни cancel — не выполняется. Сообщение в логе к тому же не то, которое задаёт условие дословно: «Shutting down gracefully...» вместо «Shutting down service-courier».',
        evidence: [
          at('cmd/myapp/main.go', '		if err := srv.Start(); err != nil && err != context.Canceled {'),
          at('cmd/myapp/main.go', '			log.Fatalf("server failed: %v", err)'),
          at('cmd/myapp/main.go', '	log.Println("Shutting down gracefully...")'),
        ],
        student_feedback:
          'Схема с NotifyContext и Shutdown выбрана правильно, но проверить её не получится: на любом Ctrl+C сервис завершится через os.Exit с кодом 1, потому что штатное закрытие сервера считается ошибкой. Сообщение в логе тоже стоит привести к тому, что просит условие, — оно задано буквально.',
        improvement_hint:
          'Сравнивайте ошибку через errors.Is(err, http.ErrServerClosed) и не вызывайте log.Fatalf в горутине; в лог пишите «Shutting down service-courier».',
        needs_human_attention: true,
        attention_reason:
          'обязательный минимум по критерию — 1; при 0.5 работа уходит в незачёт независимо от суммы',
      },
      {
        criterion_id: 'c5',
        score: 1,
        confidence: 0.71,
        verdict:
          'Именование пакетов и функций осмысленно, слои разведены, дублирования нет. Но ошибки глушатся систематически: json.NewEncoder(...).Encode во всех четырёх обработчиках вызывается без проверки, godotenv.Load присвоен в пустой идентификатор, а вместо errors.New в репозитории написан самодельный тип customError на четыре строки. Плюс отладочный text.txt в корне и комментарии на двух языках вперемешку.',
        evidence: [
          at('internal/courier/handler/handler.go', '	json.NewEncoder(w).Encode(map[string]string{"message": "pong"})'),
          at('internal/courier/repository/interface.go', 'func errorNew(msg string) error { return &customError{msg} }'),
          at('internal/server/config/config.go', '	_ = godotenv.Load()'),
        ],
        student_feedback:
          'Читать код приятно: слои на месте, имена говорящие. Мешает другое — проглоченные ошибки. Encode может упасть на закрытом соединении, и тогда клиент получит 200 с пустым телом, а в логе не будет ничего.',
        improvement_hint:
          'Проверяйте ошибку Encode и логируйте её; замените customError на errors.New — стандартный errors.Is с ним работать не будет.',
        needs_human_attention: false,
        attention_reason: '',
      },
    ],
    needs_human_attention: true,
    attention_reasons: [
      'обязательный минимум провален: 7 баллов из 10 при пороге 6 — и всё равно незачёт',
      'блокирующее требование «Shutting down service-courier» осталось без ответа гейта: среди .go-файлов есть фрагмент, и проверка на отсутствие запрещена',
      'каталога migrations/ в работе нет — требование задания 2, рубрики на него в каталоге пока нет',
      'c4: обязательный минимум по критерию — 1; при 0.5 работа уходит в незачёт независимо от суммы',
    ],
    partial_artifacts: ['internal/courier/repository/postgres.go'],
    tokens_in: 7240,
    tokens_out: 1610,
    cost_rub: 2.4,
    failed_criteria: [],
    evidence_coverage: 1,
  },
}

export const DEMO_GO_WEAK_DETECT: DetectResponse = {
  bundle: BUNDLE,
  files: DEMO_GO_WEAK_REVIEW.files,
  report: {
    overall_score: 0.26,
    confidence_low: 0.15,
    confidence_high: 0.4,
    label: 'низкая вероятность',
    declared_ai_usage: false,
    declaration_note:
      'Декларации об использовании ИИ в работе нет, а политика рубрики — «использование разрешено, но должно быть заявлено». При сигнале 0.26 это не расхождение: признаков генерации не найдено, и требовать декларацию не за что.',
    mismatch: false,
    advisory: true,
    advisory_note:
      'Сигнал носит рекомендательный характер, не является доказательством нарушения и не влияет на балл автоматически. Решение принимает куратор.',
    limitations: [
      'Сигнал «перплексия» не участвовал: перплексия требует локальной модели с logprobs (AI_LLM__PROVIDER=local). Вес перераспределён между остальными тремя.',
      'Вывод построен на 3 сигналах из четырёх.',
      'Фрагменты короче 200 символов не оцениваются: на них статистика не работает.',
      'Шаблонный и сгенерированный инструментами код исключён из анализа: go.mod, go.sum и docker-compose.yaml в разбор не вошли.',
      'Доступны только фрагментами (полный текст не загружался): internal/courier/repository/postgres.go. Статистические сигналы по нему не считались.',
      'Критерии, чувствительные к самостоятельности: c5',
    ],
    tokens_in: 1420,
    tokens_out: 190,
    cost_rub: 0.4,
    signals: [
      {
        kind: 'forensics',
        status: 'ok',
        score: 0.24,
        weight: 0.467,
        spans: [],
        findings: [
          'восемь коммитов, шесть из них за один вечер 7 ноября — темп высокий, но шаги мелкие и последовательные',
          'коммит «rework after q&a» через десять дней после остальных — правки после ревью, а не единовременная выгрузка',
        ],
        note: '',
      },
      { kind: 'perplexity', status: 'unavailable', score: 0, weight: 0, spans: [], findings: [], note: 'локальная модель с logprobs не подключена' },
      { kind: 'stylometry', status: 'ok', score: 0.3, weight: 0.2, spans: [], findings: ['комментарии на русском и английском вперемешку, один без пробела после слэшей'], note: '' },
      { kind: 'judge', status: 'ok', score: 0.27, weight: 0.333, spans: [], findings: [], note: '' },
    ],
    spans: [
      {
        id: 'span-custom-error',
        artifact: 'internal/courier/repository/interface.go',
        start: null,
        end: null,
        start_line: 16,
        end_line: 24,
        score: 0.41,
        signals: ['judge'],
        reason:
          'Самодельная обёртка над errors.New — узнаваемый шаблон из ответов ассистентов: интерфейс, две переменные ошибок, приватный тип с методом Error и функция-конструктор. В остальном коде такой стиль не встречается, там ошибки создаются и возвращаются напрямую.',
        excerpt: 'type customError struct{ msg string }',
        ai_sensitive: true,
        reviewer_verdict: 'pending',
      },
    ],
  },
}
