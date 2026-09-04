/** Файлы демо-работы. Это настоящее решение первого задания курса Go:
 *  веб-сервер с /ping и /healthcheck, порт из .env с переопределением флагом,
 *  корректное завершение по сигналу. Формат текста тот же, что у
 *  `ArtifactTextOut`: строки нумеруются от `first_line`. */

export interface DemoFile {
  path: string
  lang: string
  firstLine: number
  partial: boolean
  origin: string
  changedLines: string
  text: string
}

const MAIN_GO = `package main

import (
	"context"
	"errors"
	"flag"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/student-1043/service-courier/internal/config"
	"github.com/student-1043/service-courier/internal/handler"
)

func main() {
	cfg := config.Load()

	port := flag.String("port", cfg.Port, "порт HTTP-сервера")
	flag.Parse()

	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	mux := http.NewServeMux()
	handler.Register(mux)

	server := &http.Server{
		Addr:    ":" + *port,
		Handler: mux,
	}

	go func() {
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Error("listen failed", "err", err)
			os.Exit(1)
		}
	}()
	log.Info("service-courier started", "port", *port)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	<-ctx.Done()

	log.Info("Shutting down service-courier")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Error("shutdown failed", "err", err)
	}
}
`

const HANDLER_GO = `package handler

import (
	"net/http"
)

func Register(mux *http.ServeMux) {
	mux.HandleFunc("/ping", ping)
	mux.HandleFunc("/healthcheck", healthcheck)
}

func ping(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("pong"))
}

func healthcheck(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
}
`

const CONFIG_GO = `package config

import (
	"os"
)

type Config struct {
	Port string
	Env  string
}

func Load() Config {
	return Config{
		Port: getenv("PORT", "8080"),
		Env:  getenv("APP_ENV", "local"),
	}
}

func getenv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
`

const README_MD = `# service-courier

Сервис курьерской доставки, первое домашнее задание курса «Разработка
микросервисов на Go».

## Архитектура

Проект разделён на слои в соответствии с рекомендациями golang-standards/project-layout.
Важно отметить, что подобное разделение обеспечивает высокую степень поддерживаемости
кода и позволяет масштабировать систему без существенных изменений в существующих
компонентах. Точка входа расположена в директории cmd, внутренние пакеты вынесены
в internal, что предотвращает их импорт из внешних модулей.

Следует отметить, что такой подход является общепринятой практикой в индустрии
и позволяет обеспечить тестируемость каждого компонента в отдельности.

## Запуск

    go run cmd/main.go --port 3000

## Эндпоинты

- GET /ping — возвращает pong
- HEAD /healthcheck — проба готовности

## Конфигурация

Параметры читаются из окружения: PORT, APP_ENV.
`

export const DEMO_FILES: DemoFile[] = [
  {
    path: 'cmd/main.go',
    lang: 'go',
    firstLine: 1,
    partial: false,
    origin: 'excerpt',
    changedLines: '1–68',
    text: MAIN_GO,
  },
  {
    path: 'internal/handler/health.go',
    lang: 'go',
    firstLine: 1,
    partial: false,
    origin: 'excerpt',
    changedLines: '1–21',
    text: HANDLER_GO,
  },
  {
    path: 'internal/config/config.go',
    lang: 'go',
    firstLine: 1,
    partial: false,
    origin: 'excerpt',
    changedLines: '1–23',
    text: CONFIG_GO,
  },
  {
    path: 'README.md',
    lang: 'markdown',
    firstLine: 1,
    partial: false,
    origin: 'excerpt',
    changedLines: '1–30',
    text: README_MD,
  },
]
