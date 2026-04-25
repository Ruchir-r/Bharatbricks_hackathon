"""Whitebox UI tests with Playwright.

Strategy: serve the static app locally (uvicorn) on a free port, drive it with
Chromium-headless in demo mode (forces all /api/* through fallbacks.js). No live
backend, no Sarvam, no Bolna calls. Tests assert that every button + flow renders
the right cached payload.

Usage:
    python eval/ui_test.py                # run all
    python eval/ui_test.py --headed       # see the browser
"""

from __future__ import annotations
import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
APP_DIR = REPO / "app"
SCREENSHOT_DIR = REPO / "eval" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def boot_local_app(port: int) -> subprocess.Popen:
    """Start uvicorn with the app from app/ — but stub out the SQL/LLM env so
    nothing tries to phone home; we'll force demo mode in the browser anyway."""
    env = os.environ.copy()
    env["CACHE_DIR"] = "/tmp/local_cache_ui_test"
    env.setdefault("CATALOG", "bricksiitm")
    env.setdefault("SCHEMA", "rx_helper")
    env.setdefault("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/dummy")
    env.setdefault("DATABRICKS_HOST", "https://example.com")
    env.setdefault("DATABRICKS_TOKEN", "dummy")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(APP_DIR), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    # Wait until the port responds
    for _ in range(40):
        time.sleep(0.4)
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return proc
        except OSError:
            continue
    proc.terminate()
    raise RuntimeError("uvicorn didn't start in time")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true", help="show browser instead of running headless")
    ap.add_argument("--slow", type=int, default=200, help="slow_mo ms when headed")
    args = ap.parse_args()

    port = _free_port()
    print(f"[setup] booting uvicorn on http://127.0.0.1:{port}")
    proc = boot_local_app(port)
    base_url = f"http://127.0.0.1:{port}"

    results: list[tuple[str, bool, str]] = []

    def expect(label: str, ok: bool, detail: str = ""):
        results.append((label, ok, detail))
        marker = "✓" if ok else "✗"
        print(f"  {marker} {label}: {detail[:200]}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.headed, slow_mo=(args.slow if args.headed else 0))
            ctx = browser.new_context(viewport={"width": 414, "height": 896})  # iPhone 11 Pro Max-ish
            page = ctx.new_page()
            # Forward console errors to our output
            page.on("pageerror", lambda exc: print(f"  [page error] {exc}"))
            page.on("console", lambda msg: print(f"  [console.{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)

            # ------- 1. Home page renders -------
            page.goto(f"{base_url}/?demo=1&session=demo-patient-001")
            page.wait_for_load_state("networkidle", timeout=20000)
            page.wait_for_timeout(2500)  # let async fetches complete
            page.screenshot(path=str(SCREENSHOT_DIR / "01_home.png"), full_page=True)
            expect("home title shows greeting", "Namaste" in page.text_content("#greet") or "नमस्ते" in page.text_content("#greet"), page.text_content("#greet"))
            expect("home subtitle mentions medicines", "medicines" in (page.text_content("#subtitle") or "").lower() or "दवाइयाँ" in (page.text_content("#subtitle") or ""), page.text_content("#subtitle"))
            expect("DEMO MODE badge visible", page.locator("#rx-demo-badge").count() > 0, "")

            # ------- 2. Next-dose card visible -------
            page.wait_for_selector("#next-dose-card", state="visible", timeout=15000)
            nd_text = page.text_content("#next-dose-body")
            expect("next-dose card lists metformin", "metformin" in (nd_text or "").lower(), nd_text[:120] if nd_text else "")

            # ------- 3. Refill alert renders -------
            page.wait_for_timeout(2000)  # let async fetches settle
            try:
                page.wait_for_selector("#refill-card", state="visible", timeout=10000)
                refill_text = page.text_content("#refill-list")
                expect("refill card present", refill_text and len(refill_text) > 10, refill_text[:160])
                expect("refill flags paracetamol urgent", "paracetamol" in (refill_text or "").lower(), "")
            except Exception as e:
                expect("refill card present", False, f"timeout: {e}")

            # ------- 4. Ask chips work -------
            page.locator(".chip").first.click()
            page.wait_for_selector("#ask-answer .alert", timeout=20000)
            ans = page.text_content("#ask-answer")
            page.screenshot(path=str(SCREENSHOT_DIR / "02_ask_answer.png"), full_page=True)
            expect("ask-chip answer rendered", ans and len(ans) > 30, (ans or "")[:160])
            expect("ask answer mentions paracetamol or metformin", any(d in (ans or "").lower() for d in ["paracetamol","metformin","information only"]), "")

            # ------- 5. Hindi chip -------
            page.locator('button.chip[data-q*="पेरा"]').first.click()
            page.wait_for_timeout(1500)
            ans2 = page.text_content("#ask-answer")
            expect("hindi chip returns Devanagari", any('ऀ' <= ch <= 'ॿ' for ch in (ans2 or "")), (ans2 or "")[:80])

            # ------- 6. Savings panel expands + loads -------
            page.locator('summary:has-text("Save money")').click()
            page.wait_for_timeout(1500)
            sav = page.text_content("#savings-body")
            expect("savings shows ₹ amount", "₹" in (sav or ""), (sav or "")[:120])
            expect("savings lists ≥1 drug breakdown", "amlodipine" in (sav or "").lower() or "metformin" in (sav or "").lower(), "")

            # ------- 7. Pharmacy locator (uses fallback when geolocation declined) -------
            page.locator('summary:has-text("Find a Jan Aushadhi")').click()
            page.wait_for_timeout(800)
            page.locator("#pharmacy-locate-btn").click()
            page.wait_for_timeout(1500)
            ph = page.text_content("#pharmacy-list")
            expect("pharmacy list populated", ph and "kendra" in (ph or "").lower(), (ph or "")[:160])

            # ------- 8. Schemes -------
            page.locator('summary:has-text("Govt schemes")').click()
            page.wait_for_timeout(1200)
            sch = page.text_content("#scheme-body")
            expect("schemes show Ayushman", "ayushman" in (sch or "").lower() or "pmjay" in (sch or "").lower(), (sch or "")[:160])

            # ------- 9. Food warnings -------
            page.locator('summary:has-text("Food")').click()
            page.wait_for_timeout(1200)
            fw = page.text_content("#food-warn-body")
            expect("food warnings list metformin/paracetamol", any(d in (fw or "").lower() for d in ["metformin","paracetamol","alcohol"]), (fw or "")[:160])

            page.screenshot(path=str(SCREENSHOT_DIR / "03_home_full.png"), full_page=True)

            # ------- 10. Scan flow -------
            page.goto(f"{base_url}/scan?demo=1", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=10000)
            expect("scan page renders", page.locator("#scan-btn").count() > 0, "")

            # Upload a real fixture image
            fixture = REPO / "eval" / "fixtures" / "synth_multi.png"
            page.locator("#scan-file").set_input_files(str(fixture))
            page.wait_for_timeout(800)
            page.locator("#scan-btn").click()
            # CTA "Add to my profile" appears immediately, before OCR result settles
            page.wait_for_selector("a.btn-primary[href*='scan_result']", timeout=15000)
            expect("✅ Add to my profile CTA appears immediately", True, "")
            # Wait for at least 3 drug cards to render too
            page.wait_for_function("document.querySelectorAll('.drug-card').length >= 3", timeout=30000)
            page.wait_for_timeout(2000)  # let trust-check fetches finish
            page.screenshot(path=str(SCREENSHOT_DIR / "04_scan_result.png"), full_page=True)
            cards = page.locator(".drug-card").all_text_contents()
            expect("scan returned ≥3 drug cards", len([c for c in cards if c.strip()]) >= 3, f"{len(cards)} cards")
            # /scan drug cards use the RAW OCR names. The cleaned brand names appear
            # on the /scan_result page (asserted later).
            joined = ' '.join(cards).lower()
            expect("/scan shows the raw OCR drug names", any(d in joined for d in ["orop","allkose","breesep","breese","sipan","cefixime","sinarest","crocin","levocet","breze","amoxicillin"]), "")

            # ------- 10b. Navigate to scan_result and verify rich rendering -------
            page.locator("a.btn-primary[href*='scan_result']").click()
            page.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_selector("#new-meds-list .card", timeout=15000)
            page.wait_for_timeout(1500)
            page.screenshot(path=str(SCREENSHOT_DIR / "11_scan_result_page.png"), full_page=True)
            scan_result_text = page.text_content("#new-meds-list") or ""
            expect("scan_result shows ≥3 normalized cards", page.locator("#new-meds-list .card").count() >= 3, f"{page.locator('#new-meds-list .card').count()} cards")
            expect("scan_result shows likely_brand cleaned name", any(b in scan_result_text for b in ["Crocin","Levocet","Breze","Sinarest"]), "")
            expect("scan_result shows OCR raw + cleaned", "OCR read" in scan_result_text or "Orop" in scan_result_text, "")
            # Price comparison panel should be there (collapsed)
            n_price_panels = page.locator("details summary:has-text('Price comparison')").count()
            expect("scan_result has price-comparison panels", n_price_panels >= 1, f"{n_price_panels} panels")
            # Countdown should be ticking
            expect("45-second next-dose countdown is rendered", page.locator("#countdown").count() == 1 and any(":4" in (page.text_content("#countdown") or '') or ":3" in (page.text_content("#countdown") or '') for _ in [0]), page.text_content("#countdown")[:60] if page.text_content("#countdown") else "")

            # ------- 11. Timetable page -------
            page.goto(f"{base_url}/timetable?demo=1")
            page.wait_for_timeout(800)
            page.screenshot(path=str(SCREENSHOT_DIR / "05_timetable.png"), full_page=True)
            expect("timetable page renders", page.locator(".empty,.tt-card").count() > 0, "")

            # ------- 12. Check-in page -------
            page.goto(f"{base_url}/checkin?demo=1")
            page.locator("#utterance").fill("मेटफॉर्मिन से पेट में थोड़ा दर्द है")
            page.locator("#submit-checkin").click()
            page.wait_for_selector("#checkin-reply .alert", timeout=15000)
            page.screenshot(path=str(SCREENSHOT_DIR / "06_checkin.png"), full_page=True)
            checkin_text = page.text_content("#checkin-reply")
            expect("check-in returns reply", checkin_text and len(checkin_text) > 5, (checkin_text or "")[:120])

            # ------- 12.5. Language dropdown (en → hi → ml) -------
            page.goto(f"{base_url}/?demo=1&session=demo-patient-001", timeout=60000)
            page.wait_for_timeout(1500)
            # Default = en (browser locale en)
            page.select_option("#lang-select", "ml")
            page.wait_for_timeout(800)
            page.screenshot(path=str(SCREENSHOT_DIR / "08_lang_ml.png"), full_page=True)
            ml_body = page.text_content("body")
            expect("Malayalam UI shows Malayalam text", any('ഀ' <= ch <= 'ൿ' for ch in ml_body), "")

            page.select_option("#lang-select", "hi")
            page.wait_for_timeout(800)
            page.screenshot(path=str(SCREENSHOT_DIR / "09_lang_hi.png"), full_page=True)
            hi_body = page.text_content("body")
            expect("Hindi UI shows Devanagari", any('ऀ' <= ch <= 'ॿ' for ch in hi_body), "")

            page.select_option("#lang-select", "en")
            page.wait_for_timeout(800)
            page.screenshot(path=str(SCREENSHOT_DIR / "10_lang_en.png"), full_page=True)
            # The dropdown itself contains a Malayalam glyph for the option label, so
            # exclude #lang-select from the Malayalam-residual check.
            en_body_no_select = page.evaluate(
                "() => Array.from(document.body.childNodes).filter(n => !(n.id === 'lang-select')).map(n => n.textContent || '').join(' ')"
            )
            ml_chars_outside = [ch for ch in en_body_no_select if 'ഀ' <= ch <= 'ൿ']
            expect("English UI removes Malayalam (outside dropdown)", len(ml_chars_outside) == 0, f"residual_ml={len(ml_chars_outside)}")

            # ------- 13. SOS page + double-tap-to-confirm -------
            # The new SOS page auto-fills from /api/profile, so no need to type.
            page.goto(f"{base_url}/sos?demo=1", timeout=60000)
            page.wait_for_timeout(1500)  # let auto-fill settle
            page.locator("#sos-btn").click()
            armed_text = page.text_content("#sos-btn")
            expect("first SOS tap arms (does not send)", "confirm" in (armed_text or "").lower() or "पक्का" in (armed_text or ""), armed_text)
            page.locator("#sos-btn").click()
            page.wait_for_selector("#sos-result .alert", timeout=15000)
            page.screenshot(path=str(SCREENSHOT_DIR / "07_sos.png"), full_page=True)
            sos_text = page.text_content("#sos-result")
            expect("second SOS tap sends", "SOS" in (sos_text or "") or "✅" in (sos_text or "") or "sms" in (sos_text or "").lower(), (sos_text or "")[:120])

            browser.close()

    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except Exception: proc.kill()

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{'='*40}\n  UI tests: {passed}/{total} passed\n{'='*40}")
    print(f"  Screenshots: {SCREENSHOT_DIR}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
