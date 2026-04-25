"""Generate the translations.json cache for the UI's i18n layer.

Strategy:
  - Hand-curate the most-visible UI strings (~50 items).
  - Each item ships in 3 languages: en-IN, hi-IN, ml-IN.
  - For any item where Hindi or Malayalam is missing, fall back to Sarvam translate
    (one call per missing pair). Cache to disk so demo-day spend = 0.

Run:
    SARVAM_API_KEY=... python scripts/build_translations.py
Outputs:
    app/static/translations.json
"""

from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "app"))

OUT = REPO / "app" / "static" / "translations.json"


# Hand-curated translations. Keys are EXACT current text in the templates / JS.
# Format:  current → { en, hi, ml }
# - The "en" is the clean monolingual English form.
# - "hi" is the clean monolingual Hindi form.
# - "ml" is the Malayalam form.
T: dict[str, dict[str, str]] = {
    # === Header / nav ===
    "Bharosa":            {"en": "Bharosa", "hi": "भरोसा", "ml": "ഭരോസ"},
    "घर":                  {"en": "Home", "hi": "घर", "ml": "ഹോം"},
    "स्कैन":                {"en": "Scan", "hi": "स्कैन", "ml": "സ്കാൻ"},
    "दवाइयाँ":              {"en": "Medicines", "hi": "दवाइयाँ", "ml": "മരുന്നുകൾ"},
    "जाँच":                {"en": "Check-in", "hi": "जाँच", "ml": "ചെക്ക്-ഇൻ"},
    "SOS":                {"en": "SOS", "hi": "SOS", "ml": "SOS"},

    # === Home ===
    "Namaste 🙏":          {"en": "Welcome 🙏", "hi": "नमस्ते 🙏", "ml": "സ്വാഗതം 🙏"},
    "Loading your profile…":{"en": "Loading your profile…", "hi": "आपकी जानकारी लाई जा रही है…", "ml": "നിങ്ങളുടെ വിവരങ്ങൾ ലോഡ് ചെയ്യുന്നു…"},
    "Next dose · अगली दवा": {"en": "Next dose", "hi": "अगली दवा", "ml": "അടുത്ത ഡോസ്"},
    "My medicines · मेरी दवाइयाँ":{"en": "My medicines", "hi": "मेरी दवाइयाँ", "ml": "എന്റെ മരുന്നുകൾ"},
    "Recent check-ins · हाल की जाँच":{"en": "Recent check-ins", "hi": "हाल की जाँच", "ml": "സമീപകാല ചെക്ക്-ഇൻ"},
    "Ask · पूछिए":         {"en": "Ask", "hi": "पूछिए", "ml": "ചോദിക്കുക"},
    "Tap a question or type your own.":{"en": "Tap a question or type your own.", "hi": "नीचे से कोई सवाल चुनिए या ख़ुद लिखिए।", "ml": "ഒരു ചോദ്യത്തിൽ ടാപ്പ് ചെയ്യുക അല്ലെങ്കിൽ സ്വന്തമായി ടൈപ്പ് ചെയ്യുക."},
    "Type your own question…":{"en": "Type your own question…", "hi": "अपना सवाल यहाँ लिखिए…", "ml": "നിങ്ങളുടെ ചോദ്യം ഇവിടെ ടൈപ്പ് ചെയ്യുക…"},
    "Ask · पूछें":          {"en": "Ask", "hi": "पूछें", "ml": "ചോദിക്കുക"},
    "Refill alerts · दवाई ख़त्म होने से पहले":{"en": "Refill alerts", "hi": "दवाई ख़त्म होने से पहले", "ml": "റീഫിൽ അലേർട്ടുകൾ"},
    "💰 Save money · पैसे बचाइए":{"en": "💰 Save money", "hi": "💰 पैसे बचाइए", "ml": "💰 പണം ലാഭിക്കൂ"},
    "Jan Aushadhi generics":{"en": "Jan Aushadhi generics", "hi": "जन औषधि जेनेरिक", "ml": "ജൻ ഔഷധി ജനറിക്സ്"},
    "tap to load…":        {"en": "tap to load…", "hi": "देखने के लिए दबाइए…", "ml": "ലോഡ് ചെയ്യാൻ ടാപ്പ് ചെയ്യുക…"},
    "🏥 Find a Jan Aushadhi pharmacy · नज़दीकी जन औषधि":{"en": "🏥 Find a Jan Aushadhi pharmacy", "hi": "🏥 नज़दीकी जन औषधि", "ml": "🏥 അടുത്തുള്ള ജൻ ഔഷധി"},
    "📍 Use my location":   {"en": "📍 Use my location", "hi": "📍 मेरी जगह से ढूँढिए", "ml": "📍 എന്റെ സ്ഥലം ഉപയോഗിക്കുക"},
    "🛡️ Govt schemes · सरकारी योजना":{"en": "🛡️ Govt schemes", "hi": "🛡️ सरकारी योजना", "ml": "🛡️ സർക്കാർ പദ്ധതികൾ"},
    "Loading schemes for your profile…":{"en": "Loading schemes…", "hi": "योजनाएँ लाई जा रही हैं…", "ml": "പദ്ധതികൾ ലോഡ് ചെയ്യുന്നു…"},
    "⚠️ Food & drink warnings · खाने-पीने में सावधानी":{"en": "⚠️ Food & drink warnings", "hi": "⚠️ खाने-पीने में सावधानी", "ml": "⚠️ ഭക്ഷണ-പാനീയ മുന്നറിയിപ്പുകൾ"},
    "tap to load warnings for your medicines":{"en": "tap to load warnings", "hi": "देखने के लिए दबाइए", "ml": "ലോഡ് ചെയ്യാൻ ടാപ്പ് ചെയ്യുക"},
    "Scan a prescription · पर्ची स्कैन करें":{"en": "Scan a prescription", "hi": "पर्ची स्कैन करें", "ml": "കുറിപ്പടി സ്കാൻ ചെയ്യുക"},
    "Care Card · घरवालों के लिए कार्ड":{"en": "Care Card", "hi": "घरवालों के लिए कार्ड", "ml": "കെയർ കാർഡ്"},
    "Information only — not a substitute for a doctor. · यह ऐप केवल जानकारी के लिए है।":{
        "en": "Information only — not a substitute for a doctor.",
        "hi": "यह ऐप केवल जानकारी के लिए है। डॉक्टर की सलाह ज़रूरी है।",
        "ml": "വിവരങ്ങൾക്ക് മാത്രം — ഡോക്ടറുടെ ഉപദേശത്തിന് പകരമല്ല."},

    # === Scan page ===
    "पर्ची या दवाई की फ़ोटो":{"en": "Photo of prescription or medicine", "hi": "पर्ची या दवाई की फ़ोटो", "ml": "കുറിപ്പടി അല്ലെങ്കിൽ മരുന്നിന്റെ ഫോട്ടോ"},
    "क्या स्कैन कर रहे हैं?":{"en": "What are you scanning?", "hi": "क्या स्कैन कर रहे हैं?", "ml": "എന്താണ് സ്കാൻ ചെയ്യുന്നത്?"},
    "📝 पर्ची":              {"en": "📝 Prescription", "hi": "📝 पर्ची", "ml": "📝 കുറിപ്പടി"},
    "💊 दवाई का पत्ता":      {"en": "💊 Medicine strip", "hi": "💊 दवाई का पत्ता", "ml": "💊 മരുന്നിന്റെ പട്ട"},
    "फ़ोटो चुनें या खींचें":  {"en": "Choose or take a photo", "hi": "फ़ोटो चुनें या खींचें", "ml": "ഫോട്ടോ തിരഞ്ഞെടുക്കുക അല്ലെങ്കിൽ എടുക്കുക"},
    "🔎 जाँच करें":           {"en": "🔎 Check", "hi": "🔎 जाँच करें", "ml": "🔎 പരിശോധിക്കുക"},
    "🔊 सुनें":              {"en": "🔊 Listen", "hi": "🔊 सुनें", "ml": "🔊 കേൾക്കുക"},

    # === Timetable ===
    "मेरी दवाइयाँ":           {"en": "My medicines", "hi": "मेरी दवाइयाँ", "ml": "എന്റെ മരുന്നുകൾ"},
    "यहाँ आपकी सभी दवाइयाँ और उनका समय देखें।":{"en": "All your medicines and their times in one place.", "hi": "यहाँ आपकी सभी दवाइयाँ और उनका समय देखें।", "ml": "നിങ്ങളുടെ എല്ലാ മരുന്നുകളും അവയുടെ സമയങ്ങളും ഒറ്റയിടത്ത് കാണുക."},
    "अभी कोई दवा नहीं है। पहले पर्ची स्कैन कीजिए।":{"en": "No medicines yet. Scan a prescription first.", "hi": "अभी कोई दवा नहीं है। पहले पर्ची स्कैन कीजिए।", "ml": "ഇതുവരെ മരുന്നുകൾ ഒന്നുമില്ല. ആദ്യം ഒരു കുറിപ്പടി സ്കാൻ ചെയ്യുക."},
    "पर्ची स्कैन करें":       {"en": "Scan prescription", "hi": "पर्ची स्कैन करें", "ml": "കുറിപ്പടി സ്കാൻ ചെയ്യുക"},

    # === Check-in ===
    "आप कैसा महसूस कर रहे हैं?":{"en": "How are you feeling?", "hi": "आप कैसा महसूस कर रहे हैं?", "ml": "നിങ്ങൾക്ക് എങ്ങനെയാണ് തോന്നുന്നത്?"},
    "दवा लेने के बाद कोई तकलीफ़ है? हमें बताइए।":{"en": "Any trouble after taking your medicine? Tell us.", "hi": "दवा लेने के बाद कोई तकलीफ़ है? हमें बताइए।", "ml": "മരുന്ന് കഴിച്ച ശേഷം എന്തെങ്കിലും പ്രയാസമുണ്ടോ? ഞങ്ങളോട് പറയൂ."},
    "लिखिए या बोलिए":         {"en": "Write or speak", "hi": "लिखिए या बोलिए", "ml": "എഴുതുക അല്ലെങ്കിൽ പറയുക"},
    "🎤 बोलकर बताएँ":          {"en": "🎤 Speak", "hi": "🎤 बोलकर बताएँ", "ml": "🎤 സംസാരിക്കുക"},
    "📤 भेजें":               {"en": "📤 Send", "hi": "📤 भेजें", "ml": "📤 അയക്കുക"},

    # === SOS ===
    "🚨 आपातकाल":             {"en": "🚨 Emergency", "hi": "🚨 आपातकाल", "ml": "🚨 അടിയന്തിരാവസ്ഥ"},
    "यह बटन दबाने पर आपके घरवालों को तुरंत SMS और कॉल जाएगा।":{
        "en": "Tapping this button immediately sends an SMS and call to your family.",
        "hi": "यह बटन दबाने पर आपके घरवालों को तुरंत SMS और कॉल जाएगा।",
        "ml": "ഈ ബട്ടൺ അമർത്തിയാൽ ഉടനെ നിങ്ങളുടെ കുടുംബത്തിന് SMS-ഉം കോളും അയക്കും."},
    "आपका नाम":              {"en": "Your name", "hi": "आपका नाम", "ml": "നിങ്ങളുടെ പേര്"},
    "नाम लिखिए":              {"en": "Type your name", "hi": "नाम लिखिए", "ml": "നിങ്ങളുടെ പേര് ടൈപ്പ് ചെയ്യുക"},
    "📍 अपनी जगह भेजें (Location)":{"en": "📍 Share my location", "hi": "📍 अपनी जगह भेजें", "ml": "📍 എന്റെ സ്ഥലം പങ്കിടുക"},
    "🚨 SOS भेजें":            {"en": "🚨 Send SOS", "hi": "🚨 SOS भेजें", "ml": "🚨 SOS അയക്കുക"},

    # === Common micro-strings ===
    "days left":              {"en": "days left", "hi": "दिन बाकी", "ml": "ദിവസങ്ങൾ ബാക്കി"},
    "month":                  {"en": "month", "hi": "महीना", "ml": "മാസം"},
    "save":                   {"en": "save", "hi": "बचत", "ml": "ലാഭിക്കുക"},
    "Could not load.":        {"en": "Could not load.", "hi": "जानकारी नहीं मिली।", "ml": "ലോഡ് ചെയ്യാൻ കഴിഞ്ഞില്ല."},
}


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(T, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT}  ({len(T)} entries)")


if __name__ == "__main__":
    main()
