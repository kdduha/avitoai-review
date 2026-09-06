package handler

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
}
