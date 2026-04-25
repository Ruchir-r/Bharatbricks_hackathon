/* Stub timetable page: renders demo entries from localStorage if present.
   Harshit: wire this to /api/timetable GET when backend endpoint is added. */

(() => {
  const entries = JSON.parse(localStorage.getItem('rx_timetable') || '[]');
  const list = document.getElementById('timetable-list');
  if (!entries.length) return;
  list.innerHTML = '';
  const tpl = document.getElementById('tt-card-tpl');
  for (const e of entries) {
    const node = tpl.content.cloneNode(true);
    node.querySelector('.tt-drug').textContent = '💊 ' + e.drug_name;
    node.querySelector('.tt-dose').textContent = e.dose;
    const times = node.querySelector('.tt-times');
    (e.times_of_day || []).forEach(t => {
      const chip = document.createElement('span');
      chip.className = 'chip'; chip.textContent = t;
      times.appendChild(chip);
    });
    const callBtn = node.querySelector('.call-btn');
    callBtn.addEventListener('click', async () => {
      const phone = prompt('Phone number (+91…)') || '+919074839967';
      if (!phone) return;
      callBtn.textContent = '⏳ ringing…';
      callBtn.disabled = true;
      try {
        const fd = new FormData();
        fd.append('phone', phone);
        fd.append('drug', e.drug_name);
        fd.append('dose', e.dose || '');
        fd.append('lang', window.rx.lang() || 'hi-IN');
        fd.append('patient_name', 'Patient');
        fd.append('time_slot', (e.times_of_day || [])[0] || 'now');
        fd.append('session_id', window.rx.sessionId());
        const r = await fetch('/api/call_reminder', { method: 'POST', body: fd }).then(r => r.json());
        if (r.call_id) alert('📞 Reminder sent. Call ID: ' + r.call_id.slice(0, 12));
        else alert('Could not place call: ' + (r.detail || r.error || 'unknown'));
      } catch (err) {
        alert('Call failed: ' + err.message);
      } finally {
        callBtn.textContent = '📞 कॉल रिमाइंडर';
        callBtn.disabled = false;
      }
    });
    // Speak button: uses /api/voice_reminder for the cached "take your X" message
    const speak = node.querySelector('.speak-btn');
    speak.addEventListener('click', async () => {
      speak.textContent = '⏳';
      try {
        const lang = window.rx.lang() || 'hi-IN';
        const r = await fetch(`/api/voice_reminder?drug=${encodeURIComponent(e.drug_name)}&dose=${encodeURIComponent(e.dose || '')}&lang=${encodeURIComponent(lang)}`).then(r => r.json());
        if (r.audio_b64) {
          new Audio('data:audio/wav;base64,' + r.audio_b64).play();
        } else {
          // Browser TTS fallback
          window.rx.speak(r.text || `Time to take your ${e.drug_name} ${e.dose}`, lang);
        }
      } catch (err) {
        window.rx.speak(`Time to take your ${e.drug_name} ${e.dose || ''}`, window.rx.lang());
      } finally {
        speak.textContent = '🔊 सुनें';
      }
    });
    list.appendChild(node);
  }
})();
