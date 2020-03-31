import logging
from logging.handlers import RotatingFileHandler


# loggers = {}
class LoggingUtil(object):
    """ Logging utility controlling format and setting initial logging level """

    @staticmethod
    def init_logging(name, level=logging.INFO, format='short', logFilePath=None, logFileLevel=None):
        logger = logging.getLogger(__name__)
        if not logger.parent.name == 'root':
            return logger

        FORMAT = {
            "short": '%(funcName)s: %(message)s',
            "medium": '%(funcName)s: %(asctime)-15s %(message)s',
            "long": '%(asctime)-15s %(filename)s %(funcName)s %(levelname)s: %(message)s'
        }[format]

        # create a stream handler (default to console)
        stream_handler = logging.StreamHandler()

        # create a formatter
        formatter = logging.Formatter(FORMAT)

        # set the formatter on the console stream
        stream_handler.setFormatter(formatter)

        # get the name of this logger
        logger = logging.getLogger(name)

        # set the logging level
        logger.setLevel(level)

        # if there was a file path passed in use it
        if logFilePath is not None:
            # create a rotating file handler, 100mb max per file with a max number of 10 files
            file_handler = RotatingFileHandler(filename=logFilePath + name + '.log', maxBytes=1000000, backupCount=10)

            # set the formatter
            file_handler.setFormatter(formatter)

            # if a log level for the file was passed in use it
            if logFileLevel is not None:
                level = logFileLevel

            # set the log level
            file_handler.setLevel(level)

            # add the handler to the logger
            logger.addHandler(file_handler)

        # add the console handler to the logger
        logger.addHandler(stream_handler)

        # return to the caller
        return logger


class Text:
    """ Utilities for processing text. """

    @staticmethod
    def get_curie(text):
        return text.upper().split(':', 1)[0] if ':' in text else None

    @staticmethod
    def un_curie(text):
        return ':'.join(text.split(':', 1)[1:]) if ':' in text else text

    @staticmethod
    def short(obj, limit=80):
        text = str(obj) if obj else None
        return (text[:min(len(text), limit)] + ('...' if len(text) > limit else '')) if text else None

    @staticmethod
    def path_last(text):
        return text.split('/')[-1:][0] if '/' in text else text

    @staticmethod
    def snakify(text):
        decomma = '_'.join(text.split(','))
        dedash = '_'.join(decomma.split('-'))
        resu = '_'.join(dedash.split())
        return resu

    @staticmethod
    def upper_curie(text):
        if ':' not in text:
            return text
        p = text.split(':', 1)
        return f'{p[0].upper()}:{p[1]}'