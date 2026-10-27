/* Wizard Search: private web + image search with an AI overview. Opens in Wizard's link sheet. */
(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const BASE = location.pathname.replace(/[^/]*$/, '');
  const api = (p, q) => fetch(`${BASE}api/${p}?q=${encodeURIComponent(q)}`, { credentials: 'same-origin' }).then(r => r.ok ? r.json() : r.json().then(j => Promise.reject(new Error(j.error || r.status))));
  const S = { q: '', tab: 'all', images: null, web: null, ov: null, seq: 0 };
  // Search owns its result viewer; shared Back owns the exit boundary.
  const shellViewer = () => null;
  const setupText = 'Setup required — configure this capability using the setup instructions above.';
  const configReady = fetch(`${BASE}api/config`).then(r => { if (!r.ok) throw new Error('config'); return r.json(); }).then(d => {
    S.config = d;
    const missing = Object.entries(d.capabilities).filter(([, enabled]) => !enabled).map(([name]) => name);
    $('#setup-status').textContent = d.state === 'setup_required' ? 'Setup required: connect a search provider.' : missing.length ? `Optional setup: ${missing.join(', ')} unavailable.` : 'Search providers configured.';
    // Optional extras (e.g. AI overview) stay quiet: only a box with no search provider at all shows setup.
    $('#setup').hidden = d.state !== 'setup_required';
    $('#ov').hidden = !d.capabilities.overview;
    if (!window.WizardApp) { $('#setup').hidden = false; $('#setup-status').textContent = 'Wizard shared client missing. Configure /wizard-os-home/core/app-client.js at the gateway.'; }
    return d;
  }).catch(() => { $('#setup-status').textContent = 'Configuration check failed. Reload to retry.'; return null; });

  // Optional AI overviews: only offered when the Tinfoil app is on this box. Turning on asks Tinfoil (sibling app,
  // same origin, owner's page) for a Search-only token and hands it to Search's server; Turn off revokes it.
  const TINFOIL = new URL('../wizard-tinfoil/', location.href).pathname;
  const post = (url, body) => fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-Wizard-Request': '1' }, body: JSON.stringify(body) })
    .then(r => r.json().then(j => r.ok ? j : Promise.reject(new Error(j.error || r.status))));
  function paintAi(p) {
    const on = p.mode !== 'off', t = p.tinfoil || {};
    $('#ai').hidden = !(on || t.installed);
    $('#ai-btn').hidden = p.mode === 'proxy' || (!on && !t.connected);
    $('#ai-btn').textContent = on ? 'Turn off' : 'Turn on';
    $('#ai-btn').setAttribute('aria-pressed', String(on));
    $('#ai-sub').textContent = p.mode === 'proxy' ? 'On · set up by your server admin.' : on ? `On · private answers from Tinfoil (${p.model}).`
      : t.connected ? 'A short private answer above your results, from Tinfoil. Uses your Tinfoil credit.' : 'Connect Tinfoil in the Tinfoil app first, then turn this on here.';
    if (S.config) { S.config.capabilities.overview = on && S.config.state !== 'setup_required'; $('#ov').hidden = !S.config.capabilities.overview; }
  }
  const aiReady = configReady.then(() => fetch(`${BASE}api/overview-provider`).then(r => r.json())).then(paintAi).catch(() => {});
  $('#ai-btn').addEventListener('click', async () => {
    const b = $('#ai-btn'), on = b.getAttribute('aria-pressed') === 'true'; b.disabled = true;
    try {
      if (on) {
        paintAi(await post(`${BASE}api/overview-provider`, { provider: 'off' }));
        post(`${TINFOIL}api/app-tokens/remove`, { app: 'wizard-search' }).catch(() => {});
      } else {
        const g = await post(`${TINFOIL}api/app-tokens`, { app: 'wizard-search' });
        paintAi(await post(`${BASE}api/overview-provider`, { provider: 'tinfoil', token: g.token, models: g.models, recommended: g.recommended }));
      }
    } catch (e) { $('#ai-sub').textContent = `Could not change AI overviews (${e.message}). Check the Tinfoil app and try again.`; }
    finally { b.disabled = false; }
  });

  function setUrl() {
    const u = new URL(location.href); u.searchParams.set('q', S.q);
    if (S.tab === 'images') u.searchParams.set('tab', 'images'); else u.searchParams.delete('tab');
    history.replaceState(null, '', u);
    document.title = S.q ? `${S.q} · ${S.tab === 'images' ? 'Images' : 'Search'}` : 'Search';
  }
  function tab(t, load = true) {
    S.tab = t;
    document.querySelectorAll('.tabs button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.t === t)));
    $('#empty').hidden = !!S.q; $('#all').hidden = !S.q || t !== 'all'; $('#images').hidden = !S.q || t !== 'images';
    if (S.q) { setUrl(); if (load) ensure(); }
    window.scrollTo(0, 0);
  }
  async function run(q, t) {
    await configReady;
    q = String(q || '').trim(); if (!q) return;
    S.q = q; S.images = S.web = S.ov = null; S.seq++;
    $('#q').value = q; $('#clear').hidden = false; $('#q').blur();
    if (S.config?.capabilities.overview) $('#ov').innerHTML = shimmer(); $('#web').innerHTML = ''; $('#strip').innerHTML = ''; $('#grid').innerHTML = '<p class="note">Finding images…</p>';
    tab(t || S.tab);
  }
  function ensure() {
    const seq = S.seq, q = S.q;
    if (!S.images) { S.images = 'loading'; api('images', q).then(d => { if (seq === S.seq) { S.images = d; paintImages(); } }).catch(e => { if (seq === S.seq) { S.images = { images: [], error: e.message }; paintImages(); } }); }
    if (S.tab !== 'all') return;
    if (!S.web) { S.web = 'loading'; api('web', q).then(d => { if (seq === S.seq) { S.web = d; paintWeb(); } }).catch(e => { if (seq === S.seq) { S.web = { results: [], error: e.message }; paintWeb(); } }); }
    if (!S.ov) streamOv(seq, q);
  }
  // The overview streams: sources land first (~1-2 s), then the answer types in token by token.
  function streamOv(seq, q) {
    if (!S.config?.capabilities.overview) { S.ov = {answer: '', error: 'setup_required'}; return; }
    S.ov = { answer: '', sources: [], streaming: true };
    let es;
    const fail = err => { if (seq !== S.seq) return; S.ov = { ...S.ov, streaming: false, error: S.ov.answer ? '' : err }; paintOv(); };
    try { es = new EventSource(`${BASE}api/overview-stream?q=${encodeURIComponent(q)}`); } catch (e) { return fail('stream'); }
    S.es && S.es.close(); S.es = es;
    let raf = 0; const paintSoon = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; if (seq === S.seq) paintOv(); }); };
    es.addEventListener('sources', ev => { if (seq !== S.seq) return es.close(); S.ov.sources = JSON.parse(ev.data).sources || []; });
    es.addEventListener('delta', ev => { if (seq !== S.seq) return es.close(); S.ov.answer += JSON.parse(ev.data).t || ''; paintSoon(); });
    es.addEventListener('done', ev => {
      es.close(); if (seq !== S.seq) return; const d = JSON.parse(ev.data || '{}');
      S.ov = { ...S.ov, streaming: false, model: d.model || S.ov.model, answer: d.answer || S.ov.answer, error: d.error || '' }; paintOv();
    });
    es.onerror = () => { es.close(); fail('stream'); };
  }
  const shimmer = () => '<h3><i>✦</i> AI overview</h3><div class="shimmer"></div><div class="shimmer"></div><div class="shimmer s"></div>';
  function paintOv() {
    const d = S.ov, el = $('#ov');
    if (!d || d === 'loading' || (d.streaming && !d.answer)) { el.innerHTML = shimmer(); return; }
    if (!d.answer) { el.innerHTML = `<h3><i>✦</i> AI overview</h3><p class="dim">${d.error === 'setup_required' ? setupText : d.error === 'no results' ? 'No sources found for an overview.' : 'Overview unavailable right now.'}</p>`; return; }
    const src = Object.fromEntries((d.sources || []).map(s => [s.n, s]));
    const body = d.answer.replace(/【(\d+)[^】]*】/g, '[$1]').split(/\n{2,}/).map(par => `<p>${esc(par).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\[(\d+)\]/g, (m, n) => src[n] ? `<a class="cite" href="${esc(src[n].url)}" target="_blank" rel="noopener noreferrer" title="${esc(src[n].title)}">${n}</a>` : '')}</p>`).join('');
    const used = new Set([...d.answer.matchAll(/\[(\d+)\]/g)].map(m => +m[1]));
    const chips = (d.sources || []).filter(s => used.has(s.n)).map(s => `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer"><b>${s.n}</b>${esc(s.host)}</a>`).join('');
    el.innerHTML = `<h3><i>✦</i> AI overview</h3>${body}${d.streaming ? '<span class="caret"></span>' : ''}${chips && !d.streaming ? `<div class="srcs">${chips}</div>` : ''}${d.streaming ? '' : `<div class="meta">Private model · ${esc(d.model || '')}</div>`}`;
  }
  function paintWeb() {
    const d = S.web, el = $('#web');
    if (!d || d === 'loading') return;
    if (!d.results.length) { el.innerHTML = `<li class="note">${d.error === 'setup_required' ? setupText : d.error ? 'Web provider unavailable or returned no results. Check provider health and retry.' : 'No web results.'}</li>`; return; }
    el.innerHTML = d.results.map(r => `<li><div class="host"><img src="https://icons.duckduckgo.com/ip3/${esc(r.host)}.ico" alt="" loading="lazy" onerror="this.style.visibility='hidden'">${esc(r.host)}</div><a class="t" href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a><p class="s">${esc(r.snippet)}</p></li>`).join('');
  }
  function paintImages() {
    const d = S.images; if (!d || d === 'loading') return;
    const list = d.images || [];
    $('#grid').innerHTML = list.length ? list.map((im, i) => {
      const ar = im.w && im.h ? ` style="aspect-ratio:${im.w}/${im.h}"` : '';
      return `<button class="tile" data-i="${i}"><span class="im"${ar}><img src="${BASE}thumb/${im.id}.jpg" alt="${esc(im.title)}" loading="lazy" referrerpolicy="no-referrer"></span><span class="cap"><b>${esc(im.host)}</b> · ${esc(im.title)}</span></button>`;
    }).join('') : `<p class="note">${d.error === 'setup_required' ? setupText : d.error ? 'Image provider unavailable or returned no results. Check provider health and retry.' : 'No images found.'}</p>`;
    $('#strip').innerHTML = list.length ? list.slice(0, 8).map((im, i) => `<button data-i="${i}"><img src="${BASE}thumb/${im.id}.jpg" alt="${esc(im.title)}" loading="lazy"></button>`).join('') + '<button class="more" data-more>More images →</button>' : '';
  }
  function view(i, withMenu) {
    const list = (S.images && S.images.images) || []; const im = list[i]; if (!im) return;
    // download: the same image as a named attachment, so Save on Android files it under the result's title.
    const items = list.map(x => ({ url: `${BASE}img/${x.id}.jpg`, download: `${BASE}img/${x.id}.jpg?dl=${encodeURIComponent(x.title || x.host || 'image')}`, name: x.title || x.host, kind: 'image', mime: '' }));
    const V = shellViewer();
    if (V && V.open(items, i)) { if (withMenu && V.menu) V.menu(); return; }
    const lb = $('#lb'); lb.hidden = false; lb.querySelector('img').src = items[i].url;
    lb.querySelector('b').textContent = im.title; const a = lb.querySelector('a'); a.href = im.page || im.full;
    $('#save-image').href = items[i].download;
  }

  $('#f').addEventListener('submit', e => { e.preventDefault(); run($('#q').value); });
  $('#q').addEventListener('input', () => { $('#clear').hidden = !$('#q').value; });
  $('#clear').addEventListener('click', () => { $('#q').value = ''; $('#clear').hidden = true; $('#q').focus(); });
  document.querySelector('.tabs').addEventListener('click', e => { const b = e.target.closest('[data-t]'); if (b) tab(b.dataset.t); });
  document.addEventListener('click', e => {
    const more = e.target.closest('[data-more]'); if (more) return tab('images');
    const t = e.target.closest('[data-i]'); if (t) { e.preventDefault(); const V = shellViewer(); if (V && V.isOpen && V.isOpen()) return; view(+t.dataset.i); } // already open: the finger lifting off a long-press
    if (e.target.closest('[data-lb="close"]')) $('#lb').hidden = true;
  });
  // Long-press (Android) or right-click a result: open it with Save / Share, like holding an image in a browser.
  const holdOpen = t => { const V = shellViewer(); if (!V) return false; if (V.isOpen && V.isOpen()) { if (V.menu) V.menu(); } else view(+t.dataset.i, true); return true; };
  document.addEventListener('contextmenu', e => { const t = e.target.closest('[data-i]'); if (t && holdOpen(t)) e.preventDefault(); });
  let lp = null; // touch hold timer (WebViews don't always turn a hold into contextmenu); a scroll cancels it
  const lpStop = () => { if (lp) { clearTimeout(lp.t); lp = null; } };
  document.addEventListener('pointerdown', e => {
    const t = e.target.closest('[data-i]'); lpStop(); if (!t || e.pointerType === 'mouse' || !shellViewer()) return;
    lp = { x: e.clientX, y: e.clientY, t: setTimeout(() => { lp = null; holdOpen(t); }, 500) };
  }, { passive: true });
  document.addEventListener('pointermove', e => { if (lp && Math.hypot(e.clientX - lp.x, e.clientY - lp.y) > 10) lpStop(); }, { passive: true });
  ['pointerup', 'pointercancel', 'scroll'].forEach(k => document.addEventListener(k, lpStop, { passive: true, capture: true }));
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('#lb').hidden) { e.stopPropagation(); $('#lb').hidden = true; } }, true);

  if (!window.WizardApp) { $('#setup').hidden = false; $('#setup-status').textContent = 'Wizard shared client missing. Configure the gateway resource /wizard-os-home/core/app-client.js before opening Search.'; return; }
  WizardApp.ready({ name: 'Search', version: '0.3.0' });

  WizardApp.back.register({
    canGoBack: () => !$('#lb').hidden || S.tab !== 'all',
    back: () => { if (!$('#lb').hidden) { $('#lb').hidden = true; return true; } if (S.tab !== 'all') { tab('all'); return true; } return false; }
  });
  const feedback = message => { $('#voice-status').hidden = !message; $('#voice-status').textContent = message; };
  function voiceView(result) {
    S.es?.close(); S.seq++; S.q = result.q;
    // A voice query searches the frozen tab only. No additional inference or Chat call.
    S.web = result.web || null; S.images = result.images || null;
    S.ov = { answer: '', error: 'voice_query' };
    $('#q').value = S.q; $('#clear').hidden = false; $('#lb').hidden = true;
    $('#ov').innerHTML = '<p class="dim">Voice query · web results below.</p>';
    $('#web').innerHTML = ''; $('#strip').innerHTML = ''; $('#grid').innerHTML = '';
    tab(result.tab, false); paintWeb(); paintImages();
  }
  const voice = window.SearchVoiceInput?.register({
    state: () => ({ q: S.q, tab: S.tab, seq: S.seq, results: S.tab === 'images' ? S.images?.images : S.web?.results }),
    feedback, restore: voiceView,
    async search(q, target, authorize) {
      authorize();
      voiceView({ q, tab: target.tab });
      const seq = S.seq, kind = target.tab === 'images' ? 'images' : 'web';
      S[kind] = 'loading';
      if (kind === 'images') $('#grid').innerHTML = '<p class="note">Finding images…</p>';
      else $('#web').innerHTML = '<li class="note">Finding web results…</li>';
      let data;
      try {
        data = await api(kind, q);
        if (data.error) throw new Error(data.error);
      } catch (error) {
        if (seq === S.seq) {
          S[kind] = { results: [], images: [], error: error.message };
          if (kind === 'images') paintImages(); else paintWeb();
        }
        throw error;
      }
      const result = { q, tab: target.tab, [kind]: data };
      if (seq === S.seq) { S[kind] = data; if (kind === 'images') paintImages(); else paintWeb(); }
      return result;
    }
  });
  const p = new URLSearchParams(location.search);
  if (p.get('q')) {
    const q = p.get('q'), t = p.get('tab') === 'images' ? 'images' : 'all';
    if (voice) voice.restoreQuery(q).then(restored => { if (!restored) run(q, t); }).catch(() => feedback('Voice storage unavailable. Type a query to search; previous voice requests will not be replayed.'));
    else run(q, t);
  } else setTimeout(() => { if (!window.WizardApp?.hosted) $('#q').focus(); }, 50); // Hosted orb defaults to Search; explicit field focus still dictates.
  window.WizardSearch = { run, tab, state: () => ({ q: S.q, tab: S.tab, images: S.images?.images?.length || 0, web: S.web?.results?.length || 0, overview: !!S.ov?.answer && !S.ov?.streaming, streaming: !!S.ov?.streaming }) };
})();
