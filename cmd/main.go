package main

import (
	"net/http"
	"serviceDelivery/internal/route"
)

func main() {
	http.ListenAndServe(":8080", route.SetupRoute())
}
