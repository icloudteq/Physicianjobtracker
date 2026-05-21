import sys
from pathlib import Path
from loguru import logger

LOG_DIR = Path(__file__).parent.parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")
logger.add(
    LOG_DIR / "physician_tracker_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name} | {message}",
)


def get_logger(name: str):
    return logger.bind(name=name)
