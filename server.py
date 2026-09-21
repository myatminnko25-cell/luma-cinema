#!/usr/bin/env python3
"""Luma personal cinema: Render-friendly server using Supabase for persistence.

Required environment variables on Render:
  SUPABASE_URL=https://YOUR_PROJECT.supabase.co
  SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVER_ONLY_KEY

Optional:
  LUMA_SUPABASE_BUCKET=luma-thumbnails
  LUMA_ADMIN_PASSWORD=your-admin-password
  LUMA_HTTPS=1
  LUMA_HOST=0.0.0.0
  LUMA_PORT=4173

The service-role/secret key must NEVER be exposed in browser JavaScript.
"""

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
        raise RuntimeError(
            "Missing Render environment variable(s): " + ", ".join(missing)
        )


def _supabase_request(
    method,
    path,
    *,
    json_data=None,
    raw_data=None,
    content_type=None,
    prefer=None,
    timeout=25,
):
    """Call Supabase REST/Storage APIs using only the Python standard library."""
    require_supabase_config()

    url = SUPABASE_URL + path
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
    }

    body = None
    if json_data is not None:
        body = json.dumps(json_data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif raw_data is not None:
        body = raw_data
        if content_type:
            headers["Content-Type"] = content_type

    if prefer:
        headers["Prefer"] = prefer

    req = Request(url, data=body, headers=headers, method=method)

    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
            response_type = resp.headers.get("Content-Type", "")
            if not payload:
                return None
            if "application/json" in response_type:
                return json.loads(payload.decode("utf-8"))
            return payload
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise SupabaseError(
            f"Supabase HTTP {exc.code}: {details[:1000]}"
        ) from exc
    except URLError as exc:
        raise SupabaseError(f"Cannot reach Supabase: {exc.reason}") from exc


def get_videos():
    rows = _supabase_request(
        "GET", "/rest/v1/videos?select=*&order=created.desc"
    )
    return rows or []


def get_video(video_id):
    safe_id = quote(video_id, safe="")
    rows = _supabase_request(
        "GET", f"/rest/v1/videos?id=eq.{safe_id}&select=*&limit=1"
    )
    return rows[0] if rows else None


def insert_video(video):
    rows = _supabase_request(
        "POST",
        "/rest/v1/videos",
        json_data=video,
        prefer="return=representation",
    )
    return rows[0] if rows else video


def update_video(video_id, video):
    safe_id = quote(video_id, safe="")
    rows = _supabase_request(
        "PATCH",
        f"/rest/v1/videos?id=eq.{safe_id}",
        json_data=video,
        prefer="return=representation",
    )
    return rows or []


def delete_video(video_id):
    safe_id = quote(video_id, safe="")
    rows = _supabase_request(
        "DELETE",
        f"/rest/v1/videos?id=eq.{safe_id}",
        prefer="return=representation",
    )
    return rows or []


def get_password():
    rows = _supabase_request(
        "GET", "/rest/v1/settings?key=eq.password&select=value&limit=1"
    )
    return rows[0]["value"] if rows else None


def save_password_record(record, ignore_existing=False):
    prefer = "return=minimal"
    path = "/rest/v1/settings"
    if ignore_existing:
        path += "?on_conflict=key"
        prefer = "resolution=ignore-duplicates,return=minimal"
    _supabase_request(
        "POST",
        path,
        json_data={"key": "password", "value": record},
        prefer=prefer,
    )


def storage_upload(name, content, content_type):
    bucket = quote(SUPABASE_BUCKET, safe="")
    obj = quote(name, safe="")
    # Supabase Storage upload endpoint. x-upsert=false prevents accidental overwrite.
    require_supabase_config()
    url = SUPABASE_URL + f"/storage/v1/object/{bucket}/{obj}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": content_type,
        "x-upsert": "false",
    }
    req = Request(url, data=content, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=30) as resp:
            resp.read()
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise SupabaseError(
            f"Supabase Storage HTTP {exc.code}: {details[:1000]}"
        ) from exc
    except URLError as exc:
        raise SupabaseError(f"Cannot reach Supabase Storage: {exc.reason}") from exc


