#!/usr/bin/env python3
"""Luma personal cinema: standard-library server with SQLite catalog and admin sessions."""
import os,json,sqlite3,secrets,hashlib,hmac,time,re,mimetypes,ipaddress,threading
from pathlib import Path
from urllib.parse import urlsplit,unquote
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from http.cookies import SimpleCookie
ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('LUMA_DATA',ROOT/'work'/'data'));DATA.mkdir(parents=True,exist_ok=True)
UPLOADS=DATA/'thumbnails';UPLOADS.mkdir(exist_ok=True)
DB=DATA/'library.sqlite3'
SESSIONS={};ATTEMPTS={};LOCK=threading.Lock()
def db():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c
with db() as c:
 c.executescript('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS videos(id TEXT PRIMARY KEY,name TEXT NOT NULL,url TEXT NOT NULL,thumbnail TEXT NOT NULL,kind TEXT NOT NULL,series TEXT NOT NULL,season INTEGER NOT NULL,episode INTEGER NOT NULL,description TEXT NOT NULL,created REAL NOT NULL);')
 try:
  seed_file=ROOT/'dist'/'api'/'videos.json'
  if c.execute('SELECT COUNT(*) FROM videos').fetchone()[0]==0 and seed_file.is_file():
   for item in json.loads(seed_file.read_text(encoding='utf-8')):
    c.execute('INSERT OR IGNORE INTO videos VALUES(?,?,?,?,?,?,?,?,?,?)',(item['id'],item['name'],item['url'],item['thumbnail'],item['kind'],item.get('series',''),item.get('season',1),item.get('episode',1),item.get('description',''),item.get('created',time.time())))
 except Exception:pass
def password_record(password):
 salt=secrets.token_hex(16);return salt+':'+hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
def password_check(password,record):
 salt,digest=record.split(':');return hmac.compare_digest(hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex(),digest)
def get_password():
 with db() as c:
  row=c.execute("SELECT value FROM settings WHERE key='password'").fetchone();return row[0] if row else None
if os.environ.get('LUMA_ADMIN_PASSWORD') and not get_password():
 with db() as c:c.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',('password',password_record(os.environ['LUMA_ADMIN_PASSWORD'])))
def https_url(value):
 if not isinstance(value,str) or len(value)>4096:raise ValueError('Link is too long.')
 u=urlsplit(value.strip())
 if u.scheme!='https' or not u.hostname or u.username or u.password:raise ValueError('HTTPS link ထည့်ပါ။')
 return value.strip()
def stream_url(value):
 value=https_url(value);u=urlsplit(value);host=u.hostname.lower()
 if host=='watch.cloudflarestream.com':
  parts=u.path.strip('/').split('/')
  if len(parts)!=1 or not re.fullmatch(r'[a-zA-Z0-9_.-]+',parts[0]):raise ValueError('Cloudflare Stream playback link ထည့်ပါ။')
  return 'https://videodelivery.net/'+parts[0]+'/manifest/video.m3u8'
 if host.endswith('.cloudflarestream.com') or host in ('videodelivery.net','iframe.videodelivery.net'):
  parts=u.path.strip('/').split('/')
  if not parts[0]:raise ValueError('Video ID ပါတဲ့ link ထည့်ပါ။')
  if len(parts)==1 or parts[1] in ('watch','iframe','manifest'):
   host='videodelivery.net' if host=='iframe.videodelivery.net' else host
   return 'https://'+host+'/'+parts[0]+'/manifest/video.m3u8'+('?'+u.query if u.query else '')
 streamtape_hosts = ('streamtape.com', 'streamtape.to', 'streamta.pe', 'streamtape.net', 'streamtape.xyz')
 if any(host == d or host.endswith('.' + d) for d in streamtape_hosts):
  parts=u.path.strip('/').split('/')
  if len(parts)>=2 and parts[0] in ('v','e'):
   return f'https://streamtape.com/e/{parts[1]}'
  if len(parts)==1 and parts[0]:
   return f'https://streamtape.com/e/{parts[0]}'
  raise ValueError('Streamtape video link မမှန်ပါ။ (ဥပမာ: https://streamtape.com/e/...)')
 lulu_hosts = ('lulustream.com', 'luluvdo.com')
 if any(host == d or host.endswith('.' + d) for d in lulu_hosts):
  parts=u.path.strip('/').split('/')
  if len(parts)>=2 and parts[0] in ('e','d'):
   return f'https://{host}/e/{parts[1]}'
  if len(parts)==1 and parts[0]:
   return f'https://{host}/e/{parts[0]}'
  raise ValueError('LuluStream video link မမှန်ပါ။ (ဥပမာ: https://lulustream.com/e/...)')
 if host.endswith('.mediadelivery.net') or host.endswith('.b-cdn.net') or host.endswith('.bunnycdn.com'):
  parts=u.path.strip('/').split('/')
  if host.endswith('.mediadelivery.net') or host.endswith('.bunnycdn.com'):
   if len(parts)>=3 and parts[0] in ('embed','play'):
    return f'https://iframe.mediadelivery.net/embed/{parts[1]}/{parts[2]}'
   if len(parts)>=2 and parts[0] in ('embed','play'):
    return f'https://iframe.mediadelivery.net/embed/{parts[1]}'
  if re.search(r'\.(m3u8|mp4|webm|m4v)$',u.path,re.I):
   return value
  if len(parts)>=1 and parts[0] and host.endswith('.b-cdn.net'):
   return f'https://{host}/{parts[0]}/playlist.m3u8'
  return value
 if re.search(r'/(?:e|embed)/[a-zA-Z0-9_-]+', u.path):
  return value
 if not re.search(r'\.(mp4|webm|m4v|m3u8)$',u.path,re.I):raise ValueError('Bunny Stream / Streamtape / LuluStream / Cloudflare Stream သို့မဟုတ် MP4/M3U8 link ထည့်ပါ။')
 return value
