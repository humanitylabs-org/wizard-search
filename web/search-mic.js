/* Search bar microphone (switch search-bar-mic, wizard-search#29). Tap to listen, tap again to search.
 * The microphone is Wizard's shared capture (WizardApp.capture) and the words come from the box's own speech-to-text:
 * through the shell when Search is open inside Wizard, or the same system route (WizConfig.transcribe) when Search runs
 * as its own installed app. There is deliberately no browser speech-recognition fallback. */
(() => {
  'use strict';
  const HOME = '/wizard-os-home/core/', MAX_MS = 30000;
  const loads = {};
  // Standalone pages load the shared capture resource and system config on demand (inside Wizard the shell has them).
  const load = name => loads[name] ||= new Promise((resolve, reject) => {
    const el = document.createElement('script');
    el.src = HOME + name;
    el.onload = resolve;
    el.onerror = () => { delete loads[name]; reject(new Error('Wizard voice could not load here')); };
    document.head.append(el);
  });
  // Top-level page = Search installed as its own app (or a plain tab); a frame = inside Wizard, where the shell serves voice.
  const standalone = () => window.parent === window;
  async function prepare() {
    if (!standalone()) return;
    if (!window.WizAppCapture) await load('app-capture.js');
    if (!window.WizConfig) await load('config.js');
  }
  async function transcribe(blob) {
    if (!standalone()) {
      const r = await WizardApp.voice.transcribe(blob);
      if (r?.unavailable) throw new Error('Voice is not set up on this Wizard');
      return String(r?.text || '').trim();
    }
    await prepare();
    await window.WizConfig.ready;
    const r = await window.WizConfig.transcribe(blob, { prompt: window.WizConfig.voicePrompt?.() || '' });
    return String(r?.text || '').trim();
  }

  window.SearchMic = { register({ button, run, feedback }) {
    if (!button || !window.WizardApp?.capture?.start) return null;
    let phase = 'idle', session = null, timer = 0;
    const paint = () => {
      button.dataset.phase = phase;
      button.setAttribute('aria-pressed', String(phase === 'listening'));
      button.setAttribute('aria-label', phase === 'listening' ? 'Stop and search' : 'Search by voice');
      button.disabled = phase === 'starting' || phase === 'working';
    };
    const reset = message => { clearTimeout(timer); session = null; phase = 'idle'; paint(); feedback(message || ''); };
    async function start() {
      phase = 'starting'; paint(); feedback('Starting the microphone…');
      try {
        await prepare();
        session = await WizardApp.capture.start({ kind: 'audio', maxMs: MAX_MS + 5000, meta: { purpose: 'search-query' } });
      } catch (e) { return reset((e.message || 'Microphone unavailable') + '. Type your search instead.'); }
      phase = 'listening'; paint(); feedback('Listening… tap the mic again to search.');
      timer = setTimeout(stop, MAX_MS);
    }
    async function stop() {
      if (phase !== 'listening' || !session) return;
      clearTimeout(timer); const s = session; phase = 'working'; paint(); feedback('Working out what you said…');
      let take;
      try { take = await s.stop(); }
      catch (e) { return reset((e.message || 'Recording failed') + '. Tap the mic to try again.'); }
      try {
        const text = await transcribe(take.blob);
        if (!text) return reset('No speech heard. Tap the mic and try again.');
        reset(); run(text.slice(0, 300));
      } catch (e) { reset((e.message || 'Speech-to-text failed') + '. Tap the mic to try again, or type.'); }
      finally { if (take?.id) WizardApp.capture.ack(take.id).catch(() => {}); }
    }
    button.addEventListener('click', () => { if (phase === 'idle') start(); else if (phase === 'listening') stop(); });
    button.hidden = false; paint();
    if (standalone()) prepare().catch(() => {}); // warm up so the first tap starts listening at once
    return {
      busy: () => phase !== 'idle',
      // Back while listening cancels the take; it never leaves Search.
      cancel() { const s = session; if (phase === 'listening' && s) { s.cancel().catch(() => {}); reset('Voice search cancelled.'); } return true; },
    };
  } };
})();
