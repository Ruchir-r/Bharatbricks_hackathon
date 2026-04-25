# Rx Helper — Eval Scorecard

- **Cases passed:** 14 / 16  (88%)
- **Individual checks passed:** 33 / 36  (92%)
- **Demo-critical cases passed:** 3 / 3  (100%)

## `/api/scan`

| Case | Status | Checks | Latency | Notes |
|---|---|---|---|---|
| **SCAN-001** | ⚠️ | 1/2 | 3261ms | diagnosis_contains_any: expected is None (skip) |
| **SCAN-002** | ✅ | 1/1 | 5194ms | all checks passed |
| **SCAN-003** | ✅ | 1/1 | 2189ms | all checks passed |
| **SCAN-004** | ✅ | 1/1 | 4333ms | all checks passed |
| **SCAN-005** | ✅ | 1/1 | 2926ms | all checks passed |

## `/api/trust`

| Case | Status | Checks | Latency | Notes |
|---|---|---|---|---|
| **TRUST-001** | ✅ | 4/4 | 5067ms | all checks passed |
| **TRUST-002** | ✅ | 3/3 | 4734ms | all checks passed |
| **TRUST-003** (demo-critical) | ✅ | 4/4 | 3777ms | all checks passed |
| **TRUST-004** (demo-critical) | ✅ | 2/2 | 3530ms | all checks passed |
| **TRUST-005** | ✅ | 2/2 | 4504ms | all checks passed |

## `/api/explain`

| Case | Status | Checks | Latency | Notes |
|---|---|---|---|---|
| **EXPLAIN-001** | ✅ | 4/4 | 16726ms | all checks passed |
| **EXPLAIN-002** | ✅ | 3/3 | 16154ms | all checks passed |
| **EXPLAIN-003** | ⚠️ | 1/3 | 15274ms | english_contains_any: matched [] in this medicine is for controlling sugar in your blood. take one 500mg tablet t...; translated_contains_any: matched [] in यह दवा आपके रक्त में शर्करा को नियंत्रित करने के लिए है। दिन में दो बार नाश्त... |

## `/api/interactions`

| Case | Status | Checks | Latency | Notes |
|---|---|---|---|---|
| **INTERACT-001** (demo-critical) | ✅ | 2/2 | 6076ms | all checks passed |
| **INTERACT-002** | ✅ | 2/2 | 5749ms | all checks passed |
| **INTERACT-003** | ✅ | 1/1 | 6309ms | all checks passed |
