package repository

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Avito-courses/course-go-avito-Turbina0N/internal/entity"
)

type CourierRepository struct {
	pool *pgxpool.Pool
}

func NewCourierRepository(pool *pgxpool.Pool) *CourierRepository {
	return &CourierRepository{pool: pool}
}

// GET /courier/{id}
func (r *CourierRepository) GetOneByID(ctx context.Context, id int) (*entity.Courier, error) {
	row := r.pool.QueryRow(ctx,
		"SELECT id, name, phone, status FROM couriers WHERE id = $1;", id,
	)

	var c entity.Courier
	err := row.Scan(&c.ID, &c.Name, &c.Phone, &c.Status)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, fmt.Errorf("database error: %w", err)
	}
	return &c, nil
}

// GET /couriers
func (r *CourierRepository) GetAll(ctx context.Context) ([]entity.Courier, error) {
	rows, err := r.pool.Query(ctx,
		"SELECT id, name, phone, status FROM couriers ORDER BY id;",
	)

	if err != nil {
		return nil, fmt.Errorf("database error: %w", err)
	}

	defer rows.Close()

	var out []entity.Courier
	for rows.Next() {
		var c entity.Courier
		if err := rows.Scan(&c.ID, &c.Name, &c.Phone, &c.Status); err != nil {
			return nil, fmt.Errorf("error reading data: %w", err)
		}
		out = append(out, c)
	}

	if err = rows.Err(); err != nil {
		return nil, fmt.Errorf("database error: %w", err)
	}

	if out == nil {
		out = []entity.Courier{}
	}

	return out, nil
}

// POST /courier
func (r *CourierRepository) Create(ctx context.Context, c *entity.Courier) (int, error) {
	row := r.pool.QueryRow(ctx,
		"INSERT INTO couriers (name, phone, status) VALUES ($1, $2, $3) RETURNING id;",
		c.Name, c.Phone, c.Status,
	)

	var id int
	if err := row.Scan(&id); err != nil {
		if strings.Contains(err.Error(), "duplicate key value") ||
			strings.Contains(err.Error(), "unique constraint") {
			return 0, ErrConflict
		}
		return 0, fmt.Errorf("database error: %w", err)
	}

	return int(id), nil
}

// PUT /courier
func (r *CourierRepository) Update(ctx context.Context, c *entity.Courier) error {
	ct, err := r.pool.Exec(ctx,
		`UPDATE couriers
		   SET name       = COALESCE(NULLIF($1, ''), name),
		       phone      = COALESCE(NULLIF($2, ''), phone),
		       status     = COALESCE(NULLIF($3, ''), status),
		       updated_at = now()
		 WHERE id = $4;`,
		c.Name, c.Phone, c.Status, c.ID,
	)

	if err != nil {
		if strings.Contains(err.Error(), "duplicate key value") {
			return ErrConflict
		}
		return fmt.Errorf("database error: %w", err)
	}

	if ct.RowsAffected() == 0 {
		return ErrNotFound
	}

	return nil
}
