#!/usr/bin/env python3
"""Forum-only bridge protocol test on the candidate's disposable Docker bridge.
Synthetic upstream only; real PRIVATE inference evidence is recorded separately.
"""
import argparse,json,os,pathlib,secrets,subprocess,sys,tempfile,threading,time,urllib.request,urllib.error
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
p=argparse.ArgumentParser();p.add_argument('--bind',required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args()
class Fixture(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  assert self.headers.get('Authorization')=='Bearer '+upstream_token
  assert self.headers.get('Authorization')!='Bearer '+token
  j=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
  self.wfile.write(b'data: {"fixture":1}\n\n');self.wfile.flush();time.sleep(.4)
  self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
up=ThreadingHTTPServer(('127.0.0.1',0),Fixture);threading.Thread(target=up.serve_forever,daemon=True).start()
root=pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(dir=root) as temp:
 token=secrets.token_urlsafe(48);f=pathlib.Path(temp)/'token';f.write_text(token);os.chmod(f,0o600)
 upstream_token=secrets.token_urlsafe(48);uf=pathlib.Path(temp)/'upstream-token';uf.write_text(upstream_token);os.chmod(uf,0o600)
 # Dedicated test port; the user-facing release uses a different fixed port.
 port=19339
 proc=subprocess.Popen([sys.executable,str(root/'ops/private-proxy-bridge.py'),'--bind',a.bind,'--port',str(port),'--token-file',str(f),'--upstream-token-file',str(uf),'--upstream',f'http://127.0.0.1:{up.server_port}/v1/chat/completions'])
 url=f'http://{a.bind}:{port}/v1/chat/completions'
 def request(token_value=token,model='gpt-oss-120b',**headers):
  return urllib.request.urlopen(urllib.request.Request(url,data=json.dumps({'model':model,'messages':[{'role':'user','content':'synthetic fixture'}],'stream':True,'reasoning_effort':'low'}).encode(),headers={'Authorization':'Bearer '+token_value,'Content-Type':'application/json',**headers}),timeout=5)
 try:
  for i in range(40):
   try:
    request('wrong')
   except urllib.error.HTTPError as e:
    assert e.code==401;break
   except OSError:
    if i==39:raise
    time.sleep(.05)
  checks=[]
  for kwargs,status in [({'token_value':'wrong'},401),({'model':'non-private-model'},400),({'Origin':'https://elsewhere.invalid'},403)]:
   try:request(**kwargs);raise AssertionError('should reject')
   except urllib.error.HTTPError as e:assert e.code==status;checks.append(status)
  start=time.monotonic()
  with request() as r:first=r.readline();first_ms=round((time.monotonic()-start)*1000);rest=r.read();total_ms=round((time.monotonic()-start)*1000)
  assert b'fixture' in first and b'[DONE]' in rest and first_ms<300 and total_ms>=350
  result={'fixture_only':True,'auth_rejected':checks,'separate_upstream_authorization':True,'first_line_ms':first_ms,'total_ms':total_ms,'no_buffering':True}
  a.out.write_text(json.dumps(result,indent=2));print(json.dumps(result))
 finally:proc.terminate();proc.wait(timeout=5);up.shutdown()
