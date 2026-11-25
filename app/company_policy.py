"""Company skip and per-company apply limits for NixNet Job Command."""
import calendar
import datetime
import json

GOOGLE_POLICY_URL = "https://support.google.com/googlecareers/answer/6095391?hl=en"
GOOGLE_POLICY_NOTE = "You can apply to up to three jobs within a rolling 30 day window."
WINDOW_KINDS = ("rolling", "calendar_month")


def co_key(name):
    return (name or "").strip().lower()


def setting(c, k, default=None):
    row = c.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["v"])
    except Exception:
        return default


def set_setting(c, k, v):
    c.execute(
        "INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (k, json.dumps(v)),
    )


def ensure_defaults(c):
    if setting(c, "company_apply_limits") is None:
        set_setting(c, "company_apply_limits", [{
            "company": "Google",
            "max_apps": 3,
            "window_days": 30,
            "window_kind": "rolling",
            "policy_url": GOOGLE_POLICY_URL,
            "note": GOOGLE_POLICY_NOTE,
        }])
    if setting(c, "company_skips") is None:
        set_setting(c, "company_skips", [])
    if setting(c, "company_extra_applications") is None:
        set_setting(c, "company_extra_applications", [])


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def add_calendar_month(d):
    y, m = d.year, d.month + 1
    if m == 13:
        y, m = y + 1, 1
    last = calendar.monthrange(y, m)[1]
    return datetime.date(y, m, min(d.day, last))


def next_open_date(dates, max_apps, window_days, window_kind):
    """dates is a sorted list of YYYY-MM-DD strings. None means a slot is open now."""
    max_apps = int(max_apps)
    if max_apps < 1 or len(dates) < max_apps:
        return None
    oldest = parse_date(dates[-max_apps])
    if not oldest:
        return None
    if window_kind == "calendar_month":
        return add_calendar_month(oldest)
    return oldest + datetime.timedelta(days=int(window_days or 30))


def _receipt_id(url):
    if not url:
        return ""
    return str(url).rstrip("/").split("/")[-1].lower()


def application_dates(jobs, extras, company):
    key = co_key(company)
    out = []
    seen = set()
    for j in jobs or []:
        if co_key(j.get("company")) != key:
            continue
        da = parse_date(j.get("date_applied"))
        if not da:
            continue
        rec = _receipt_id((j.get("gmail_receipt_url") or j.get("receipt_url")))
        if rec:
            seen.add(rec)
        out.append({
            "date": da.isoformat(),
            "ref": j.get("ref"),
            "role": j.get("role"),
            "status": j.get("status"),
            "receipt": (j.get("gmail_receipt_url") or j.get("receipt_url")),
        })
    for e in extras or []:
        if co_key(e.get("company")) != key:
            continue
        da = parse_date(e.get("date_applied"))
        if not da:
            continue
        rec = _receipt_id((e.get("gmail_receipt_url") or e.get("receipt_url")))
        if rec and rec in seen:
            continue
        out.append({
            "date": da.isoformat(),
            "ref": None,
            "role": e.get("note") or "Unmapped receipt",
            "status": "extra",
            "receipt": (e.get("gmail_receipt_url") or e.get("receipt_url")),
        })
        if rec:
            seen.add(rec)
    out.sort(key=lambda x: (x["date"], x.get("ref") or ""))
    return out


def skip_until_active(skip, today):
    """True if a manual skip still holds. Jobs return to the queue on the until date."""
    if not skip:
        return False
    until = parse_date(skip.get("until"))
    if until is None:
        return True
    return today < until


def _empty_state(name):
    return {
        "company": name,
        "max_apps": None,
        "window_days": None,
        "window_kind": None,
        "policy_url": None,
        "note": None,
        "applications": [],
        "used": 0,
        "at_cap": False,
        "next_open": None,
        "skip": None,
        "paused": False,
        "pause_until": None,
        "pause_reason": None,
        "banner": None,
        "to_apply": 0,
        "queued": 0,
    }


