/* Home dashboard: fetch profile summary + render cards. Bilingual en/hi. */

(() => {
  const isEn = () => (window.rx.lang() || 'en-IN').startsWith('en');
  const bi = (en, hi) => isEn() ? en : hi;

  // Demo session can be overridden by ?session=... query; else use stored session_id
  const params = new URLSearchParams(location.search);
  const sid = params.get('session') || window.rx.sessionId();

  const greet = document.getElementById('greet');
  const sub = document.getElementById('subtitle');
  const speakBtn = document.getElementById('greet-speak');

  async function render() {
    try {
      const res = await fetch('/api/profile?session_id=' + encodeURIComponent(sid));
      const p = await res.json();
      const name = (p.session && p.session.patient_name) || null;

      if (name) {
        greet.textContent = isEn() ? `Namaste ${name}` : `नमस्ते ${name}`;
      } else {
        greet.textContent = isEn() ? 'Welcome' : 'नमस्ते';
      }

      const medCount = (p.medicines || []).length;
      sub.textContent = medCount
        ? bi(`You have ${medCount} medicines on file.`, `आपके पास ${medCount} दवाइयाँ हैं।`)
        : bi('No medicines yet — scan a prescription to begin.', 'अभी कोई दवा नहीं — पर्ची स्कैन कीजिए।');

      // ── Demo override: if /scan_result set a 20s anchor, show that countdown
      const anchorTs = parseInt(localStorage.getItem('rx_next_dose_ts') || '0', 10);
      const anchorDrug = localStorage.getItem('rx_next_dose_drug');
      if (anchorTs && anchorDrug) {
        const card = document.getElementById('next-dose-card');
        const body = document.getElementById('next-dose-body');
        card.style.display = '';
        const refresh = () => {
          const left = Math.max(0, Math.floor((anchorTs - Date.now())/1000));
          const m = Math.floor(left/60), s = left % 60;
          const span = `${m}:${s.toString().padStart(2,'0')}`;
          if (left > 0) {
            body.innerHTML = `<strong>💊 ${anchorDrug}</strong><br>` +
              `<span style="font-size:2rem;color:var(--c-primary);font-weight:700">${span}</span>` +
              `<span class="muted"> ${bi('until next dose','अगली खुराक तक')}</span>`;
          } else {
            body.innerHTML = `<div class="alert alert-warn"><strong>🔔 ${bi('Time to take','समय हो गया')} ${anchorDrug}!</strong></div>`;
          }
        };
        refresh();
        setInterval(refresh, 1000);
        return;   // skip the regular next-dose path
      }

      // Next dose
      if (p.next_dose) {
        document.getElementById('next-dose-card').style.display = '';
        const nd = p.next_dose;
        const when = new Date(nd.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const inMin = nd.minutes_from_now;
        const mins = inMin <= 60 ? bi(`in ${inMin} min`, `${inMin} मिनट में`) : bi(`at ${when}`, `${when} बजे`);
        document.getElementById('next-dose-body').innerHTML =
          `<strong>💊 ${nd.drug_name}</strong> ${nd.dose ? '(' + nd.dose + ')' : ''}<br>` +
          `${bi('Next dose', 'अगली खुराक')}: <strong>${mins}</strong>` +
          `<div style="margin-top:12px"><button class="speak-btn" onclick='window.rx.speak(${JSON.stringify(bi("Next dose of " + nd.drug_name + " " + mins, "अगली खुराक " + nd.drug_name + " " + mins))})'>🔊</button></div>`;
      }

      // ── Merge in any drugs added by the most-recent scan ──
      let merged = (p.medicines || []).slice();
      try {
        const added = JSON.parse(localStorage.getItem('rx_added_medicines_json') || '[]');
        if (Array.isArray(added) && added.length) {
          merged = merged.concat(added);
          // Reflect the new count in the subtitle
          sub.textContent = bi(
            `You have ${merged.length} medicines on file (${added.length} just added).`,
            `आपके पास ${merged.length} दवाइयाँ हैं (${added.length} अभी जोड़ी गईं)।`
          );
        }
      } catch (e) {}
      const medCount2 = merged.length;

      // Meds list
      if (medCount2) {
        document.getElementById('meds-card').style.display = '';
        const list = document.getElementById('meds-list');
        list.innerHTML = '';
        merged.forEach(m => {
          const el = document.createElement('div');
          el.className = 'tt-card';
          el.style.padding = '12px 0';
          el.style.borderBottom = '1px solid var(--c-border)';
          const badge = m._added ? `<span class="pill" style="margin-left:6px;background:#dcfce7;color:#166534">new</span>` : '';
          el.innerHTML =
            `<strong>💊 ${m.drug_name}</strong> <span class="muted">${m.dose || ''}</span>${badge}<br>` +
            `<span class="muted">${bi('times', 'समय')}: ${(m.times_of_day || []).join(', ') || bi('as needed', 'ज़रूरत पर')}</span> · ` +
            `<span class="muted">${m.duration_days || ''} ${bi('days', 'दिन')}</span>`;
          list.appendChild(el);
        });
      }

      // Check-ins
      if ((p.recent_checkins || []).length) {
        document.getElementById('checkins-card').style.display = '';
        const list = document.getElementById('checkins-list');
        list.innerHTML = '';
        p.recent_checkins.forEach(c => {
          const el = document.createElement('div');
          el.style.padding = '8px 0';
          const cls = c.severity >= 4 ? 'alert-danger' : c.severity >= 3 ? 'alert-warn' : 'alert-info';
          el.innerHTML = `<div class="alert ${cls}" style="font-size:var(--fs-base);padding:10px">` +
            `<strong>${c.symptom}</strong> (severity ${c.severity}) · ${c.drug_name}<br>` +
            `<small class="muted">${c.logged_at}</small></div>`;
          list.appendChild(el);
        });
      }
    } catch (e) {
      sub.textContent = bi('Could not load profile. Using demo mode.', 'प्रोफ़ाइल लोड नहीं हुई।');
      console.error(e);
    }
  }

  speakBtn.addEventListener('click', () => {
    window.rx.speak(greet.textContent + '. ' + sub.textContent);
  });

  // Pre-canned answers (used as fallback if /api/ask is slow / fails)
  const FALLBACK_ANSWERS = {
    'Can I take paracetamol with metformin?': 'Yes, paracetamol and metformin are safe to take together. They do not interact in a harmful way. Take paracetamol only when needed for pain or fever, and continue your metformin as prescribed by your doctor. This is information only — not a substitute for your doctor.',
    'What is amoxicillin for?': 'Amoxicillin is an antibiotic used to treat bacterial infections like throat, ear, and chest infections. Take it for the full number of days your doctor told you, even if you feel better — stopping early can make the infection come back stronger. This is information only — not a substitute for your doctor.',
    'When should I take cefixime?': 'Cefixime is usually taken twice a day, about 12 hours apart. It can be taken with or without food, but taking with food may reduce stomach upset. Drink plenty of water. Finish the full course as prescribed. This is information only — not a substitute for your doctor.',
    'क्या पेरासिटामोल और मेटफॉर्मिन साथ ले सकते हैं?': 'जी हाँ, पेरासिटामोल और मेटफॉर्मिन साथ लेना सुरक्षित है। इनमें कोई हानिकारक टकराव नहीं है। पेरासिटामोल केवल बुखार या दर्द होने पर लीजिए, और मेटफॉर्मिन डॉक्टर के अनुसार जारी रखिए। यह जानकारी केवल मदद के लिए है — डॉक्टर की सलाह ज़रूरी है।',
    'मेटफॉर्मिन से पेट में दर्द हो रहा है, क्या करूँ?': 'मेटफॉर्मिन से शुरू में पेट में हल्का दर्द आम है और आमतौर पर 1–2 हफ़्ते में ठीक हो जाता है। हमेशा खाने के साथ लीजिए, अकेले नहीं। अगर दर्द बहुत तेज़ है या बार-बार उल्टी हो रही है, तुरंत डॉक्टर से मिलिए। यह जानकारी केवल मदद के लिए है — डॉक्टर की सलाह ज़रूरी है।',
    'What should I watch for with amlodipine?': 'Amlodipine can cause swelling in the ankles or feet, mild dizziness when standing up, and headaches. These usually settle within a few weeks. If you feel very dizzy, have a fast heartbeat, or chest pain, see your doctor right away. This is information only — not a substitute for your doctor.',
  };

  // Ask feature
  const askBtn = document.getElementById('ask-btn');
  const askQ = document.getElementById('ask-q');
  const askAnswer = document.getElementById('ask-answer');

  // Wire chip clicks → fill textarea + auto-submit
  document.querySelectorAll('#ask-chips .chip').forEach(c => {
    c.addEventListener('click', () => {
      askQ.value = c.dataset.q;
      askBtn.click();
    });
  });

  askBtn.addEventListener('click', async () => {
    const q = askQ.value.trim();
    if (!q) return;
    askBtn.disabled = true;
    askBtn.textContent = bi('Thinking…', 'सोच रहा हूँ…');
    let timeoutId = null;
    try {
      const fd = new FormData();
      fd.append('session_id', sid);
      fd.append('question', q);
      fd.append('lang', window.rx.lang() || 'en-IN');
      const ctrl = new AbortController();
      timeoutId = setTimeout(() => ctrl.abort(), 15000);  // 15s before fallback
      const r = await fetch('/api/ask', { method: 'POST', body: fd, signal: ctrl.signal }).then(r => r.json());
      clearTimeout(timeoutId);
      if (r.error) throw new Error(r.error);
      // Text reply by default, with a 🔊 button. Auto-TTS only if input came via voice
      // (chips are text, so this never auto-plays today; future mic input will set the flag).
      const wasVoice = (window.rx && window.rx._lastAskFromVoice) || false;
      askAnswer.innerHTML = `<div class="alert alert-info big-text">${r.answer.replace(/\n/g, '<br>')}<br><button class="speak-btn" onclick='window.rx.speak(${JSON.stringify(r.answer)}, "${r.lang}")'>🔊 ${bi('Listen','सुनें')}</button></div>`;
      if (wasVoice) {
        window.rx.speak(r.answer, r.lang);
        window.rx._lastAskFromVoice = false;
      }
    } catch (e) {
      // Offline / timeout fallback: show pre-canned answer if we have one for this question
      if (timeoutId) clearTimeout(timeoutId);
      const fallback = FALLBACK_ANSWERS[q];
      if (fallback) {
        const lang = (q.match(/[ऀ-ॿ]/) ? 'hi-IN' : 'en-IN');
        askAnswer.innerHTML = `<div class="alert alert-info big-text">${fallback.replace(/\n/g, '<br>')}<br><span class="muted" style="font-size:0.85em">(cached)</span> <button class="speak-btn" onclick='window.rx.speak(${JSON.stringify(fallback)}, "${lang}")'>🔊</button></div>`;
      } else {
        askAnswer.innerHTML = `<div class="alert alert-danger">${bi('Could not answer right now.', 'अभी जवाब नहीं दे सका।')}</div>`;
      }
    } finally {
      askBtn.disabled = false;
      askBtn.textContent = bi('Ask · पूछें', 'पूछें · Ask');
    }
  });

  // -------------------------------------------------------------------
  // New support features
  // -------------------------------------------------------------------
  async function loadRefills() {
    try {
      const r = await fetch('/api/refill_alert?session_id=' + encodeURIComponent(sid)).then(r => r.json());
      const alerts = r.alerts || [];
      const card = document.getElementById('refill-card');
      const list = document.getElementById('refill-list');
      const urgent = alerts.filter(a => a.needs_refill);
      if (alerts.length === 0) return;
      card.style.display = '';
      list.innerHTML = '';
      alerts.forEach(a => {
        const cls = a.needs_refill ? 'alert-warn' : 'alert-info';
        const row = document.createElement('div');
        row.className = 'alert ' + cls;
        row.style.fontSize = 'var(--fs-base)';
        row.style.padding = '10px';
        row.innerHTML = a.needs_refill
          ? `<strong>⚠ ${a.drug_name}</strong> ${a.dose} — ${bi('only ' + a.days_remaining + ' days left', a.days_remaining + ' दिन बाकी')}`
          : `<strong>${a.drug_name}</strong> ${a.dose} — ${bi(a.days_remaining + ' days left', a.days_remaining + ' दिन बाकी')}`;
        list.appendChild(row);
      });
    } catch (e) { /* silent */ }
  }

  async function loadSavings() {
    const body = document.getElementById('savings-body');
    if (body.dataset.loaded) return;
    body.dataset.loaded = '1';
    body.textContent = bi('loading…', 'देख रहे हैं…');
    try {
      const r = await fetch('/api/savings_summary?session_id=' + encodeURIComponent(sid)).then(r => r.json());
      const total = r.monthly_savings || 0;
      const breakdown = r.breakdown || [];
      body.innerHTML =
        `<div class="savings-amount">₹${total.toFixed(0)} / ${bi('month', 'महीना')}</div>` +
        `<p class="muted">${bi('saved if you switch to Jan Aushadhi generics', 'अगर आप जन औषधि के जेनेरिक पर बदलें')}</p>` +
        breakdown.map(b =>
          `<div class="refill-row"><strong>${b.drug_name}</strong> · ` +
          `₹${b.branded_per_month.toFixed(0)} → ₹${b.generic_per_month.toFixed(0)} ` +
          `<span class="muted">(${bi('save', 'बचत')} ₹${b.savings.toFixed(0)})</span></div>`
        ).join('');
    } catch (e) {
      body.textContent = bi('Could not load savings.', 'जानकारी नहीं मिली।');
    }
  }
  document.querySelector('#savings-body')?.parentElement?.addEventListener('toggle', (ev) => {
    if (ev.target.open) loadSavings();
  });

  async function loadFoodWarnings() {
    const body = document.getElementById('food-warn-body');
    if (body.dataset.loaded) return;
    body.dataset.loaded = '1';
    body.textContent = bi('loading…', 'देख रहे हैं…');
    try {
      const r = await fetch('/api/food_warnings?session_id=' + encodeURIComponent(sid)).then(r => r.json());
      const warnings = r.warnings || [];
      if (warnings.length === 0) {
        body.textContent = bi('No special food warnings.', 'कोई विशेष चेतावनी नहीं।');
        return;
      }
      body.innerHTML = warnings.map(w =>
        `<div class="food-row"><strong>💊 ${w.drug_name}</strong>` +
        w.warnings.map(x => `<div class="muted">+ ${x.with}: ${x.advice} <small>[${x.severity}]</small></div>`).join('') +
        `</div>`
      ).join('');
    } catch (e) {
      body.textContent = bi('Could not load.', 'जानकारी नहीं मिली।');
    }
  }
  document.querySelector('#food-warn-body')?.parentElement?.addEventListener('toggle', (ev) => {
    if (ev.target.open) loadFoodWarnings();
  });

  async function loadSchemes() {
    const body = document.getElementById('scheme-body');
    if (body.dataset.loaded) return;
    body.dataset.loaded = '1';
    body.textContent = bi('loading…', 'देख रहे हैं…');
    try {
      const r = await fetch('/api/scheme_eligibility?diagnosis=diabetes').then(r => r.json());
      const schemes = r.schemes || [];
      body.innerHTML = schemes.map(s =>
        `<div class="scheme-row"><strong>${s.scheme}</strong><div class="muted">${s.details}</div></div>`
      ).join('') || bi('No schemes found.', 'कोई योजना नहीं मिली।');
    } catch (e) {
      body.textContent = bi('Could not load.', 'जानकारी नहीं मिली।');
    }
  }
  document.querySelector('#scheme-body')?.parentElement?.addEventListener('toggle', (ev) => {
    if (ev.target.open) loadSchemes();
  });

  document.getElementById('pharmacy-locate-btn')?.addEventListener('click', () => {
    const out = document.getElementById('pharmacy-list');
    out.textContent = bi('locating…', 'जगह खोज रहे हैं…');
    if (!navigator.geolocation) {
      // For demo: fall back to Lucknow coords
      fetchPharmacies(26.85, 80.95);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) => fetchPharmacies(p.coords.latitude, p.coords.longitude),
      () => fetchPharmacies(26.85, 80.95)
    );
  });

  async function fetchPharmacies(lat, lon) {
    const out = document.getElementById('pharmacy-list');
    try {
      const r = await fetch(`/api/pharmacy_locator?lat=${lat}&lon=${lon}&limit=5`).then(r => r.json());
      const list = r.pharmacies || [];
      out.innerHTML = list.map(p =>
        `<div class="pharmacy-row"><strong>${p.name}</strong> · ${p.distance_km} km<br>` +
        `<small class="muted">${p.address} · ☎ ${p.phone}</small></div>`
      ).join('') || bi('No pharmacies nearby.', 'पास में कोई फ़ार्मेसी नहीं।');
    } catch (e) {
      out.textContent = bi('Could not load.', 'जानकारी नहीं मिली।');
    }
  }

  loadRefills();
  render();
})();
