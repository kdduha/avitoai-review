package route

import (
	"github.com/go-chi/chi/v5"
)

func SetupRoute() chi.Router {
	mR := chi.NewRouter()
	mR.Mount("/", HealthRoute())
	return mR
}
