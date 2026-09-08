"""Fase 2 (Prompt 2) — dedup fingerprints for Signal/Opportunity/Watch.

Deterministic, side-effect-free (same pattern as quality.py's job_fingerprint):
mirrors the existing job/application dedup discipline instead of inventing a
new one. Fingerprints are always non-null strings so uniqueness constraints
never depend on Postgres NULL semantics (multiple NULLs are never treated as
duplicates by a plain UNIQUE constraint) - a deliberate choice recorded in
the Prompt 2 report, not an oversight.
"""

from __future__ import annotations

from hashlib import sha256

from .quality import normalize

NONE_TOKEN = "__NONE__"


def signal_fingerprint(company_id: str | None, type_: str, source_url: str) -> str:
    material = "|".join((company_id or NONE_TOKEN, normalize(type_), normalize(source_url)))
    return sha256(material.encode()).hexdigest()


def opportunity_fingerprint(company_id: str, type_: str, job_id: str | None,
                             signal_id: str | None) -> str:
    material = "|".join((company_id, normalize(type_), job_id or NONE_TOKEN, signal_id or NONE_TOKEN))
    return sha256(material.encode()).hexdigest()


def watch_fingerprint(company_id: str, opportunity_id: str | None) -> str:
    material = "|".join((company_id, opportunity_id or NONE_TOKEN))
    return sha256(material.encode()).hexdigest()
