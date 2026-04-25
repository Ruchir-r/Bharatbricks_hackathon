/* scan_result.js — page that opens after an OCR upload.
 *
 * Reads the just-extracted prescription from sessionStorage (set by scan.js
 * after a successful upload), renders:
 *   - new medicines list
 *   - alternate Jan Aushadhi brands (RAG via /api/rag)
 *   - combined timesheet (existing + new)
 *   - 45-second next-dose countdown that PERSISTS to home
 */

(() => {
  // ---- 1. Pull the OCR result that scan.js stashed ----
  const session = (new URLSearchParams(location.search).get('session')) || 'demo-patient-001';
  const cachedRaw = sessionStorage.getItem('rx_last_scan');
  const fallback = (window.rx && window.rx.fixtures && window.rx.fixtures.scan_prescription_demo) || { drugs: [], diagnosis: 'Cold' };
  const scan = cachedRaw ? JSON.parse(cachedRaw) : fallback;
  const newDrugs = scan.drugs || [];
  document.getElementById('visit-summary').textContent =
    `From your visit${scan.doctor ? ' with ' + scan.doctor : ''}${scan.clinic ? ' at ' + scan.clinic : ''}.`;

  // ---- 2. Set the 45s next dose anchor (persisted across pages) ----
  const NEXT_DOSE_KEY = 'rx_next_dose_ts';
  let target = parseInt(localStorage.getItem(NEXT_DOSE_KEY) || '0', 10);
  if (!target || target < Date.now()) {
    target = Date.now() + 45_000;   // 45 seconds from now
    localStorage.setItem(NEXT_DOSE_KEY, String(target));
    if (newDrugs.length) {
      const d = newDrugs[0];
      const drugName = d.brand_or_generic || d.generic_name || 'your medicine';
      localStorage.setItem('rx_next_dose_drug', `${drugName} ${d.dose || ''}`.trim());
    }
  }

  // ---- 2b. Persist the new meds so home page merges them into Rina's profile ----
  // 100/010/001 binary frequency → time-of-day. Each digit = morning/noon/night slot.
  function freqToTimes(freq) {
    const f = (freq || '').replace(/\s+/g, '').replace(/\+/g, '');
    if (/^[01]{3}$/.test(f)) {
      const slots = ['08:00','14:00','20:00'];
      return slots.filter((_, i) => f[i] === '1');
    }
    const map = {
      'morning, noon': ['08:00','13:00'], 'thrice daily': ['08:00','14:00','20:00'],
      'twice daily': ['08:00','20:00'], 'morning': ['08:00'], 'PRN': ['as needed'],
      'OD': ['08:00'], 'BD': ['08:00','20:00'], 'TDS': ['08:00','14:00','20:00'],
    };
    return map[freq] || ['08:00','20:00'];
  }
  const addedMeds = newDrugs.map((d, i) => {
    const name = d.brand_or_generic || d.generic_name || `med_${i}`;
    const times = freqToTimes(d.frequency);
    return {
      entry_id: `tt-added-${i+1}`,
      drug_name: name, dose: d.dose || '',
      times_of_day: times,
      duration_days: parseInt(d.duration || '5', 10),
      start_date: new Date().toISOString().slice(0,10),
      _added: true,
    };
  });
  localStorage.setItem('rx_added_medicines_json', JSON.stringify(addedMeds));
  const drugLabel = localStorage.getItem('rx_next_dose_drug') || 'your medicine';

  function tick() {
    const left = Math.max(0, Math.floor((target - Date.now()) / 1000));
    const m = Math.floor(left / 60), s = left % 60;
    const span = `${m}:${s.toString().padStart(2,'0')}`;
    const el = document.getElementById('countdown');
    if (left > 0) {
      el.innerHTML = `<strong>💊 ${drugLabel}</strong><br>` +
        `<span style="font-size:2.4rem;color:var(--c-primary);font-weight:700">${span}</span>` +
        `<br><span class="muted">until next dose</span>`;
    } else {
      el.innerHTML = `<div class="alert alert-warn"><strong>🔔 Time to take ${drugLabel}!</strong></div>`;
    }
  }
  tick(); setInterval(tick, 1000);

  // ---- 3. Render the normalized medicines (with raw OCR + CDSCO cross-check) ----
  // Language-aware: when UI is Hindi, prefer the *_hi fields.
  function isHi() {
    return (window.rxI18n && window.rxI18n.getLang && window.rxI18n.getLang() === 'hi');
  }
  function pick(en, hi) { return isHi() && hi ? hi : en; }
  const newMedsList = document.getElementById('new-meds-list');
  const normalized = scan.normalized_drugs;
  // Re-render on language change
  window.addEventListener('rx-lang-changed', () => renderNormalized());
  function renderNormalized() {
  if (normalized && normalized.length) {
    newMedsList.innerHTML = normalized.map((n) => {
      const conf = (n.confidence || 0);
      const confColor = conf >= 0.7 ? 'var(--c-safe)' : conf >= 0.45 ? 'var(--c-warn)' : 'var(--c-muted)';
      const confLabel = conf >= 0.7 ? 'high' : conf >= 0.45 ? 'medium' : 'low';
      const cdscoBadge = n.cdsco_status === 'banned'
        ? `<span class="pill" style="background:#fee;color:#c62828">⛔ banned</span>`
        : n.cdsco_status === 'approved'
        ? `<span class="pill" style="background:#dcfce7;color:#166534">✓ CDSCO approved</span>`
        : `<span class="pill" style="background:#fef3c7;color:#92400e">? not in registry</span>`;
      const pmbjp = n.pmbjp_alternative
        ? `<div class="muted" style="margin-top:6px">💰 Jan Aushadhi: ${n.pmbjp_alternative.name} — ₹${n.pmbjp_alternative.mrp_inr}</div>`
        : '';
      // 3-tier price comparison
      const pc = (n.price_comparison || []);
      const priceTable = pc.length ? `
        <details style="margin-top:8px">
          <summary class="muted" style="font-size:0.9em;cursor:pointer">💸 Price comparison (${pc.length} tiers)</summary>
          <table style="width:100%;border-collapse:collapse;margin-top:6px;font-size:0.9em">
            <thead><tr style="border-bottom:1px solid var(--c-border)">
              <th style="text-align:left;padding:4px">Where</th>
              <th style="text-align:left;padding:4px">Name</th>
              <th style="text-align:right;padding:4px">MRP</th>
            </tr></thead>
            <tbody>
              ${pc.map(p => {
                const c = p.tier === 'generic' ? 'var(--c-safe)'
                       : p.tier === 'mid' ? 'var(--c-info)' : 'var(--c-danger)';
                return `<tr style="border-bottom:1px solid var(--c-border)">
                  <td style="padding:4px;color:${c};font-weight:600">${p.label}</td>
                  <td style="padding:4px" class="muted">${p.name}</td>
                  <td style="padding:4px;text-align:right;font-weight:600">₹${p.mrp_inr.toFixed(2)}</td>
                </tr>`;
              }).join('')}
            </tbody>
          </table>
          ${pc.find(p=>p.tier==='branded') && pc.find(p=>p.tier==='generic')
            ? `<div style="margin-top:6px;font-size:0.85em;color:var(--c-safe)"><strong>Save up to ₹${(pc.find(p=>p.tier==='branded').mrp_inr - pc.find(p=>p.tier==='generic').mrp_inr).toFixed(0)}</strong> by switching to Jan Aushadhi.</div>`
            : ''}
        </details>` : '';
      const cdscoMatch = n.cdsco_match;
      const cdscoMatchLoc = isHi() && n.cdsco_match_hi ? n.cdsco_match_hi : cdscoMatch;
      const cdscoDetail = cdscoMatchLoc
        ? `<div class="muted" style="margin-top:4px">📚 CDSCO: ${cdscoMatchLoc.indication}; ${cdscoMatchLoc.dosage}</div>`
        : '';
      const brands = (n.equivalent_brands || []);
      const brandsBlock = brands.length
        ? `<div style="margin-top:6px"><strong>🏷️ ${isHi()?'इसी दवा के अन्य ब्रांड':'Same molecule, other brands'}:</strong> <span class="muted">${brands.slice(0,5).join(' · ')}</span></div>`
        : '';
      const sides = pick(n.common_side_effects, n.common_side_effects_hi) || [];
      const sideBlock = sides.length
        ? `<div style="margin-top:6px"><strong>⚠️ ${isHi()?'सामान्य साइड इफ़ेक्ट':'Common side effects'}:</strong> <span class="muted">${sides.join('; ')}</span></div>`
        : '';
      const warns = pick(n.warnings, n.warnings_hi) || [];
      const warnBlock = warns.length
        ? `<div class="alert alert-warn" style="margin-top:6px;font-size:0.9em;padding:8px"><strong>${isHi()?'ज़रूरी':'Important'}:</strong> ${warns.join(' · ')}</div>`
        : '';
      const reasoning = pick(n.reasoning, n.reasoning_hi);
      const drugClass = pick(n.drug_class, n.drug_class_hi);
      return `<div class="card" style="margin: 8px 0; padding: 12px;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <strong>💊 ${n.likely_brand || n.raw_name}</strong>
          ${cdscoBadge}
        </div>
        <div class="muted" style="font-size:0.9em;margin-top:4px">
          (OCR read: <em>"${n.raw_name}"</em> · ${n.raw_dose || ''} · ${n.raw_frequency || ''} · ${n.raw_duration || ''} days)
        </div>
        <div style="margin-top:6px"><strong>Molecule:</strong> ${n.generic_or_molecule || 'unknown'} <span style="color:${confColor};font-size:0.85em">· ${confLabel} confidence</span></div>
        ${cdscoDetail}
        ${brandsBlock}
        ${sideBlock}
        ${warnBlock}
        ${pmbjp}
        ${priceTable}
        ${n.reasoning ? `<details style="margin-top:6px"><summary class="muted" style="font-size:0.85em;cursor:pointer">why this match</summary><div class="muted" style="font-size:0.85em;padding:4px 0">${n.reasoning}</div></details>` : ''}
      </div>`;
    }).join('');
  } else if (newDrugs && newDrugs.length) {
    newMedsList.innerHTML = newDrugs.map((d, i) => {
      const name = d.brand_or_generic || d.generic_name || 'unknown';
      return `<div class="card" style="margin: 8px 0; padding: 12px;">
        <strong>💊 ${name}</strong>
        ${d.dose ? `<span class="muted"> · ${d.dose}</span>` : ''}
        <br>
        ${d.frequency ? `<small class="muted">When: ${d.frequency}</small>` : ''}
        ${d.duration ? `<small class="muted"> · Duration: ${d.duration} days</small>` : ''}
      </div>`;
    }).join('');
  } else {
    newMedsList.textContent = 'No new medicines parsed.';
  }
  }
  renderNormalized();

  // ---- 4. Alternate brands via /api/rag for each drug ----
  const altList = document.getElementById('alternates-list');
  altList.innerHTML = '<p class="muted">Looking up Jan Aushadhi matches…</p>';
  (async () => {
    const blocks = [];
    for (const d of newDrugs) {
      const drug = d.brand_or_generic || d.generic_name || '';
      if (!drug) continue;
      try {
        const r = await fetch('/api/rag?drug_name=' + encodeURIComponent(drug)).then(r => r.json());
        const pmbjp = (r.citations || []).filter(c => c.table === 'pmbjp_catalog_real' || c.table === 'pmbjp_prices');
        if (pmbjp.length) {
          blocks.push(`<div class="card" style="margin: 6px 0; padding: 10px;">
            <strong>${drug}</strong> →<br>
            ${pmbjp.slice(0,2).map(p => `<small class="muted">  • ${p.snippet}</small>`).join('<br>')}
          </div>`);
        } else {
          blocks.push(`<div class="muted" style="margin: 6px 0;">${drug}: no Jan Aushadhi match (proprietary brand)</div>`);
        }
      } catch (e) {
        blocks.push(`<div class="muted">${drug}: lookup failed</div>`);
      }
    }
    altList.innerHTML = blocks.join('') || '<p class="muted">No alternates found.</p>';
  })();

  // ---- 5. Combined timesheet ----
  const tsBox = document.getElementById('timesheet');
  (async () => {
    try {
      const p = await fetch('/api/profile?session_id=' + encodeURIComponent(session)).then(r => r.json());
      const meds = p.medicines || [];
      tsBox.innerHTML = `<table style="width:100%; border-collapse: collapse;">
        <thead><tr style="text-align:left; border-bottom: 2px solid var(--c-border);">
          <th>Medicine</th><th>Dose</th><th>Times</th><th>Days</th>
        </tr></thead>
        <tbody>` +
        meds.map(m => `<tr style="border-bottom: 1px solid var(--c-border);">
          <td><strong>💊 ${m.drug_name}</strong></td>
          <td class="muted">${m.dose || '-'}</td>
          <td>${(m.times_of_day || []).map(t => `<span class="chip" style="margin: 2px;">${t}</span>`).join('')}</td>
          <td class="muted">${m.duration_days || '-'}</td>
        </tr>`).join('') +
        `</tbody></table>`;
    } catch (e) {
      tsBox.textContent = 'Could not load timesheet.';
    }
  })();

  // ---- 6. Hero speak ----
  document.getElementById('hero-speak').addEventListener('click', () => {
    const text = `Your visit with ${scan.doctor || 'the doctor'} added ${newDrugs.length} new medicines. Next dose in 45 seconds.`;
    window.rx.speak(text);
  });

  // ---- 7. Live Bolna call buttons — bypasses demo cache via window.rx.realFetch ----
  const bolnaStatus = document.getElementById('bolna-status');
  function setBolnaStatus(msg) {
    if (!bolnaStatus) return;
    const t = new Date().toLocaleTimeString();
    bolnaStatus.textContent += `\n[${t}] ${msg}`;
    bolnaStatus.scrollTop = bolnaStatus.scrollHeight;
  }

  async function fireLiveCall(kind, body) {
    const live = (window.rx && window.rx.realFetch) || window.fetch.bind(window);
    const fd = new FormData();
    Object.entries(body).forEach(([k, v]) => fd.append(k, v));
    setBolnaStatus(`→ POST /api/flow/${kind} (live, bypassing cache)`);
    try {
      const r = await live(`/api/flow/${kind}`, { method: 'POST', body: fd });
      const j = await r.json();
      const cid = j.call_id || j.error || '(no id)';
      setBolnaStatus(`✓ call_id: ${cid}`);
      if (j.call_id) pollStatus(j.call_id);
    } catch (e) {
      setBolnaStatus(`✗ error: ${e.message}`);
    }
  }

  async function pollStatus(callId) {
    const live = (window.rx && window.rx.realFetch) || window.fetch.bind(window);
    setBolnaStatus(`→ polling /api/call_status?call_id=${callId.slice(0,8)}…`);
    for (let i = 0; i < 8; i++) {
      await new Promise(r => setTimeout(r, 12_000));
      try {
        const r = await live(`/api/call_status?call_id=${encodeURIComponent(callId)}`);
        const j = await r.json();
        setBolnaStatus(`  poll ${i+1}: status=${j.status} confirmed=${j.confirmed} dur=${(j.raw && j.raw.telephony_data && j.raw.telephony_data.duration) || '?'}s`);
        if (j.completed) {
          if (j.summary) setBolnaStatus(`  summary: ${j.summary.slice(0, 200)}`);
          const rec = j.raw && j.raw.telephony_data && j.raw.telephony_data.recording_url;
          if (rec) setBolnaStatus(`  recording: ${rec}`);
          return;
        }
      } catch (e) {
        setBolnaStatus(`  poll ${i+1} error: ${e.message}`);
      }
    }
    setBolnaStatus(`(stopped polling after 8 attempts)`);
  }

  document.getElementById('btn-bolna-take')?.addEventListener('click', () => {
    if (!confirm('This will place a REAL Bolna call to Dr. Saab on +91 9074839967. ~3 credits. Proceed?')) return;
    fireLiveCall('take_now', {
      phone: '+919074839967',
      patient_name: 'Rina Devi',
      medicine_name: 'Crocin Cold',
      dosage: '500mg',
      time_slot: 'now',
      language: 'hi-IN',
      session_id: 'demo-patient-001',
    });
  });

  document.getElementById('btn-bolna-checkup')?.addEventListener('click', () => {
    if (!confirm('This will place a REAL Bolna check-up call to Dr. Saab. ~3 credits. Proceed?')) return;
    fireLiveCall('checkup', {
      phone: '+919074839967',
      patient_name: 'Rina Devi',
      language: 'hi-IN',
      session_id: 'demo-patient-001',
    });
  });
})();
