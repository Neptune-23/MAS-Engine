import logging
import sys
from pathlib import Path

def setup_logger():
    """配置并返回 logger 实例"""
    BASE_DIR = Path(__file__).parent.parent
    LOG_DIR = BASE_DIR / "logs"
    LOG_DIR.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(LOG_DIR / "mcp.log", encoding='utf-8'),
            logging.StreamHandler(sys.stderr)
        ],
        force=True
    )
    return logging.getLogger("company-mcp")