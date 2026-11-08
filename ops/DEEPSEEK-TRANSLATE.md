# Orb Translate on deepseek-v4-1-flash (8 Nov 2026)

Reading (`/api/read-image`) and translating (`/api/translate`) use `deepseek-v4-1-flash` via the private Tinfoil proxy, with
`chat_template_kwargs {"thinking": false}` (otherwise it thinks ~2000 tokens, 6 s median). Fallback for translate stays `gpt-oss-120b`.
Synthetic benchmark (6 Nov): read 1.95 s vs 2.95 s, CER 0.003 vs 0.014, translate 0.85 s vs 1.16 s.
Revert without code: set `WIZARD_TRANSLATE_MODEL` and `WIZARD_VISION_MODEL` back to `gemma4-31b` (update-config).
The host bridge `ops/private-proxy-bridge.py` allowlist now includes `deepseek-v4-1-flash`; restart `wizard-search-private-proxy.service` after changing it.

## Reading falls back to gemma4-31b (8 Nov 2026)
`/api/read-image` retries once on `gemma4-31b` (code default, `WIZARD_VISION_FALLBACK`) when the DeepSeek read errors, times out (40 s)
or returns no usable line; the response `model` names the model that answered. Both are approved private Tinfoil models on the same bridge allowlist.
Thinking-off check through the Search route (bridge): `completion_tokens_details.reasoning_tokens` is 0 with `chat_template_kwargs {"thinking": false}`.
