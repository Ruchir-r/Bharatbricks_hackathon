/* SOS — pre-fills patient + emergency contact from /api/profile so the user can
 * just tap the big red button. Double-tap-to-confirm prevents accidents.
 */

(() => {
  const session = (new URLSearchParams(location.search).get('session')) || 'demo-patient-001';
  const nameEl = document.getElementById('pname');
  const phoneEl = document.getElementById('ephone');
  const noteEl = document.getElementById('note');
  const locBtn = document.getElementById('locate-btn');
  const locStatus = document.getElementById('loc-status');
  const sosBtn = document.getElementById('sos-btn');
  const result = document.getElementById('sos-result');

  let lat = null, lon = null;

  // Pre-fill from profile so the user doesn't have to type
  (async () => {
    try {
      const r = await fetch('/api/profile?session_id=' + encodeURIComponent(session)).then(r => r.json());
      const sess = r.session || {};
      nameEl.value = sess.patient_name || 'Patient';
      phoneEl.value = sess.emergency_contact_phone || '+919074839967';
      // Display contact name + phone in the headline
      const contactName = sess.emergency_contact_name || 'Dr. Saab';
      document.getElementById('sos-contact-name').textContent = contactName;
      document.getElementById('sos-contact-phone').textContent = phoneEl.value;
    } catch (e) {
      // Fall back to defaults already in the HTML
      nameEl.value = 'Rina Devi';
      phoneEl.value = '+919074839967';
    }
  })();

  // Auto-attempt geolocation on page load (silent — no permission yet, so this just preps the user)
  function tryLocate(silent = false) {
    if (!navigator.geolocation) { locStatus.textContent = 'Location not supported by browser.'; return; }
    if (!silent) locStatus.textContent = 'जगह ढूँढ रहे हैं… / Locating…';
    navigator.geolocation.getCurrentPosition(
      (p) => {
        lat = p.coords.latitude; lon = p.coords.longitude;
        locStatus.textContent = `📍 ${lat.toFixed(4)}, ${lon.toFixed(4)}`;
      },
      () => { if (!silent) locStatus.textContent = 'Could not get location. SOS will still send (without map).'; }
    );
  }
  locBtn.addEventListener('click', () => tryLocate(false));

  // Double-tap to confirm
  let armed = false, armedTimer = null;
  sosBtn.addEventListener('click', async () => {
    if (!armed) {
      armed = true;
      sosBtn.classList.add('btn-hero');
      sosBtn.innerHTML = '<span aria-hidden="true">⚠</span><span>Tap again to confirm · पक्का करें</span>';
      if (armedTimer) clearTimeout(armedTimer);
      armedTimer = setTimeout(() => {
        armed = false;
        sosBtn.innerHTML = '<span aria-hidden="true">🚨</span><span>SEND SOS</span>';
      }, 4000);
      return;
    }
    clearTimeout(armedTimer);
    armed = false;
    sosBtn.disabled = true;
    sosBtn.textContent = 'भेज रहे हैं… / Sending…';

    const fd = new FormData();
    fd.append('session_id', session);
    fd.append('patient_name', nameEl.value || 'Rina Devi');
    fd.append('emergency_phone', phoneEl.value || '+919074839967');
    if (lat) fd.append('lat', lat);
    if (lon) fd.append('lon', lon);
    fd.append('note', noteEl.value || '');

    try {
      const r = await fetch('/api/sos', { method: 'POST', body: fd }).then(r => r.json());
      const contactName = document.getElementById('sos-contact-name').textContent;
      result.innerHTML = `<div class="alert alert-safe big-text">
        ✅ SOS sent to ${contactName}<br>
        SMS · ${r.sms_sid || '—'}<br>
        Call · ${r.call_sid || '—'}<br>
        <small class="muted">${r.location || ''}</small>
      </div>`;

      // Bonus: also fire the Bolna emergency flow (richer agent-driven call) in parallel.
      // Use window.rx.realFetch so the call ACTUALLY rings even when demo mode is on.
      try {
        const live = (window.rx && window.rx.realFetch) || window.fetch.bind(window);
        const fd2 = new FormData();
        fd2.append('doctor_phone', phoneEl.value || '+919074839967');
        fd2.append('patient_name', nameEl.value || 'Rina Devi');
        fd2.append('patient_phone', '+919999000001');
        if (lat) fd2.append('lat', lat);
        if (lon) fd2.append('lon', lon);
        fd2.append('language', 'en-IN');
        fd2.append('session_id', session);
        const r2 = await live('/api/flow/emergency', { method: 'POST', body: fd2 }).then(r => r.json());
        if (r2.call_id) {
          result.insertAdjacentHTML('beforeend',
            `<div class="alert alert-info">📞 Bolna emergency call placed (live, id ${r2.call_id.slice(0,12)}…) · Dr. Saab will receive in seconds.</div>`);
        }
      } catch(e){}
    } catch (e) {
      result.innerHTML = `<div class="alert alert-danger">Could not send SOS. Try again or call ${phoneEl.value} directly.</div>`;
    } finally {
      sosBtn.disabled = false;
      sosBtn.innerHTML = '<span aria-hidden="true">🚨</span><span>SEND SOS</span>';
    }
  });

  // Try to grab location quietly on page load (will pop browser permission prompt
  // — that's intentional so the location is ready by the time they tap SOS)
  tryLocate(true);
})();
