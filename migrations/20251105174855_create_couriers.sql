-- +goose Up
CREATE TABLE IF NOT EXISTS couriers (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    phone       TEXT NOT NULL UNIQUE,
    status      TEXT NOT NULL,  -- например: 'available', 'busy', 'paused'
    created_at  TIMESTAMP NOT NULL DEFAULT now(),
    updated_at  TIMESTAMP NOT NULL DEFAULT now()
);

-- +goose Down
DROP TABLE IF EXISTS couriers;
