#!/usr/bin/env python3
"""Hostile input against every endpoint the brief names.

    python3 /golden/probes/abuse.py <config.json>

config: {"base_url", "endpoints": [{"method", "path"}], "out_dir"}

The one question it asks is "does the server stay standing?": every response to
garbage must be a deliberate 4xx, never a 5xx or a dropped connection. Whether a
refusal is the RIGHT refusal is the bundle's own pytest suite's job, and the
task-specific cases (races, replays, cross-tenant) are the golden_tests/abuse/
suite's. Writes <out_dir>/abuse.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import httpx

PARAM = re.compile(r"\{[^}/]+\}|:[A-Za-z_][A-Za-z0-9_]*|<[^>/]+>")
BAD_IDS = ["0", "-1", "999999999999999999999999", "abc", "..%2F..%2Fetc%2Fpasswd",
           "%27%20OR%201%3D1--", "%00", "x" * 300, "%F0%9F%92%A9"]
BAD_BODIES = {
    "malformed_json": ("{not json", "application/json"),
    "wrong_types": (json.dumps({"id": {"$ne": 1}, "name": [[[]]], "amount": "1e309",
                                "email": 12, "items": "x"}), "application/json"),
    "empty_object": ("{}", "application/json"),
    "oversize": (json.dumps({"name": "x" * 1_500_000}), "application/json"),
    "form_not_json": ("a=1&b=2", "application/x-www-form-urlencoded"),
}
WRITE = {"POST", "PUT", "PATCH", "DELETE"}


def fill(path: str, value: str) -> str:
    return PARAM.sub(value, path)


def call(client: httpx.Client, method: str, url: str, case: str, body=None, ctype=None) -> dict:
    headers = {"content-type": ctype} if ctype else {}
    row = {"method": method, "url": url, "case": case}
    try:
        r = client.request(method, url, content=body, headers=headers)
        row["status"] = r.status_code
    except httpx.HTTPError as exc:
        row["status"] = None
        row["error"] = f"{exc.__class__.__name__}: {str(exc)[:160]}"
    return row


def main() -> int:
    cfg = json.loads(Path(sys.argv[1]).read_text())
    base, out = cfg["base_url"].rstrip("/"), Path(cfg["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        for ep in cfg.get("endpoints") or []:
            method, path = ep["method"].upper(), ep["path"]
            has_param = bool(PARAM.search(path))
            targets = [fill(path, v) for v in BAD_IDS] if has_param else [path]
            for target in targets:
                case = "bad_path_param" if has_param else "plain"
                if method in WRITE:
                    for name, (body, ctype) in BAD_BODIES.items():
                        rows.append(call(client, method, base + target, f"{case}+{name}", body, ctype))
                else:
                    rows.append(call(client, method, base + target, case))
    crashes = [r for r in rows if r["status"] is None or r["status"] >= 500]
    unauth_writes = [r for r in rows if r["method"] in WRITE and r["status"] and 200 <= r["status"] < 300]
    (out / "abuse.json").write_text(json.dumps({"calls": len(rows), "crashes": crashes,
                                                "unauthenticated_writes_accepted": unauth_writes,
                                                "rows": rows}, indent=2))
    print(f"abuse.py: {len(rows)} hostile call(s), {len(crashes)} crash(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
