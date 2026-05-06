"""
core/logger.py
로그 시스템 — logs/app.log 에 기록
"""
import logging
import os
from datetime import datetime

os.makedirs("logs", exist_ok=True)

def get_logger(name: str = "auction") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # 이미 설정된 경우 재사용

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 파일 핸들러
    fh = logging.FileHandler("logs/app.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # 콘솔 핸들러
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

log = get_logger()
