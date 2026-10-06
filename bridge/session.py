"""Prototype shim: build_headers now lives in ``src.capture.session`` (single
source of truth). Kept so the old ``bridge`` prototype and its tests import."""

from src.capture.session import (  # noqa: F401
    ORIGIN,
    MissingSapisidError,
    build_headers,
)
