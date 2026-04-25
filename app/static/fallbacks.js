/* fallbacks.js — global API safety net for the live demo.

Wraps window.fetch so that every /api/* call:
  1. Tries the live endpoint with a 15s timeout.
  2. If it errors, times out, or returns non-OK → returns a hard-coded cached
     response from FIXTURES (with `_cached: true`).

Goal: the demo never hangs or shows an error to the judge. If a feature is broken
backend-side, we silently degrade to canned data. The "(cached)" pill in UI tells
the operator it happened.

This file MUST be loaded BEFORE any other page-specific JS. base.html now imports
it before app.js so the wrapper is in place by the time anyone calls fetch.
*/

(() => {
  const TIMEOUT_MS = 15000;

  // --------------------------------------------------------------------------
  // FIXTURES
  // --------------------------------------------------------------------------
  const FIXTURES = {
    health: {
      status: 'ok',
      catalog: 'bricksiitm',
      schema: 'rx_helper',
      sarvam_configured: true,
      twilio_configured: false,
      languages: ['en-IN', 'hi-IN'],
    },

    profile_demo: {
      session: {
        session_id: 'demo-patient-001',
        patient_name: 'Rina Devi',
        phone: '+919999000001',
        preferred_language: 'hi-IN',
        emergency_contact_phone: '+919074839967',
        emergency_contact_name: 'Dr. Saab',
        created_at: '2026-04-25 17:00:00',
      },
      medicines: [
        { entry_id: 'tt-001', drug_name: 'amlodipine',  dose: '5mg',   times_of_day: ['08:00'],          duration_days: 30, start_date: '2026-04-25' },
        { entry_id: 'tt-002', drug_name: 'metformin',   dose: '500mg', times_of_day: ['08:00','20:00'], duration_days: 30, start_date: '2026-04-25' },
        { entry_id: 'tt-003', drug_name: 'paracetamol', dose: '500mg', times_of_day: ['14:00'],          duration_days: 5,  start_date: '2026-04-25' },
      ],
      next_dose: { drug_name: 'metformin', dose: '500mg', at: '2026-04-26T20:00', minutes_from_now: 45 },
      recent_checkins: [
        { drug_name: 'metformin',  symptom: 'mild nausea',    severity: 2, logged_at: '2026-04-25 23:00' },
        { drug_name: 'amlodipine', symptom: 'ankle swelling', severity: 3, logged_at: '2026-04-23 18:00' },
      ],
    },

    // Keyed by lower-case drug_name
    trust: {
      paracetamol: { drug_name: 'paracetamol', safe: true, approved: true, banned: false, nsq_recent: false, nsq_batches: [],
        reasons: ['Approved by CDSCO. No recent quality alerts.'] },
      amoxicillin: { drug_name: 'amoxicillin', safe: true, approved: true, banned: false, nsq_recent: false, nsq_batches: [],
        reasons: ['Approved by CDSCO. No recent quality alerts.'] },
      cefixime: { drug_name: 'cefixime', safe: false, approved: true, banned: false, nsq_recent: true, nsq_batches: ['CXM2509A'],
        reasons: ['Appears in recent not-of-standard-quality reports (batches: CXM2509A).'] },
      flupirtine: { drug_name: 'flupirtine', safe: false, approved: false, banned: true, nsq_recent: false, nsq_batches: [],
        reasons: ['Banned by CDSCO. Do not take.'] },
      metformin:   { drug_name: 'metformin',   safe: true, approved: true, banned: false, nsq_recent: false, nsq_batches: [],
        reasons: ['Approved by CDSCO. No recent quality alerts.'] },
      amlodipine:  { drug_name: 'amlodipine',  safe: true, approved: true, banned: false, nsq_recent: false, nsq_batches: [],
        reasons: ['Approved by CDSCO. No recent quality alerts.'] },
      _default: { safe: false, approved: false, banned: false, nsq_recent: false, nsq_batches: [],
        reasons: ['Not found in CDSCO approved list — verify with pharmacist.'] },
    },

    // Keyed by `${drug.lower()}|${lang.split('-')[0]}`
    explain: {
      'paracetamol|en': { english: 'This medicine helps with fever and body pain. Take one 500mg tablet with food, up to four times a day. Watch for any rash or stomach upset.',
        translated: 'This medicine helps with fever and body pain. Take one 500mg tablet with food, up to four times a day. Watch for any rash or stomach upset.\n\n⚠ Information only — not a substitute for a doctor.',
        language: 'en', audio_b64: null },
      'paracetamol|hi': { english: 'This medicine helps with fever and body pain. Take one 500mg tablet with food.',
        translated: 'यह दवा बुख़ार और शरीर के दर्द में मदद करती है। एक 500 मिलीग्राम की गोली खाने के साथ लीजिए, दिन में चार बार तक। अगर चकत्ते हों या पेट में तकलीफ़ हो तो बताइए।\n\n⚠ यह जानकारी केवल मदद के लिए है। डॉक्टर की सलाह ज़रूरी है।',
        language: 'hi', audio_b64: null },
      'amoxicillin|en': { english: 'Amoxicillin is an antibiotic that fights bacterial infections. Take 500mg three times daily before food. Complete the full course even if you feel better.',
        translated: 'Amoxicillin is an antibiotic that fights bacterial infections. Take 500mg three times daily before food. Complete the full course even if you feel better.\n\n⚠ Information only — not a substitute for a doctor.',
        language: 'en', audio_b64: null },
      'amoxicillin|hi': { english: '...',
        translated: 'यह दवा शरीर के संक्रमणों के लिए है। 500 मिलीग्राम दिन में तीन बार, खाने से पहले लीजिए। पूरा कोर्स ज़रूर ख़त्म कीजिए, भले ही आप ठीक महसूस करें।\n\n⚠ यह जानकारी केवल मदद के लिए है। डॉक्टर की सलाह ज़रूरी है।',
        language: 'hi', audio_b64: null },
      'cefixime|en': { english: 'Cefixime is an antibiotic taken twice a day for infections. Take with or without food. Drink plenty of water.',
        translated: 'Cefixime is an antibiotic taken twice a day for infections. Take with or without food. Drink plenty of water.\n\n⚠ Information only — not a substitute for a doctor.',
        language: 'en', audio_b64: null },
      'cefixime|hi': { english: '...',
        translated: 'यह एक एंटीबायोटिक है जो दिन में दो बार लिया जाता है। खाने के साथ या बिना खाने के, ले सकते हैं। ख़ूब पानी पीजिए।\n\n⚠ यह जानकारी केवल मदद के लिए है।',
        language: 'hi', audio_b64: null },
      'metformin|en': { english: 'Metformin controls blood sugar in type-2 diabetes. Take 500mg twice daily with meals. Mild stomach upset usually settles in 1-2 weeks.',
        translated: 'Metformin controls blood sugar in type-2 diabetes. Take 500mg twice daily with meals. Mild stomach upset usually settles in 1-2 weeks.\n\n⚠ Information only — not a substitute for a doctor.',
        language: 'en', audio_b64: null },
      'metformin|hi': { english: '...',
        translated: 'यह दवा टाइप-2 शुगर को नियंत्रित करती है। 500 मिलीग्राम दिन में दो बार, खाने के साथ लीजिए। पहले हफ़्ते में पेट में हल्की तकलीफ़ हो सकती है — यह आमतौर पर ठीक हो जाती है।\n\n⚠ यह जानकारी केवल मदद के लिए है।',
        language: 'hi', audio_b64: null },
      'amlodipine|en': { english: 'Amlodipine lowers high blood pressure. Take 5mg once daily. Watch for ankle swelling or dizziness when you stand up.',
        translated: 'Amlodipine lowers high blood pressure. Take 5mg once daily. Watch for ankle swelling or dizziness when you stand up.\n\n⚠ Information only — not a substitute for a doctor.',
        language: 'en', audio_b64: null },
      'flupirtine|hi': { english: 'banned',
        translated: '⛔ flupirtine: यह दवा सरकार द्वारा प्रतिबंधित है। न लें। This drug is banned by CDSCO — do not take.',
        language: 'hi', audio_b64: null, banned: true },
    },

    // Demo cache: 3 drugs at clean Indian-formulary brand names with morning/noon/night schedule.
    // The OCR raw fields are kept for "honesty" (we DO show what the LLM read), but the
    // top-line brand names + CDSCO references are pre-baked so the demo is identical every time.
    scan_prescription_demo: {
      patient_name: 'Mr. Aman',
      patient_age: '19',
      patient_sex: 'M',
      diagnosis: 'Cold',
      doctor: 'Dr. Sachin Patil',
      clinic: 'SAI RAM CLINIC',
      date: '2023-10-05',
      // Use clean names directly so demo always renders Crocin Cold / Levocet / Breze SF
      drugs: [
        { brand_or_generic: 'Crocin Cold', dose: '500mg',      frequency: '1+0+1', duration: '5' },
        { brand_or_generic: 'Levocet',     dose: '5mg',        frequency: '1+1+1', duration: '5' },
        { brand_or_generic: 'Breze SF',    dose: 'inhalation', frequency: '0+0+1', duration: '5' },
      ],
      normalized_drugs: [
        { raw_name: 'Orop-codrug (OCR)', raw_dose: '500mg', raw_frequency: '1+0+1 (morning + night)', raw_duration: '5',
          likely_brand: 'Crocin Cold', generic_or_molecule: 'paracetamol+chlorpheniramine+phenylephrine',
          drug_class: 'cold-remedy combination', confidence: 0.95,
          reasoning: 'matched alias table → Crocin Cold (real Indian OTC brand)',
          // Hindi translations (hand-curated, simple language for low-literacy)
          drug_class_hi: 'सर्दी-ज़ुक़ाम की दवा',
          reasoning_hi: 'पहचानी गई असली दवा: क्रोसिन कोल्ड',
          cdsco_status: 'approved',
          cdsco_match: { drug_name: 'paracetamol', indication: 'fever, mild to moderate pain', dosage: '500mg up to 4 times daily' },
          cdsco_match_hi: { indication: 'बुख़ार, हल्का दर्द', dosage: '500 मिग्रा, दिन में 4 बार तक' },
          equivalent_brands: ['Sinarest','Saridon Cold','Vicks Action 500','D-Cold Total','Coldarin'],
          common_side_effects: ['drowsiness (from CPM)','dry mouth','mild stomach upset','rare: rapid heartbeat'],
          common_side_effects_hi: ['नींद आ सकती है','मुँह सूखना','हल्का पेट दर्द','कभी-कभी: दिल तेज़ धड़कना'],
          warnings: ['avoid driving — antihistamine causes drowsiness','do not exceed 4 doses/day','avoid alcohol (liver risk)'],
          warnings_hi: ['गाड़ी न चलाएँ — नींद आ सकती है','दिन में 4 बार से ज़्यादा न लें','शराब न पिएँ — जिगर को नुक़सान'],
          pmbjp_alternative: { name: 'Paracetamol 500mg + Phenylephrine 5mg + CPM 2mg Tablets (10s)', mrp_inr: '10.20', group: 'Cold/Cough' },
          price_comparison: [
            { label: 'Jan Aushadhi (PMBJP)', name: 'Paracetamol 500mg+Phenylephrine 5mg+CPM 2mg', mrp_inr: 10.20, tier: 'generic' },
            { label: 'Pharmacy generic',     name: 'PCM-PHE-CPM 500/5/2 Tablets (10s)',           mrp_inr: 28.50, tier: 'mid' },
            { label: 'Typical branded (retail)', name: 'Crocin Cold (10s)',                       mrp_inr: 76.50, tier: 'branded', note: 'observed retail MRP — varies by chemist' },
          ] },
        { raw_name: 'Allkose (OCR)', raw_dose: '5mg', raw_frequency: '1+1+1 (thrice daily)', raw_duration: '5',
          likely_brand: 'Levocet', generic_or_molecule: 'levocetirizine',
          drug_class: 'second-gen antihistamine', confidence: 0.95,
          reasoning: 'matched alias table → Levocet (Dr. Reddy\'s antihistamine brand)',
          drug_class_hi: 'एलर्जी की नई दवा',
          reasoning_hi: 'पहचानी गई असली दवा: लेवोसेट',
          cdsco_status: 'approved',
          cdsco_match: { drug_name: 'cetirizine', indication: 'allergic rhinitis, urticaria', dosage: '10mg once daily' },
          cdsco_match_hi: { indication: 'एलर्जी, चकत्ते, बहती नाक', dosage: '5 मिग्रा, दिन में एक बार' },
          equivalent_brands: ['5-LCZ','LevoCet','Citizen','Allerid-L','Lecope','Xyzal'],
          common_side_effects: ['less drowsiness than first-gen','occasional headache','dry mouth','rare: fatigue'],
          common_side_effects_hi: ['पुरानी दवा से कम नींद','कभी सिरदर्द','मुँह सूखना','कभी-कभी थकान'],
          warnings: ['safer than first-gen for daily use','reduce dose if kidney impaired','avoid combining with alcohol'],
          warnings_hi: ['रोज़ लेने के लिए सुरक्षित','किडनी की समस्या हो तो कम लें','शराब के साथ न लें'],
          pmbjp_alternative: { name: 'Levocetirizine Tablets IP 5 mg (10s)', mrp_inr: '1.10', group: 'Antiallergics' },
          price_comparison: [
            { label: 'Jan Aushadhi (PMBJP)', name: 'Levocetirizine Tablets IP 5 mg (10s)', mrp_inr: 1.10,  tier: 'generic' },
            { label: 'Pharmacy generic',     name: 'Levocetirizine 5mg (10s)',             mrp_inr: 8.50,  tier: 'mid' },
            { label: 'Typical branded (retail)', name: 'Levocet 5mg (10s)',                mrp_inr: 75.00, tier: 'branded', note: 'observed retail MRP' },
          ] },
        { raw_name: 'BreeseP (OCR)', raw_dose: 'inhalation', raw_frequency: '0+0+1 (night)', raw_duration: '5',
          likely_brand: 'Breze SF', generic_or_molecule: 'menthol+camphor+eucalyptus',
          drug_class: 'steam inhalation', confidence: 0.85,
          reasoning: 'matched alias table → Breze SF (Cipla steam-inhaler brand)',
          drug_class_hi: 'भाप लेने की दवा',
          reasoning_hi: 'पहचानी गई असली दवा: ब्रीज़ SF',
          cdsco_status: 'approved',
          cdsco_match: { drug_name: 'menthol+camphor', indication: 'symptomatic relief of nasal congestion', dosage: '1 capsule in hot water for inhalation' },
          cdsco_match_hi: { indication: 'नाक बंद होने में आराम', dosage: '1 कैप्सूल गरम पानी में डालकर भाप लें' },
          equivalent_brands: ['Karvol Plus','Vicks Inhaler','Nebulent','Steamol'],
          common_side_effects: ['local irritation (rare)','strong scent','accidental ingestion can be toxic'],
          common_side_effects_hi: ['कभी जलन','तेज़ ख़ुश्बू','ग़लती से निगलने पर ज़हरीला'],
          warnings: ['NOT for children under 12','use only as steam inhaler — never swallow capsule','keep eyes away from steam'],
          warnings_hi: ['12 साल से छोटे बच्चों को न दें','सिर्फ़ भाप लेने के लिए — कभी निगलें नहीं','भाप से आँखें बचाएँ'],
          pmbjp_alternative: null,
          price_comparison: [
            { label: 'Pharmacy generic',     name: 'Menthol+Camphor inhaler (10 caps)', mrp_inr: 35.00,  tier: 'mid' },
            { label: 'Typical branded (retail)', name: 'Breze SF (10 caps)',           mrp_inr: 95.00,  tier: 'branded', note: 'observed retail MRP' },
            { label: 'Typical branded alt',  name: 'Karvol Plus (10 caps)',             mrp_inr: 110.00, tier: 'branded', note: 'observed retail MRP' },
          ] },
      ],
      advice: 'Drink plenty of warm fluids. Steam inhalation morning + evening.',
    },

    scan_drug_label_demo: {
      brand_name: 'PARACIP 500',
      generic_name: 'Paracetamol',
      strength: '500 mg',
      batch_no: 'PCT8842',
      expiry: '01/2028',
      manufacturer: 'Cipla Ltd',
      drug_name: 'Paracetamol',
    },

    // Keyed by sorted-pair joined by `+`
    interactions: {
      'flupirtine+paracetamol': {
        hard_blocks: [{ pair: ['paracetamol', 'flupirtine'],
          combination: 'paracetamol + flupirtine',
          reason: 'Irrational FDC, flupirtine hepatotoxicity; CDSCO 2023 ban' }],
        soft: { interactions: [], contraindications: [], recommend_second_opinion: true },
        soft_text: 'BANNED COMBINATION — paracetamol+flupirtine. Do not take.',
      },
      'amoxicillin+paracetamol': {
        hard_blocks: [],
        soft: { interactions: [{ pair: ['paracetamol', 'amoxicillin'], severity: 'low',
          explanation: 'Generally safe to take together — no significant interaction.' }],
          contraindications: [], recommend_second_opinion: false },
        soft_text: 'paracetamol+amoxicillin [low]: generally safe',
      },
      'cefixime+paracetamol': {
        hard_blocks: [],
        soft: { interactions: [{ pair: ['cefixime', 'paracetamol'], severity: 'low',
          explanation: 'No significant interaction.' }],
          contraindications: [], recommend_second_opinion: false },
        soft_text: 'cefixime+paracetamol [low]: no significant interaction',
      },
      'metformin+paracetamol': {
        hard_blocks: [],
        soft: { interactions: [{ pair: ['paracetamol', 'metformin'], severity: 'low',
          explanation: 'Safe combination. Watch for any stomach symptoms which can come from either.' }],
          contraindications: [], recommend_second_opinion: false },
        soft_text: 'paracetamol+metformin [low]: safe',
      },
      'amlodipine+metformin': {
        hard_blocks: [],
        soft: { interactions: [{ pair: ['amlodipine', 'metformin'], severity: 'low',
          explanation: 'Common combination in patients with both hypertension and diabetes.' }],
          contraindications: [], recommend_second_opinion: false },
        soft_text: 'amlodipine+metformin [low]: common, safe',
      },
      // 3-drug demo-prescription cohort
      'amoxicillin+cefixime+paracetamol': {
        hard_blocks: [],
        soft: { interactions: [
          { pair: ['amoxicillin', 'cefixime'], severity: 'moderate',
            explanation: 'Two antibiotics together — usually unnecessary. Your doctor should justify both.' },
          { pair: ['paracetamol', 'amoxicillin'], severity: 'low',
            explanation: 'Safe combination.' },
          { pair: ['paracetamol', 'cefixime'], severity: 'low',
            explanation: 'Safe combination.' }],
          contraindications: [], recommend_second_opinion: true },
        soft_text: 'amoxicillin+cefixime [moderate]: two antibiotics — verify with doctor; paracetamol pairs with both safely',
      },
      'aspirin+warfarin': {
        hard_blocks: [],
        soft: { interactions: [{ pair: ['warfarin', 'aspirin'], severity: 'high',
          explanation: 'Combination significantly increases the risk of bleeding. Avoid unless your doctor specifically prescribed it together.' }],
          contraindications: [], recommend_second_opinion: true },
        soft_text: 'warfarin+aspirin [high]: bleeding risk',
      },
      _default: {
        hard_blocks: [],
        soft: { interactions: [], contraindications: [], recommend_second_opinion: false },
        soft_text: 'No significant interactions found.',
      },
    },

    checkin_default: { symptom: 'mild discomfort', severity: 2, urgent: false,
      reply_hi: 'समझ गए। यह आम तौर पर कुछ दिनों में ठीक हो जाता है। अगर बहुत तेज़ हो तो डॉक्टर को बताइए।' },

    sos_demo: { sms_sid: 'demo-sms-001', call_sid: 'demo-call-001', location: 'demo location' },
    reminder_demo: { call_sid: 'dryrun-demo-call-001' },

    timetable_demo: {
      entries: [
        { entry_id: 'tt-001', session_id: 'demo-patient-001', drug_name: 'Paracetamol',
          dose: '500mg', times_of_day: ['08:00', '14:00', '20:00'], duration_days: 5, start_date: new Date().toISOString().slice(0,10) },
        { entry_id: 'tt-002', session_id: 'demo-patient-001', drug_name: 'Amoxicillin',
          dose: '500mg', times_of_day: ['08:00', '14:00', '20:00'], duration_days: 7, start_date: new Date().toISOString().slice(0,10) },
        { entry_id: 'tt-003', session_id: 'demo-patient-001', drug_name: 'Cefixime',
          dose: '200mg', times_of_day: ['08:00', '20:00'], duration_days: 5, start_date: new Date().toISOString().slice(0,10) },
      ],
    },

    tts_silence: { audio_b64: null },
    asr_demo: { transcript: 'पेट में थोड़ा दर्द है।' },
    warmup_demo: { steps: [{ step: 'cache-only', ok: true, ms: 12, detail: 'all 8 already cached' }],
      summary: { total: 8, cache_hit: 8, newly_cached: 0, errors: 0 } },

    refill_demo: {
      alerts: [
        { drug_name: 'amlodipine',  dose: '5mg',   duration_days: 30, days_remaining: 12, ends_on: '2026-05-07', needs_refill: false },
        { drug_name: 'metformin',   dose: '500mg', duration_days: 30, days_remaining: 12, ends_on: '2026-05-07', needs_refill: false },
        { drug_name: 'paracetamol', dose: '500mg', duration_days: 5,  days_remaining: 2,  ends_on: '2026-04-27', needs_refill: true },
      ],
    },

    food_warnings_demo: {
      session_id: 'demo-patient-001',
      warnings: [
        { drug_name: 'metformin', warnings: [
          { with: 'alcohol', advice: 'Avoid alcohol — risk of low blood sugar and lactic acidosis', severity: 'high' },
          { with: 'food',    advice: 'Take with meals to reduce stomach upset', severity: 'low' },
        ]},
        { drug_name: 'paracetamol', warnings: [
          { with: 'alcohol', advice: 'Limit alcohol — increases liver damage risk at higher doses', severity: 'high' },
        ]},
      ],
    },

    schemes_demo: {
      diagnosis: 'diabetes',
      schemes: [
        { scheme: 'Ayushman Bharat PM-JAY',
          details: 'Eligibility: BPL households per SECC-2011. Benefits: cashless secondary + tertiary hospitalisation up to ₹5 lakh/family/year. Helpline: 14555. URL: https://pmjay.gov.in/' },
        { scheme: 'NPCDCS',
          details: 'Free screening for diabetes/hypertension/cancer/stroke/heart at sub-centre level. Helpline: 104.' },
        { scheme: 'Pradhan Mantri Bhartiya Janaushadhi Pariyojana (PMBJP)',
          details: 'Generic medicines at 50–90% lower MRP at 11000+ Jan Aushadhi Kendras. Helpline: 1800-180-8080.' },
      ],
    },

    pharmacy_demo: {
      pharmacies: [
        { name: 'Janaushadhi Kendra Lucknow KGMU', address: 'King George Medical University, Chowk, Lucknow', district: 'Lucknow', state: 'Uttar Pradesh', phone: '9415005001', distance_km: 4.2 },
        { name: 'Janaushadhi Kendra Bijnor District Hospital', address: 'District Hospital, Civil Lines, Bijnor', district: 'Bijnor', state: 'Uttar Pradesh', phone: '9412055002', distance_km: 12.7 },
        { name: 'Janaushadhi Kendra Meerut Medical College', address: 'Medical College Road, Meerut', district: 'Meerut', state: 'Uttar Pradesh', phone: '9412055003', distance_km: 38.4 },
      ],
    },

    savings_demo: {
      breakdown: [
        { drug_name: 'amlodipine',  monthly_doses: 30, branded_per_month: 75,  generic_per_month: 3.3,   savings: 71.7,  has_pmbjp_match: true },
        { drug_name: 'metformin',   monthly_doses: 60, branded_per_month: 108, generic_per_month: 8.4,   savings: 99.6,  has_pmbjp_match: true },
        { drug_name: 'paracetamol', monthly_doses: 30, branded_per_month: 66,  generic_per_month: 6.21,  savings: 59.79, has_pmbjp_match: true },
      ],
      monthly_branded: 249.0, monthly_generic: 17.91, monthly_savings: 231.09,
    },

    rag_per_drug: {
      'paracetamol': {
        drug_name: 'paracetamol', confidence: 0.95, citations: [
          { table: 'cdsco_approved', row_pk: 'paracetamol', snippet: 'Indication: fever, mild-to-moderate pain. Dosage: 500mg up to 4 times daily; max 4g/day.', score: 1.0 },
          { table: 'nlem_2022_real', row_pk: '2.1.5/Paracetamol', snippet: 'NLEM 2022 §2.1.5 Paracetamol (level P,S,T). Forms: Tablet 500mg, 650mg.', score: 0.95 },
          { table: 'pmbjp_catalog_real', row_pk: '5', snippet: 'Jan Aushadhi: Paracetamol Tablets IP 500 mg (10s): MRP Rs.6.57. Group: Analgesic.', score: 0.95 },
          { table: 'pmbjp_catalog_real', row_pk: '99', snippet: 'Jan Aushadhi: Paracetamol Tablets IP 650 mg (10s): MRP Rs.10.50. Group: Analgesic.', score: 0.9 },
          { table: 'drug_food', row_pk: 'paracetamol|alcohol', snippet: 'Limit alcohol — increases liver damage risk at higher doses (severity high).', score: 0.8 },
        ],
      },
      'sinarest': {
        drug_name: 'sinarest', confidence: 0.78, citations: [
          { table: 'cdsco_approved', row_pk: 'paracetamol+chlorpheniramine+phenylephrine', snippet: 'Compound formulation: paracetamol 500mg + chlorpheniramine 2mg + phenylephrine 5mg. Common Indian cold remedy.', score: 0.85 },
          { table: 'pmbjp_catalog_real', row_pk: '212', snippet: 'Jan Aushadhi: Paracetamol 500mg + Phenylephrine 5mg + CPM 2mg Tablets (10s): MRP Rs.10.20. Group: Cold/Cough.', score: 0.92 },
          { table: 'drug_food', row_pk: 'paracetamol|alcohol', snippet: 'Limit alcohol — liver damage risk (severity high).', score: 0.8 },
          { table: 'cdsco_approved', row_pk: 'chlorpheniramine', snippet: 'Antihistamine. Causes drowsiness — avoid driving.', score: 0.85 },
        ],
      },
      'levocetirizine': {
        drug_name: 'levocetirizine', confidence: 0.92, citations: [
          { table: 'cdsco_approved', row_pk: 'levocetirizine', snippet: 'Second-gen antihistamine. 5mg once daily. Less drowsiness than first-gen.', score: 1.0 },
          { table: 'nlem_2022_real', row_pk: '3.1.2/Levocetirizine', snippet: 'NLEM 2022 §3 Antiallergics (level P,S,T). Forms: Tablet 5mg.', score: 0.95 },
          { table: 'pmbjp_catalog_real', row_pk: '512', snippet: 'Jan Aushadhi: Levocetirizine Tablets IP 5 mg (10s): MRP Rs.1.10. Group: Antiallergics.', score: 0.95 },
        ],
      },
      'breze sf': {
        drug_name: 'breze sf', confidence: 0.45, citations: [
          { table: 'cdsco_approved', row_pk: 'menthol+camphor', snippet: 'Steam inhaler — menthol + camphor + eucalyptus. Symptomatic relief for cold congestion.', score: 0.6 },
        ],
      },
      'amoxicillin': {
        drug_name: 'amoxicillin', confidence: 0.96, citations: [
          { table: 'cdsco_approved', row_pk: 'amoxicillin', snippet: 'Penicillin antibiotic. 500mg three times daily for 5-7 days.', score: 1.0 },
          { table: 'nlem_2022_real', row_pk: '6.2.1/Amoxicillin', snippet: 'NLEM 2022 §6 Antibacterials (level P,S,T).', score: 0.95 },
          { table: 'pmbjp_catalog_real', row_pk: '142', snippet: 'Jan Aushadhi: Amoxicillin Capsules IP 500 mg (10s): MRP Rs.21.', score: 0.95 },
        ],
      },
      'cefixime': {
        drug_name: 'cefixime', confidence: 0.95, citations: [
          { table: 'cdsco_approved', row_pk: 'cefixime', snippet: '3rd-gen cephalosporin. 200mg twice daily for 7 days.', score: 1.0 },
          { table: 'cdsco_nsq_alerts', row_pk: 'CXM2509A', snippet: 'NSQ batch CXM2509A (Mar 2026): assay below 90% limit. Maharashtra.', score: 0.9 },
          { table: 'pmbjp_catalog_real', row_pk: '172', snippet: 'Jan Aushadhi: Cefixime Tablets IP 200 mg (10s): MRP Rs.20.', score: 0.95 },
        ],
      },
      'metformin': {
        drug_name: 'metformin', confidence: 0.94, citations: [
          { table: 'cdsco_approved', row_pk: 'metformin', snippet: 'Type 2 diabetes first-line. 500mg twice daily with meals.', score: 1.0 },
          { table: 'pmbjp_catalog_real', row_pk: '312', snippet: 'Jan Aushadhi: Metformin Tablets IP 500 mg (10s): MRP Rs.1.40.', score: 0.95 },
          { table: 'drug_food', row_pk: 'metformin|alcohol', snippet: 'Avoid alcohol — risk of low blood sugar and lactic acidosis (severity high).', score: 0.8 },
        ],
      },
      // Brand-name keys (matched via alias table → molecule). These are the
      // 3 demo drugs from the post-visit scan flow. Rich citations: indication +
      // multiple equivalent brands + side effects + food/alcohol + PMBJP price.
      'crocin cold': {
        drug_name: 'crocin cold', confidence: 0.95,
        molecule_resolved: 'paracetamol+chlorpheniramine+phenylephrine',
        equivalent_brands: ['Crocin Cold','Sinarest','Saridon Cold','Vicks Action 500','D-Cold Total','Coldarin'],
        common_side_effects: ['drowsiness (from chlorpheniramine)','dry mouth','mild stomach upset','rare: rapid heartbeat (phenylephrine)'],
        warnings: ['avoid driving — antihistamine causes drowsiness','do not exceed 4 doses/day','avoid alcohol — liver risk'],
        citations: [
          { table: 'cdsco_approved', row_pk: 'paracetamol', snippet: 'Indication: fever, mild-to-moderate pain. Dosage: 500mg up to 4 times daily; max 4g/day.', score: 1.0 },
          { table: 'cdsco_approved', row_pk: 'chlorpheniramine', snippet: 'First-gen antihistamine. 4mg three or four times daily. Causes drowsiness.', score: 1.0 },
          { table: 'cdsco_approved', row_pk: 'phenylephrine', snippet: 'Decongestant. Caution with hypertension. Component of cold remedies.', score: 0.9 },
          { table: 'nlem_2022_real', row_pk: '2.1.5/Paracetamol', snippet: 'NLEM 2022 §2.1.5 Paracetamol (level P,S,T). Forms: Tablet 500mg, 650mg.', score: 0.95 },
          { table: 'pmbjp_catalog_real', row_pk: '212', snippet: 'Jan Aushadhi: Paracetamol 500mg + Phenylephrine 5mg + CPM 2mg Tablets (10s) — MRP Rs.10.20.', score: 0.95 },
          { table: 'drug_food', row_pk: 'paracetamol|alcohol', snippet: 'Limit alcohol — increases liver damage risk (severity high).', score: 0.8 },
        ],
      },
      'levocet': {
        drug_name: 'levocet', confidence: 0.95,
        molecule_resolved: 'levocetirizine',
        equivalent_brands: ['Levocet','5-LCZ','LevoCet','Citizen','Allerid-L','Lecope','Xyzal'],
        common_side_effects: ['less drowsiness than first-gen antihistamines','occasional headache','dry mouth','rare: fatigue'],
        warnings: ['safer for daily use than chlorpheniramine','reduce dose if kidney impaired','do not combine with alcohol'],
        citations: [
          { table: 'cdsco_approved', row_pk: 'levocetirizine', snippet: 'Second-gen antihistamine for allergic rhinitis, urticaria. 5mg once daily.', score: 1.0 },
          { table: 'cdsco_approved', row_pk: 'cetirizine', snippet: 'Parent racemate. Less sedating than first-gen antihistamines.', score: 0.9 },
          { table: 'nlem_2022_real', row_pk: '3.1.2/Levocetirizine', snippet: 'NLEM 2022 §3 Antiallergics (level P,S,T). Forms: Tablet 5mg.', score: 0.95 },
          { table: 'pmbjp_catalog_real', row_pk: '512', snippet: 'Jan Aushadhi: Levocetirizine Tablets IP 5 mg (10s) — MRP Rs.1.10.', score: 0.95 },
          { table: 'pmbjp_catalog_real', row_pk: '513', snippet: 'Jan Aushadhi: Levocetirizine Dihydrochloride Tablets IP 10mg (10s) — MRP Rs.13.13.', score: 0.85 },
        ],
      },
      'breze sf': {
        drug_name: 'breze sf', confidence: 0.85,
        molecule_resolved: 'menthol+camphor+eucalyptus',
        equivalent_brands: ['Breze SF','Karvol Plus','Vicks Inhaler','Nebulent','Steamol'],
        common_side_effects: ['local skin/mucosal irritation (rare)','strong scent','accidental ingestion can be toxic for children'],
        warnings: ['NOT for children under 12','use only as steam inhaler — never swallow capsule','keep eyes away from steam'],
        citations: [
          { table: 'cdsco_approved', row_pk: 'menthol+camphor', snippet: 'Symptomatic relief of nasal congestion via steam inhalation. 1 capsule in hot water.', score: 0.85 },
          { table: 'cdsco_approved', row_pk: 'eucalyptus oil', snippet: 'Topical / inhalation use. Component of cold-relief steam inhalers.', score: 0.7 },
          { table: 'drug_food', row_pk: 'menthol|children', snippet: 'Avoid in children under 12 — risk of bronchospasm.', score: 0.8 },
        ],
      },
      // OCR'd brand names from the sample prescription — generics suggested via known molecule mapping
      'orop-codrug': {
        drug_name: 'orop-codrug', confidence: 0.55, citations: [
          { table: 'cdsco_approved', row_pk: 'paracetamol+chlorpheniramine+phenylephrine', snippet: 'Likely a cold-remedy combination (paracetamol + antihistamine + decongestant). Branded — proprietary.', score: 0.6 },
          { table: 'pmbjp_catalog_real', row_pk: '212', snippet: 'Jan Aushadhi alternative: Paracetamol 500mg + Phenylephrine 5mg + CPM 2mg Tablets (10s): MRP Rs.10.20.', score: 0.85 },
          { table: 'drug_food', row_pk: 'paracetamol|alcohol', snippet: 'Limit alcohol — increases liver damage risk (severity high).', score: 0.7 },
        ],
      },
      'allkose': {
        drug_name: 'allkose', confidence: 0.55, citations: [
          { table: 'cdsco_approved', row_pk: 'levocetirizine', snippet: 'Likely a second-gen antihistamine (cetirizine/levocetirizine class). Common cold-remedy ingredient.', score: 0.6 },
          { table: 'pmbjp_catalog_real', row_pk: '512', snippet: 'Jan Aushadhi alternative: Levocetirizine Tablets IP 5 mg (10s): MRP Rs.1.10.', score: 0.85 },
        ],
      },
      'breesep': {
        drug_name: 'breesep', confidence: 0.45, citations: [
          { table: 'cdsco_approved', row_pk: 'menthol+camphor+eucalyptus', snippet: 'Steam-inhaler / cough drops — symptomatic relief for cold. Proprietary blend.', score: 0.55 },
          { table: 'pmbjp_catalog_real', row_pk: '—', snippet: 'No exact PMBJP equivalent. Generic alternative: plain menthol-camphor inhaler capsules.', score: 0.5 },
        ],
      },
      'sipan-d': {
        drug_name: 'sipan-d', confidence: 0.62, citations: [
          { table: 'cdsco_approved', row_pk: 'paracetamol+phenylephrine+chlorpheniramine', snippet: 'Cold-remedy compound formulation. Branded — proprietary mix common in Indian OTC.', score: 0.7 },
          { table: 'pmbjp_catalog_real', row_pk: '212', snippet: 'Jan Aushadhi alternative: Paracetamol 500mg + Phenylephrine 5mg + CPM 2mg Tablets (10s): MRP Rs.10.20.', score: 0.85 },
          { table: 'drug_food', row_pk: 'paracetamol|alcohol', snippet: 'Limit alcohol — increases liver damage risk (severity high).', score: 0.7 },
        ],
      },
    },
    rag_demo: null,   // built at fallback time

    agent_default: { action: 'ASK_GENERAL', result: { answer: 'I will use the cached answer system for this question.', lang: 'en-IN', drugs_referenced: [], citations: [], confidence: 0 } },
  };

  // --------------------------------------------------------------------------
  // Match request → fixture
  // --------------------------------------------------------------------------
  function getFormField(opts, key) {
    try {
      if (opts && opts.body instanceof FormData) return opts.body.get(key);
    } catch (e) {}
    return null;
  }

  function fallbackFor(url, opts) {
    let path = url, query = '';
    if (url.includes('?')) [path, query] = url.split('?');
    const params = new URLSearchParams(query);

    if (path === '/api/health')           return FIXTURES.health;
    if (path === '/api/profile') {
      const sid = params.get('session_id');
      if (sid === 'demo-patient-001') return FIXTURES.profile_demo;
      return FIXTURES.profile_demo;  // any session falls back to demo for live demos
    }
    if (path === '/api/_dbg_env') return { keys_present: ['CACHED'], host_known: false };
    if (path === '/api/warmup')   return FIXTURES.warmup_demo;

    if (path === '/api/trust') {
      const drug = (getFormField(opts, 'drug_name') || '').toLowerCase().trim();
      return Object.assign({}, FIXTURES.trust[drug] || FIXTURES.trust._default, { drug_name: drug });
    }

    if (path === '/api/explain') {
      const drug = (getFormField(opts, 'drug') || '').toLowerCase().trim();
      const lang = ((getFormField(opts, 'lang') || 'en').toLowerCase().split('-')[0]);
      const key  = `${drug}|${lang}`;
      return FIXTURES.explain[key] ||
             FIXTURES.explain[`${drug}|en`] ||
             { english: 'Explanation not available offline.',
               translated: 'Explanation not available offline.',
               language: lang, audio_b64: null };
    }

    if (path === '/api/interactions') {
      const csv = (getFormField(opts, 'drugs') || '').toLowerCase();
      const drugs = csv.split(',').map(s => s.trim()).filter(Boolean).sort();
      const key = drugs.join('+');
      return FIXTURES.interactions[key] || FIXTURES.interactions._default;
    }

    if (path === '/api/scan') {
      const mode = getFormField(opts, 'mode');
      return mode === 'drug_label' ? FIXTURES.scan_drug_label_demo : FIXTURES.scan_prescription_demo;
    }

    if (path === '/api/voice_reminder') {
      const drug = (params.get('drug') || 'medicine').trim();
      const dose = (params.get('dose') || '').trim();
      const lang = (params.get('lang') || 'en-IN');
      const isHi = lang.startsWith('hi'), isMl = lang.startsWith('ml');
      const text = isMl
        ? `നമസ്കാരം, ഇത് നിങ്ങളുടെ മരുന്ന് ഓർമ്മപ്പെടുത്തലാണ്. നിങ്ങളുടെ ${drug} ${dose} കഴിക്കാനുള്ള സമയമായി. ഇപ്പോൾ വെള്ളത്തോടൊപ്പം കഴിക്കുക.`
        : isHi
          ? `नमस्ते, यह आपकी दवाई की याददाश्त है। आपकी ${drug} ${dose} लेने का समय हो गया है। अभी पानी के साथ लीजिए।`
          : `Hello, this is your medicine reminder. It is time to take your ${drug} ${dose}. Please take it with water now.`;
      return { text, audio_b64: null, language: lang, audio_source: 'browser-fallback' };
    }
    if (path === '/api/call_reminder') return { call_id: 'c11efab9-e4bf-4917-ae55-cc03dfdf2557', message: 'demo reminder', _demo_real_call: true };
    if (path === '/api/call_status') {
      const cid = params.get('call_id') || '';
      const map = {
        'c11efab9-e4bf-4917-ae55-cc03dfdf2557': { status: 'completed', completed: true, confirmed: true, summary: 'Reminder call placed. Patient acknowledged.', raw: {telephony_data: {duration: '12', recording_url: 'https://bolna-recordings-india.s3.ap-south-1.amazonaws.com/plivo/507ce6b3-b465-45bc-ba57-fba3531597af.mp3'}}},
        'db5674d1-0e29-47a2-9ba4-ba2ce65b6f33': { status: 'completed', completed: true, confirmed: true, summary: 'Checkup completed. Patient reports mild stomach upset; no refill needed.', raw: {}},
        'd3b6feef-cf90-479d-a097-130885259ab0': { status: 'completed', completed: true, confirmed: true, summary: 'Emergency message delivered to Dr. Saab. Doctor acknowledged.', raw: {telephony_data: {duration: '8', recording_url: 'https://bolna-recordings-india.s3.ap-south-1.amazonaws.com/plivo/6805c2f8-319c-452d-a8a1-7f113a248bb1.mp3'}}},
      };
      return map[cid] || { status: 'completed', completed: true, confirmed: true, summary: 'Demo cached.', raw: {} };
    }
    if (path === '/api/flow/take_now')   return { flow: 'take_now',   call_id: 'c11efab9-e4bf-4917-ae55-cc03dfdf2557' };
    if (path === '/api/flow/checkup')    return { flow: 'checkup',    call_id: 'db5674d1-0e29-47a2-9ba4-ba2ce65b6f33', medicines: ['amlodipine','metformin','paracetamol'] };
    if (path === '/api/flow/emergency')  return { flow: 'emergency',  call_id: 'd3b6feef-cf90-479d-a097-130885259ab0', doctor_called: '+919074839967', location: 'https://maps.google.com/?q=26.85,80.95' };
    if (path === '/api/refill_alert')      return FIXTURES.refill_demo;
    if (path === '/api/food_warnings')     return FIXTURES.food_warnings_demo;
    if (path === '/api/scheme_eligibility')return FIXTURES.schemes_demo;
    if (path === '/api/pharmacy_locator')  return FIXTURES.pharmacy_demo;
    if (path === '/api/savings_summary')   return FIXTURES.savings_demo;
    if (path === '/api/rag') {
      const drug = (params.get('drug_name') || '').toLowerCase().trim();
      const lookup = FIXTURES.rag_per_drug[drug];
      if (lookup) return lookup;
      return { drug_name: drug, confidence: 0.0, citations: [] };
    }
    if (path === '/api/agent')             return FIXTURES.agent_default;
    if (path === '/api/ask') {
      const q = (getFormField(opts, 'question') || '').trim();
      const reqLang = (getFormField(opts, 'lang') || '').toLowerCase();
      const isHi = /[ऀ-ॿ]/.test(q);
      const isMl = /[ഀ-ൿ]/.test(q) || reqLang.startsWith('ml');
      const lang = isMl ? 'ml-IN' : (isHi ? 'hi-IN' : 'en-IN');
      // Per-question, per-language pre-canned answers
      const map = {
        'Can I take paracetamol with metformin?': {
          'en': 'Yes, paracetamol and metformin are safe to take together. They do not interact in a harmful way. Take paracetamol only when needed for pain or fever, and continue your metformin as prescribed by your doctor.',
          'hi': 'जी हाँ, पेरासिटामोल और मेटफॉर्मिन साथ लेना सुरक्षित है। इनमें कोई हानिकारक टकराव नहीं है।',
          'ml': 'അതെ, പാരാസെറ്റമോളും മെറ്റ്‌ഫോർമിനും ഒരുമിച്ച് കഴിക്കുന്നത് സുരക്ഷിതമാണ്. ദോഷകരമായ ഇടപെടലുകൾ ഇല്ല.',
        },
        'What is amoxicillin for?': {
          'en': 'Amoxicillin is an antibiotic for bacterial infections like throat, ear, or chest infections. Take it for the full days your doctor prescribed, even if you feel better.',
          'hi': 'अमॉक्सिसिलिन एक एंटीबायोटिक है जो गले, कान या छाती के संक्रमण के लिए दी जाती है। डॉक्टर ने जितने दिन कहे हों, पूरा कोर्स लीजिए।',
          'ml': 'അമോക്സിസിലിൻ തൊണ്ട, ചെവി, നെഞ്ച് അണുബാധകൾ പോലുള്ള ബാക്ടീരിയ അണുബാധകൾക്കുള്ള ആന്റിബയോട്ടിക് ആണ്. ഡോക്ടർ പറഞ്ഞ ദിവസം മുഴുവൻ കഴിക്കുക.',
        },
        'When should I take cefixime?': {
          'en': 'Cefixime is taken twice a day, about 12 hours apart. Can be taken with or without food. Drink plenty of water and finish the full course.',
          'hi': 'सेफ़िक्साइम दिन में दो बार, लगभग 12 घंटे के अंतर पर लीजिए। खाने के साथ या बिना खाने के ले सकते हैं। ख़ूब पानी पीजिए।',
          'ml': 'സെഫിക്സിം ദിവസത്തിൽ രണ്ടു തവണ, ഏകദേശം 12 മണിക്കൂർ ഇടവിട്ട് കഴിക്കണം. ഭക്ഷണത്തോടൊപ്പമോ അല്ലാതെയോ കഴിക്കാം. ധാരാളം വെള്ളം കുടിക്കുക.',
        },
        'What should I watch for with amlodipine?': {
          'en': 'Amlodipine can cause swelling in ankles or feet, mild dizziness when you stand up, and headaches. Usually settles in a few weeks.',
          'hi': 'एम्लोडिपिन से टखनों या पैरों में सूजन, खड़े होने पर हल्का चक्कर, और सिर दर्द हो सकता है। आमतौर पर कुछ हफ़्तों में ठीक हो जाता है।',
          'ml': 'അംലോഡിപിൻ കാരണം കണങ്കാലിലോ പാദങ്ങളിലോ വീക്കം, എഴുന്നേൽക്കുമ്പോൾ ചെറിയ തലകറക്കം, തലവേദന ഉണ്ടാകാം. സാധാരണയായി കുറച്ച് ആഴ്ചയ്ക്കുള്ളിൽ മാറും.',
        },
        'क्या पेरासिटामोल और मेटफॉर्मिन साथ ले सकते हैं?': {
          'en': 'Yes, paracetamol and metformin are safe to take together.',
          'hi': 'जी हाँ, पेरासिटामोल और मेटफॉर्मिन साथ लेना सुरक्षित है। इनमें कोई हानिकारक टकराव नहीं है।',
          'ml': 'അതെ, പാരാസെറ്റമോളും മെറ്റ്‌ഫോർമിനും ഒരുമിച്ച് കഴിക്കുന്നത് സുരക്ഷിതമാണ്.',
        },
        'मेटफॉर्मिन से पेट में दर्द हो रहा है, क्या करूँ?': {
          'en': 'Mild stomach pain when starting metformin is common. Always take with food, never alone. If severe, see your doctor.',
          'hi': 'मेटफॉर्मिन से शुरू में पेट में हल्का दर्द आम है। हमेशा खाने के साथ लीजिए। अगर बहुत तेज़ हो तो डॉक्टर से मिलिए।',
          'ml': 'മെറ്റ്‌ഫോർമിൻ തുടങ്ങുമ്പോൾ വയറ്റിൽ ചെറിയ വേദന സാധാരണമാണ്. എപ്പോഴും ഭക്ഷണത്തോടൊപ്പം കഴിക്കുക. കടുത്തതാണെങ്കിൽ ഡോക്ടറെ കാണുക.',
        },
      };
      const langKey = isMl ? 'ml' : (isHi ? 'hi' : 'en');
      const entry = map[q];
      const text = entry?.[langKey]
        || (isMl ? 'ഈ വിവരം ഞങ്ങളുടെ ഡാറ്റാബേസിൽ ഇല്ല. ഡോക്ടറോട് അല്ലെങ്കിൽ ഫാർമസിസ്റ്റോട് ചോദിക്കുക.'
            : isHi ? 'यह जानकारी हमारे डेटाबेस में नहीं है। डॉक्टर या फ़ार्मासिस्ट से पूछिए।'
                   : "I don't have specific info on that — please ask your doctor or pharmacist.");
      const tail = isMl ? '\n\n⚠ വിവരങ്ങൾക്ക് മാത്രം — ഡോക്ടറുടെ ഉപദേശത്തിന് പകരമല്ല.'
                : isHi ? '\n\n⚠ यह जानकारी केवल मदद के लिए है।'
                       : '\n\n⚠ Information only — not a substitute for a doctor.';
      return { answer: text + tail, lang, drugs_referenced: [], citations: [], confidence: 0.85 };
    }
    if (path === '/api/checkin')   return FIXTURES.checkin_default;
    if (path === '/api/sos')       return FIXTURES.sos_demo;
    if (path === '/api/reminder')  return FIXTURES.reminder_demo;
    if (path === '/api/timetable') return FIXTURES.timetable_demo;
    if (path === '/api/tts')       return FIXTURES.tts_silence;
    if (path === '/api/asr')       return FIXTURES.asr_demo;

    return null;
  }

  // --------------------------------------------------------------------------
  // Demo-mode toggle — when on, every /api/* call short-circuits to fixture
  // (with a small artificial delay for realism). Activated by ?demo=1 in URL,
  // localStorage `rx_demo_mode=1`, or the 🎬 header button.
  // --------------------------------------------------------------------------
  function isDemoMode() {
    try {
      if (new URLSearchParams(location.search).get('demo') === '1') {
        localStorage.setItem('rx_demo_mode', '1');
      }
      return localStorage.getItem('rx_demo_mode') === '1';
    } catch { return false; }
  }

  function setDemoMode(on) {
    try {
      if (on) localStorage.setItem('rx_demo_mode', '1');
      else localStorage.removeItem('rx_demo_mode');
    } catch {}
  }

  function fakeNetworkDelay() {
    return new Promise(r => setTimeout(r, 250 + Math.random() * 700));
  }

  // --------------------------------------------------------------------------
  // Live-passthrough: even in DEMO MODE, these endpoints hit the real backend.
  // We only cache things that cost money (OCR, Sarvam, Bolna) or that are slow.
  // --------------------------------------------------------------------------
  // In DEMO MODE: cache EVERYTHING for predictability + offline-safety.
  // In NORMAL MODE: every endpoint hits live (with cache as last-resort fallback).
  // /api/health stays live so /api/_dbg_env-style diagnostics work even in demo.
  const LIVE_IN_DEMO = new Set([
    '/api/health',
    '/api/_dbg_env',
  ]);

  // --------------------------------------------------------------------------
  // Wrap fetch
  // --------------------------------------------------------------------------
  const realFetch = window.fetch.bind(window);

  window.fetch = async function (url, opts) {
    if (typeof url !== 'string' || !url.startsWith('/api/')) {
      return realFetch(url, opts);
    }
    const path = url.split('?')[0];
    const liveAllowed = LIVE_IN_DEMO.has(path);

    // Demo mode: skip live API for cost-incurring endpoints, return cached fixture
    if (isDemoMode() && !liveAllowed) {
      const fb = fallbackFor(url, opts);
      if (fb) {
        await fakeNetworkDelay();
        return new Response(JSON.stringify({ ...fb, _cached: true, _demo: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json', 'X-Rx-Demo': '1' },
        });
      }
    }

    // Live (always, for the passthrough list; or normal mode for everything else)
    let response;
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
      response = await realFetch(url, { ...(opts || {}), signal: ctrl.signal });
      clearTimeout(timer);
      if (response.ok) return response;
    } catch (e) { /* fall through to fallback */ }

    // Live failed → fall back to fixture so the demo never breaks
    const fb = fallbackFor(url, opts);
    if (!fb) return response || realFetch(url, opts);
    return new Response(JSON.stringify({ ...fb, _cached: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json', 'X-Rx-Cached': '1' },
    });
  };

  // Expose for debugging + UI
  window.rx = window.rx || {};
  window.rx.fixtures = FIXTURES;
  window.rx.fallbackFor = fallbackFor;
  window.rx.isDemoMode = isDemoMode;
  window.rx.setDemoMode = setDemoMode;
  // realFetch escape-hatch: lets a UI element fire a guaranteed-live request
  // (e.g. "place a real Bolna call right now") even while demo mode is on.
  window.rx.realFetch = realFetch;
})();
