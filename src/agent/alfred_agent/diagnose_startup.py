import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Diagnostic")

logger.info(f"Python Version: {sys.version}")
logger.info("Step 1: Importing agent.py...")
try:
    import agent
    logger.info("SUCCESS: agent.py imported.")
except Exception as e:
    logger.error(f"FAILURE: Could not import agent.py: {e}", exc_info=True)

logger.info("Step 2: Initializing FastAPI...")
try:
    from fastapi import FastAPI
    app = FastAPI()
    logger.info("SUCCESS: FastAPI initialized.")
except Exception as e:
    logger.error(f"FAILURE: Could not initialize FastAPI: {e}", exc_info=True)

logger.info("Step 3: Port binding check (8080)...")
import socket
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    result = s.connect_ex(('127.0.0.1', 8080))
    if result == 0:
        logger.warning("PORT 8080 IS ALREADY IN USE.")
    else:
        logger.info("PORT 8080 IS FREE.")
