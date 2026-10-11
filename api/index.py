import os
import sys

# Ensure root directory is in sys.path so 'jh' package is importable
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from jh import db
from jh.httpd import Handler

# Ensure database tables exist in the writable runtime environment (/tmp)
try:
    db.init_db()
except Exception:
    pass

class handler(Handler):
    """Vercel Serverless Function entrypoint."""
    pass