def auto_thumbnail(url):
 u=urlsplit(url)
 if u.hostname and (u.hostname.endswith('.cloudflarestream.com') or u.hostname=='videodelivery.net'):
  return u.scheme+'://'+u.netloc+'/'+u.path.strip('/').split('/')[0]+'/thumbnails/thumbnail.jpg?time=1s&height=480'
 if u.hostname and u.hostname.endswith('.b-cdn.net'):
  parts=u.path.strip('/').split('/')
  if parts and parts[0]:
   return f'{u.scheme}://{u.netloc}/{parts[0]}/thumbnail.jpg'
 return ''
def validate_video(d):
 name=str(d.get('name','')).strip()[:100]
 if not name:raise ValueError('Video နာမည် ဖြည့်ပါ။')
 url=stream_url(d.get('url',''));kind=d.get('kind','movie')
 if kind not in ('movie','series'):raise ValueError('Invalid category.')
 thumb=d.get('thumbnail','').strip()
 if thumb and not re.fullmatch(r'/uploads/[a-f0-9]{32}\.(jpg|png|webp)',thumb):thumb=https_url(thumb)
 series=str(d.get('series','')).strip()[:100]
 if kind=='series' and not series:raise ValueError('Series နာမည် ဖြည့်ပါ။')
 season=int(d.get('season',1));episode=int(d.get('episode',1))
 if not 1<=season<=999 or not 1<=episode<=9999:raise ValueError('Season / episode နံပါတ်ကို စစ်ပါ။')
 return dict(name=name,url=url,thumbnail=thumb or auto_thumbnail(url),kind=kind,series=series if kind=='series' else '',season=season,episode=episode,description=str(d.get('description',''))[:2000])
