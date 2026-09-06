package handlers

import (
	"encoding/json"
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"

	"github.com/Avito-courses/course-go-avito-Turbina0N/internal/dto"
	"github.com/Avito-courses/course-go-avito-Turbina0N/internal/usecase"
)

type CourierController struct {
	useCase courierUseCase
}

func NewCourierController(useCase courierUseCase) *CourierController {
	return &CourierController{useCase: useCase}
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

// GET /courier/{id}
func (c *CourierController) Get(w http.ResponseWriter, r *http.Request) {
	idStr := chi.URLParam(r, "id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		http.Error(w, `{"error":"invalid id"}`, http.StatusBadRequest)
		return
	}

	cr, err := c.useCase.GetCourier(r.Context(), id)
	if err != nil {
		switch err {
		case usecase.ErrNotFound:
			http.Error(w, `{"error":"not found"}`, http.StatusNotFound)
		case usecase.ErrBadRequest:
			http.Error(w, `{"error":"bad request"}`, http.StatusBadRequest)
		default:
			http.Error(w, `{"error":"database error"}`, http.StatusInternalServerError)
		}
		return
	}

	resp := dto.CourierResponse{
		ID:     cr.ID,
		Name:   cr.Name,
		Phone:  cr.Phone,
		Status: cr.Status,
	}
	writeJSON(w, http.StatusOK, resp)
}

// GET /couriers
func (c *CourierController) GetMany(w http.ResponseWriter, r *http.Request) {
	list, err := c.useCase.GetCouriers(r.Context())
	if err != nil {
		http.Error(w, `{"error": "database error"}`, http.StatusInternalServerError)
		return
	}
	out := make([]dto.CourierResponse, 0, len(list))
	for _, it := range list {
		out = append(out, dto.CourierResponse{
			ID:     it.ID,
			Name:   it.Name,
			Phone:  it.Phone,
			Status: it.Status,
		})
	}
	writeJSON(w, http.StatusOK, out)
}

// POST /courier
func (c *CourierController) Create(w http.ResponseWriter, r *http.Request) {
	var req dto.CourierCreateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid json"}`, http.StatusBadRequest)
		return
	}

	id, err := c.useCase.CreateCourier(r.Context(), &req)
	if err != nil {
		switch err {
		case usecase.ErrMissingRequiredFields, usecase.ErrInvalidStatus, usecase.ErrInvalidPhone:
			http.Error(w, `{"error":"bad request"}`, http.StatusBadRequest)
		case usecase.ErrPhoneExists:
			http.Error(w, `{"error":"conflict"}`, http.StatusConflict)
		default:
			http.Error(w, `{"error": "database error"}`, http.StatusInternalServerError)
		}
		return
	}

	writeJSON(w, http.StatusCreated, map[string]any{"id": id})
}

// PUT /courier
func (c *CourierController) Update(w http.ResponseWriter, r *http.Request) {
	var req dto.CourierUpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid json"}`, http.StatusBadRequest)
		return
	}

	if err := c.useCase.UpdateCourier(r.Context(), &req); err != nil {
		switch err {
		case usecase.ErrBadRequest, usecase.ErrInvalidStatus, usecase.ErrInvalidPhone:
			http.Error(w, `{"error":"bad request"}`, http.StatusBadRequest)
		case usecase.ErrNotFound:
			http.Error(w, `{"error":"not found"}`, http.StatusNotFound)
		case usecase.ErrPhoneExists:
			http.Error(w, `{"error":"conflict"}`, http.StatusConflict)
		default:
			http.Error(w, `{"error":"internal error"}`, http.StatusInternalServerError)
		}
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"message": "updated"})
}
