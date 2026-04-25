/* ========================================================================
   Bharosa — shared client logic
   - text-size toggle
   - language toggle (UI labels only; content uses server language param)
   - speak buttons → /api/tts → base64 wav → <audio>
   - session_id bootstrap (localStorage)
   ======================================================================== */

(() => {
  const SESSION_KEY = 'rx_session_id';

  // Visible "cached" pill when fallback fired
  function showCachedPill() {
    if (document.getElementById('rx-cached-pill')) return;
    const pill = document.createElement('div');
    pill.id = 'rx-cached-pill';
    pill.textContent = '⚡ offline cache';
    Object.assign(pill.style, {
      position: 'fixed', bottom: 'calc(var(--tap) + 16px)', right: '12px',
      background: '#f57c00', color: 'white', padding: '6px 12px',
      borderRadius: '999px', fontSize: '0.8rem', fontWeight: '600',
      zIndex: '200', opacity: '0.9', boxShadow: '0 2px 6px rgba(0,0,0,0.2)',
    });
    document.body.appendChild(pill);
    setTimeout(() => pill.remove(), 4000);
  }
  // monkey-patch json so any consumer that reads {_cached:true} body shows the pill
  const origJson = Response.prototype.json;
  Response.prototype.json = async function () {
    const data = await origJson.call(this);
    if (data && typeof data === 'object' && data._cached) showCachedPill();
    return data;
  };
  if (!localStorage.getItem(SESSION_KEY)) {
    localStorage.setItem(SESSION_KEY, crypto.randomUUID());
  }
  window.rx = window.rx || {};
  window.rx.sessionId = () => localStorage.getItem(SESSION_KEY);
  window.rx.lang = () => {
    const saved = localStorage.getItem('rx_lang');
    if (saved) return saved;
    // Default from browser: English UI if browser starts with en, else Hindi
    const nav = (navigator.language || 'en-IN').toLowerCase();
    return nav.startsWith('hi') ? 'hi-IN' : 'en-IN';
  };
  window.rx.setLang = (l) => { localStorage.setItem('rx_lang', l); document.documentElement.lang = l.split('-')[0]; };

  // ---- text size toggle ----
  const SIZES = ['', 'text-lg', 'text-xl'];
  const savedSize = localStorage.getItem('rx_textsize') || '';
  if (savedSize) document.body.classList.add(savedSize);
  const sizeBtn = document.getElementById('text-size-btn');
  if (sizeBtn) sizeBtn.addEventListener('click', () => {
    const cur = SIZES.find(s => s && document.body.classList.contains(s)) || '';
    const next = SIZES[(SIZES.indexOf(cur) + 1) % SIZES.length];
    SIZES.filter(Boolean).forEach(s => document.body.classList.remove(s));
    if (next) document.body.classList.add(next);
    localStorage.setItem('rx_textsize', next);
  });

  // ---- language dropdown (en / hi / ml) ----
  const langSelect = document.getElementById('lang-select');
  const SHORT_TO_FULL = { en: 'en-IN', hi: 'hi-IN', ml: 'ml-IN' };
  // Initial value from i18n's stored language (or browser default)
  if (langSelect && window.rxI18n) {
    const cur = window.rxI18n.getLang();
    langSelect.value = cur;
    // Sync window.rx.lang (used by /api/* form data) with UI lang
    window.rx.setLang(SHORT_TO_FULL[cur] || 'en-IN');
    langSelect.addEventListener('change', () => {
      const v = langSelect.value;
      window.rxI18n.apply(v);
      window.rx.setLang(SHORT_TO_FULL[v] || 'en-IN');
    });
  }
  // Kick off i18n
  if (window.rxI18n) window.rxI18n.init();

  // ---- speak: try server TTS (Sarvam) → fall back to browser speechSynthesis ----
  let sarvamReady = null;  // cache /api/health result so we don't hammer it
  async function checkSarvam() {
    if (sarvamReady !== null) return sarvamReady;
    try {
      const h = await fetch('/api/health').then(r => r.json());
      sarvamReady = !!h.sarvam_configured;
    } catch { sarvamReady = false; }
    return sarvamReady;
  }
  async function speak(text, lang) {
    lang = lang || window.rx.lang();
    const useServer = await checkSarvam();
    if (useServer) {
      try {
        const fd = new FormData();
        fd.append('text', text); fd.append('lang', lang);
        const res = await fetch('/api/tts', { method: 'POST', body: fd });
        if (res.ok) {
          const { audio_b64 } = await res.json();
          if (audio_b64) { new Audio('data:audio/wav;base64,' + audio_b64).play(); return; }
        }
      } catch (e) { /* fall through */ }
    }
    // Browser fallback (works for English well; Hindi depends on installed voices)
    if ('speechSynthesis' in window) {
      const utter = new SpeechSynthesisUtterance(text);
      utter.lang = lang;
      speechSynthesis.speak(utter);
    }
  }
  window.rx.speak = speak;

  document.addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-speak]');
    if (!btn) return;
    speak(btn.dataset.speak);
  });

  // ---- demo-mode toggle (🎬 button) ----
  const demoBtn = document.getElementById('demo-btn');
  function refreshDemoUI() {
    const on = window.rx.isDemoMode && window.rx.isDemoMode();
    let badge = document.getElementById('rx-demo-badge');
    if (on && !badge) {
      badge = document.createElement('div');
      badge.id = 'rx-demo-badge';
      badge.textContent = 'DEMO MODE';
      Object.assign(badge.style, {
        position: 'fixed', top: '8px', left: '50%', transform: 'translateX(-50%)',
        background: '#c62828', color: 'white', padding: '4px 12px',
        borderRadius: '999px', fontSize: '0.75rem', fontWeight: '700', letterSpacing: '0.06em',
        zIndex: '300', boxShadow: '0 2px 6px rgba(0,0,0,0.25)',
      });
      document.body.appendChild(badge);
    } else if (!on && badge) {
      badge.remove();
    }
    if (demoBtn) demoBtn.style.background = on ? '#c62828' : '';
  }
  if (demoBtn) demoBtn.addEventListener('click', () => {
    const wantOn = !window.rx.isDemoMode();
    window.rx.setDemoMode(wantOn);
    // Always reset demo state on toggle: clear added-meds, countdown, scan stash.
    // This puts Rina back to her 3-medicine baseline so the demo can be re-run.
    try {
      localStorage.removeItem('rx_added_medicines_json');
      localStorage.removeItem('rx_next_dose_ts');
      localStorage.removeItem('rx_next_dose_drug');
      sessionStorage.removeItem('rx_last_scan');
    } catch(e) {}
    refreshDemoUI();
    if (wantOn) {
      const url = new URL(location.href);
      url.searchParams.set('session', 'demo-patient-001');
      url.pathname = '/';
      location.href = url.toString();
    } else {
      location.reload();
    }
  });
  refreshDemoUI();

  // ---- warmup button ----
  const warmBtn = document.getElementById('warmup-btn');
  if (warmBtn) warmBtn.addEventListener('click', async () => {
    if (!confirm('Pre-warm services + cache demo TTS?\n(One-time API spend; subsequent demos hit cache.)')) return;
    const original = warmBtn.textContent;
    warmBtn.textContent = '⏳';
    warmBtn.disabled = true;
    const t0 = Date.now();
    try {
      const r = await fetch('/api/warmup', { method: 'POST' });
      const body = await r.json();
      const s = body.summary || {};
      const dur = ((Date.now() - t0) / 1000).toFixed(1);
      alert(`Warm-up done in ${dur}s\n` +
            `cache hits: ${s.cache_hit || 0}\n` +
            `newly cached: ${s.newly_cached || 0}\n` +
            `errors: ${s.errors || 0}`);
    } catch (e) {
      alert('Warm-up failed: ' + e.message);
    } finally {
      warmBtn.textContent = original;
      warmBtn.disabled = false;
    }
  });
})();
