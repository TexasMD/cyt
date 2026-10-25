#!/usr/bin/env python3
"""Survey saved SHS HTML files: extract page-type signals and metadata markers."""
import os, re, sys, json, random
from collections import Counter

DIRS = [
    r"E:\CYT\sources\zOLDderived\SHS-audit\originals",
    r"E:\CYT2\sources\derived\SHS\html",
    r"E:\CYT\sources\zOLDderived\SHS_transformed",
    r"E:\CYT\sources\original\SHS",
    r"E:\MDBsources\SHS",
    r"E:\MusicDBsourcematerial\raw\saved_web_pages\SHS-HTML",
    r"E:\CYT2\sources\original\SHS\html",
]

RE_URL = re.compile(rb'secondhandsongs\.com/([a-z_-]+)/(\d+)')
RE_TITLE = re.compile(rb'<title>(.*?)</title>', re.S)
RE_CANONICAL = re.compile(rb'<link rel="canonical" href="([^"]+)"')
RE_OGURL = re.compile(rb'property="og:url" content="([^"]+)"')
RE_OGTYPE = re.compile(rb'property="og:type" content="([^"]+)"')

def classify(head_text):
    """Classify page from the first ~60KB of text."""
    m = RE_URL.search(head_text.encode('utf-8', 'ignore')) if isinstance(head_text, str) else None
    return m

def scan_file(path):
    with open(path, 'rb') as f:
        data = f.read()
    info = {}
    t = RE_TITLE.search(data[:200000])
    info['title'] = t.group(1).decode('utf-8', 'ignore')[:150] if t else ''
    for name, rx in [('canonical', RE_CANONICAL), ('ogurl', RE_OGURL)]:
        m = rx.search(data[:200000])
        info[name] = m.group(1).decode('utf-8', 'ignore')[:120] if m else ''
    m = RE_OGTYPE.search(data[:200000])
    info['ogtype'] = m.group(1).decode() if m else ''
    urls = Counter()
    for mm in RE_URL.finditer(data):
        urls[mm.group(1).decode()] += 1
    info['url_types'] = dict(urls)
    # text signals
    low = data.lower()
    info['has_search_results'] = b'search results' in low[:200000]
    info['size'] = len(data)
    return info

def main():
    random.seed(42)
    out = {}
    for d in DIRS:
        if not os.path.isdir(d):
            continue
        files = [f for f in os.listdir(d) if f.lower().endswith('.html')]
        sample = sorted(random.sample(files, min(120, len(files))))
        res = {}
        for fn in sample:
            try:
                res[fn] = scan_file(os.path.join(d, fn))
            except Exception as e:
                res[fn] = {'error': str(e)}
        out[d] = {'total': len(files), 'sample': res}
    with open(r'E:\MDB2\shs_survey.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    # summary
    for d, v in out.items():
        types = Counter()
        for fn, info in v['sample'].items():
            u = info.get('url_types', {})
            if u:
                top = max(u, key=u.get)
                types[top] += 1
            elif info.get('has_search_results'):
                types['SEARCH'] += 1
            else:
                types['UNKNOWN'] += 1
        print(d, v['total'], dict(types))

if __name__ == '__main__':
    main()
