#!/usr/bin/env python3
import argparse, json, re
from pathlib import Path

BASE = 76561197960265728
STEAM3 = re.compile(r"^\[U:(\d+):(\d+)\]$")
STEAM2 = re.compile(r"^STEAM_[0-5]:([01]):(\d+)$")

def normalize(raw):
    raw = str(raw).strip()
    if raw.isdigit() and int(raw) >= BASE:
        n=int(raw); return n, n-BASE, f"[U:1:{n-BASE}]"
    m=STEAM3.match(raw)
    if m:
        aid=int(m.group(2)); return BASE+aid, aid, f"[U:1:{aid}]"
    m=STEAM2.match(raw)
    if m:
        aid=int(m.group(2))*2+int(m.group(1)); return BASE+aid, aid, f"[U:1:{aid}]"
    raise ValueError(f"unsupported Steam ID: {raw}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("playerlist", type=Path)
    args=ap.parse_args()
    data=json.loads(args.playerlist.read_text(encoding="utf-8"))
    out=[]
    for rec in data.get("players",[]):
        sid64, aid, steam3=normalize(rec["steamid"])
        out.append({"steamid64":sid64,"account_id":aid,"steam3":steam3,"record":rec})
    print(json.dumps(out, ensure_ascii=False, indent=2))
if __name__ == "__main__": main()
