# Luma Cinema

Personal movie and series catalog for LG TV web browsers. Inspired by the supplied Bioscope app's feature structure; not an exact visual reproduction or a connection to its service.

## Start

Requires Python 3.9+ and no third-party Python packages.

```sh
python3 server.py
```

Open http://127.0.0.1:4173/admin on the server computer. Set an admin password of at least 12 characters. First-time setup is restricted to a loopback connection and localhost Host header. No default password is provided.

For a TV on the same trusted local network:

```sh
LUMA_HOST=0.0.0.0 python3 server.py
```

Open `http://<computer-LAN-IP>:4173/` in the TV browser. The server computer must stay awake and connected. Allow incoming access through the computer firewall if needed. Do not port-forward this development server onto the Internet. For Internet hosting, run behind HTTPS with persistent storage, set `LUMA_HTTPS=1`, and use a production reverse proxy/process supervisor. No Internet deployment is included.

## Admin workflow

1. Upload video to Cloudflare Stream separately.
2. Copy its playback Watch, iframe, or HLS URL, not the Cloudflare dashboard URL.
3. In `/admin`, enter the title and Stream playback URL.
4. Upload a JPG/PNG/WebP thumbnail (max 5 MB), paste its URL, or leave it blank to use the Stream thumbnail.
5. Choose Movie or Series episode. For series, enter a series name, season and episode number.
6. Save. Viewers reload the library to see changes.

Admin supports add, edit and remove. Removing an item does not delete its source video on Cloudflare. Viewer pages have no file upload or link entry controls. Favorites and playback progress are browser-local; the catalog and thumbnails are shared through the server.

## Data and security

SQLite catalog, salted scrypt password hash, and thumbnails are stored under `work/data/` by default. Back up this directory. Change it via `LUMA_DATA`. Never publish the data directory as static assets. Sessions are HttpOnly, SameSite=Strict and expire after 12 hours; restart requires signing in again. Admin writes require authentication and same-origin requests. Login attempts are rate limited. Set `LUMA_HTTPS=1` behind HTTPS to enable Secure cookies. The viewer catalog is accessible to anyone who can reach this server; viewer authentication is not implemented.

Local-network HTTP is intended for trusted private networks only. Public deployment needs HTTPS. `server.py` is a small self-hosted Python service, not a Cloudflare Worker. Cloudflare Stream hosts the video; it does not host this catalog backend automatically.

## Playback

Cloudflare watch/iframe links are normalized to the documented HLS manifest URL. hls.js is bundled; Safari/native HLS is used when supported. Direct HTTPS MP4/WebM/M3U8 URLs are also supported. Signed links can expire and must be replaced by the admin; automatic signing is not implemented. Cloudflare allowed origins must include the app origin if you restrict playback. DRM, offline downloads and video transcoding are not provided.

LG TV remote: arrows move focus, OK activates controls, Back closes a dialog or returns from player. Video has explicit play/pause, 10-second seek, fullscreen and next-episode buttons. Real LG model/firmware playback has not been verified.

## Validation

```sh
python3 -m unittest discover -s tests -v
node --check dist/app.js
node --check dist/admin.js
```

Tests use an isolated temporary database and cover authenticated CRUD, anonymous read-only access, origin rejection, setup rules, login/logout, thumbnail type restrictions and URL normalization. Browser verification covers login, publish/edit, viewer selection, favorites and HLS sample playback. Exact Bioscope visuals are unverified because no screen references were supplied.

## Sources

- https://developers.cloudflare.com/stream/viewing-videos/using-own-player/
- https://developers.cloudflare.com/stream/viewing-videos/displaying-thumbnails/
- https://github.com/video-dev/hls.js (Apache-2.0)