def sync_static_videos():
 try:
  p=ROOT/'dist'/'api';p.mkdir(parents=True,exist_ok=True)
  with db() as c:rows=[dict(r) for r in c.execute('SELECT * FROM videos ORDER BY created DESC')]
  (p/'videos.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 except Exception:pass
class Handler(BaseHTTPRequestHandler):
 server_version='Luma'
 def log_message(self,fmt,*args):pass
 def respond(self,status,data,headers=None):
  body=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(body)))
  for k,v in (headers or {}).items():self.send_header(k,v)
  self.end_headers();self.wfile.write(body)
 def auth(self):
  try:
   cookie=SimpleCookie(self.headers.get('Cookie',''));token=cookie['luma_session'].value
   with LOCK:
    expiry=SESSIONS.get(token,0)
    if expiry<time.time():SESSIONS.pop(token,None);return False
   return True
  except (KeyError,ValueError):return False
 def body(self,limit=16384):
  n=int(self.headers.get('Content-Length','0'))
  if n<1 or n>limit:raise ValueError('Request size invalid.')
  return self.rfile.read(n)
 def json_body(self):
  if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON required.')
  d=json.loads(self.body())
  if not isinstance(d,dict):raise ValueError('Invalid object.')
  return d
 def origin_ok(self):
  origin=self.headers.get('Origin','');host=self.headers.get('Host','')
  return bool(origin and urlsplit(origin).netloc==host and urlsplit(origin).scheme in ('http','https'))
 def local(self):
  return self.client_address[0] in ('127.0.0.1','::1') and self.headers.get('Host','').split(':')[0] in ('localhost','127.0.0.1')
 def do_GET(self):
  path=urlsplit(self.path).path
  if path=='/api/session':return self.respond(200,dict(authenticated=self.auth(),needsSetup=not bool(get_password()),canSetup=not bool(get_password()) or self.local()))
  if path=='/api/videos':
   with db() as c:rows=[dict(r) for r in c.execute('SELECT * FROM videos ORDER BY created DESC')]
   return self.respond(200,rows)
  if path.startswith('/api/'):return self.respond(404,{'error':'Not found'})
  if path.startswith('/uploads/'):
   name=path.removeprefix('/uploads/')
   if not re.fullmatch(r'[a-f0-9]{32}\.(jpg|png|webp)',name):return self.respond(404,{'error':'Not found'})
   file=UPLOADS/name
  else:
   rel='admin.html' if path in ('/admin','/admin/') else 'index.html' if path=='/' else unquote(path).lstrip('/')
   file=(ROOT/'dist'/rel).resolve()
   if not file.is_relative_to((ROOT/'dist').resolve()):return self.respond(404,{'error':'Not found'})
  if not file.is_file():return self.respond(404,{'error':'Not found'})
  data=file.read_bytes();self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(file.name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(len(data)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Cache-Control','no-cache');self.end_headers();self.wfile.write(data)
 def do_POST(self):self.mutate('POST')
 def do_PUT(self):self.mutate('PUT')
 def do_DELETE(self):self.mutate('DELETE')
 def mutate(self,method):
  path=urlsplit(self.path).path
  try:
   if not self.origin_ok():return self.respond(403,{'error':'Origin rejected.'})
   if path in ('/api/login','/api/setup') and method=='POST':
    d=self.json_body();password=d.get('password','')
    if not isinstance(password,str) or len(password)>200:raise ValueError('Invalid password.')
    if path=='/api/setup':
     if bool(get_password()):return self.respond(409,{'error':'Admin already configured.'})
     if len(password)<12:raise ValueError('Password အနည်းဆုံး 12 လုံး ထည့်ပါ။')
     with db() as c:
      result=c.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',('password',password_record(password)))
      if not result.rowcount:return self.respond(409,{'error':'Admin already configured.'})
    else:
     now=time.time();ip=self.client_address[0]
     with LOCK:
      failures=[t for t in ATTEMPTS.get(ip,[]) if t>now-300];ATTEMPTS[ip]=failures
      if len(failures)>=10:return self.respond(429,{'error':'5 မိနစ်နောက် ပြန်စမ်းပါ။'})
     record=get_password()
     if not record or not password_check(password,record):
      with LOCK:ATTEMPTS[ip].append(now)
      return self.respond(401,{'error':'Password မမှန်ပါ။'})
     with LOCK:ATTEMPTS.pop(ip,None)
    token=secrets.token_urlsafe(32)
    with LOCK:SESSIONS[token]=time.time()+43200
    secure='; Secure' if os.environ.get('LUMA_HTTPS')=='1' or self.headers.get('X-Forwarded-Proto')=='https' else ''
    return self.respond(200,{'ok':True},{'Set-Cookie':'luma_session='+token+'; HttpOnly; SameSite=Lax; Path=/; Max-Age=43200'+secure})
   if not self.auth():return self.respond(401,{'error':'Admin login လိုပါတယ်။'})
   if path=='/api/logout' and method=='POST':
    cookie=SimpleCookie(self.headers.get('Cookie',''))
    with LOCK:SESSIONS.pop(cookie['luma_session'].value,None)
    return self.respond(200,{'ok':True},{'Set-Cookie':'luma_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0'})
   if path=='/api/thumbnails' and method=='POST':
    content=self.body(5*1024*1024)
    ext='png' if content.startswith(b'\x89PNG\r\n\x1a\n') else 'jpg' if content.startswith(b'\xff\xd8\xff') else 'webp' if content[:4]==b'RIFF' and content[8:12]==b'WEBP' else None
    if not ext:raise ValueError('JPG, PNG သို့မဟုတ် WebP ပုံကိုပဲ တင်ပါ။')
    name=secrets.token_hex(16)+'.'+ext;(UPLOADS/name).write_bytes(content)
    return self.respond(201,{'url':'/uploads/'+name})
   if path=='/api/videos' and method=='POST':
    d=validate_video(self.json_body());d['id']=secrets.token_hex(12);d['created']=time.time()
    with db() as c:c.execute('INSERT INTO videos('+','.join(d)+') VALUES('+','.join('?' for _ in d)+')',tuple(d.values()))
    sync_static_videos()
    return self.respond(201,d)
   match=re.fullmatch(r'/api/videos/([a-f0-9]{24})',path)
   if match and method in ('PUT','DELETE'):
    with db() as c:
     if method=='DELETE':result=c.execute('DELETE FROM videos WHERE id=?',(match[1],))
     else:
      d=validate_video(self.json_body());result=c.execute('UPDATE videos SET '+','.join(k+'=?' for k in d)+' WHERE id=?',(*d.values(),match[1]))
     if not result.rowcount:return self.respond(404,{'error':'Video not found.'})
    sync_static_videos()
    return self.respond(200,{'ok':True})
   return self.respond(404,{'error':'Not found'})
  except (ValueError,TypeError,KeyError,json.JSONDecodeError) as e:return self.respond(400,{'error':str(e)})
  except Exception:return self.respond(500,{'error':'Server error. Please retry.'})
if __name__=='__main__':
 sync_static_videos()
 host=os.environ.get('LUMA_HOST','0.0.0.0')
 port=int(os.environ.get('PORT', os.environ.get('LUMA_PORT','4173')))
 print('Luma: http://'+host+':'+str(port),flush=True)
 ThreadingHTTPServer((host,port),Handler).serve_forever()
