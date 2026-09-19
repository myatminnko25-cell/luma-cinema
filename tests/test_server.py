import os,sys,tempfile,threading,unittest,json,urllib.request,urllib.error,http.cookiejar
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
TEMP=tempfile.TemporaryDirectory();os.environ['LUMA_DATA']=TEMP.name
import server
class AppTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
  threading.Thread(target=cls.http.serve_forever,daemon=True).start();cls.base='http://127.0.0.1:'+str(cls.http.server_port)
  cls.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 @classmethod
 def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();TEMP.cleanup()
 def call(self,path,method='GET',data=None,client=None,origin=None,raw=False):
  body=data if raw else json.dumps(data).encode() if data is not None else None
  req=urllib.request.Request(self.base+path,data=body,method=method,headers={'Origin':origin or self.base,'Content-Type':'application/octet-stream' if raw else 'application/json'})
  try:r=(client or self.client).open(req)
  except urllib.error.HTTPError as e:r=e
  return r.status,json.loads(r.read())
 def test_full_admin_and_viewer_flow(self):
  anonymous=urllib.request.build_opener()
  self.assertEqual(self.call('/api/videos','POST',{},anonymous)[0],401)
  self.assertEqual(self.call('/api/setup','POST',{'password':'short'})[0],400)
  self.assertEqual(self.call('/api/setup','POST',{'password':'test-password-long'})[0],200)
  self.assertEqual(self.call('/api/setup','POST',{'password':'other-password-long'})[0],409)
  self.assertEqual(self.call('/api/videos','POST',{},origin='https://evil.example')[0],403)
  item={'name':'Test movie','url':'https://customer-example.cloudflarestream.com/abc123/iframe','kind':'movie'}
  code,v=self.call('/api/videos','POST',item);self.assertEqual(code,201)
  self.assertEqual(v['url'],'https://customer-example.cloudflarestream.com/abc123/manifest/video.m3u8')
  self.assertIn('/thumbnails/',v['thumbnail'])
  self.assertEqual(self.call('/api/videos',client=anonymous)[1][0]['name'],'Test movie')
  item.update(name='Edited movie',thumbnail='javascript:alert(1)');self.assertEqual(self.call('/api/videos/'+v['id'],'PUT',item)[0],400)
  item['thumbnail']='';self.assertEqual(self.call('/api/videos/'+v['id'],'PUT',item)[0],200)
  self.assertEqual(self.call('/api/thumbnails','POST',b'<svg/>',raw=True)[0],400)
  self.assertEqual(self.call('/api/thumbnails','POST',b'\x89PNG\r\n\x1a\nfixture',raw=True)[0],201)
  self.assertEqual(self.call('/api/videos/'+v['id'],'DELETE')[0],200)
  self.assertEqual(self.call('/api/videos')[1],[])
  self.assertEqual(self.call('/api/logout','POST',{})[0],200)
  self.assertEqual(self.call('/api/videos','POST',item)[0],401)
  self.assertEqual(self.call('/api/login','POST',{'password':'wrong'})[0],401)
  self.assertEqual(self.call('/api/login','POST',{'password':'test-password-long'})[0],200)
 def test_stream_normalization(self):
  for suffix in ('watch','iframe','manifest/video.m3u8'):
   self.assertEqual(server.stream_url('https://customer-x.cloudflarestream.com/abc/'+suffix),'https://customer-x.cloudflarestream.com/abc/manifest/video.m3u8')
  self.assertEqual(server.stream_url('https://watch.cloudflarestream.com/abc'),'https://videodelivery.net/abc/manifest/video.m3u8')
  self.assertEqual(server.stream_url('https://streamtape.com/v/abc1234/test.mp4'),'https://streamtape.com/e/abc1234')
  self.assertEqual(server.stream_url('https://streamtape.to/e/abc1234'),'https://streamtape.com/e/abc1234')
  self.assertEqual(server.stream_url('https://lulustream.com/e/xyz5678'),'https://lulustream.com/e/xyz5678')
  self.assertEqual(server.stream_url('https://lulustream.com/d/xyz5678'),'https://lulustream.com/e/xyz5678')
  self.assertEqual(server.stream_url('https://iframe.mediadelivery.net/play/12345/vid67890'),'https://iframe.mediadelivery.net/embed/12345/vid67890')
  self.assertEqual(server.stream_url('https://vz-abc123.b-cdn.net/vid67890/playlist.m3u8'),'https://vz-abc123.b-cdn.net/vid67890/playlist.m3u8')
  self.assertEqual(server.stream_url('https://vz-abc123.b-cdn.net/vid67890'),'https://vz-abc123.b-cdn.net/vid67890/playlist.m3u8')
  self.assertEqual(server.auto_thumbnail('https://vz-abc123.b-cdn.net/vid67890/playlist.m3u8'),'https://vz-abc123.b-cdn.net/vid67890/thumbnail.jpg')
  for bad in ['javascript:alert(1)','http://test/video.mp4','https://dash.cloudflare.com/abc','https://youtube.com/watch?v=abc']:
   with self.assertRaises(ValueError):server.stream_url(bad)
if __name__=='__main__':unittest.main()
