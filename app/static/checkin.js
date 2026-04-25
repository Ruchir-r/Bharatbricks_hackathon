/* Check-in: submit text to /api/checkin, render empathetic reply + severity banner. */

(() => {
  const submitBtn = document.getElementById('submit-checkin');
  const micBtn = document.getElementById('mic-btn');
  const utter = document.getElementById('utterance');
  const reply = document.getElementById('checkin-reply');

  // Track whether the most recent input came from voice (mic) — toggled in onstop below
  let lastInputFromVoice = false;

  submitBtn.addEventListener('click', async () => {
    const text = utter.value.trim();
    if (!text) return;
    submitBtn.disabled = true;
    submitBtn.textContent = 'भेज रहे हैं...';
    try {
      const fd = new FormData();
      fd.append('session_id', window.rx.sessionId());
      fd.append('utterance', text);
      const r = await fetch('/api/checkin', { method: 'POST', body: fd }).then(r => r.json());
      const cls = r.urgent ? 'alert-danger' : r.severity >= 3 ? 'alert-warn' : 'alert-info';
      // Default: text reply with a 🔊 button. If input was voice → auto-play TTS too.
      const speakBtn = `<button class="speak-btn" onclick='window.rx.speak(${JSON.stringify(r.reply_hi)}, "hi-IN")'>🔊 सुनें</button>`;
      reply.innerHTML = `<div class="alert ${cls}">${r.reply_hi}<br>${speakBtn}</div>`;
      if (r.reply_hi && lastInputFromVoice) {
        // Voice input → auto-speak the reply
        window.rx.speak(r.reply_hi, 'hi-IN');
      }
      if (r.urgent) reply.insertAdjacentHTML('beforeend', `<div class="alert alert-danger">🏥 तुरन्त डॉक्टर से मिलें।</div>`);
      utter.value = '';
      lastInputFromVoice = false;  // reset
    } catch (e) {
      reply.innerHTML = `<div class="alert alert-danger">भेज नहीं पाए। फिर कोशिश कीजिए।</div>`;
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = '<span>📤</span> भेजें';
    }
  });

  // ---- mic recorder (uses MediaRecorder, sends to /api/asr) ----
  let recorder, chunks = [];
  micBtn.addEventListener('click', async () => {
    if (recorder && recorder.state === 'recording') {
      recorder.stop();
      micBtn.innerHTML = '<span>🎤</span> बोलकर बताएँ';
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recorder = new MediaRecorder(stream);
      chunks = [];
      recorder.ondataavailable = (e) => chunks.push(e.data);
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: 'audio/wav' });
        const fd = new FormData();
        fd.append('file', blob, 'r.wav');
        fd.append('lang', window.rx.lang());
        const r = await fetch('/api/asr', { method: 'POST', body: fd }).then(r => r.json());
        utter.value = (utter.value + ' ' + (r.transcript || '')).trim();
        lastInputFromVoice = true;  // mark voice → next reply will auto-play TTS
      };
      recorder.start();
      micBtn.innerHTML = '<span>⏹</span> रोकें';
    } catch (e) {
      alert('माइक नहीं खुल सका। Please allow microphone.');
    }
  });
})();
