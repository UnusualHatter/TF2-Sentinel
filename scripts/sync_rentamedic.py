#!/usr/bin/env python3
import argparse, csv, json, time
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',default='data/raw/web/rentamedic_lookup.json'); ap.add_argument('--batch-size',type=int,default=100); args=ap.parse_args()
    with (ROOT/'data/normalized/accounts.csv').open(encoding='utf-8',newline='') as f: ids=[r['steamid64'] for r in csv.DictReader(f)]
    results=[]; s=requests.Session()
    for i in range(0,len(ids),min(args.batch_size,100)):
        batch=ids[i:i+min(args.batch_size,100)]
        while True:
            r=s.get('https://rentamedic.org/api/cheaters/lookup',params={'steamids':','.join(batch)},timeout=30)
            if r.status_code==429: time.sleep(10); continue
            r.raise_for_status(); results.extend(r.json().get('results',[])); break
    out=ROOT/args.out; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps({'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Wrote {len(results)} matching records to {out}')
if __name__=='__main__': main()