def storage_download(name):
    bucket = quote(SUPABASE_BUCKET, safe="")
    obj = quote(name, safe="")
    return _supabase_request(
        "GET", f"/storage/v1/object/authenticated/{bucket}/{obj}"
    )


def seed_from_static_if_empty():
    """Import dist/api/videos.json once, only when the Supabase table is empty."""
    try:
        existing = _supabase_request(
            "GET", "/rest/v1/videos?select=id&limit=1"
        )
        if existing:
            return

        seed_file = ROOT / "dist" / "api" / "videos.json"
        if not seed_file.is_file():
            return

        raw_items = json.loads(seed_file.read_text(encoding="utf-8"))
        if not isinstance(raw_items, list):
            return

        for item in raw_items:
            if not isinstance(item, dict):
                continue
            try:
                row = {
                    "id": str(item.get("id") or secrets.token_hex(12))[:64],
                    "name": str(item.get("name", "")).strip()[:100],
                    "url": str(item.get("url", "")),
                    "thumbnail": str(item.get("thumbnail", "")),
                    "kind": str(item.get("kind", "movie")),
                    "series": str(item.get("series", ""))[:100],
                    "season": int(item.get("season", 1)),
                    "episode": int(item.get("episode", 1)),
                    "description": str(item.get("description", ""))[:2000],
                    "created": float(item.get("created", time.time())),
                }
                if row["name"] and row["url"]:
                    insert_video(row)
            except Exception:
                pass
    except Exception as exc:
        print(f"Luma seed warning: {exc}", flush=True)


def password_record(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1
    ).hex()
    return salt + ":" + digest


def password_check(password, record):
    salt, digest = record.split(":")
    candidate = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1
    ).hex()
    return hmac.compare_digest(candidate, digest)


def https_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("Link is too long.")
    u = urlsplit(value.strip())
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise ValueError("HTTPS link ထည့်ပါ။")
    return value.strip()


def stream_url(value):
    value = https_url(value)
    u = urlsplit(value)
    host = u.hostname.lower()

    if host == "watch.cloudflarestream.com":
        parts = u.path.strip("/").split("/")
        if len(parts) != 1 or not re.fullmatch(r"[a-zA-Z0-9_.-]+", parts[0]):
            raise ValueError("Cloudflare Stream playback link ထည့်ပါ။")
        return "https://videodelivery.net/" + parts[0] + "/manifest/video.m3u8"

    if host.endswith(".cloudflarestream.com") or host in (
        "videodelivery.net",
        "iframe.videodelivery.net",
    ):
        parts = u.path.strip("/").split("/")
        if not parts[0]:
            raise ValueError("Video ID ပါတဲ့ link ထည့်ပါ။")
        if len(parts) == 1 or parts[1] in ("watch", "iframe", "manifest"):
            host = "videodelivery.net" if host == "iframe.videodelivery.net" else host
            return (
                "https://"
                + host
                + "/"
                + parts[0]
                + "/manifest/video.m3u8"
                + ("?" + u.query if u.query else "")
            )

    streamtape_hosts = (
        "streamtape.com",
        "streamtape.to",
        "streamta.pe",
        "streamtape.net",
        "streamtape.xyz",
    )
    if any(host == d or host.endswith("." + d) for d in streamtape_hosts):
        parts = u.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] in ("v", "e"):
            return f"https://streamtape.com/e/{parts[1]}"
        if len(parts) == 1 and parts[0]:
            return f"https://streamtape.com/e/{parts[0]}"
        raise ValueError(
            "Streamtape video link မမှန်ပါ။ (ဥပမာ: https://streamtape.com/e/...)"
        )

    lulu_hosts = ("lulustream.com", "luluvdo.com")
    if any(host == d or host.endswith("." + d) for d in lulu_hosts):
        parts = u.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] in ("e", "d"):
            return f"https://{host}/e/{parts[1]}"
        if len(parts) == 1 and parts[0]:
            return f"https://{host}/e/{parts[0]}"
        raise ValueError(
            "LuluStream video link မမှန်ပါ။ (ဥပမာ: https://lulustream.com/e/...)"
        )

    if (
        host.endswith(".mediadelivery.net")
        or host.endswith(".b-cdn.net")
        or host.endswith(".bunnycdn.com")
    ):
        parts = u.path.strip("/").split("/")
        if host.endswith(".mediadelivery.net") or host.endswith(".bunnycdn.com"):
            if len(parts) >= 3 and parts[0] in ("embed", "play"):
                return f"https://iframe.mediadelivery.net/embed/{parts[1]}/{parts[2]}"
            if len(parts) >= 2 and parts[0] in ("embed", "play"):
                return f"https://iframe.mediadelivery.net/embed/{parts[1]}"
        if re.search(r"\.(m3u8|mp4|webm|m4v)$", u.path, re.I):
            return value
        if len(parts) >= 1 and parts[0] and host.endswith(".b-cdn.net"):
            return f"https://{host}/{parts[0]}/playlist.m3u8"
        return value

    if re.search(r"/(?:e|embed)/[a-zA-Z0-9_-]+", u.path):
        return value

    if not re.search(r"\.(mp4|webm|m4v|m3u8)$", u.path, re.I):
        raise ValueError(
            "Bunny Stream / Streamtape / LuluStream / Cloudflare Stream သို့မဟုတ် MP4/M3U8 link ထည့်ပါ။"
        )
    return value


