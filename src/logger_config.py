"""User-writable logs; installed/frozen application directories stay untouched."""
import logging
import os
from pathlib import Path
import tempfile
from datetime import datetime


def create_logger():
    logger=logging.getLogger('AVSnap'); logger.setLevel(logging.DEBUG)
    if logger.handlers: return logger
    formatter=logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    console=logging.StreamHandler(); console.setFormatter(formatter); logger.addHandler(console)
    base=Path(os.environ.get('AV_SNAP_LOG_DIR') or (Path(os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_STATE_HOME') or Path.home()/'.local'/'state')/'ArtificialVision'/'AVSnap'/'logs'))
    for folder in [base,Path(tempfile.gettempdir())/'av-snap-logs']:
        try:
            folder.mkdir(parents=True,exist_ok=True)
            handler=logging.FileHandler(folder/f'alignment_{datetime.now():%Y%m%d_%H%M%S}.log',encoding='utf-8')
            handler.setFormatter(formatter); logger.addHandler(handler)
            break
        except OSError:
            continue
    return logger


log=create_logger()

def log_milestone(phase,name,status):
    log.info('[%s] %s: %s',phase,name,status)
