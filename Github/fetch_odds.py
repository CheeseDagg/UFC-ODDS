#!/usr/bin/env python3
"""Fetch the next event's odds from fightodds.io's GraphQL API -> raw.json.
Stdlib only (urllib) so it runs anywhere with no pip install."""
import urllib.request, urllib.error, json, pathlib, sys
HERE = pathlib.Path(__file__).parent
URL = "https://api.fightodds.io/gql"
HEADERS = {
    "content-type": "application/json",
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "origin": "https://fightodds.io",
    "referer": "https://fightodds.io/",
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"),
}
def main():
    body = (HERE / "query.json").read_bytes()
    req = urllib.request.Request(URL, data=body, method="POST", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"FETCH FAILED: HTTP {e.code} {e.reason} -- the API may be blocking this IP.")
    except Exception as e:
        sys.exit(f"FETCH FAILED: {e}")
    try:
        J = json.loads(data)
    except Exception:
        sys.exit("FETCH FAILED: response was not JSON (likely a block/challenge page).")
    eot = (J.get("data", {}) or {}).get("eventOfferTable")
    if not eot:
        sys.exit("FETCH FAILED: response had no eventOfferTable (blocked or schema changed).")
    (HERE / "raw.json").write_bytes(data)
    n = len(eot.get("fightOffers", {}).get("edges", []))
    print(f"Fetched {len(data)} bytes -- {eot.get('name')} ({n} fights)")
if __name__ == "__main__":
    main()
