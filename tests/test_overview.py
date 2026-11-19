"""wizard-search#50: a plain question whose first results don't answer it gets one rewritten retry;
when that also fails the box is hidden ("no answer") instead of saying "The sources do not provide an answer"."""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('search_ov', ROOT / 'server.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

DO_PAGES = [{'url': f'https://dict.example/do{i}', 'title': f'DO definition {i}', 'host': 'dict.example',
             'snippet': 'do: to perform an action'} for i in range(8)]
QA_PAGES = [{'url': 'https://jobs.example/qa', 'title': 'QA job titles', 'host': 'jobs.example',
             'snippet': 'A person who does QA is called a QA tester, QA analyst or QA engineer.'}]


class FakeLLM:
    """Answers the overview from whatever sources it is given; rewrites questions to a fixed query."""
    def __init__(self, rewrite='QA job title', refusal='NO_ANSWER'):
        self.rewrite, self.refusal, self.calls = rewrite, refusal, []

    def reply(self, body):
        system = body['messages'][0]['content']
        user = body['messages'][1]['content']
        if system == s.REWRITE_SYSTEM:
            self.calls.append(('rewrite', user))
            return self.rewrite
        self.calls.append(('answer', user))
        return 'Someone who does QA is a QA tester or QA analyst [1].' if 'QA tester' in user else self.refusal

    def __call__(self, req, timeout=0):
        body = json.loads(req.data)
        text = self.reply(body)
        if body.get('stream'):
            chunks = [text[i:i + 4] for i in range(0, len(text), 4)]
            lines = [('data: ' + json.dumps({'choices': [{'delta': {'content': c}}]}) + '\n').encode() for c in chunks]
            lines.append(b'data: [DONE]\n')
            return _Resp(lines)
        return _Resp([json.dumps({'choices': [{'message': {'content': text}}]}).encode()])


class _Resp(io.BytesIO):
    def __init__(self, lines):
        super().__init__(b''.join(lines))
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)


def fake_web(q):
    return {'q': q, 'source': 'fake', 'results': QA_PAGES if 'job' in q.lower() else DO_PAGES}


class OverviewTests(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(s, 'LLM_URL', 'http://llm.invalid/v1/chat/completions'),
                        patch.object(s, 'web_search', fake_web),
                        patch.object(s, 'WEB_CACHE', s.TTLCache(100, 60)), patch.object(s, 'OVR_CACHE', s.TTLCache(100, 60))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def stream(self, q):
        events = []
        s.overview_stream(q, lambda ev, data: events.append((ev, data)))
        return events

    def test_plain_question_retries_with_rewritten_query(self):
        fake = FakeLLM()
        with patch.object(s.urllib.request, 'urlopen', fake):
            d = s.overview('What do you call someone who does QA')
        self.assertIn('QA tester', d['answer'])
        self.assertEqual(d['sources'][0]['url'], 'https://jobs.example/qa')
        self.assertEqual([c[0] for c in fake.calls], ['answer', 'rewrite', 'answer'])

    def test_stream_never_shows_the_refusal_and_answers_after_retry(self):
        fake = FakeLLM()
        with patch.object(s.urllib.request, 'urlopen', fake):
            events = self.stream('What do you call someone who does QA')
        shown = ''.join(d['t'] for ev, d in events if ev == 'delta')
        self.assertNotIn('NO_ANSWER', shown)
        self.assertIn('QA tester', shown)
        self.assertEqual([ev for ev, _ in events].count('sources'), 2)
        self.assertEqual(events[-1][0], 'done')
        self.assertEqual(events[-1][1].get('error', ''), '')

    def test_nonsense_query_hides_the_box(self):
        fake = FakeLLM(rewrite='zxqv blorp', refusal='The sources do not provide an answer.')
        with patch.object(s.urllib.request, 'urlopen', fake):
            events = self.stream('zxqv blorp wibble')
            plain = s.overview('zxqv blorp wibble again')
        self.assertEqual(''.join(d['t'] for ev, d in events if ev == 'delta'), '')
        self.assertEqual(events[-1][1]['error'], 'no answer')
        self.assertEqual(events[-1][1]['answer'], '')
        self.assertEqual((plain['answer'], plain['error']), ('', 'no answer'))
        # cached second look: still no box
        with patch.object(s.urllib.request, 'urlopen', fake):
            again = self.stream('zxqv blorp wibble')
        self.assertEqual(again[-1][1]['error'], 'no answer')

    def test_good_answer_streams_without_retry(self):
        fake = FakeLLM()
        with patch.object(s.urllib.request, 'urlopen', fake):
            events = self.stream('QA job title')
        self.assertIn('QA tester', ''.join(d['t'] for ev, d in events if ev == 'delta'))
        self.assertEqual([c[0] for c in fake.calls], ['answer'])

    def test_no_answer_detection(self):
        for t in ('NO_ANSWER', ' no_answer.', 'The sources do not provide an answer.', "The provided sources don't say.", ''):
            self.assertTrue(s._is_no_answer(t), t)
        self.assertFalse(s._is_no_answer('The sources do not agree on a date, but most say 1912 [1][2]. ' * 4))
        self.assertFalse(s._is_no_answer('A QA analyst tests software [1].'))
        self.assertFalse(s._may_be_no_answer('A QA analyst'))
        self.assertTrue(s._may_be_no_answer('The sour'))
        self.assertTrue(s._may_be_no_answer('NO_A'))

    def test_rewrite_falls_back_to_dropping_filler_words(self):
        def broken(req, timeout=0):
            raise OSError('model down')
        with patch.object(s.urllib.request, 'urlopen', broken):
            self.assertEqual(s._rewrite_query('What do you call someone who does QA'), 'call someone QA')


if __name__ == '__main__':
    unittest.main()
