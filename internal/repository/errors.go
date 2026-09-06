package repository

import (
	"errors"
)

var (
	ErrNotFound   = errors.New("courier not found")
	ErrConflict   = errors.New("courier conflict")
	ErrValidation = errors.New("validation error")
)
