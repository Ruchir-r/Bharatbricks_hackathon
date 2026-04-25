"""Generate the two missing eval fixtures (synth_multi.png, label_paracetamol.jpg).

Deterministic, copyright-safe: pure PIL rendering, no external images used.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).parent
OUT = HERE / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)


def _font(size: int):
    # Try a few common faces; PIL falls back to default if none found.
    for cand in [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
    ]:
        try:
            return ImageFont.truetype(cand, size)
        except Exception:
            continue
    return ImageFont.load_default()


def make_synth_multi() -> Path:
    """Synthetic typed-style prescription with 3 drugs. Used by SCAN-004."""
    W, H = 1000, 1300
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    f_head = _font(34)
    f_body = _font(30)
    f_small = _font(22)
    f_footer = _font(20)

    # Clinic letterhead
    d.rectangle([(40, 40), (W - 40, 140)], outline="#1565c0", width=3)
    d.text((60, 55), "PRIMARY HEALTH CENTRE — BIJNOR", fill="#1565c0", font=f_head)
    d.text((60, 100), "Dr. S. K. Verma · Reg. 45231 · District UP", fill="#333", font=f_small)

    # Patient meta
    y = 180
    d.text((60, y),     "Patient: Rina Devi           Age: 52 F", fill="black", font=f_body); y += 40
    d.text((60, y),     "Date:    2026-04-25          OPD: 2041", fill="black", font=f_body); y += 50

    d.text((60, y), "Diagnosis: Hypertension, Type-2 DM", fill="black", font=f_body); y += 60

    d.line([(60, y), (W - 60, y)], fill="#999", width=1); y += 20

    # The R/x block
    d.text((60, y), "Rx", fill="black", font=f_head); y += 60

    drugs = [
        ("1.", "Tab. Paracetamol 500 mg",   "1 tab, thrice daily after food, 5 days"),
        ("2.", "Tab. Amoxicillin 500 mg",   "1 tab, thrice daily before food, 7 days"),
        ("3.", "Tab. Cefixime 200 mg",      "1 tab, twice daily, 5 days   (Batch: CXM2509A)"),
    ]
    for n, name, dose in drugs:
        d.text((70,  y), n,    fill="black", font=f_body)
        d.text((120, y), name, fill="black", font=f_body); y += 40
        d.text((120, y), dose, fill="#333",  font=f_small); y += 50

    y += 60
    d.line([(60, y), (W - 60, y)], fill="#999", width=1); y += 20

    d.text((60, y), "Follow up: 5 days.   Keep ORS at home.", fill="black", font=f_body); y += 60
    d.text((60, y), "Signature: _______________________", fill="black", font=f_small); y += 40
    d.text((60, H - 60), "Generated for Bharosa eval. Non-clinical fixture.", fill="#999", font=f_footer)

    out = OUT / "synth_multi.png"
    img.save(out, "PNG")
    return out


def make_label_paracetamol() -> Path:
    """Mock paracetamol drug-strip label. Used by SCAN-005 (mode=drug_label)."""
    W, H = 900, 350
    img = Image.new("RGB", (W, H), "#f2faf2")
    d = ImageDraw.Draw(img)

    # Strip outer border
    d.rectangle([(15, 15), (W - 15, H - 15)], outline="#2e7d32", width=4)
    # Green brand band
    d.rectangle([(15, 15), (W - 15, 90)], fill="#2e7d32")

    f_brand = _font(40)
    f_strength = _font(36)
    f_body = _font(26)
    f_small = _font(20)

    d.text((40, 28), "PARACIP 500", fill="white", font=f_brand)
    d.text((W - 280, 38), "Rx", fill="white", font=f_brand)

    d.text((40, 110), "Paracetamol Tablets IP 500 mg", fill="#1a1a1a", font=f_strength)
    d.text((40, 165), "10 tablets  |  For oral use",  fill="#333",    font=f_body)
    d.text((40, 205), "B.No:  PCT8842      Mfg: 02/2025   Exp: 01/2028", fill="#333", font=f_body)
    d.text((40, 245), "Mfd by: Cipla Ltd, Plot 8, MIDC Kurkumbh 413802",  fill="#333", font=f_small)
    d.text((40, 275), "Store below 30°C. Keep out of reach of children.", fill="#333", font=f_small)
    d.text((40, 305), "Generated for Bharosa eval. Non-clinical fixture.", fill="#999", font=f_small)

    out = OUT / "label_paracetamol.jpg"
    img.save(out, "JPEG", quality=88)
    return out


if __name__ == "__main__":
    a = make_synth_multi()
    b = make_label_paracetamol()
    print("wrote:", a)
    print("wrote:", b)
