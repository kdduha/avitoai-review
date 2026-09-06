package entity

import "time"

type Courier struct {
	ID        int
	Name      string
	Phone     string
	Status    string
	CreatedAt time.Time
	UpdatedAt time.Time
}
