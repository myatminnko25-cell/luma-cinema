
import os
import json
import secrets
import hashlib
import hmac
import time
import re
import mimetypes
import threading
from pathlib import Path
from urllib.parse import urlsplit, unquote, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie

ROOT = Path(__file__).resolve().parent

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    or os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
)
SUPABASE_BUCKET = os.environ.get("LUMA_SUPABASE_BUCKET", "luma-thumbnails").strip()

SESSIONS = {}
ATTEMPTS = {}
LOCK = threading.Lock()


class SupabaseError(RuntimeError):
    pass


def require_supabase_config():
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
