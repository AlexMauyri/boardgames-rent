"""Application-wide logging setup for console output."""
import logging

_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logging once."""
    logging.basicConfig(level=level, format=_FORMAT, datefmt=_DATEFMT)