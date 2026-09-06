package main

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
}
