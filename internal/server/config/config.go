package config

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
}
