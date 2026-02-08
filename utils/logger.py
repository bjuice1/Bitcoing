"""Logging configuration."""
import logging


def setup_logging(level="INFO", log_file=None):
    """Configure logging with rich console and optional file handler."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger("btcmonitor")
    root.setLevel(numeric_level)

    if not root.handlers:
        try:
            from rich.logging import RichHandler
            console_handler = RichHandler(level=numeric_level, rich_tracebacks=True, markup=True)
        except ImportError:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(numeric_level)
            formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
            console_handler.setFormatter(formatter)

        root.addHandler(console_handler)

        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(numeric_level)
            file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
            file_handler.setFormatter(file_formatter)
            root.addHandler(file_handler)

    return root
