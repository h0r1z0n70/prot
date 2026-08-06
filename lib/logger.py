import logging
import sys

class _ColoredFormatter(logging.Formatter):
    _COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self._COLORS.get(record.levelname, self._RESET)
        record.levelname = f"{color}{record.levelname}{self._RESET}"
        return super().format(record)

def get_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"
    if sys.stdout.isatty():
        formatter = _ColoredFormatter(fmt, datefmt=date_fmt)
    else:
        formatter = logging.Formatter(fmt, datefmt=date_fmt)
    handler.setFormatter(formatter)
    log.addHandler(handler)
    return log
