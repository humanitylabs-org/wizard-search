"""Regression coverage for the live Search union; no real inference in unit tests."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(**env):
    with patch.dict(os.environ, {"WIZARD_SEARCH_BASE": "", "TINFOIL_PROXY_URL": "", "TINFOIL_API_KEY": "", "TINFOIL_API_KEY_FILE": "", **env}):
        spec = importlib.util.spec_from_file_location("search_consolidation", ROOT / "server.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class ConsolidationTests(unittest.TestCase):
    def test_empty_legacy_form_does_not_disable_app_discovery(self):
        m = load(WIZARD_SEARCH_TINFOIL_APP="")
        self.assertEqual(m.TINFOIL_APP, "http://wizard-tinfoil:18804")

    def test_box_local_credential_file_and_missing_file_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            token = Path(temp) / "app-token"
            m = load(TINFOIL_PROXY_URL="http://wizard-tinfoil:18804/v1/chat/completions", TINFOIL_API_KEY_FILE=str(token))
            self.assertIsNone(m.llm())
            token.write_text("synthetic-internal-token\n")
            self.assertEqual(m.llm()["key"], "synthetic-internal-token")
            body = json.loads(m._overview_request("test", [], True).data)
            self.assertEqual(body["model"], "gpt-oss-120b")
            self.assertEqual(body["reasoning_effort"], "low")
            self.assertTrue(body["stream"])
            self.assertNotIn("synthetic-internal-token", json.dumps(m.configuration()))
            token.unlink()
            self.assertIsNone(m.llm())

    def test_translation_private_fallback_and_failure(self):
        m = load(TINFOIL_PROXY_URL="http://localhost:1/v1/chat/completions")
        with patch.object(m, "_llm", side_effect=[RuntimeError("primary failed"), '{"from":"French","items":["Hello"]}']) as call:
            self.assertEqual(m.translate_items(["Bonjour"])["items"], ["Hello"])
            self.assertEqual([c.args[0] for c in call.call_args_list], ["gemma4-31b", "gpt-oss-120b"])
        with patch.object(m, "_llm", side_effect=RuntimeError("unreachable")):
            with self.assertRaisesRegex(RuntimeError, "translate failed"):
                m.translate_items(["Au revoir"])

    def test_read_image_success_and_failure(self):
        m = load(TINFOIL_PROXY_URL="http://localhost:1/v1/chat/completions")
        with patch.object(m, "_llm", return_value='{"lines":["SEARCH QA"]}') as call:
            self.assertEqual(m.read_image(b"synthetic-image", "image/png")["lines"], ["SEARCH QA"])
            self.assertEqual(call.call_args.args[0], "gemma4-31b")
        with patch.object(m, "_llm", side_effect=RuntimeError("vision unavailable")):
            with self.assertRaises(RuntimeError):
                m.read_image(b"synthetic-image", "image/png")

    def test_read_image_default_reply_and_prompt_unchanged(self):
        m = load(TINFOIL_PROXY_URL="http://localhost:1/v1/chat/completions")
        with patch.object(m, "_llm", return_value='{"lines":["SEARCH QA"]}') as call:
            out = m.read_image(b"synthetic-image", "image/png")
        self.assertNotIn("boxes", out)
        self.assertEqual(call.call_args.args[1][0]["content"], m.READ_IMAGE_SYSTEM)
        self.assertEqual(call.call_args.args[2], 4000)

    def test_read_image_geometry_same_model_validated_boxes(self):
        m = load(TINFOIL_PROXY_URL="http://localhost:1/v1/chat/completions")
        reply = json.dumps({"lines": [
            {"text": "SYNTHETIC ONE", "box": [100, 200, 600, 250]},
            {"text": "  SYNTHETIC   TWO ", "box": [10, 20, 30]},        # wrong arity
            {"text": "SYNTHETIC THREE", "box": [900, 10, 100, 40]},     # right before left
            {"text": "SYNTHETIC FOUR", "box": [0, 0, 1001, 50]},        # outside the image
            {"text": "SYNTHETIC FIVE", "box": [True, 0, 50, 50]},       # not numbers
            {"text": "SYNTHETIC SIX"},                                  # no box at all
            {"text": "", "box": [1, 1, 50, 50]},                        # empty text is not a line
            "SYNTHETIC SEVEN",                                          # plain line, no geometry
        ]})
        with patch.object(m, "_llm", return_value=reply) as call:
            out = m.read_image(b"synthetic-image", "image/png", geometry=True)
        self.assertEqual(call.call_args.args[0], "gemma4-31b")
        self.assertEqual(call.call_args.args[1][0]["content"], m.READ_IMAGE_BOXES_SYSTEM)
        self.assertEqual(out["lines"], ["SYNTHETIC ONE", "SYNTHETIC TWO", "SYNTHETIC THREE", "SYNTHETIC FOUR",
                                        "SYNTHETIC FIVE", "SYNTHETIC SIX", "SYNTHETIC SEVEN"])
        self.assertEqual(out["boxes"], [[0.1, 0.2, 0.6, 0.25], None, None, None, None, None, None])
        self.assertEqual(len(out["boxes"]), len(out["lines"]))

    def test_read_image_geometry_route_flag(self):
        m = load(TINFOIL_PROXY_URL="http://localhost:1/v1/chat/completions")
        seen = []
        with patch.object(m, "llm", return_value={"url": "x"}), \
                patch.object(m, "read_image", side_effect=lambda b, mime, g: seen.append(g) or {"lines": []}):
            for path, want in (("/api/read-image", False), ("/api/read-image?geometry=1", True),
                               ("/api/read-image?geometry=yes", False)):  # load() clears the base path
                h = m.H.__new__(m.H)
                h.path, h.command = path, "POST"
                h.headers = {"Content-Length": "4", "Content-Type": "image/jpeg"}
                h.rfile = __import__("io").BytesIO(b"\xff\xd8\xff\xd9")
                sent = []
                h._json = lambda code, obj: sent.append((code, obj))
                h.do_POST()
                self.assertEqual(sent[-1][0], 200)
                self.assertEqual(seen[-1], want)

    def test_voice_identity_and_shared_paths_retained(self):
        voice = (ROOT / "web/voice-input.js").read_text()
        self.assertIn("indexedDB.open('wizard-search-voice:' + scope, 1)", voice)
        app = (ROOT / "web/app.js").read_text()
        for token in ("WizardApp.media.view", "WizardApp.back.register", "SearchVoiceInput?.register", "TINFOIL = '/wizard-tinfoil/'"):
            self.assertIn(token, app)
        self.assertNotIn("haiku", (ROOT / "server.py").read_text().lower())


if __name__ == "__main__":
    unittest.main()
