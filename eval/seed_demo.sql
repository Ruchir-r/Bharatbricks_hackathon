-- Seed: Rina Devi (demo-patient-001)
-- Rural UP patient, 52, Hindi speaker, hypertensive + diabetic + occasional aches.

DELETE FROM bricksiitm.rx_helper.patient_sessions WHERE session_id = 'demo-patient-001';
DELETE FROM bricksiitm.rx_helper.drug_timetable  WHERE session_id = 'demo-patient-001';
DELETE FROM bricksiitm.rx_helper.side_effect_log WHERE session_id = 'demo-patient-001';

INSERT INTO bricksiitm.rx_helper.patient_sessions VALUES (
  'demo-patient-001', 'Rina Devi', '+919999000001', 'hi-IN', '+919999000002', current_timestamp()
);

INSERT INTO bricksiitm.rx_helper.drug_timetable VALUES
  ('tt-001','demo-patient-001','amlodipine','5mg', array('08:00'),                30, current_date()),
  ('tt-002','demo-patient-001','metformin','500mg', array('08:00','20:00'),      30, current_date()),
  ('tt-003','demo-patient-001','paracetamol','500mg', array('14:00'),             5, current_date());

INSERT INTO bricksiitm.rx_helper.side_effect_log VALUES
  ('se-001','demo-patient-001','metformin','mild nausea', 2, current_timestamp() - INTERVAL 6 HOURS),
  ('se-002','demo-patient-001','amlodipine','ankle swelling', 3, current_timestamp() - INTERVAL 2 DAYS);
