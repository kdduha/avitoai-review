package route

import (
	"serviceDelivery/internal/handler"

	"github.com/go-chi/chi/v5"
)

func HealthRoute() chi.Router {
	hh := handler.HealthHandler{}
	hr := chi.NewRouter()
	hr.Get("/ping", hh.PingHandler)
	hr.Head("/healthcheck", hh.HealthCheckHandler)
	return hr
}