def company_policy(c, jobs, today=None):
    today = today or datetime.date.today()
    limits = setting(c, "company_apply_limits") or []
    skips = setting(c, "company_skips") or []
    extras = setting(c, "company_extra_applications") or []
    by = {}

    def slot(name):
        k = co_key(name)
        if not k:
            return None
        if k not in by:
            st = _empty_state(name)
            by[k] = st
        elif name and by[k]["company"] and by[k]["company"].islower() and name != by[k]["company"]:
            by[k]["company"] = name
        elif name and not by[k]["company"]:
            by[k]["company"] = name
        return by[k]

    for lim in limits:
        s = slot(lim.get("company"))
        if not s:
            continue
        s["company"] = lim.get("company") or s["company"]
        s["max_apps"] = int(lim["max_apps"]) if lim.get("max_apps") is not None else None
        s["window_days"] = int(lim["window_days"]) if lim.get("window_days") is not None else None
        s["window_kind"] = lim.get("window_kind") or "rolling"
        s["policy_url"] = lim.get("policy_url")
        s["note"] = lim.get("note")

    for sk in skips:
        s = slot(sk.get("company"))
        if s:
            s["company"] = sk.get("company") or s["company"]
            s["skip"] = {
                "company": sk.get("company"),
                "until": sk.get("until") or None,
                "created_at": sk.get("created_at"),
                "source": sk.get("source") or "manual",
                "note": sk.get("note"),
            }

    for j in jobs or []:
        s = slot(j.get("company"))
        if not s:
            continue
        # Prefer the casing already on the job
        if j.get("company"):
            s["company"] = j.get("company")
        if j.get("status") == "To apply":
            s["to_apply"] += 1

    # Only emit companies that have a limit, a skip, extras, or To apply jobs? We need
    # states for limited and skipped companies; To apply counts are useful on those.
    # Build usage for limited companies, pause for skip + cap.
    keep = {}
    for k, s in by.items():
        apps = application_dates(jobs, extras, s["company"])
        s["applications"] = apps
        s["used"] = len(apps)
        if s["max_apps"]:
            nxt = next_open_date(
                [a["date"] for a in apps],
                s["max_apps"],
                s["window_days"] or 30,
                s["window_kind"] or "rolling",
            )
            if nxt and today < nxt:
                s["at_cap"] = True
                s["next_open"] = nxt.isoformat()
            elif nxt and today >= nxt:
                s["at_cap"] = False
                s["next_open"] = nxt.isoformat()
            else:
                s["at_cap"] = False
                s["next_open"] = None

        cap_until = parse_date(s["next_open"]) if s["at_cap"] else None
        manual = skip_until_active(s.get("skip"), today)
        manual_until = parse_date((s.get("skip") or {}).get("until")) if manual else None
        manual_indefinite = manual and not (s.get("skip") or {}).get("until")

        if manual or s["at_cap"]:
            s["paused"] = True
            if manual_indefinite:
                s["pause_until"] = None
            elif manual_until and cap_until:
                s["pause_until"] = max(manual_until, cap_until).isoformat()
            elif manual_until:
                s["pause_until"] = manual_until.isoformat()
            elif cap_until:
                s["pause_until"] = cap_until.isoformat()
            if manual and s["at_cap"]:
                s["pause_reason"] = "apply_limit+skip"
            elif s["at_cap"]:
                s["pause_reason"] = "apply_limit"
            else:
                s["pause_reason"] = "skip"

        if s["at_cap"] and s["max_apps"]:
            when = s["next_open"] or "soon"
            s["banner"] = "%s: %d/%d used, next slot opens %s" % (
                s["company"], s["used"], s["max_apps"], when)
        elif s["paused"] and s.get("skip"):
            if s["pause_until"]:
                s["banner"] = "%s: skipped until %s" % (s["company"], s["pause_until"])
            else:
                s["banner"] = "%s: skipped (resume anytime)" % s["company"]
        elif s["max_apps"]:
            s["banner"] = "%s: %d/%d used" % (s["company"], s["used"], s["max_apps"])

        if s["paused"]:
            s["queued"] = 0
        else:
            s["queued"] = s["to_apply"]

        # Keep limited companies, skipped companies, and anything paused/bannered.
        if s["max_apps"] or s.get("skip") or s["paused"] or (s["used"] and s["max_apps"]):
            keep[k] = s

    banners = [keep[k]["banner"] for k in sorted(keep) if keep[k].get("banner") and (keep[k]["paused"] or keep[k]["at_cap"])]
    def _stretch(j):
        v = (j or {}).get("stretch")
        return v is True or v == 1 or v == "true" or v == "1"

    queued = sum(1 for j in (jobs or []) if j.get("status") == "To apply" and not _stretch(j) and not (keep.get(co_key(j.get("company"))) or {}).get("paused"))
    paused_to_apply = sum(1 for j in (jobs or []) if j.get("status") == "To apply" and not _stretch(j) and (keep.get(co_key(j.get("company"))) or {}).get("paused"))
    stretch_to_apply = sum(1 for j in (jobs or []) if j.get("status") == "To apply" and _stretch(j))
    return {
        "today": today.isoformat(),
        "limits": limits,
        "skips": skips,
        "extras": extras,
        "companies": keep,
        "banners": banners,
        "queued_to_apply": queued,
        "paused_to_apply": paused_to_apply,
        "stretch_to_apply": stretch_to_apply,
    }


