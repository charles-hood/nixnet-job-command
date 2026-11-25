#!/usr/bin/env python3
"""Duplicate-job detection for NixNet Job Command.

Same normalized apply URL (query string and fragment stripped), or the same
company plus a near-identical role title. Used by the API audit and kept in
sync with the front-end logic in app.js.
"""
import re
from urllib.parse import urlsplit

LATER = ("Applied", "Next steps", "Interview scheduled", "Offer", "Rejected")

def norm_url(u):
    if not u:
        return ""
    u = str(u).strip()
    try:
        p = urlsplit(u)
    except Exception:
        return u.split("?")[0].split("#")[0].rstrip("/").lower()
    if p.scheme and p.netloc:
        path = (p.path or "/").rstrip("/") or "/"
        return (p.scheme + "://" + p.netloc.lower() + path).lower()
    return u.split("?")[0].split("#")[0].rstrip("/").lower()

def job_url(j):
    return norm_url(j.get("apply_url")) or norm_url(j.get("posting_url"))

def norm_role(r):
    s = (r or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def role_near(a, b):
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        shorter = a if len(a) < len(b) else b
        return len(shorter.split()) >= 3 or len(shorter) >= 20
    A, B = set(a.split()), set(b.split())
    if not A or not B:
        return False
    inter = len(A & B)
    uni = len(A | B)
    jacc = inter / float(uni) if uni else 0
    # Sequence-like ratio on compact strings, no extra imports beyond stdlib
    ra = _ratio(a, b)
    return (jacc >= 0.85 and ra >= 0.8) or ra >= 0.95

def _ratio(a, b):
    try:
        from difflib import SequenceMatcher
        return SequenceMatcher(None, a, b).ratio()
    except Exception:
        return 0.0

def is_later(j):
    if (j.get("status") or "") in LATER:
        return True
    return bool(j.get("date_applied")) and (j.get("status") or "") not in ("To apply",)

def find_duplicates(job, jobs, require_later=True):
    """Return other jobs that look like the same application."""
    url = job_url(job)
    role = norm_role(job.get("role"))
    company = (job.get("company") or "").strip().lower()
    out = []
    for other in jobs:
        if not other or other.get("ref") == job.get("ref"):
            continue
        if require_later and not is_later(other):
            continue
        ou = job_url(other)
        url_hit = bool(url and ou and url == ou)
        role_hit = bool(
            company
            and company == (other.get("company") or "").strip().lower()
            and role_near(role, norm_role(other.get("role")))
        )
        if url_hit or role_hit:
            item = dict(other)
            item["_dup_via"] = "url+role" if url_hit and role_hit else ("url" if url_hit else "role")
            out.append(item)
    return out

def audit_pairs(jobs, require_later=False):
    """All unique pairs. require_later=False for the one-time full audit."""
    pairs = []
    seen = set()
    for i, a in enumerate(jobs):
        for b in find_duplicates(a, jobs[i + 1 :], require_later=require_later):
            key = tuple(sorted([a.get("ref"), b.get("ref")]))
            if key in seen:
                continue
            seen.add(key)
            pairs.append({
                "a": a.get("ref"),
                "b": b.get("ref"),
                "via": b.get("_dup_via"),
                "company": a.get("company"),
                "a_role": a.get("role"),
                "b_role": b.get("role"),
                "a_status": a.get("status"),
                "b_status": b.get("status"),
                "a_applied": a.get("date_applied") or "",
                "b_applied": b.get("date_applied") or "",
                "a_url": a.get("apply_url") or a.get("posting_url") or "",
                "b_url": b.get("apply_url") or b.get("posting_url") or "",
            })
    return pairs
