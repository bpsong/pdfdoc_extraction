import logging
import os

os.environ.setdefault('PREFECT_LOGGING_TO_API_ENABLED', 'false')
server_logger = logging.getLogger('prefect.server.api.server')
server_logger.disabled = True
server_logger.handlers.clear()
server_logger.propagate = False