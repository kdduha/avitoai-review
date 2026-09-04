from avito_reviewer.app.routers.base import router as base_router
from avito_reviewer.app.routers.ingest import router as ingest_router
from avito_reviewer.app.routers.review import router as review_router

__all__ = ["base_router", "ingest_router", "review_router"]
