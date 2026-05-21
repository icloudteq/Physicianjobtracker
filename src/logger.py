import logging
import os
from datetime import datetime
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    log_dir = Path(os.getenv("LOG_DIR", "data/logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"{datetime.utcnow().strftime('%Y-%m-%d')}.log"

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger
