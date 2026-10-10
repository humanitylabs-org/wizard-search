/* Wizard Search: private web + image search with an AI overview. Opens in Wizard's link sheet. */
(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const BASE = location.pathname.replace(/[^/]*$/, '');
  const api = (p, q) => fetch(`${BASE}api/${p}?q=${encodeURIComponent(q)}`, { credentials: 'same-origin' }).then(r => r.ok ? r.json() : r.json().then(j => Promise.reject(new Error(j.error || r.status))));
  const S = { q: '', tab: 'all', images: null, web: null, ov: null, seq: 0 };
  // Inside Wizard the shell's media viewer (fit, pinch, swipe, Back closes it) shows full images.
  const shellViewer = () => { try { return window.parent !== window && window.parent.WosChat && window.parent.WosChat.viewer; } catch (e) { return null; } };

  function setUrl() {
    const u = new URL(location.href); u.searchParams.set('q', S.q);
    if (S.tab === 'images') u.searchParams.set('tab', 'images'); else u.searchParams.delete('tab');
    history.replaceState(null, '', u);
    document.title = S.q ? `${S.q} · ${S.tab === 'images' ? 'Images' : 'Search'}` : 'Search';
  }
  function tab(t) {
    S.tab = t;
    document.querySelectorAll('.tabs button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.t === t)));
    $('#empty').hidden = !!S.q; $('#all').hidden = !S.q || t !== 'all'; $('#images').hidden = !S.q || t !== 'images';
    if (S.q) { setUrl(); ensure(); }
    window.scrollTo(0, 0);
  }
  function run(q, t) {
    q = String(q || '').trim(); if (!q) return;
    S.q = q; S.images = S.web = S.ov = null; S.seq++;
    $('#q').value = q; $('#clear').hidden = false; $('#q').blur();
    $('#ov').innerHTML = shimmer(); $('#web').innerHTML = ''; $('#strip').innerHTML = ''; $('#grid').innerHTML = '<p class="note">Finding images…</p>';
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
    if (!d.answer) { el.innerHTML = `<h3><i>✦</i> AI overview</h3><p class="dim">${d.error === 'no results' ? 'No sources found for an overview.' : 'Overview unavailable right now.'}</p>`; return; }
    const src = Object.fromEntries((d.sources || []).map(s => [s.n, s]));
    const body = d.answer.replace(/【(\d+)[^】]*】/g, '[$1]').split(/\n{2,}/).map(par => `<p>${esc(par).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\[(\d+)\]/g, (m, n) => src[n] ? `<a class="cite" href="${esc(src[n].url)}" target="_blank" rel="noopener noreferrer" title="${esc(src[n].title)}">${n}</a>` : '')}</p>`).join('');
    const used = new Set([...d.answer.matchAll(/\[(\d+)\]/g)].map(m => +m[1]));
    const chips = (d.sources || []).filter(s => used.has(s.n)).map(s => `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer"><b>${s.n}</b>${esc(s.host)}</a>`).join('');
    el.innerHTML = `<h3><i>✦</i> AI overview</h3>${body}${d.streaming ? '<span class="caret"></span>' : ''}${chips && !d.streaming ? `<div class="srcs">${chips}</div>` : ''}${d.streaming ? '' : `<div class="meta">Private model · ${esc(d.model || '')}</div>`}`;
  }
  function paintWeb() {
    const d = S.web, el = $('#web');
    if (!d || d === 'loading') return;
    if (!d.results.length) { el.innerHTML = `<li class="note">${d.error ? 'Web results unavailable right now.' : 'No web results.'}</li>`; return; }
    el.innerHTML = d.results.map(r => `<li><div class="host"><img src="https://icons.duckduckgo.com/ip3/${esc(r.host)}.ico" alt="" loading="lazy" onerror="this.style.visibility='hidden'">${esc(r.host)}</div><a class="t" href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a><p class="s">${esc(r.snippet)}</p></li>`).join('');
  }
  function paintImages() {
    const d = S.images; if (!d || d === 'loading') return;
    const list = d.images || [];
    $('#grid').innerHTML = list.length ? list.map((im, i) => {
      const ar = im.w && im.h ? ` style="aspect-ratio:${im.w}/${im.h}"` : '';
      return `<button class="tile" data-i="${i}"><span class="im"${ar}><img src="${BASE}thumb/${im.id}.jpg" alt="${esc(im.title)}" loading="lazy" referrerpolicy="no-referrer"></span><span class="cap"><b>${esc(im.host)}</b> · ${esc(im.title)}</span></button>`;
    }).join('') : `<p class="note">${d.error ? 'Image search is unavailable right now.' : 'No images found.'}</p>`;
    $('#strip').innerHTML = list.length ? list.slice(0, 8).map((im, i) => `<button data-i="${i}"><img src="${BASE}thumb/${im.id}.jpg" alt="${esc(im.title)}" loading="lazy"></button>`).join('') + '<button class="more" data-more>More images →</button>' : '';
  }
  function view(i) {
    const list = (S.images && S.images.images) || []; const im = list[i]; if (!im) return;
    const items = list.map(x => ({ url: `${BASE}img/${x.id}.jpg`, name: x.title || x.host, kind: 'image', mime: '' }));
    const V = shellViewer();
    if (V && V.open(items, i)) return;
    const lb = $('#lb'); lb.hidden = false; lb.querySelector('img').src = items[i].url;
    lb.querySelector('b').textContent = im.title; const a = lb.querySelector('a'); a.href = im.page || im.full;
  }

  $('#f').addEventListener('submit', e => { e.preventDefault(); run($('#q').value); });
  $('#q').addEventListener('input', () => { $('#clear').hidden = !$('#q').value; });
  $('#clear').addEventListener('click', () => { $('#q').value = ''; $('#clear').hidden = true; $('#q').focus(); });
  document.querySelector('.tabs').addEventListener('click', e => { const b = e.target.closest('[data-t]'); if (b) tab(b.dataset.t); });
  document.addEventListener('click', e => {
    const more = e.target.closest('[data-more]'); if (more) return tab('images');
    const t = e.target.closest('[data-i]'); if (t) { e.preventDefault(); view(+t.dataset.i); }
    if (e.target.closest('[data-lb="close"]')) $('#lb').hidden = true;
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('#lb').hidden) { e.stopPropagation(); $('#lb').hidden = true; } }, true);

  const p = new URLSearchParams(location.search);
  if (p.get('q')) run(p.get('q'), p.get('tab') === 'images' ? 'images' : 'all');
  else setTimeout(() => $('#q').focus(), 50);
  window.WizardSearch = { run, tab, state: () => ({ q: S.q, tab: S.tab, images: S.images?.images?.length || 0, web: S.web?.results?.length || 0, overview: !!S.ov?.answer && !S.ov?.streaming, streaming: !!S.ov?.streaming }) };
})();
