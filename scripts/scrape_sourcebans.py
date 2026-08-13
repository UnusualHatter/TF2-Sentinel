#!/usr/bin/env python3
import argparse, json, re, time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

STEAM2 = re.compile(r"STEAM_[0-5]:[01]:\d+")
STEAM3 = re.compile(r"\[U:[0-5]:\d+\]")
STEAM64 = re.compile(r"\b7656119\d{10}\b")

def scrape(base_url, pages, delay=1.0, timeout=15):
    session=requests.Session()
    session.headers["User-Agent"]="Holiday-CheaterDB/1.0 (+public SourceBans importer)"
    records=[]; seen=set()
    for page in range(1,pages+1):
        url=f"{base_url.rstrip('/')}/index.php?p=banlist&page={page}"
        r=session.get(url,timeout=timeout); r.raise_for_status()
        soup=BeautifulSoup(r.text,"html.parser")
        rows=soup.select("table tr")
        found=0
        for row in rows:
            text=" ".join(row.stripped_strings)
            match=STEAM3.search(text) or STEAM2.search(text) or STEAM64.search(text)
            if not match: continue
            steam_id=match.group(0)
            links=[urljoin(url,a.get("href")) for a in row.find_all("a") if a.get("href")]
            key=(steam_id,text)
            if key in seen: continue
            seen.add(key); found+=1
            records.append({"steam_id":steam_id,"row_text":text,"links":links,"source_url":url})
        if found == 0 and page > 1: break
        time.sleep(delay)
    return records

def main():
    ap=argparse.ArgumentParser(description="Scrape a public SourceBans ban list into a portable JSON snapshot.")
    ap.add_argument("--url",required=True)
    ap.add_argument("--pages",type=int,default=10)
    ap.add_argument("--delay",type=float,default=1.0)
    ap.add_argument("--out",required=True)
    args=ap.parse_args()
    rows=scrape(args.url,args.pages,args.delay)
    with open(args.out,"w",encoding="utf-8") as f:
        json.dump({"source":args.url,"records":rows},f,ensure_ascii=False,indent=2)
    print(f"saved {len(rows)} records to {args.out}")
if __name__=="__main__": main()
