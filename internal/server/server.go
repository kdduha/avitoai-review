package server

import (
	"context"
	"fmt"
	"net/http"
)

type Server struct {
	httpServer *http.Server
}

func New(port string, handler http.Handler) *Server {
	srv := &http.Server{
		Addr:    fmt.Sprintf(":%s", port),
		Handler: handler,
	}
	return &Server{httpServer: srv}
}

func (s *Server) Start() error {
	return s.httpServer.ListenAndServe()
}

func (s *Server) Shutdown(ctx context.Context) error {
	return s.httpServer.Shutdown(ctx)
}
