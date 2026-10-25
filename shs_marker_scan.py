#!/usr/bin/env python3
"""Find ~20 SHS saved pages whose union covers every metadata marker.

Usage: python shs_marker_scan.py
Reads a capped random sample from each collection (caps below), classifies every
file by page type, records which extraction markers are present, and writes
marker_scan.json next to this script.

This is the script used to select the 20 archetype example pages documented in
SHS_metadata_inventory.csv / SHS_example_pages_coverage.csv.
"""
import os, re, json, random
from collections import Counter

DIRS = {
 'G1a': r"E:\MDBsources\SHS",
 'G1b': r"E:\MusicDBsourcematerial\raw\saved_web_pages\SHS-HTML",
 'G2a': r"E:\CYT\sources\original\SHS",
 'G2b': r"E:\CYT2\sources\original\SHS\html",
 'G3a': r"E:\CYT\sources\zOLDderived\SHS_transformed",
 'G3b': r"E:\CYT2\sources\derived\SHS\html",
 'G3c': r"E:\CYT\sources\zOLDderived\SHS-audit\originals",
}

# marker name -> bytes regex (checked in every file, regardless of type)
MARKERS = {
  # provenance / generation
  'gen1_saved_from': rb'saved from url=\(\d+\)',
  'gen1_source_url': rb'name="source-webpage-url"',
  'gen3_cyt_meta': rb'name="cyt:',
  'canonical': rb'rel="canonical"',
  'og_url': rb'property="og:url"',
  # head
  'meta_description': rb'name="description"|property="og:description"',
  'meta_keywords': rb'name="keywords"',
  'og_title': rb'property="og:title"',
  'og_type_song': rb'property="og:type" content="music.song"',
  # work
  'work_rank_badge': rb'statistics/stats_work_covered\?year=\d+',
  'work_iswc': rb'<dt>\s*ISWC',
  'work_published_by': rb'<dt>\s*Published by',
  'sec_adaptations': rb'section-title">\s*(<a[^>]*>)?\s*Adaptations',
  'sec_partial_adapt': rb'section-title">\s*Partial adaptations',
  'sec_versions': rb'section-title">\s*Versions',
  'sec_web_covers': rb'section-title">\s*Web [Cc]overs',
  'sec_forum': rb'section-title">\s*Forum topics',
  'work_orig_first_release': rb'>\s*First release\s*<',
  # performance
  'perf_released_on': rb'<dt>\s*Released on',
  'perf_chart': rb'<dt>\s*Chart placings',
  'perf_tags': rb'search/performance\?tag=',
  'perf_comments': rb'<dt>\s*Comments',
  'perf_other_version': rb'<dt>\s*Other version',
  'perf_streaming': rb'streaming-service-link',
  'sec_sampled_by': rb'section-title">\s*Sampled by',
  # artist
  'art_personal_name': rb'<dt>\s*Personal name',
  'art_born': rb'itemprop="birthDate"',
  'art_country': rb'search/artist\?country=',
  'art_ipi': rb'id="root.ipis"',
  'art_affiliation': rb'<dt>\s*Affiliation',
  'art_aliases': rb'id="root.aliases"',
  'art_members': rb'<dt>\s*Members',
  'art_related': rb'<dt>\s*Related',
  'art_ranking': rb'<dt>\s*Ranking',
  'art_is_group': rb'schema.org/MusicGroup',
  'sec_covers_by': rb'section-title">\s*Covers by',
  'sec_songs_written': rb'section-title">\s*Songs written by',
  'sec_releases': rb'section-title">\s*Releases',
  'sec_albums': rb'<h3[^>]*>\s*Albums',
  'sec_singles': rb'<h3[^>]*>\s*Singles',
  'sec_appear_on': rb'Performances also appear on',
  'sec_tributes': rb'section-title">\s*Tributes',
  'sec_web_covers_by': rb'Web Covers by',
  # release
  'rel_date': rb'itemprop="datePublished"',
  'rel_label': rb'href="/label/\d+"',
  'rel_ean': rb'<dt[^>]*>\s*EAN',
  'rel_format': rb'musicReleaseFormat',
  'rel_tracks': rb'id="root.tracks"',
  # search
  'search_results_title': rb'<title>\s*Search Results for',
  'sec_contributions': rb'section-title">\s*Contributions',
  'tag_facet': rb'search/performance\?tag=[^" ]+"',
  'country_facet': rb'search/artist\?country=[A-Z]{2}',
  # referenced
  'youtube': rb'youtube\.com/watch|youtu\.be/',
  'adapt_tree': rb'id="adaptation-tree"',
  'apple_music': rb'music\.apple\.com|itunes\.apple\.com',
}

def page_type(data):
    if re.search(rb'<title>\s*Search Results for', data[:100000]):
        return 'search'
    head = data[:200000]
    m = re.search(rb'secondhandsongs\.com/(work|performance|artist|release|label)/(\d+)', head)
    if m: return m.group(1).decode()
    # fallback: source-webpage-url
    m = re.search(rb'source-webpage-url" content="[^"]*/(work|performance|artist|release|label)/', head)
    if m: return m.group(1).decode()
    m = re.search(rb'itemtype="https?://schema\.org/(MusicComposition|MusicRecording|MusicRelease|Person|MusicGroup)"', head)
    if m:
        return {'MusicComposition':'work','MusicRecording':'performance','MusicRelease':'release',
                'Person':'artist','MusicGroup':'artist'}[m.group(1).decode()]
    return None

def scan(path):
    with open(path,'rb') as f:
        data = f.read()
    t = page_type(data)
    if not t: return None, {}
    hits = {k for k,rx in MARKERS.items() if re.search(rx, data)}
    # version-row granularity
    if t in ('work','performance'):
        if re.search(rb'field-performer', data): hits.add('vrow_performer')
        if re.search(rb'field-date', data): hits.add('vrow_date')
        if re.search(rb'field-instrumental', data): hits.add('vrow_instrumental')
        if re.search(rb'field-info', data): hits.add('vrow_info')
    if t=='release':
        if re.search(rb'field-performer', data): hits.add('vrow_performer')
    return t, hits

def main():
    random.seed(7)
    out_json = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'marker_scan.json')
    pool = []  # (path, gen, type, hits)
    caps = {'G1a':900,'G1b':500,'G2a':1200,'G2b':900,'G3a':400,'G3b':1400,'G3c':400}
    for gen, d in DIRS.items():
        files = [f for f in os.listdir(d) if f.lower().endswith(('.html','.htm'))]
        random.shuffle(files)
        n=0
        for fn in files:
            if n>=caps[gen]: break
            p = os.path.join(d, fn)
            try:
                t, hits = scan(p)
            except Exception:
                continue
            if t:
                pool.append((p, gen, t, hits)); n+=1
    print('scanned pool:', len(pool))
    json.dump([{'path':p,'gen':g,'type':t,'hits':sorted(h)} for p,g,t,h in pool],
              open(out_json,'w'), indent=0)
    print('wrote', out_json)
    # all markers seen
    seen = Counter()
    for _,_,_,h in pool: seen.update(h)
    print('markers never seen in pool:', sorted(set(MARKERS)-set(seen)))

if __name__=='__main__':
    main()
