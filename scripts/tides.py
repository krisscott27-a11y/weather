"""Download Queensland Government (MSQ) predicted high/low tides for Shorncliffe pier
and write tides.json for the app. Times are AEST (UTC+10); heights are metres above LAT."""
import csv, io, json, re, sys, urllib.request
from datetime import datetime, timezone

DATASET = "595d3eb3-3412-4a5d-ad2f-5071657128e0"  # Shorncliffe tide gauge, predicted high/low data
API = "https://www.data.qld.gov.au/api/3/action/package_show?id=" + DATASET
UA = {"User-Agent": "weather-app-tides/1.0"}

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()

pkg = json.loads(get(API))["result"]
year = datetime.now(timezone.utc).year
wanted = [r for r in pkg["resources"] if r.get("format", "").lower() == "csv" and re.search(r"(%d|%d)" % (year, year + 1), (r.get("name") or "") + r.get("url", ""))]
print("resources:", [(r.get("name"), r["url"]) for r in wanted])

events = []
for r in wanted:
    text = get(r["url"]).decode("utf-8-sig", "replace")
    if not text.strip():
        # The file download can come back empty for scripts; fall back to the CKAN datastore API
        rows, offset = [], 0
        while True:
            res = json.loads(get(f"https://www.data.qld.gov.au/api/3/action/datastore_search?resource_id={r['id']}&limit=5000&offset={offset}"))["result"]
            if offset == 0: print("fields:", [f["id"] for f in res["fields"]], "total:", res.get("total"))
            recs = res["records"]
            names = [f["id"] for f in res["fields"] if f["id"] != "_id"]
            rows += [",".join(str(rec.get(n, "")) for n in names) for rec in recs]
            offset += len(recs)
            if not recs or offset >= res.get("total", 0): break
        text = "\n".join(rows)
    lines = text.splitlines()
    print("----", r["url"], len(lines), "lines")
    for l in lines[:12]: print("HEAD|", l)
    for l in lines[-3:]: print("TAIL|", l)
    for row in csv.reader(io.StringIO(text)):
        cells = [c.strip() for c in row if c.strip()]
        joined = " ".join(cells)
        # Find a date+time and a height in each row, whatever the exact layout
        m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})[ T]+(\d{1,2}):(\d{2})", joined) or None
        if m:
            y, mo, d, hh, mm = map(int, m.groups())
        else:
            m = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})[ T]+(\d{1,2}):(\d{2})", joined)
            if not m: continue
            d, mo, y, hh, mm = map(int, m.groups())
        rest = joined[m.end():]
        h = re.search(r"(-?\d+\.\d+)", rest)
        if not h: continue
        events.append([f"{y:04d}-{mo:02d}-{d:02d}T{hh:02d}:{mm:02d}", float(h.group(1))])

events = sorted({e[0]: e for e in events}.values())
# Label highs and lows by comparing with neighbours
out = []
for i, (t, h) in enumerate(events):
    prev = events[i - 1][1] if i else None
    nxt = events[i + 1][1] if i + 1 < len(events) else None
    ref = prev if prev is not None else nxt
    out.append({"t": t, "h": round(h, 2), "type": "high" if h > ref else "low"})
print("events:", len(out), out[:4], out[-2:])
if len(out) < 100:
    sys.exit("Too few tide events parsed; leaving tides.json unchanged")
json.dump({"station": "Shorncliffe pier", "source": "Maritime Safety Queensland predictions via data.qld.gov.au",
           "tz": "+10:00", "datum": "LAT", "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "events": out},
          open("tides.json", "w"), separators=(",", ":"))
