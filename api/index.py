import os
import sys

# Set up paths for Vercel serverless environment
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app.server import Handler, init_db

# Initialize database connections on cold start
try:
    init_db()
except Exception as e:
    pass

class handler(Handler):
    pass
