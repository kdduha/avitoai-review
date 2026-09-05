from avito_reviewer.app.routers.auth import router as auth_router
from avito_reviewer.app.routers.base import router as base_router
from avito_reviewer.app.routers.distribution import router as distribution_router
from avito_reviewer.app.routers.ingest import router as ingest_router
from avito_reviewer.app.routers.review import router as review_router
from avito_reviewer.app.routers.submissions import router as submissions_router
from avito_reviewer.app.routers.users import router as users_router

__all__ = [
    "auth_router",
    "base_router",
    "distribution_router",
    "ingest_router",
    "review_router",
    "submissions_router",
    "users_router",
]
