"""Glossary enforcement (SPEC §4.5 rule 1) — deterministic, never trusted to the model."""

import re
import unicodedata
from functools import lru_cache

from sqlmodel import Session, select

from app.analysis.schemas import AddressCandidate, GlossaryCandidate
from app.models.analysis import AddressRule, GlossaryTerm


def norm(s: str) -> str:
    """Case/Unicode-normalised form for comparisons (NFC + casefold + single spaces)."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s).casefold()).strip()


@lru_cache(maxsize=4096)
def _pattern(variant: str) -> re.Pattern[str]:
    # \w is Unicode-aware: Vietnamese letters count as word characters, so "Linh" won't match
    # inside "Linhh"; spaces inside multi-word variants are matched flexibly.
    body = r"\s+".join(re.escape(p) for p in unicodedata.normalize("NFC", variant).split())
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


def apply_glossary(text: str, terms: list[GlossaryTerm]) -> str:
    """Replace known variants (and wrong-cased spellings) with the canonical term."""
    out = unicodedata.normalize("NFC", text)
    pairs: list[tuple[str, str]] = []
    for t in terms:
        if t.status != "approved" or not t.term.strip():
            continue
        for v in [*t.variants, t.term]:
            if v and v.strip():
                pairs.append((v.strip(), t.term.strip()))
    # longest variants first so "Khế Nguyên Linh Thạch" wins over "Linh Thạch"
    for variant, canonical in sorted(pairs, key=lambda p: len(p[0]), reverse=True):
        out = _pattern(variant).sub(canonical, out)
    return out


def approved_terms(s: Session, project_id: str) -> list[GlossaryTerm]:
    return list(
        s.exec(
            select(GlossaryTerm).where(
                GlossaryTerm.project_id == project_id, GlossaryTerm.status == "approved"
            )
        ).all()
    )


def merge_glossary_candidates(
    s: Session, project_id: str, chapter_id: str, cands: list[GlossaryCandidate]
) -> int:
    """Add suggestions; for a term that already exists, only union its variants."""
    existing = list(s.exec(select(GlossaryTerm).where(GlossaryTerm.project_id == project_id)))
    by_norm = {norm(t.term): t for t in existing}
    for t in existing:
        for v in t.variants:
            by_norm.setdefault(norm(v), t)
    added = 0
    for c in cands:
        hit = by_norm.get(norm(c.term)) or next(
            (by_norm[norm(v)] for v in c.variants if norm(v) in by_norm), None
        )
        variants = [v for v in c.variants if v.strip() and norm(v) != norm(c.term)]
        if hit:
            known = {norm(x) for x in [hit.term, *hit.variants]}
            new = [v for v in variants + [c.term] if norm(v) not in known]
            if new:
                hit.variants = [*hit.variants, *dict.fromkeys(new)]
                s.add(hit)
            continue
        t = GlossaryTerm(
            project_id=project_id,
            term=c.term.strip(),
            kind=c.kind,
            variants=list(dict.fromkeys(variants)),
            note=c.note,
            status="suggested",
            first_seen_chapter_id=chapter_id,
        )
        s.add(t)
        by_norm[norm(t.term)] = t
        added += 1
    return added


def merge_address_candidates(s: Session, project_id: str, cands: list[AddressCandidate]) -> int:
    rules = list(s.exec(select(AddressRule).where(AddressRule.project_id == project_id)))
    seen = {(r.speaker_key, r.listener_key) for r in rules}
    added = 0
    for c in cands:
        key = (c.speaker_key, c.listener_key)
        if key in seen or c.speaker_key == c.listener_key:
            continue
        s.add(
            AddressRule(
                project_id=project_id,
                speaker_key=c.speaker_key,
                listener_key=c.listener_key,
                self_term=c.self_term,
                address_term=c.address_term,
                note=c.note,
                status="suggested",
            )
        )
        seen.add(key)
        added += 1
    return added
