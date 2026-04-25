/* Scan page: pick image → POST /api/scan → render drug cards → per-drug /api/trust + /api/explain */

(() => {
  const upload = document.getElementById('file-upload');
  const fileInput = document.getElementById('scan-file');
  const preview = document.getElementById('preview');
  const scanBtn = document.getElementById('scan-btn');
  const result = document.getElementById('result');
  const stepper = document.querySelectorAll('.stepper .step');
  let mode = 'prescription';
  let file = null;

  // ---- visible debug strip — shows step-by-step what's happening ----
  const dbg = document.createElement('pre');
  dbg.id = 'scan-debug';
  Object.assign(dbg.style, {
    position: 'sticky', bottom: '64px',
    background: '#0f172a', color: '#10b981',
    padding: '10px 14px', borderRadius: '8px',
    fontSize: '12px', fontFamily: 'ui-monospace, monospace',
    margin: '12px 0', maxHeight: '180px', overflowY: 'auto',
    boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
  });
  dbg.textContent = '[debug] scan.js v2 ready';
  result.parentNode.insertBefore(dbg, result);
  function log(msg) {
    const t = new Date().toLocaleTimeString();
    dbg.textContent += `\n[${t}] ${msg}`;
    dbg.scrollTop = dbg.scrollHeight;
    console.log('[scan]', msg);
  }

  document.querySelectorAll('.choice').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('.choice').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      mode = b.dataset.mode;
    });
  });

  // The <input> is inside a <label> with class "file-upload" so the browser
  // already opens the picker on click. Don't add a manual handler — the
  // double-click can cause Chromium to ignore programmatic openings.
  fileInput.addEventListener('change', (e) => {
    file = e.target.files[0];
    log(`change event: file=${file ? file.name + ' (' + file.size + ' bytes, ' + file.type + ')' : 'NONE'}`);
    if (!file) return;
    const url = URL.createObjectURL(file);
    preview.src = url; preview.classList.remove('hidden');
    scanBtn.disabled = false;
    setStep(2);
    log(`scan button enabled`);
  });
  upload.addEventListener('click', () => log('upload area clicked'));
  scanBtn.addEventListener('click', () => log('scan button clicked'));

  function setStep(n) {
    stepper.forEach((el, i) => {
      el.classList.toggle('done', i < n - 1);
      el.classList.toggle('current', i === n - 1);
    });
  }

  scanBtn.addEventListener('click', async () => {
    if (!file) { log('ERROR: scan clicked but no file selected'); return; }
    scanBtn.disabled = true;
    scanBtn.textContent = 'जाँच रहे हैं...';
    result.innerHTML = '';
    setStep(3);
    log(`scan handler START — mode=${mode}, file=${file.name}`);

    // Reset any prior 45s anchor + added-meds so this scan becomes the active one
    try {
      localStorage.removeItem('rx_next_dose_ts');
      localStorage.removeItem('rx_next_dose_drug');
      localStorage.removeItem('rx_added_medicines_json');
      sessionStorage.removeItem('rx_last_scan');
    } catch(e) {}

    // Render the "Add to my profile" CTA IMMEDIATELY so the user can navigate
    // even if the OCR call is slow / fails. /scan_result has its own fallback fixture.
    const cta = document.createElement('a');
    cta.href = '/scan_result?session=demo-patient-001';
    cta.className = 'btn btn-primary btn-hero';
    cta.style.marginTop = '8px';
    cta.innerHTML = '<span aria-hidden="true">✅</span><span>Add to my profile · प्रोफ़ाइल में जोड़ें</span>';
    result.appendChild(cta);

    // OCR + render drug cards in the background (results enrich the same page)
    try {
      const fd = new FormData();
      fd.append('mode', mode);
      fd.append('file', file);
      log(`POST /api/scan started (demo_mode=${window.rx?.isDemoMode?.() ? 'YES' : 'no'})`);
      const t0 = Date.now();
      const res = await fetch('/api/scan', { method: 'POST', body: fd });
      log(`POST /api/scan finished: HTTP ${res.status} in ${Date.now()-t0}ms`);
      if (!res.ok) throw new Error(`scan HTTP ${res.status}`);
      const parsed = await res.json();
      log(`response parsed: drugs=${(parsed.drugs||[]).length}, diagnosis=${parsed.diagnosis||'-'}, _cached=${!!parsed._cached}`);
      const drugs = parsed.drugs || [];
      if (!drugs.length) {
        log('WARNING: 0 drugs in response — falling back to fixture for demo continuity');
        result.insertBefore(
          Object.assign(document.createElement('div'), {
            className: 'alert alert-warn',
            innerHTML: 'कोई दवा नहीं मिली। तस्वीर साफ़ नहीं थी। (Tap the green button above to use the cached demo result.)',
          }),
          cta
        );
        return;
      }
      // Stash for the next page
      try { sessionStorage.setItem('rx_last_scan', JSON.stringify(parsed)); } catch(e) {}
      log(`stashed scan result in sessionStorage`);

      // Insert drug cards ABOVE the existing cta (which stays as the bottom action)
      for (const d of drugs) {
        log(`renderDrug start: ${d.brand_or_generic || d.generic_name}`);
        try { await renderDrug(d, cta); }
        catch(e) { log(`renderDrug ERROR: ${e.message}`); }
      }
      // Skip interactions/trust on pre-add view — moved to /scan_result page
      log('all renders complete (pre-add view: names only)');
    } catch (e) {
      console.error(e);
      log(`scan FAILED: ${e.message}`);
      result.insertBefore(
        Object.assign(document.createElement('div'), {
          className: 'alert alert-warn',
          innerHTML: `OCR didn't return — tap the green button above to continue with the cached result.<br><small class="muted">${e.message}</small>`,
        }),
        cta
      );
    } finally {
      scanBtn.disabled = false;
      scanBtn.innerHTML = '<span>🔎</span> जाँच करें';
    }
  });

  // PRE-ADD view: just show drug name + dose. Trust verdict, side effects, prices,
  // alternate brands — all of that lives on /scan_result after the user taps the
  // green "Add to my profile" button.
  async function renderDrug(drug, anchor) {
    const name = drug.brand_or_generic || drug.generic_name || drug.brand_name || '';
    const dose = drug.dose || '';
    const freq = drug.frequency || '';
    const dur  = drug.duration || '';
    const card = document.createElement('article');
    card.className = 'card drug-card';
    card.style.padding = '12px';
    card.innerHTML =
      `<strong>💊 ${name}</strong>` +
      (dose ? `<span class="muted"> · ${dose}</span>` : '') +
      (freq ? `<br><small class="muted">When: ${freq}</small>` : '') +
      (dur  ? `<small class="muted"> · ${dur} day${dur === '1' ? '' : 's'}</small>` : '');
    if (anchor && anchor.parentNode === result) result.insertBefore(card, anchor);
    else result.appendChild(card);
  }

  function _alertBefore(html, anchor) {
    const wrap = document.createElement('div');
    wrap.innerHTML = html;
    while (wrap.firstChild) {
      if (anchor && anchor.parentNode === result) result.insertBefore(wrap.firstChild, anchor);
      else result.appendChild(wrap.firstChild);
    }
  }

  async function renderInteractions(drugs, diagnosis, anchor) {
    const names = drugs.map(d => d.brand_or_generic || d.generic_name || '').filter(Boolean);
    if (names.length < 2) return;
    try {
      const fd = new FormData();
      fd.append('drugs', names.join(','));
      if (diagnosis) fd.append('diagnosis', diagnosis);
      const r = await fetch('/api/interactions', { method: 'POST', body: fd }).then(r => r.json());
      if ((r.hard_blocks || []).length) {
        r.hard_blocks.forEach(h => {
          _alertBefore(`<div class="alert alert-danger"><strong>⚠ प्रतिबंधित मिश्रण:</strong> ${h.pair.join(' + ')} — ${h.reason || ''}</div>`, anchor);
        });
      }
      (r.soft?.interactions || []).forEach(i => {
        const cls = i.severity === 'high' ? 'alert-danger' : i.severity === 'moderate' ? 'alert-warn' : 'alert-info';
        _alertBefore(`<div class="alert ${cls}"><strong>${i.pair.join(' + ')}:</strong> ${i.explanation}</div>`, anchor);
      });
      if (r.soft?.recommend_second_opinion) {
        _alertBefore(`<div class="alert alert-warn">🏥 दूसरे डॉक्टर की राय लें।</div>`, anchor);
      }
    } catch (e) { console.error(e); }
  }
})();
