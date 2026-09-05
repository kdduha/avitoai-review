package usecase

import (
	"context"
	"errors"
	"regexp"

	"github.com/Avito-courses/course-go-avito-Turbina0N/internal/dto"
	"github.com/Avito-courses/course-go-avito-Turbina0N/internal/entity"
	"github.com/Avito-courses/course-go-avito-Turbina0N/internal/model"
	"github.com/Avito-courses/course-go-avito-Turbina0N/internal/repository"
)

type CourierUseCase struct {
	repository courierRepository
}

func NewCourierUseCase(repository courierRepository) *CourierUseCase {
	return &CourierUseCase{repository: repository}
}

// Возвращает курьера по ID
func (u *CourierUseCase) GetCourier(ctx context.Context, id int) (*model.Courier, error) {
	courierDB, err := u.repository.GetOneByID(ctx, id)

	if err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			return nil, ErrNotFound
		}
		return nil, err
	}

	courier := &model.Courier{
		ID:     courierDB.ID,
		Name:   courierDB.Name,
		Phone:  courierDB.Phone,
		Status: courierDB.Status,
	}

	return courier, nil
}

// Возвращает все профили
func (u *CourierUseCase) GetCouriers(ctx context.Context) ([]model.Courier, error) {
	courierDB, err := u.repository.GetAll(ctx)
	if err != nil {
		return nil, err
	}

	var couriers []model.Courier
	for _, courierDB := range courierDB {
		profile := model.Courier{
			ID:     courierDB.ID,
			Name:   courierDB.Name,
			Phone:  courierDB.Phone,
			Status: courierDB.Status,
		}
		couriers = append(couriers, profile)
	}

	if couriers == nil {
		couriers = []model.Courier{}
	}

	return couriers, nil
}

// CreateCourier создаёт нового курьера (без TrimSpace, как в шаблоне)
func (u *CourierUseCase) CreateCourier(ctx context.Context, req *dto.CourierCreateRequest) (int, error) {
	if req == nil || req.Name == "" || req.Phone == "" || req.Status == "" {
		return 0, ErrMissingRequiredFields
	}

	if !model.IsValidStatus(req.Status) {
		return 0, ErrInvalidStatus
	}

	re := regexp.MustCompile(`^\+?[0-9]{7,15}$`)
	if !re.MatchString(req.Phone) {
		return 0, ErrInvalidPhone
	}

	courier := &entity.Courier{
		Name:   req.Name,
		Phone:  req.Phone,
		Status: req.Status,
	}

	id, err := u.repository.Create(ctx, courier)

	if err != nil {
		if errors.Is(err, repository.ErrConflict) {
			return 0, ErrPhoneExists
		}
		return 0, err
	}

	return id, nil
}

// UpdateCourier обновляет данные курьера (частично: непереданные поля не меняются)
func (u *CourierUseCase) UpdateCourier(ctx context.Context, req *dto.CourierUpdateRequest) error {
	if req == nil || req.ID <= 0 {
		return ErrBadRequest
	}

	if req.Status != nil && *req.Status != "" && !model.IsValidStatus(*req.Status) {
		return ErrInvalidStatus // статус прислали и он недопустим
	}

	if req.Phone != nil && *req.Phone != "" {
		re := regexp.MustCompile(`^\+?[0-9]{7,15}$`)
		if !re.MatchString(*req.Phone) {
			return ErrInvalidPhone // прислали телефон, но формат неверный
		}
	}

	var name, phone, status string
	if req.Name != nil {
		name = *req.Name
	}
	if req.Phone != nil {
		phone = *req.Phone
	}
	if req.Status != nil {
		status = *req.Status
	}

	c := &entity.Courier{
		ID:     req.ID,
		Name:   name,
		Phone:  phone,
		Status: status,
	}

	if err := u.repository.Update(ctx, c); err != nil {
		switch err {
		case repository.ErrNotFound:
			return ErrNotFound
		case repository.ErrConflict:
			return ErrPhoneExists
		default:
			return err
		}
	}

	return nil
}
