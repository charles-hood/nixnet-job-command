#!/usr/bin/env python3
"""Generate custom answers from a jobs JSON file and the local profile.

  python3 builder/gen_custom_answers.py [--profile profile.json] jobs.json [out.json]

This calls the same engine the app uses. It does not talk to the live
server, and it never sends mail or messages.
"""
import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app"))


def main():
    p = argparse.ArgumentParser(description="Generate profile-grounded custom answers.")
    p.add_argument("jobs", help="JSON file: a list of jobs, or {\"jobs\": [...]}")
    p.add_argument("out", nargs="?", help="Output JSON (default: stdout)")
    p.add_argument("--profile", help="Path to profile.json")
    args = p.parse_args()
    if args.profile:
        os.environ["NJC_PROFILE"] = args.profile
    os.environ.setdefault("NJC_ROOT", str(REPO))
    import config
    config.CFG.reload()
    import custom_answers as CA
    payload = json.load(open(args.jobs))
    jobs = payload["jobs"] if isinstance(payload, dict) and "jobs" in payload else payload
    out = {j["ref"]: CA.generate(j) for j in jobs if j.get("ref")}
    text = json.dumps(out, indent=2) + "\n"
    if args.out:
        open(args.out, "w").write(text)
        print("wrote", args.out, "jobs", len(out))
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
