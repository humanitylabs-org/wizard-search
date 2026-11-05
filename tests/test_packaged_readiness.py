"""Regression coverage for retained HTTP failures and bounded real-search checks."""
import io
from email.message import Message
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'qa'))
from packaged_readiness import request_json, useful, wait_search

WEB={'source':'searxng','results':[{'title':'Python documentation','url':'https://docs.python.org/3/'}]}
IMAGES={'source':'searxng','images':[{'title':'Python logo','full':'https://www.python.org/logo.png','page':'https://www.python.org/'}]}

class PackagedReadinessTests(unittest.TestCase):
    def test_http_error_body_is_retained(self):
        error=urllib.error.HTTPError('http://example.invalid',502,'Bad Gateway',Message(),io.BytesIO(b'{"error":"RuntimeError"}'))
        with patch('urllib.request.urlopen',side_effect=error):
            result=request_json('http://example.invalid')
        self.assertEqual(result['status'],502)
        self.assertEqual(result['body_excerpt'],'{"error":"RuntimeError"}')

    def test_transient_failure_then_useful_web_and_images(self):
        responses=iter([{'status':502,'body_excerpt':'warming up'},{'status':200,'data':WEB},{'status':200,'data':IMAGES}])
        with tempfile.TemporaryDirectory() as directory:
            evidence=Path(directory)
            result=wait_search('http://example.invalid',evidence,request=lambda *a,**k:next(responses),sleep=lambda _:None)
            receipt=json.loads((evidence/'packaged-readiness.json').read_text())
            self.assertEqual(receipt['attempts'][0]['body_excerpt'],'warming up')
            self.assertEqual(set(result),{'web','images'})
            self.assertEqual(receipt['passed_kinds'],['images','web'])

    def test_no_results_never_passes_and_preserves_failure(self):
        calls=[]
        def request(*args,**kwargs):
            calls.append(args)
            return {'status':502,'body_excerpt':'provider down'}
        with tempfile.TemporaryDirectory() as directory:
            evidence=Path(directory)
            with self.assertRaisesRegex(RuntimeError,'web unavailable'):
                wait_search('http://example.invalid',evidence,request=request,sleep=lambda _:None)
            self.assertEqual(len(calls),3)
            self.assertFalse((evidence/'packaged-live-search.json').exists())
            self.assertEqual(len(json.loads((evidence/'packaged-readiness.json').read_text())['attempts']),3)

    def test_nonempty_but_invalid_or_unrelated_results_fail(self):
        for data in ({'source':'searxng','results':[{}]}, {'source':'fixture','results':WEB['results']},
                     {'source':'searxng','results':[{'title':'News','url':'https://example.com/'}]}):
            self.assertFalse(useful('web',data))
        self.assertTrue(useful('web',WEB));self.assertTrue(useful('images',IMAGES))
