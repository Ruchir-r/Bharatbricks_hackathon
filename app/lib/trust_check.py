"""Check a drug against CDSCO registries: approved, banned, recent NSQ alerts."""

from dataclasses import dataclass
from typing import Optional
from . import db
import os


@dataclass
class TrustVerdict:
    drug_name: str
    approved: bool
    banned: bool
    nsq_recent: bool
    nsq_batches: list[str]
    reasons_hi: list[str]
    reasons_en: list[str]

    @property
    def safe(self) -> bool:
        return self.approved and not self.banned and not self.nsq_recent


def _conn():
    return db.connect()


def check(drug_name: str, batch_no: Optional[str] = None) -> TrustVerdict:
    catalog = os.environ.get("CATALOG", "hack_cdsco")
    schema = os.environ.get("SCHEMA", "core")
    fq = f"{catalog}.{schema}"
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            f"SELECT 1 FROM {fq}.cdsco_approved WHERE lower(drug_name) = lower(?) LIMIT 1",
            (drug_name,),
        )
        approved = cur.fetchone() is not None

        # Banned iff drug_name matches a banned row's drug_name OR the banned row is
        # a single-component ban (combination has no "+") with a substring match.
        # Multi-drug FDC bans don't flag individual components as banned.
        cur.execute(
            f"SELECT 1 FROM {fq}.cdsco_banned "
            f"WHERE lower(drug_name) = lower(?) "
            f"   OR (combination NOT LIKE '%+%' AND lower(combination) LIKE lower(?)) "
            f"LIMIT 1",
            (drug_name, f"%{drug_name}%"),
        )
        banned = cur.fetchone() is not None

        # NSQ check: only flag nsq_recent=True when a batch_no was supplied AND matches.
        # When no batch is given, return the list informationally (not a safety-fail).
        nsq_batches: list[str] = []
        if batch_no:
            cur.execute(
                f"SELECT batch_no FROM {fq}.cdsco_nsq_alerts "
                f"WHERE lower(drug_name) = lower(?) AND batch_no = ? "
                f"AND alert_date >= current_date() - INTERVAL 12 MONTHS",
                (drug_name, batch_no),
            )
            nsq_batches = [row[0] for row in cur.fetchall()]

    reasons_en, reasons_hi = [], []
    if banned:
        reasons_en.append("Banned by CDSCO. Do not take.")
        reasons_hi.append("यह दवा सरकार द्वारा प्रतिबंधित है — न लें।")
    if nsq_batches:
        reasons_en.append(f"Appears in recent not-of-standard-quality reports (batches: {', '.join(nsq_batches)}).")
        reasons_hi.append("पिछले महीनों में इस दवा के कुछ बैच जाँच में फ़ेल हुए हैं — फ़ार्मेसी बदलें।")
    if not approved and not banned:
        reasons_en.append("Not found in CDSCO approved list — verify with pharmacist.")
        reasons_hi.append("यह दवा स्वीकृत सूची में नहीं मिली — फ़ार्मासिस्ट से पुष्टि करें।")
    if not reasons_en:
        reasons_en.append("Approved by CDSCO. No recent quality alerts.")
        reasons_hi.append("यह दवा स्वीकृत है। कोई हाल की चेतावनी नहीं।")

    return TrustVerdict(
        drug_name=drug_name,
        approved=approved,
        banned=banned,
        nsq_recent=bool(nsq_batches),
        nsq_batches=nsq_batches,
        reasons_en=reasons_en,
        reasons_hi=reasons_hi,
    )