def annotate_jobs(jobs, policy):
    companies = (policy or {}).get("companies") or {}
    for j in jobs or []:
        st = companies.get(co_key(j.get("company"))) or {}
        j["company_paused"] = bool(st.get("paused"))
        j["pause_until"] = st.get("pause_until")
        j["pause_reason"] = st.get("pause_reason")
    return jobs


def upsert_skip(c, company, until=None, source="manual", note=None, now_iso=None):
    company = (company or "").strip()
    if not company:
        raise ValueError("company is required")
    until_s = None
    if until:
        d = parse_date(until)
        if not d:
            raise ValueError("until must be YYYY-MM-DD")
        until_s = d.isoformat()
    skips = [s for s in (setting(c, "company_skips") or []) if co_key(s.get("company")) != co_key(company)]
    skips.append({
        "company": company,
        "until": until_s,
        "created_at": now_iso or datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": source or "manual",
        "note": note,
    })
    set_setting(c, "company_skips", skips)
    return skips


def resume_skip(c, company):
    company = (company or "").strip()
    if not company:
        raise ValueError("company is required")
    skips = [s for s in (setting(c, "company_skips") or []) if co_key(s.get("company")) != co_key(company)]
    set_setting(c, "company_skips", skips)
    return skips


def upsert_limit(c, body):
    company = (body.get("company") or "").strip()
    if not company:
        raise ValueError("company is required")
    try:
        max_apps = int(body["max_apps"])
        window_days = int(body.get("window_days") or 30)
    except (KeyError, TypeError, ValueError):
        raise ValueError("max_apps and window_days must be integers")
    if max_apps < 1 or window_days < 1:
        raise ValueError("max_apps and window_days must be >= 1")
    kind = body.get("window_kind") or "rolling"
    if kind not in WINDOW_KINDS:
        raise ValueError("window_kind must be rolling or calendar_month")
    item = {
        "company": company,
        "max_apps": max_apps,
        "window_days": window_days,
        "window_kind": kind,
        "policy_url": body.get("policy_url") or "",
        "note": body.get("note") or "",
    }
    limits = [x for x in (setting(c, "company_apply_limits") or []) if co_key(x.get("company")) != co_key(company)]
    limits.append(item)
    limits.sort(key=lambda x: co_key(x.get("company")))
    set_setting(c, "company_apply_limits", limits)
    return limits


def replace_limits(c, limits):
    if not isinstance(limits, list):
        raise ValueError("limits must be a list")
    out = []
    seen = set()
    for raw in limits:
        company = (raw.get("company") or "").strip()
        if not company:
            raise ValueError("each limit needs a company")
        k = co_key(company)
        if k in seen:
            raise ValueError("duplicate company in limits: %s" % company)
        seen.add(k)
        try:
            max_apps = int(raw["max_apps"])
            window_days = int(raw.get("window_days") or 30)
        except (KeyError, TypeError, ValueError):
            raise ValueError("max_apps and window_days must be integers")
        if max_apps < 1 or window_days < 1:
            raise ValueError("max_apps and window_days must be >= 1")
        kind = raw.get("window_kind") or "rolling"
        if kind not in WINDOW_KINDS:
            raise ValueError("window_kind must be rolling or calendar_month")
        out.append({
            "company": company,
            "max_apps": max_apps,
            "window_days": window_days,
            "window_kind": kind,
            "policy_url": raw.get("policy_url") or "",
            "note": raw.get("note") or "",
        })
    set_setting(c, "company_apply_limits", out)
    return out


def remove_limit(c, company):
    company = (company or "").strip()
    if not company:
        raise ValueError("company is required")
    limits = [x for x in (setting(c, "company_apply_limits") or []) if co_key(x.get("company")) != co_key(company)]
    set_setting(c, "company_apply_limits", limits)
    return limits


def upsert_extra(c, body):
    company = (body.get("company") or "").strip()
    da = parse_date(body.get("date_applied"))
    if not company or not da:
        raise ValueError("company and date_applied are required")
    rec = (body.get("gmail_receipt_url") or body.get("receipt_url")) or ""
    extras = setting(c, "company_extra_applications") or []
    rid = _receipt_id(rec)
    kept = []
    for e in extras:
        if rid and _receipt_id((e.get("gmail_receipt_url") or e.get("receipt_url"))) == rid:
            continue
        kept.append(e)
    kept.append({
        "company": company,
        "date_applied": da.isoformat(),
        "gmail_receipt_url": rec,
        "note": body.get("note") or "",
    })
    set_setting(c, "company_extra_applications", kept)
    return kept
