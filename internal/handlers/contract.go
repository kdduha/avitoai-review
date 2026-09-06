package handlers

import (
	"context"

	"github.com/Avito-courses/course-go-avito-Turbina0N/internal/dto"
	"github.com/Avito-courses/course-go-avito-Turbina0N/internal/model"
)

type courierUseCase interface {
	GetCourier(ctx context.Context, id int) (*model.Courier, error)
	GetCouriers(ctx context.Context) ([]model.Courier, error)
	CreateCourier(ctx context.Context, req *dto.CourierCreateRequest) (int, error)
	UpdateCourier(ctx context.Context, req *dto.CourierUpdateRequest) error
}
