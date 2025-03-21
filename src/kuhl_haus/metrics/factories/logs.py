import logging
from pathlib import Path
from functools import lru_cache

from kuhl_haus.metrics.env import LOG_LEVEL


@lru_cache()
def get_logger(application_name: str = None, log_level: str = LOG_LEVEL, log_directory: str = None) -> logging.Logger:
    application_name = __name__ if application_name is None else application_name
    logger: logging.Logger = logging.getLogger(application_name)
    logger.setLevel(log_level)

    # Stream Handler (console)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(log_level)
    logging_template = '{' \
        '"timestamp": "%(asctime)s", ' \
        '"filename": "%(filename)s", ' \
        '"function": "%(funcName)s", ' \
        '"line": "%(lineno)d", ' \
        '"level": "%(levelname)s", ' \
        '"pid": "%(process)d", ' \
        '"thr": "%(thread)d", ' \
        '"message": "%(message)s", ' \
        '}'
    log_formatter = logging.Formatter(logging_template)
    stream_handler.setFormatter(log_formatter)
    logger.addHandler(stream_handler)

    # File Handler
    if log_directory is not None:
        Path(log_directory).mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler("{0}/{1}.log".format(log_directory, application_name))
        file_handler.setLevel(log_level)
        file_handler.setFormatter(log_formatter)
        logger.addHandler(file_handler)

    return logger
