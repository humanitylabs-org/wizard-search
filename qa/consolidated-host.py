#!/usr/bin/env python3
"""Isolated shell host: exact public shell static files, synthetic empty owner APIs only.
Never forwards a shell API to the owner's installation. Search APIs alone reach the candidate container.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import urllib.parse
import urllib.request
import urllib.error
import mimetypes

p=argparse.ArgumentParser();p.add_argument('--shell',type=Path,required=True);p.add_argument('--port',type=int,default=19771);p.add_argument('--app',default='http://127.0.0.1:19772');a=p.parse_args()
app={'id':'wizard-search','name':'Search','url':'/wizard-search/','view':{'mode':'original','url':'/wizard-search/'},'source':'synthetic-QA-registry','receives_voice_input':True,'provides':['web-search','image-search'],'type':'service'}
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send(self,code,data,ctype='application/json'):
  self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_GET(self):
  path=urllib.parse.urlsplit(self.path).path
  if path.startswith('/wizard-search/'):
   try:
    with urllib.request.urlopen(a.app+self.path[len('/wizard-search'):],timeout=90) as r:return self.send(r.status,r.read(),r.headers.get('Content-Type','application/json'))
   except urllib.error.HTTPError as e:return self.send(e.code,e.read())
  if path.startswith('/wizard-os-home/'):
   rel=urllib.parse.unquote(path[len('/wizard-os-home/'):]) or 'index.html';f=(a.shell/rel).resolve()
   if not f.is_relative_to(a.shell.resolve()) or not f.is_file():return self.send(404,b'{}')
   return self.send(200,f.read_bytes(),mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
  # Explicit synthetic shapes. No history, agents, recordings, Messenger or credentials are read.
  d={'apps':[app], 'in_development':[], 'agents':[], 'items':[], 'threads':[], 'sessions':[], 'events':[], 'pages':[], 'ok':True}
  if path.endswith('/agents'):d={'agents':[]}
  if 'launcher' in path:d={'links':[],'nativeLinks':[]}
  if path.endswith('/app-logos'):d={'logos':{}}
  return self.send(200,json.dumps(d).encode())
 def do_POST(self):return self.send(403,b'{"error":"synthetic_shell_read_only"}')
ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
