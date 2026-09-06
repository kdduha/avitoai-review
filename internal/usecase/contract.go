package usecase

import (
	"context"

	"github.com/Avito-courses/course-go-avito-Turbina0N/internal/entity"
)

type courierRepository interface {
	GetOneByID(ctx context.Context, id int) (*entity.Courier, error)
	GetAll(ctx context.Context) ([]entity.Courier, error)
	Create(ctx context.Context, courier *entity.Courier) (int, error)
	Update(ctx context.Context, courier *entity.Courier) error
}
