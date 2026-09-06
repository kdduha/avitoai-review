package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/joho/godotenv"
	flag "github.com/spf13/pflag"

	"github.com/Avito-courses/course-go-avito-Turbina0N/internal/handlers"
	"github.com/Avito-courses/course-go-avito-Turbina0N/internal/repository"
	"github.com/Avito-courses/course-go-avito-Turbina0N/internal/usecase"
)

func main() {
	if err := godotenv.Load(); err != nil {
		log.Printf("warn: .env not loaded: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	db := initDBPool(ctx)
	defer db.Close()
	log.Println("postgres connected")

	courierRepo := repository.NewCourierRepository(db)
	courierUC := usecase.NewCourierUseCase(courierRepo)
	courierCtrl := handlers.NewCourierController(courierUC)

	srv := &http.Server{
		Addr:         ":" + resolvePort(),
		Handler:      initRouter(courierCtrl),
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go gracefulShutdown(srv)

	log.Printf("service-courier listening on %s\n", srv.Addr)
	if err := srv.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
		log.Fatalf("server start error: %v\n", err)
	}
}

func initDBPool(ctx context.Context) *pgxpool.Pool {
	host := os.Getenv("POSTGRES_HOST")
	port := os.Getenv("POSTGRES_PORT")
	user := os.Getenv("POSTGRES_USER")
	pass := os.Getenv("POSTGRES_PASSWORD")
	dbname := os.Getenv("POSTGRES_DB")

	if host == "" || port == "" || user == "" || dbname == "" {
		log.Fatal("POSTGRES_* env vars are required: POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB")
	}

	dsn := fmt.Sprintf("postgres://%s:%s@%s:%s/%s", user, pass, host, port, dbname)

	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		log.Fatalf("pgxpool.ParseConfig: %v", err)
	}
	cfg.MaxConns = 10
	cfg.MinConns = 2
	cfg.MaxConnLifetime = time.Hour
	cfg.MaxConnIdleTime = 30 * time.Minute

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		log.Fatalf("pgxpool.NewWithConfig: %v", err)
	}
	if err := pool.Ping(ctx); err != nil {
		log.Fatalf("db ping failed: %v", err)
	}
	return pool
}

func resolvePort() string {
	port := os.Getenv("PORT")
	var portFlag = flag.String("port", "", "HTTP port to listen on")
	flag.Parse()
	if portFlag != nil && *portFlag != "" {
		port = *portFlag
	}
	if port == "" {
		port = "8080"
	}
	return port
}

func initRouter(courier *handlers.CourierController) *chi.Mux {
	r := chi.NewRouter()
	r.Use(middleware.Logger)

	r.Get("/ping", handlers.Ping)
	r.Head("/healthcheck", handlers.Healthcheck)

	// CRUD
	r.Get("/courier/{id}", courier.Get)
	r.Get("/couriers", courier.GetMany)
	r.Post("/courier", courier.Create)
	r.Put("/courier", courier.Update)

	return r
}

func gracefulShutdown(srv *http.Server) {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	<-ctx.Done()
	log.Println("Shutting down service-courier")

	shCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(shCtx); err != nil {
		log.Printf("graceful shutdown failed: %v", err)
		_ = srv.Close()
	}
}
