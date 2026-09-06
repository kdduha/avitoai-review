package repository

import (
	"context"

	"github.com/Avito-courses/course-go-avito-israpilovsha/internal/courier/model"
	"github.com/Avito-courses/course-go-avito-israpilovsha/internal/db"
	"github.com/jackc/pgconn"
	"github.com/jackc/pgx/v5"
)

type PostgresCourierRepository struct {
	DB *db.Database
}

func NewPostgresCourierRepository(db *db.Database) *PostgresCourierRepository {
	return &PostgresCourierRepository{DB: db}
}

func (r *PostgresCourierRepository) Create(ctx context.Context, c *model.Courier) error {
	query := `INSERT INTO couriers (name, phone, status) VALUES ($1, $2, $3) RETURNING id`
	err := r.DB.Pool.QueryRow(ctx, query, c.Name, c.Phone, c.Status).Scan(&c.ID)
	if err != nil {
		if pgErr, ok := err.(*pgconn.PgError); ok && pgErr.Code == "23505" {
			return ErrConflict
		}
		return err
	}
	return nil
}

func (r *PostgresCourierRepository) GetByID(ctx context.Context, id int64) (*model.Courier, error) {
	c := &model.Courier{}
	query := `SELECT id, name, phone, status, created_at, updated_at FROM couriers WHERE id=$1`
	err := r.DB.Pool.QueryRow(ctx, query, id).Scan(&c.ID, &c.Name, &c.Phone, &c.Status, &c.CreatedAt, &c.UpdatedAt)
	if err != nil {
		if err == pgx.ErrNoRows {
			return nil, ErrNotFound
		}
		return nil, err
	}
	return c, nil
}

func (r *PostgresCourierRepository) GetAll(ctx context.Context) ([]*model.Courier, error) {
	rows, err := r.DB.Pool.Query(ctx, `SELECT id, name, phone, status FROM couriers`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var couriers []*model.Courier
	for rows.Next() {
		c := &model.Courier{}
		if err := rows.Scan(&c.ID, &c.Name, &c.Phone, &c.Status); err != nil {
			return nil, err
		}
		couriers = append(couriers, c)
	}
	return couriers, nil
}

func (r *PostgresCourierRepository) Update(ctx context.Context, c *model.Courier) error {
	query := `UPDATE couriers SET 
		name = COALESCE($2, name), 
		phone = COALESCE($3, phone), 
		status = COALESCE($4, status), 
		updated_at = now()
		WHERE id = $1`
	cmd, err := r.DB.Pool.Exec(ctx, query, c.ID, c.Name, c.Phone, c.Status)
	if err != nil {
		return err
	}
	if cmd.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}
