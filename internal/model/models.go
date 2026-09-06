package model

import "time"

type Courier struct {
	ID        int
	Name      string
	Phone     string
	Status    string // "available" | "busy" | "paused"
	CreatedAt time.Time
	UpdatedAt time.Time
}

const (
	StatusAvailable = "available"
	StatusBusy      = "busy"
	StatusPaused    = "paused"
)

func IsValidStatus(s string) bool {
	switch s {
	case StatusAvailable, StatusBusy, StatusPaused:
		return true
	}
	return false
}
