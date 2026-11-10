import logging
import os
from datetime import datetime

class AlignmentLogger:
    _instance = None
    
    @classmethod
    def get_logger(cls):
        if cls._instance is None:
            cls._instance = cls._setup_logger()
        return cls._instance
        
    @staticmethod
    def _setup_logger():
        # Create logs directory if it doesn't exist
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"alignment_session_{timestamp}.log")
        
        logger = logging.getLogger("3D_Alignment_Tool")
        logger.setLevel(logging.DEBUG)
        
        # File handler updates runtime log
        file_handler = logging.FileHandler(log_file, mode='w')
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        logger.info("Session started. Log file created.")
        return logger

# Global instance for easy import
log = AlignmentLogger.get_logger()

# Convenience functions for milestone logging
def log_milestone(phase, milestone_name, status):
    """
    Standardized function to log milestone progress.
    Ex: log_milestone("Phase 2", "File I/O", "Started")
    """
    log.info(f"[{phase}] - {milestone_name} : {status}")
