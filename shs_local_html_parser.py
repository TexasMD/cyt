import csv
import glob
import re
from pathlib import Path
from bs4 import BeautifulSoup

BASKET_DIR = Path(r"D:\Music\MusicDB\basket")
OUTPUT_CSV = BASKET_DIR / "VERIFIED" / "SHSscrapeMyMusicBaseFiltered2_cleaned_VERIFIED_V2.csv"

CSV_FIELDNAMES = [
    "original song id",
    "original title",
    "original artist",
    "original artist id",
    "additional original artist",
    "additional original artist id",
    "other original artists",
    "other original artists ids",
    "performance id",
    "performance title",
    "performing artist",
    "performing artist id",
    "additional performing artist",
    "additional performing artist id",
    "other performing artists",
    "other performing artists ids",
    "release date",
    "info"
]

def uri_id(url):
    return str(url or "").rsplit("/", 1)[-1]

def clean(text):
    return " ".join((str(text) or "").split()).strip()

def append_rows(path: Path, rows: list[dict]):
    if not rows: return
    # Only write header if file is empty
    if not path.exists() or path.stat().st_size == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            
    with path.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writerows(rows)

def parse_html_file(filepath: Path):
    with filepath.open("r", encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
        
    rows = []
    
    trs = soup.find_all("tr", class_=re.compile("refresh-click-select-row"))
    for tr in trs:
        title_td = tr.find("td", class_=re.compile("field-title"))
        perf_td = tr.find("td", class_=re.compile("field-performer.name"))
        orig_td = tr.find("td", class_=re.compile("field-original"))
        date_td = tr.find("td", class_=re.compile("field-creationDate"))
        
        if not title_td or not perf_td or not orig_td:
            continue
            
        title_a = title_td.find("a")
        perf_a = perf_td.find("a")
        orig_a = orig_td.find("a")
        
        if not title_a or not perf_a or not orig_a:
            continue
            
        r = {k: "" for k in CSV_FIELDNAMES}
        
        r["performance title"] = clean(title_a.text)
        r["performance id"] = uri_id(title_a.get("href"))
        
        r["performing artist"] = clean(perf_a.text)
        r["performing artist id"] = uri_id(perf_a.get("href"))
        
        r["original artist"] = clean(orig_a.text)
        r["original artist id"] = uri_id(orig_a.get("href"))
        
        if date_td:
            r["release date"] = clean(date_td.text)
            
        r["info"] = "Local HTML Scrape"
        
        rows.append(r)
        
    return rows

def run():
    html_files = glob.glob(str(BASKET_DIR / "*.html"))
    print(f"Found {len(html_files)} HTML files to parse.")
    
    total_rows = 0
    buffer = []
    for f in html_files:
        try:
            r = parse_html_file(Path(f))
            if r:
                buffer.extend(r)
                total_rows += len(r)
        except Exception as e:
            print(f"Error parsing {f}: {e}")
            
    if buffer:
        append_rows(OUTPUT_CSV, buffer)
        
    print(f"Successfully extracted {total_rows} rows from local HTML files and appended to V2 CSV.")

if __name__ == "__main__":
    run()
