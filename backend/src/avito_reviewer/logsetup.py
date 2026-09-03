from __future__ import annotations

import logging
import os

_NAMESPACE = "avito_reviewer"


def configure_logging() -> None:
    """Attach one stderr handler to the ``avito_reviewer`` logger tree.

    Idempotent. Level from ``LOG_LEVEL`` (default INFO). Root is left alone so
    uvicorn keeps owning access/error logs.
    """
    logger = logging.getLogger(_NAMESPACE)
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    )
    logger.addHandler(handler)
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    logger.propagate = False
