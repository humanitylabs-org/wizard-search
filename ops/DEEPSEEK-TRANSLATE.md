# Orb Translate on deepseek-v4-1-flash (8 Nov 2026)

Reading (`/api/read-image`) and translating (`/api/translate`) use `deepseek-v4-1-flash` via the private Tinfoil proxy, with
`chat_template_kwargs {"thinking": false}` (otherwise it thinks ~2000 tokens, 6 s median). Fallback for translate stays `gpt-oss-120b`.
Synthetic benchmark (6 Nov): read 1.95 s vs 2.95 s, CER 0.003 vs 0.014, translate 0.85 s vs 1.16 s.
Revert without code: set `WIZARD_TRANSLATE_MODEL` and `WIZARD_VISION_MODEL` back to `gemma4-31b` (update-config).
The host bridge `ops/private-proxy-bridge.py` allowlist now includes `deepseek-v4-1-flash`; restart `wizard-search-private-proxy.service` after changing it.
