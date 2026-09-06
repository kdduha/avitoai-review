package handler

import (
	"encoding/json"
	"net/http"
)

type HealthHandler struct{}

func (hh *HealthHandler) PingHandler(w http.ResponseWriter, r *http.Request) {
	json.NewEncoder(w).Encode(map[string]string{"message": "pong"})
}

func (hh *HealthHandler) HealthCheckHandler(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusNoContent)
}
