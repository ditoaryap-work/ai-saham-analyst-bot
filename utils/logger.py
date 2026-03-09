"""
logger.py — Setup Loguru logger untuk IDX AI Trading Assistant.
"""

import sys
from pathlib import Path
from loguru import logger

# Impor konfigurasi
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import LOG_LEVEL, BASE_DIR


def setup_logger():
    """Konfigurasi logger dengan output ke console dan file."""
    # Hapus handler default
    logger.remove()

    # Format log
    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # Console handler
    logger.add(sys.stderr, format=fmt, level=LOG_LEVEL, colorize=True)

    # File handler — rotasi harian, simpan 7 hari
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    logger.add(
        str(log_dir / "trading_{time:YYYY-MM-DD}.log"),
        format=fmt,
        level=LOG_LEVEL,
        rotation="00:00",     # Rotasi setiap tengah malam
        retention="7 days",   # Simpan 7 hari
        compression="gz",     # Kompresi log lama
        encoding="utf-8",
    )

    logger.info("Logger berhasil diinisialisasi.")
    return logger


# Auto-setup saat diimpor
setup_logger()
