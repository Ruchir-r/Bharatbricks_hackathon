"""Patient Q&A — RAG-grounded, hallucination-guarded.

Pipeline:
  1. Pull profile + retrieve evidence from every relevant Delta table (rag.retrieve_for_drug)
  2. If retrieval confidence < threshold → refuse with safe fallback
  3. LLM answer with strict prompt: "you may only state facts in the citations"
  4. Post-hoc guards:
     - any drug-shaped token must appear in citations
     - any dose-number must appear in prescribed text or citations
     - self-consistency LLM second pass returns {grounded: bool}
  5. Force disclaimer
"""

from __future__ import annotations
import json
import re
from . import profile, guards, llm_client, rag


PROMPT_TEMPLATE = """You are a careful assistant for an Indian patient. Answer in {lang_name} using short simple sentences.

ABSOLUTE RULES (breaking any → unsafe):
- ONLY state facts that appear in the EVIDENCE section. Do NOT add your own knowledge.
- Do NOT invent or change drug doses; only quote doses written in the prescription or evidence.
- Do NOT recommend a different drug. Tell the patient to ask their doctor.
- For emergencies (chest pain, bleeding, breathing trouble) say: "Call emergency now or use SOS button."
- If the answer isn't in EVIDENCE, say "I don't have reliable information on that. Please ask your doctor or pharmacist."
- Always end with: "This is information only — not a substitute for your doctor."

PATIENT PROFILE
- Name: {name}
- Preferred language: {pref_lang}
- Medicines on file:
{meds}
- Recent side-effect check-ins:
{checkins}

EVIDENCE (the only ground truth — cite it implicitly):
{evidence}

QUESTION: {question}

Answer in MAX 4 sentences, in {lang_name}:
"""

LANG_NAMES = {"en-IN": "English", "hi-IN": "Hindi (Devanagari)", "ta-IN": "Tamil"}


def _format_meds(entries: list[dict]) -> str:
    if not entries:
        return "  (none on file)"
    return "\n".join(
        f"  - {e['drug_name']} {e.get('dose','')} at {', '.join(e.get('times_of_day') or ['as needed'])}"
        for e in entries
    )


def _format_checkins(rows: list[dict]) -> str:
    if not rows:
        return "  (no check-ins logged)"
    return "\n".join(f"  - {r['logged_at']}: {r['symptom']} (severity {r['severity']}) after {r['drug_name']}" for r in rows)


def _drugs_mentioned(question: str, meds: list[dict]) -> list[str]:
    """Pull any drug names mentioned in the question + all profile drugs."""
    q_low = (question or "").lower()
    out: set[str] = set()
    # add profile drugs (always allowed in answer)
    for m in meds:
        if m.get("drug_name"):
            out.add(m["drug_name"].lower())
    # naïve substring match — works for our fixed CDSCO list
    common = ["paracetamol","amoxicillin","cefixime","metformin","amlodipine","flupirtine",
              "ibuprofen","diclofenac","aspirin","atorvastatin","levothyroxine","omeprazole",
              "warfarin","ciprofloxacin","doxycycline","metronidazole","azithromycin",
              "isoniazid","rifampicin","fluconazole","prednisolone","losartan","enalapril",
              "spironolactone","furosemide","glimepiride","insulin","salbutamol","budesonide"]
    for d in common:
        if d in q_low:
            out.add(d)
    return sorted(out)


def answer(session_id: str, question: str, lang: str = "en-IN") -> dict:
    """Returns {answer, lang, drugs_referenced, citations, confidence, violations}."""
    question = guards.check_utterance(question)
    guards.check_lang(lang)

    summary = profile.summary(session_id)
    meds = summary["medicines"]
    drug_names = _drugs_mentioned(question, meds)

    # Multi-source RAG
    citations: list[rag.Citation] = []
    for d in drug_names[:5]:  # cap to keep prompt small
        citations.extend(rag.retrieve_for_drug(d, limit_per_table=2))

    confidence = rag.confidence_score(citations)
    citations_text = rag.fmt_for_prompt(citations)

    # Refusal threshold — low evidence quality
    if drug_names and guards.confidence_refuse(confidence):
        refusal = guards.force_disclaimer(
            "I don't have reliable information on that drug. Please ask your doctor or pharmacist.",
            lang,
        )
        return {
            "answer": refusal,
            "lang": lang,
            "drugs_referenced": drug_names,
            "citations": [c.as_dict() for c in citations],
            "confidence": round(confidence, 3),
            "violations": ["LOW_CONFIDENCE"],
        }

    # Build allowed text (for numeric guard) — anything in profile dose + citations + question
    allowed_dose_text = " ".join([
        question,
        " ".join(f"{m.get('drug_name','')} {m.get('dose','')}" for m in meds),
        citations_text,
    ])

    prompt = PROMPT_TEMPLATE.format(
        lang_name=LANG_NAMES.get(lang, "English"),
        name=(summary["session"] or {}).get("patient_name") or "Patient",
        pref_lang=lang,
        meds=_format_meds(meds),
        checkins=_format_checkins(summary["recent_checkins"]),
        evidence=citations_text,
        question=question,
    )

    raw = llm_client.chat(
        "databricks-meta-llama-3-3-70b-instruct",
        [{"role": "user", "content": prompt}],
        max_tokens=400,
        temperature=0.1,
    ).strip()

    # Hallucination guards (can replace text with safe refusal)
    final, violations = guards.redact_or_refuse(
        raw,
        citations_text=citations_text,
        allowed_text=allowed_dose_text,
        allow_words=drug_names + ["paracetamol","amoxicillin","cefixime","metformin"],
    )

    final = guards.force_disclaimer(final, lang)
    return {
        "answer": final,
        "lang": lang,
        "drugs_referenced": drug_names,
        "citations": [c.as_dict() for c in citations],
        "confidence": round(confidence, 3),
        "violations": violations,
    }
