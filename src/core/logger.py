"""
Structured logging setup using rich + standard logging.

Usage in any module:
    from src.core.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Queue engine started", extra={"doctor_id": 5, "session": "morning"})
"""

import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(exist_ok=True)

_RICH_FORMAT = "%(message)s"
_FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def _build_handlers() -> list[logging.Handler]:
    """Build console (rich) and rotating file handlers."""
    # Rich console handler — colourised, human-readable
    console_handler = RichHandler(
        console=Console(stderr=True),
        rich_tracebacks=True,
        tracebacks_show_locals=False,
        show_time=True,
        show_path=True,
        markup=True,
    )
    console_handler.setFormatter(logging.Formatter(_RICH_FORMAT, datefmt="[%X]"))

    # Plain file handler for persistent logs
    file_handler = logging.FileHandler(_LOG_DIR / "app.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))

    return [console_handler, file_handler]


def configure_logging(level: str = "INFO") -> None:
    """
    Configure the root logger once at application startup.

    Call this from src/main.py lifespan before any module imports start logging.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=numeric_level,
        format=_RICH_FORMAT,
        datefmt="[%X]",
        handlers=_build_handlers(),
    )

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpcore", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger inheriting from the configured root logger.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A standard :class:`logging.Logger` instance.
    """
    return logging.getLogger(name)
