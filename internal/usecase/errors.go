package usecase

import "errors"

var (
	ErrBadRequest            = errors.New("bad request")
	ErrNotFound              = errors.New("courier not found")
	ErrMissingRequiredFields = errors.New("missing required fields")
	ErrInvalidStatus         = errors.New("invalid status")
	ErrPhoneExists           = errors.New("phone already exists")
	ErrInvalidPhone          = errors.New("invalid phone")
)
