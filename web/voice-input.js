/* App-owned voice admission. The shell owns microphone, transcription and routing. */
(() => {
  'use strict';
  window.SearchVoiceInput = { register({ state, search, restore, feedback }) {
    if (!window.WizardApp?.voiceInput?.register) return null;
    const scope = location.pathname.replace(/[^/]*$/, '');
    let database;
    const active = new Map();
    function db() {
      if (!database) database = new Promise((resolve, reject) => {
        const request = indexedDB.open('wizard-search-voice:' + scope, 1);
        request.onupgradeneeded = () => request.result.createObjectStore('requests', { keyPath: 'request_id' });
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(new Error('Voice query could not be saved. Original input kept.'));
        request.onblocked = () => reject(new Error('Voice storage is busy. Original input kept.'));
      }).catch(error => { database = null; throw error; });
      return database;
    }
    const text = (value, max) => typeof value === 'string' ? value.slice(0, max) : '';
    function snapshot() {
      const s = state();
      return Object.freeze({
        label: s.tab === 'images' ? 'Search · Images' : 'Search',
        query: text(s.q, 300), tab: s.tab === 'images' ? 'images' : 'all',
        results: Object.freeze((s.results || []).slice(0, 5).map(r => Object.freeze({ title: text(r.title, 160), url: text(r.url || r.page, 1024) })))
      });
    }
    function payload(message) {
      const { request_id, text: query, target } = message || {};
      if (!/^[A-Za-z0-9_-]{8,100}$/.test(request_id || '') || typeof query !== 'string' || !query.trim() || query.length > 300 || message.files?.length || message.attachments?.length)
        throw new Error('Search accepts a text query up to 300 characters. Original input kept.');
      if (!target || !['all', 'images'].includes(target.tab) || typeof target.query !== 'string' || target.query.length > 300 || typeof target.label !== 'string' || target.label.length > 100 || !Array.isArray(target.results) || target.results.length > 5)
        throw new Error('Search target unavailable. Original input kept.');
      const results = target.results.map(r => {
        if (!r || typeof r.title !== 'string' || r.title.length > 160 || typeof r.url !== 'string' || r.url.length > 1024) throw new Error('Invalid Search context. Original input kept.');
        return { title: r.title, url: r.url };
      });
      return { request_id, text: query, target: { label: target.label, query: target.query, tab: target.tab, results } };
    }
    async function admit(message, authorize) {
      const connection = await db();
      authorize();
      return new Promise((resolve, reject) => {
        // One read/write transaction serializes retries even across two Search frames.
        const tx = connection.transaction('requests', 'readwrite', { durability: 'strict' });
        const store = tx.objectStore('requests');
        let admitted, error;
        const get = store.get(message.request_id);
        get.onsuccess = () => {
          try {
            authorize();
            const fingerprint = JSON.stringify(message);
            if (get.result) {
              if (get.result.fingerprint !== fingerprint) throw new Error('Voice request ID already has a different query. Original input kept.');
              admitted = { record: get.result, fresh: false };
            } else {
              const record = { ...message, fingerprint, status: 'accepted', created: Date.now() };
              store.add(record); admitted = { record, fresh: true };
            }
          } catch (e) { error = e; tx.abort(); }
        };
        tx.oncomplete = () => resolve(admitted);
        tx.onabort = tx.onerror = () => reject(error || new Error('Voice query could not be saved. Original input kept.'));
      });
    }
    async function save(record) {
      const connection = await db();
      return new Promise((resolve, reject) => {
        const tx = connection.transaction('requests', 'readwrite', { durability: 'strict' });
        tx.objectStore('requests').put(record);
        tx.oncomplete = resolve;
        tx.onabort = tx.onerror = () => reject(new Error('Search completed but its result could not be saved. Do not resend this request.'));
      });
    }
    function show(record) {
      restore(record.result || { q: record.text.trim(), tab: record.target.tab });
      feedback(record.status === 'done' ? 'Voice query complete.' : record.error || 'Voice query was accepted. It may have been interrupted; it will not run again automatically. Type a query to search again.');
    }
    async function receive(message, authorize) {
      if (typeof authorize !== 'function') throw new Error('Search authorization unavailable. Original input kept.');
      const input = payload(message);
      const check = () => { if (authorize() === false) throw new Error('Search target changed. Original input kept.'); };
      const { record, fresh } = await admit(input, check);
      if (fresh) {
        feedback('Searching your voice query…');
        // Admission is durable before any provider call. Never replay an ambiguous accepted request.
        const work = (async () => {
          let viewSequence;
          try {
            const pending = search(input.text.trim(), input.target, check);
            viewSequence = state().seq;
            record.result = await pending;
            record.status = 'done';
          } catch (e) { record.status = 'error'; record.error = 'Voice search failed: ' + (e.message || 'provider unavailable') + '. Type a query to try again.'; }
          try {
            await save(record);
            const current = state();
            if (current.seq === viewSequence) feedback(record.error || 'Voice query complete.');
          }
          catch (e) { feedback(e.message); }
          finally { active.delete(input.request_id); }
        })();
        active.set(input.request_id, work);
      } else if (active.has(input.request_id)) feedback('Voice query already accepted; search is running…');
      else show(record);
      return { accepted: true, request_id: input.request_id };
    }
    WizardApp.voiceInput.register({ snapshot, receive: async (message, authorize) => {
      try { return await receive(message, authorize); }
      catch (error) { feedback(error.message); throw error; }
    } });
    return { async restoreQuery(query) {
      // Reloading a voice URL must not trigger the ordinary URL-driven search again.
      const connection = await db();
      return new Promise((resolve, reject) => {
        const tx = connection.transaction('requests', 'readonly');
        const get = tx.objectStore('requests').getAll();
        get.onsuccess = () => {
          const record = get.result.filter(r => r.text.trim() === query).sort((a, b) => b.created - a.created)[0];
          if (record) show(record);
          resolve(!!record);
        };
        get.onerror = () => reject(get.error);
      });
    } };
  } };
})();
