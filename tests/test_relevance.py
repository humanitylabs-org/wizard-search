"""#72: off-topic and host-less rows never reach the page, junk engines are demoted, dictation punctuation goes."""
import importlib.util
import json
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('search_relevance', ROOT / 'server.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

# What the shipped SearXNG sidecar answered on a box with a flagged IP (shortened): Bing off topic,
# Brave host-less, Google CSE / Yahoo on topic.
YONEDA = [
    {'url': 'https://en.wikipedia.org/wiki/Yoneda_lemma', 'title': 'Yoneda lemma - Wikipedia', 'content': 'In mathematics, the Yoneda lemma is...', 'engines': ['google cse', 'yahoo']},
    {'url': 'https://comparethecity.com/compare-london-vs-moscow', 'title': 'London vs Moscow: Which City Is Better', 'content': 'Cost of living compared.', 'engines': ['bing']},
    {'url': 'http:///go/v1/AVJDROPcgH9Eawi7', 'title': 'Yoneda lemma - Wikipedia', 'content': '', 'engines': ['brave']},
    {'url': 'https://support.google.com/mail/answer/8494?hl=pt-BR', 'title': 'Fazer login no Gmail', 'content': 'Ajuda do Gmail', 'engines': ['yahoo']},
    {'url': 'https://ncatlab.org/nlab/show/Yoneda+lemma', 'title': 'nLab', 'content': 'category theory', 'engines': ['google cse']},
    {'url': 'https://www.pan.utiitsl.com/', 'title': 'PAN Card Services', 'content': 'Apply for PAN card online', 'engines': ['bing']},
    {'url': 'https://math.stackexchange.com/q/37165', 'title': 'Can someone explain the Yoneda Lemma?', 'content': '', 'engines': ['google cse', 'bing']},
]


def junk_for(q):
    return [{'url': 'https://www.wikipedia.org/', 'title': 'Wikipedia', 'content': 'The free encyclopedia', 'engines': ['bing']},
            {'url': 'https://www.change.org/', 'title': 'Change starts here', 'content': 'petitions', 'engines': ['bing']},
            {'url': 'https://example.org/' + urllib.parse.quote(q), 'title': q.title() + ' guide', 'content': 'All about ' + q, 'engines': ['google cse']},
            {'url': 'https://example.net/' + urllib.parse.quote(q), 'title': 'More on ' + q, 'content': q, 'engines': ['yahoo']}]


class FakeSearx:
    def __init__(self, answer):
        self.answer, self.queries = answer, []

    def __call__(self, req, timeout=0):
        url = getattr(req, 'full_url', req)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['q'][0]
        self.queries.append(q)
        body = json.dumps({'results': self.answer(q) if callable(self.answer) else self.answer}).encode()

        class R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return body
        return R()


class RelevanceTests(unittest.TestCase):
    def setUp(self):
        s.ENGINE_HEALTH.clear()
        self.env = patch.multiple(s, SEARXNG_URL='http://searx.invalid:8080', SOCKS='', BD_TOKEN='', FC_CLOUD_KEY='', FIRECRAWL_URL='')
        self.env.start()
        self.addCleanup(self.env.stop)

    def search(self, answer, q):
        fake = FakeSearx(answer)
        with patch.object(s.urllib.request, 'urlopen', fake):
            return s.web_search(s.norm_q(q)), fake

    def test_searxng_rows_off_topic_and_hostless_dropped(self):
        out, _ = self.search(YONEDA, 'Yoneda lemma')
        self.assertEqual(out['source'], 'searxng')
        self.assertEqual([r['url'] for r in out['results']], [
            'https://en.wikipedia.org/wiki/Yoneda_lemma', 'https://ncatlab.org/nlab/show/Yoneda+lemma',
            'https://math.stackexchange.com/q/37165'])
        self.assertTrue(all(r['host'] for r in out['results']))

    def test_dictation_full_stop_stripped_before_searching(self):
        self.assertEqual(s.norm_q('  Yoneda   lemma. '), 'Yoneda lemma')
        self.assertEqual(s.norm_q('is it raining?!'), 'is it raining')
        self.assertEqual(s.norm_q('node.js'), 'node.js')
        _, fake = self.search(YONEDA, 'Yoneda lemma.')
        self.assertEqual(fake.queries, ['Yoneda lemma'])

    def test_lenient_per_row(self):
        # Long questions keep a row that names one content word (wizard-os#616); 3-6 word searches need two.
        q = 'What are the most primitive systems that exert or exhibit a Markov blanket?'
        self.assertTrue(s._on_topic(q, {'title': 'Markov blanket - Wikipedia', 'snippet': '', 'url': 'https://x.org/a'}))
        self.assertFalse(s._on_topic('how to change a bike tire', {'title': 'CHANGE | meaning', 'snippet': 'Cambridge Dictionary', 'url': 'https://dictionary.cambridge.org/change'}))
        self.assertTrue(s._on_topic('how to change a bike tire', {'title': 'How to Remove a Bicycle Tire', 'snippet': 'Fix a flat on your bike', 'url': 'https://y.org/'}))
        self.assertTrue(s._on_topic('COP31 climate summit news', {'title': 'COP 31 | UNFCCC', 'snippet': 'climate change conference', 'url': 'https://unfccc.int/event/cop-31'}))
        self.assertTrue(s._on_topic('Lisboa', {'title': 'Lisbôa', 'snippet': '', 'url': 'https://z.pt/'}))
        self.assertTrue(s._on_topic('東京 天気', {'title': '東京の天気', 'snippet': '', 'url': 'https://tenki.jp/'}))
        self.assertTrue(s._on_topic('?!', {'title': 'anything', 'snippet': '', 'url': 'https://a.b/'}))

    def test_junk_engine_demoted_then_recovers(self):
        for q in ('how to boil an egg', 'bike tire', 'sourdough starter', 'tax return deadline'):
            out, _ = self.search(junk_for, q)
        self.assertEqual(s.demoted_engines(), ['bing'])
        self.assertEqual(out['demoted'], ['bing'])
        # A demoted engine's on-topic row is held back unless a healthy engine returned the same page.
        answer = [{'url': 'https://bing-only.example/tide', 'title': 'Tide tables', 'content': 'tide', 'engines': ['bing']},
                  {'url': 'https://both.example/tide', 'title': 'Tide times', 'content': 'tide', 'engines': ['bing', 'yahoo']}]
        out, _ = self.search(answer, 'tide')
        self.assertEqual([r['url'] for r in out['results']], ['https://both.example/tide'])
        for q in ('alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta', 'iota', 'kappa', 'lambda', 'omicron'):
            self.search(lambda q: [{'url': 'https://bing.example/' + q, 'title': q, 'content': q, 'engines': ['bing']}], q)
        self.assertEqual(s.demoted_engines(), [])

    def test_only_junk_falls_through_to_next_lane(self):
        cloud = [{'url': 'https://cloud.example/yoneda', 'title': 'Yoneda lemma explained', 'snippet': ''}]
        junk = [x for x in YONEDA if x['engines'] == ['bing'] or x['url'].startswith('http:///')]
        with patch.object(s, 'FC_CLOUD_KEY', 'x'), patch.object(s, '_cloud', lambda q: cloud):
            out, _ = self.search(junk, 'Yoneda lemma')
        self.assertEqual((out['source'], [r['url'] for r in out['results']]), ('cloud', ['https://cloud.example/yoneda']))

    def test_only_junk_and_no_other_lane_is_no_results_not_junk(self):
        # The provider answered, so the page says "No web results", not "provider unavailable".
        junk = [x for x in YONEDA if x['engines'] == ['bing']]
        out, _ = self.search(junk, 'Yoneda lemma')
        self.assertEqual((out['source'], out['results']), ('searxng', []))

    def test_provider_down_is_still_an_error(self):
        with self.assertRaises(RuntimeError):
            self.search([], 'Yoneda lemma')

    def test_overview_answers_from_the_model_when_nothing_is_on_topic(self):
        asked = []

        def fake_llm(req, timeout=0):
            body = json.loads(req.data)
            asked.append(body['messages'][1]['content'])

            class R:
                def __enter__(self): return self
                def __exit__(self, *a): return False
                def read(self): return json.dumps({'choices': [{'message': {'content': 'The Yoneda lemma says...'}}]}).encode()
            return R()
        with patch.multiple(s, LLM_URL='http://llm.invalid/v1/chat/completions', TINFOIL_KEY='x',
                            web_search=lambda q: {'q': q, 'source': 'searxng', 'results': []},
                            WEB_CACHE=s.TTLCache(10, 60), OVR_CACHE=s.TTLCache(10, 60)), \
                patch.object(s.urllib.request, 'urlopen', fake_llm):
            out = s.overview('Yoneda lemma')
        self.assertEqual((out['answer'], out['sources']), ('The Yoneda lemma says...', []))
        self.assertTrue(asked and asked[0].startswith('Query: Yoneda lemma'))

    def test_demoted_rows_are_the_last_resort(self):
        s.ENGINE_HEALTH['bing'] = [True] * 5
        answer = [{'url': 'https://bing-only.example/tide', 'title': 'Tide tables', 'content': 'tide', 'engines': ['bing']}]
        out, _ = self.search(answer, 'tide')
        self.assertEqual([r['url'] for r in out['results']], ['https://bing-only.example/tide'])

    def test_other_lanes_drop_off_topic_and_hostless_rows(self):
        rows = [{'url': 'https://a.example/x', 'title': 'Yoneda lemma', 'snippet': ''},
                {'url': 'https://b.example/', 'title': 'PAN Card Services', 'snippet': ''},
                {'url': 'http:///go/v1/abc', 'title': 'Yoneda lemma', 'snippet': ''}]
        with patch.multiple(s, SEARXNG_URL='', FC_CLOUD_KEY='x', _cloud=lambda q: [dict(r) for r in rows]):
            out = s.web_search('Yoneda lemma')
        self.assertEqual([r['url'] for r in out['results']], ['https://a.example/x'])
        self.assertNotIn('demoted', out)


if __name__ == '__main__':
    unittest.main()