def auto_thumbnail(url):
    u = urlsplit(url)
    if u.hostname and (
        u.hostname.endswith(".cloudflarestream.com")
        or u.hostname == "videodelivery.net"
    ):
        return (
            u.scheme
            + "://"
            + u.netloc
            + "/"
            + u.path.strip("/").split("/")[0]
            + "/thumbnails/thumbnail.jpg?time=1s&height=480"
        )
    if u.hostname and u.hostname.endswith(".b-cdn.net"):
        parts = u.path.strip("/").split("/")
        if parts and parts[0]:
            return f"{u.scheme}://{u.netloc}/{parts[0]}/thumbnail.jpg"
    return ""


def validate_video(d):
    name = str(d.get("name", "")).strip()[:100]
    if not name:
        raise ValueError("Video နာမည် ဖြည့်ပါ။")

    url = stream_url(d.get("url", ""))
    kind = d.get("kind", "movie")
    if kind not in ("movie", "series"):
        raise ValueError("Invalid category.")

    thumb = str(d.get("thumbnail", "")).strip()
    if thumb and not re.fullmatch(r"/uploads/[a-f0-9]{32}\.(jpg|png|webp)", thumb):
        thumb = https_url(thumb)

    series = str(d.get("series", "")).strip()[:100]
    if kind == "series" and not series:
        raise ValueError("Series နာမည် ဖြည့်ပါ။")

    season = int(d.get("season", 1))
    episode = int(d.get("episode", 1))
    if not 1 <= season <= 999 or not 1 <= episode <= 9999:
        raise ValueError("Season / episode နံပါတ်ကို စစ်ပါ။")

    return dict(
        name=name,
        url=url,
        thumbnail=thumb or auto_thumbnail(url),
        kind=kind,
        series=series if kind == "series" else "",
        season=season,
        episode=episode,
        description=str(d.get("description", ""))[:2000],
    )


