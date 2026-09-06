package repository

import (
	"context"

	"github.com/Avito-courses/course-go-avito-israpilovsha/internal/courier/model"
)

type CourierRepository interface {
	Create(ctx context.Context, c *model.Courier) error
	GetByID(ctx context.Context, id int64) (*model.Courier, error)
	GetAll(ctx context.Context) ([]*model.Courier, error)
	Update(ctx context.Context, c *model.Courier) error
}

var (
	ErrNotFound = errorNew("courier not found")
	ErrConflict = errorNew("courier with this phone already exists")
)

type customError struct{ msg string }

func (e *customError) Error() string { return e.msg }

func errorNew(msg string) error { return &customError{msg} }
