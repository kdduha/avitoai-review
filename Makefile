# Загружаем переменные из .env файла
include .env
export $(shell sed 's/=.*//' .env)

GOOSE_DRIVER = postgres
GOOSE_DBSTRING = postgres://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@$(POSTGRES_HOST):$(POSTGRES_PORT)/$(POSTGRES_DB)
MIGRATIONS_DIR = migrations
#export GOOSE_DBSTRING="postgres://postgres:postgres@localhost:5432/service_courier"

.PHONY: migrate-up migrate-down migrate-status

# Применение миграций
migrate-up:
	@echo "Applying migrations from $(MIGRATIONS_DIR)..."
	GOOSE_DRIVER=$(GOOSE_DRIVER) GOOSE_DBSTRING="$(GOOSE_DBSTRING)" goose -dir $(MIGRATIONS_DIR) up

# Откат миграций
migrate-down:
	@echo "Rolling back migrations..."
	GOOSE_DRIVER=$(GOOSE_DRIVER) GOOSE_DBSTRING="$(GOOSE_DBSTRING)" goose -dir $(MIGRATIONS_DIR) down

# Просмотр статуса миграций
migrate-status:
	@echo "Migration status in $(MIGRATIONS_DIR):"
	GOOSE_DRIVER=$(GOOSE_DRIVER) GOOSE_DBSTRING="$(GOOSE_DBSTRING)" goose -dir $(MIGRATIONS_DIR) status