def sync_static_videos():
    """Keep existing frontend compatibility if it reads dist/api/videos.json."""
    try:
        p = ROOT / "dist" / "api"
        p.mkdir(parents=True, exist_ok=True)
        rows = get_videos()
        (p / "videos.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        print(f"Luma sync warning: {exc}", flush=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "Luma"

    def log_message(self, fmt, *args):
        pass

    def respond(self, status, data, headers=None):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def auth(self):
        try:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            token = cookie["luma_session"].value
            with LOCK:
                expiry = SESSIONS.get(token, 0)
                if expiry < time.time():
                    SESSIONS.pop(token, None)
                    return False
            return True
        except (KeyError, ValueError):
            return False

    def body(self, limit=16384):
        n = int(self.headers.get("Content-Length", "0"))
        if n < 1 or n > limit:
            raise ValueError("Request size invalid.")
        return self.rfile.read(n)

    def json_body(self):
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise ValueError("JSON required.")
        d = json.loads(self.body())
        if not isinstance(d, dict):
            raise ValueError("Invalid object.")
        return d

    def origin_ok(self):
        origin = self.headers.get("Origin", "")
        host = self.headers.get("Host", "")
        return bool(
            origin
            and urlsplit(origin).netloc == host
            and urlsplit(origin).scheme in ("http", "https")
        )

    def local(self):
        return self.client_address[0] in ("127.0.0.1", "::1") and self.headers.get(
            "Host", ""
        ).split(":")[0] in ("localhost", "127.0.0.1")

    def do_GET(self):
        path = urlsplit(self.path).path

        try:
            if path == "/api/session":
                pwd = get_password()
                return self.respond(
                    200,
                    dict(
                        authenticated=self.auth(),
                        needsSetup=not bool(pwd),
                        canSetup=not bool(pwd) or self.local(),
                    ),
                )

            if path == "/api/videos":
                return self.respond(200, get_videos())

            if path.startswith("/api/"):
                return self.respond(404, {"error": "Not found"})

            if path.startswith("/uploads/"):
                name = path.removeprefix("/uploads/")
                if not re.fullmatch(r"[a-f0-9]{32}\.(jpg|png|webp)", name):
                    return self.respond(404, {"error": "Not found"})
                try:
                    data = storage_download(name)
                except SupabaseError:
                    return self.respond(404, {"error": "Not found"})
                if not isinstance(data, (bytes, bytearray)):
                    return self.respond(404, {"error": "Not found"})
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    mimetypes.guess_type(name)[0] or "application/octet-stream",
                )
                self.send_header("Content-Length", str(len(data)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(data)
                return

            rel = (
                "admin.html"
                if path in ("/admin", "/admin/")
                else "index.html"
                if path == "/"
                else unquote(path).lstrip("/")
            )
            file = (ROOT / "dist" / rel).resolve()
            if not file.is_relative_to((ROOT / "dist").resolve()):
                return self.respond(404, {"error": "Not found"})
            if not file.is_file():
                return self.respond(404, {"error": "Not found"})

            data = file.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type",
                mimetypes.guess_type(file.name)[0] or "application/octet-stream",
            )
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

        except SupabaseError as exc:
            print(f"Luma Supabase error: {exc}", flush=True)
            return self.respond(503, {"error": "Database unavailable. Please retry."})
        except Exception as exc:
            print(f"Luma GET error: {exc}", flush=True)
            return self.respond(500, {"error": "Server error. Please retry."})

    def do_POST(self):
        self.mutate("POST")

    def do_PUT(self):
        self.mutate("PUT")

    def do_DELETE(self):
        self.mutate("DELETE")

    def mutate(self, method):
        path = urlsplit(self.path).path

        try:
            if not self.origin_ok():
                return self.respond(403, {"error": "Origin rejected."})

            if path in ("/api/login", "/api/setup") and method == "POST":
                d = self.json_body()
                password = d.get("password", "")
                if not isinstance(password, str) or len(password) > 200:
                    raise ValueError("Invalid password.")

                if path == "/api/setup":
                    if bool(get_password()):
                        return self.respond(409, {"error": "Admin already configured."})
                    if len(password) < 12:
                        raise ValueError("Password အနည်းဆုံး 12 လုံး ထည့်ပါ။")
                    save_password_record(password_record(password))
                else:
                    now = time.time()
                    ip = self.client_address[0]
                    with LOCK:
                        failures = [
                            t for t in ATTEMPTS.get(ip, []) if t > now - 300
                        ]
                        ATTEMPTS[ip] = failures
                        if len(failures) >= 10:
                            return self.respond(
                                429, {"error": "5 မိနစ်နောက် ပြန်စမ်းပါ။"}
                            )

                    record = get_password()
                    if not record or not password_check(password, record):
                        with LOCK:
                            ATTEMPTS[ip].append(now)
                        return self.respond(401, {"error": "Password မမှန်ပါ။"})

                    with LOCK:
                        ATTEMPTS.pop(ip, None)

                token = secrets.token_urlsafe(32)
                with LOCK:
                    SESSIONS[token] = time.time() + 43200

                secure = (
                    "; Secure"
                    if os.environ.get("LUMA_HTTPS") == "1"
                    or self.headers.get("X-Forwarded-Proto") == "https"
                    else ""
                )
                return self.respond(
                    200,
                    {"ok": True},
                    {
                        "Set-Cookie": "luma_session="
                        + token
                        + "; HttpOnly; SameSite=Lax; Path=/; Max-Age=43200"
                        + secure
                    },
                )

            if not self.auth():
                return self.respond(401, {"error": "Admin login လိုပါတယ်။"})

            if path == "/api/logout" and method == "POST":
                cookie = SimpleCookie(self.headers.get("Cookie", ""))
                with LOCK:
                    SESSIONS.pop(cookie["luma_session"].value, None)
                return self.respond(
                    200,
                    {"ok": True},
                    {
                        "Set-Cookie": "luma_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"
                    },
                )

            if path == "/api/thumbnails" and method == "POST":
                content = self.body(5 * 1024 * 1024)
                ext = (
                    "png"
                    if content.startswith(b"\x89PNG\r\n\x1a\n")
                    else "jpg"
                    if content.startswith(b"\xff\xd8\xff")
                    else "webp"
                    if content[:4] == b"RIFF" and content[8:12] == b"WEBP"
                    else None
                )
                if not ext:
                    raise ValueError("JPG, PNG သို့မဟုတ် WebP ပုံကိုပဲ တင်ပါ။")

                name = secrets.token_hex(16) + "." + ext
                content_type = {
                    "jpg": "image/jpeg",
                    "png": "image/png",
                    "webp": "image/webp",
                }[ext]
                storage_upload(name, content, content_type)
                return self.respond(201, {"url": "/uploads/" + name})

            if path == "/api/videos" and method == "POST":
                d = validate_video(self.json_body())
                d["id"] = secrets.token_hex(12)
                d["created"] = time.time()
                saved = insert_video(d)
                sync_static_videos()
                return self.respond(201, saved)

            match = re.fullmatch(r"/api/videos/([a-f0-9]{24})", path)
            if match and method in ("PUT", "DELETE"):
                video_id = match[1]

                if method == "DELETE":
                    rows = delete_video(video_id)
                else:
                    d = validate_video(self.json_body())
                    rows = update_video(video_id, d)

                if not rows:
                    return self.respond(404, {"error": "Video not found."})

                sync_static_videos()
                return self.respond(200, {"ok": True})

            return self.respond(404, {"error": "Not found"})

        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            return self.respond(400, {"error": str(exc)})
        except SupabaseError as exc:
            print(f"Luma Supabase error: {exc}", flush=True)
            return self.respond(503, {"error": "Database unavailable. Please retry."})
        except Exception as exc:
            print(f"Luma server error: {exc}", flush=True)
            return self.respond(500, {"error": "Server error. Please retry."})


def initialize():
    require_supabase_config()

    # If Render has an admin password env var, save it only when no password exists yet.
    env_password = os.environ.get("LUMA_ADMIN_PASSWORD")
    if env_password and not get_password():
        if len(env_password) < 12:
            raise RuntimeError("LUMA_ADMIN_PASSWORD must be at least 12 characters.")
        save_password_record(password_record(env_password), ignore_existing=True)

    seed_from_static_if_empty()
    sync_static_videos()


if __name__ == "__main__":
    initialize()
    host = os.environ.get("LUMA_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("LUMA_PORT", "4173")))
    print("Luma: http://" + host + ":" + str(port), flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
