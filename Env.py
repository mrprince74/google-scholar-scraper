import logging
import threading
from threading import Lock, Thread
class Env:
    total_requests = 0
    is_running = False
    is_running_lock = Lock()
    is_debug = False
    SELENIUM_LOCALHOST = 'http://selenium-chrome:4444'
    ## Use for debugging on local machine
    # SELENIUM_LOCALHOST = 'http://localhost:4444'
    REQUESTS_LIMIT = 10
    DOI_PATTERN = r'\b(10[.][0-9]{4,}(?:[.][0-9]+)*/(?:(?!["&\'<>])\S)+)\b'
    SCHOLAR_BASE_URL = "https://scholar.google.com/"
    ACADEMIA_LOGIN_URL = 'https://www.academia.edu/login'
    ACADEMIA_EMAIL = 'hineje3688@ndiety.com'
    ACADEMIA_PASSWORD = 'aa11bb22'



class SingletonMeta(type):
    _instance = None

    def __call__(self, *args, **kwargs):
        if  not self._instance:
            self._instance = super().__call__(*args, **kwargs)
        
        return self._instance


THREAD_COLORS = {
    'Thread-1': '\033[1;95m',  # Bold Magenta
    'Thread-2': '\033[1;94m',  # Bold Blue
    'Thread-3': '\033[1;36m',  # Bold Light Blue
    'Thread-4': '\033[1;96m',  # Bold Light Magenta
    'Database': '\033[1;34m',  # Bold Light Gray
}

RESET_COLOR = '\033[1;0m'  # Reset color back to normal

class ThreadColoredFormatter(logging.Formatter):
    def format(self, record):
        # Get the current thread name
        thread_name = threading.current_thread().name
        
        # Get thread-specific color
        thread_color = THREAD_COLORS.get(thread_name, RESET_COLOR)
        
        # The log level name is already colored in your setup
        levelname = record.levelname
        
        # Format the log message
        formatted_message = super().format(record)
        
        # Apply thread color and keep log level color, then reset after the message
        return f"{record.asctime} : {thread_color}{thread_name}{RESET_COLOR} : {levelname} : {record.message}"

def setup_logger():
    # Add level name colors (your original setup)
    logging.addLevelName(logging.WARNING, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
    logging.addLevelName(logging.DEBUG, "\033[1;32m%s\033[1;0m" % "SUCCESS")
    logging.addLevelName(logging.INFO, "\033[1;37m%s\033[1;0m" % logging.getLevelName(logging.INFO))
    logging.addLevelName(logging.ERROR, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.ERROR))
    
    # Create logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    # Create file handler
    file_handler = logging.FileHandler("output.log")
    
    # Define the formatter (with the date format for 'asctime')
    formatter = ThreadColoredFormatter('%(asctime)s : %(levelname)s : %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(formatter)
    
    # Add the handler to the logger
    logger.addHandler(file_handler)
    
    return logger


logger = setup_logger()