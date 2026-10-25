# Guide to Parsing, Categorizing, and Processing Saved SecondHandSongs (SHS) Webpages

Last updated: 2026-10-24. Based on a survey of the seven saved-page collections listed below (≈ 27,900 files in total) and structural analysis of representative pages of every type.

---

## 1. What SHS pages are and where they come from

SecondHandSongs.com (rebranded **CoverCanvas** in newer/transformed saves) is a structured music database of cover versions, samples, and adaptations. Every entity page is a self-contained HTML document with consistent markup: a machine-readable "infobox" (`<dl>` definition list with `<dt>`/`<dd>` pairs), schema.org microdata (`itemscope`/`itemprop`), and human-readable list sections (`<h2 class="section-title">`).

Because the same site was saved at different times and then reprocessed by several pipelines, the collections contain **three generations** of the same underlying pages. The parsing logic must handle all three.

### 1.1 The seven collections

| # | Directory | Files | Generation | Characteristics |
|---|-----------|-------|------------|-----------------|
| 1 | `E:\CYT\sources\zOLDderived\SHS-audit\originals` | ~2,409 | mixed (G1/G2) | Audit snapshot; mostly `Artist_ …` and `CYT-*` typed filenames; a few typo'd names (`SecondHandSongws`) |
| 2 | `E:\CYT2\sources\derived\SHS\html\` | ~4,608 | **G3 transformed** | CoverCanvas titles, `cyt:` metas, `CYTaccessFiles` assets, URL-encoded names, `CYT-*` typed filenames, numeric-slug names (`01_title.html`, `__perfN`) |
| 3 | `E:\CYT\sources\zOLDderived\SHS_transformed\` | ~2,411 | G3 transformed | Same treatment as #2, older set (`10cc _ SecondHandSongs.html` style names) |
| 4 | `E:\CYT\sources\original\SHS\` | ~5,062 | G2 originals | Clean saves, `SecondHandSongs` titles, numeric-slug + `CYT-*` names |
| 5 | `E:\MDBsources\SHS\` | ~4,530 | **G1 raw saves** | `saved from url=` comments, `_files` companion dirs, `.htm`/`.mhtml` strays, non-SHS contamination |
| 6 | `E:\MusicDBsourcematerial\raw\saved_web_pages\SHS-HTML\` | ~4,563 | G1 raw saves | Same as #5 (parallel copy) |
| 7 | `E:\CYT2\sources\original\SHS\html\` | ~4,791 | G2 originals | Same as #4 |

Generations are described in §3. Note that collections 2↔4↔7 and 3↔1 overlap heavily; expect large-scale duplication of the same SHS entities across directories.

---

## 2. Page-type taxonomy — the entities SHS models

| Type | Live URL shape | Entity | schema.org itemtype on the main block |
|------|---------------|--------|----------------------------------------|
| **Work** | `/work/<id>` (and `/work/<id>/all`) | composition/song | `MusicComposition` |
| **Performance** | `/performance/<id>` (and `/performance/<id>/all`) | a specific recording/release of a work by an artist | `MusicRecording` |
| **Artist** | `/artist/<id>` (and `/artist/<id>/all`) | person or group | `Person` (solo) / `MusicGroup` (band) |
| **Release** | `/release/<id>` | album/single/EP | `MusicRelease` |
| **Label** | `/label/<id>` | record label | `Organization` (only ever seen *referenced* from release pages, not saved standalone in these collections) |
| **Search results** | `/search?q=…`, `/search/performance?tag=…`, `/search/artist?country=XX` | query result lists | none (no microdata) |
| **Statistics** | `/statistics/stats_work_covered?year=YYYY` | yearly "most covered" ranking | referenced only by the rank badge on work pages |

The **`/all` suffix** on work/performance/artist URLs means the *complete* listing variant of the same entity (no pagination truncation). In the transformed generation, `/performance/<id>/all` saves appear as `CYT-ATRA-…` files ("**A**ll **T**racks **R**elease **A**rtist" working name) titled "Cover versions of … by …".

---

## 3. Identifying the generation of a saved file (provenance signals)

The very first bytes of the file tell you which pipeline produced it:

| Signal | G1 raw browser save | G2 CYT original | G3 CYT transformed/derived |
|--------|--------------------|-----------------|---------------------------|
| DOCTYPE comment | `<!-- saved from url=(0047)https://secondhandsongs.com/performance/683/all -->` | absent | absent (or rewritten) |
| Source URL meta | `<meta name="source-webpage-url" content="secondhandsongs.com/artist/394">` | absent | absent or rewritten to local filename |
| `<title>` suffix | `… | SecondHandSongs` | `… | SecondHandSongs` | `… | CoverCanvas` |
| Custom provenance metas | none | none | `<meta name="cyt:metadata-version" content="html-derived-v4">`, `cyt:file`, `cyt:author` |
| Tag style | `<meta name="description" content="…">` | same | XHTML-ish: `<meta content="…" name="description"/>` |
| Asset links | `_files/` companion dir (`tiny`, `tiny(1)`, numeric cache dirs) | relative `/art/…` (often dangling) | rewritten to `CYTaccessFiles/…` |
| Internal links | absolute `https://secondhandsongs.com/…` | absolute or root-relative `/work/…` | **rewritten to local files** (`CYT-artist-Toto%20%5BUS%5D-2072.html`) |
| Filename style | `<Name> _ SecondHandSongs.html`, `.htm` | `NN_slug.html`, `NN_slug__perf<id>.html`, `CYT-<type>-…-<id>.html` | same as G2 |

### 3.1 Filename conventions (a hint, never ground truth)

- `CYT-work-…-<id>.html`, `CYT-performance-…-<id>.html`, `CYT-artist-…-<id>.html`, `CYT-release-…-<id>.html`, `CYT-ATRA-…-<id>.html` — explicit type + trailing SHS numeric ID.
- `NN_<title>.html` — work page; `NN_<title>__perf<id>.html` — performance page; `NN_<artist>.html` — *intended* artist page.
- `Artist_ <Name> _ SecondHandSongs*.html` — artist page (watch for dupes/typos: `SecondHandSongs5`, `SecondHandSongws`).
- `SHS_AUTO_<Title>_<Artist>.html`, `SHS_FUZZY_*`, `SHS_JOINED_*` — automated/fuzzy/merged saves; classify by content.
- **Cautionary example:** `01_the_bridgettes.html` in the CYT2 collections is actually a **search-results page** ("Search Results for 'the bridgettes'"), not an artist page — the intended entity did not exist. Always classify from content, not filename.

### 3.2 Known contamination (G1 collections)

`E:\MDBsources\SHS` and `E:\MusicDBsourcematerial\…\SHS-HTML` contain non-SHS strays: WhoSampled `.mhtml` files, Windows `.lnk` shortcuts, `SHS_JOINED_*` merged multi-page documents, `Definitions` pages, and non-`.html` extensions. Filter before parsing.

---

## 4. Categorizing a page — the signal hierarchy

Apply these checks in order; the first that fires decides the type. All signals were verified against real pages in the collections.

### Step 0 — load and normalize
- Read as UTF-8, errors=`ignore` (some G1 files have broken encodings).
- Work on the first ~200 KB for head signals; entity markup lives in the first ~500 KB of these ~0.1–0.5 MB files.

### Step 1 — provenance (§3)
Extract `saved from url=…`, `source-webpage-url`, `cyt:*` metas. These give you the **original SHS URL even when internal links were rewritten** — the single most reliable page-type key:

| Original URL contains | Type |
|----------------------|------|
| `/work/<n>` | work |
| `/performance/<n>` | performance |
| `/artist/<n>` | artist |
| `/release/<n>` | release |
| `/label/<n>` | label |
| `/search…` | search results |
| `/statistics…` | statistics |

### Step 2 — canonical / og:url / title pattern (works in every generation)

| Type | `<title>` pattern | Other head signals |
|------|-------------------|--------------------|
| Work | `Song: <Title> written by <Writers> \| …` or `Cover versions of <Title> written by … \| …` | badge `<a class="badge bg-primary" href="/statistics/stats_work_covered?year=YYYY">N<ordinal> in YYYY</a>` inside H1 |
| Performance | `Performance: <Title> by <Artist> \| …` or `Cover versions of <Title> by <Artist> \| …` | `og:type = music.song` (only page type that has it) |
| Artist | `<ArtistName> \| …` | H1 is plain `<h1 itemprop="name">Name</h1>` with no link |
| Release | `Release: <Title> - <Artist> (<Month D, YYYY>) \| …` | H1 links `/release/<id>` |
| Search | `Search Results for '<query>' \| …` | no itemprops at all |

### Step 3 — main-block microdata (decisive when titles were mangled)

| Type | `itemtype` of the main `itemscope` block (directly under `#content`) |
|------|--------------------------------------------------|
| Work | `MusicComposition` |
| Performance | `MusicRecording` (plus an inner `MusicAlbum` for the "Released on" infobox entry) |
| Artist | `Person` (solo) or `MusicGroup` (band) |
| Release | `MusicRelease` (plus `Organization` for the label) |
| Search | none |

### Step 4 — infobox `<dt>` labels and section titles (confirmation + field inventory)

- **Work dl:** `Written by`, `Language`, `ISWC`, `Published by`.
- **Performance dl:** `Written by`, `Language`, `Released on`, `Chart placings`, `Tags`, `Comments`, (`Other version`).
- **Artist dl:** `Personal name`, `Born`, `Country`, `IPI`, `Affiliation`, `Aliases`, `Members`, `Related`, `Ranking`, `Comments`.
- **Release dl:** `Release date`, `Label`, `EAN`, `Format`.
- **Work sections:** `Originals`, `Adaptations`, `Partial adaptations`, `Versions`, `Web covers`, `Forum topics`.
- **Performance sections:** `Originals`, `Adaptations`, `Partial adaptations`, `Versions`, `Sampled by`, `Web covers`.
- **Artist sections:** `Originals`, `Covers by <Name>`, `Songs written by <Name>` (with `Original songs` subsection), `Releases` (`Albums` / `Singles` / `Performances also appear on`), `Tributes`, `Web Covers by <Name>`.
- **Release sections:** `Tracks` (single table).
- **Search sections:** `Contributions` (and result groups per entity type).

---

## 5. Extraction logic per page type

### 5.1 Work (`/work/<id>`)

1. **Identity:** entity ID from `/work/<id>`; title from `span[itemprop=name] a`; ranking badge text (`2nd in 1983`) and its `year` parameter.
2. **Infobox dl** (`#entity-info dl`): `Written by` → list of `span[itemprop=author] a[href^=/artist/]` (each with artist ID + name); `Language` → `dd[itemprop=inLanguage]`; `ISWC` → one or more codes, each with `<small><em>` society annotations (e.g. `BMI, BUMA, GEMA, ISWC, JASRAC, PRS, SACM`); `Published by` → publisher names + society annotations.
3. **Originals section:** `article[itemprop=recordingOf]` → `section[itemprop=recordedAs]` per original performance: link text is the role (`First release`, `Original`, …) to `/performance/<id>`, `span[itemprop=byArtist]` artist, year in parentheses, optional YouTube link (`a.streaming-service-link`).
4. **Versions section:** one panel per related work (`p.versions-table-header` with its own `/work/<id>` + writers + language badge), each containing one or two tables (div ids ending `.vocals` / instrumental) with columns: player, instrumental flag, title (`/performance/<id>` link), performer (`/artist/<id>` link), release date, info.
5. **Adaptations / Partial adaptations:** list items describing derivative works (melody/arrangement usage notes, e.g. `<small>— uses melody and arrangement</small>`).
6. **Web covers:** `div.web-cover-grid > div.web-cover` cards (col-sm-3/4), usually YouTube-linked fan covers.
7. **Forum topics:** plain links to SHS forum threads.
8. Head meta `description` is a pre-written summary ("The song X was written by Y and was first released by Z in YYYY. It was covered by …") — useful as a fallback/validation source.

### 5.2 Performance (`/performance/<id>`)

1. **Identity:** `/performance/<id>`; H1 = title link + `<em>by</em>` + artist link (`/artist/<id>`); `og:type=music.song`.
2. **Infobox dl:** `Written by` (authors, same as work); `Language`; `Released on` → `div[itemprop=inAlbum]`: release name linking `/release/<id>`, medium (`Album`/`Single`/…), year; `Chart placings` → free text like `#1 in United States`; `Tags` → `span.badge.tag a[href^="/search/performance?tag="]`; `Comments`; `Other version`.
3. **Streaming:** `div.streaming-service-links a` (YouTube, Apple Music, Spotify, …) with `aria-label="Listen on …"`.
4. **Sections** same pattern as work, plus `Sampled by` (sampling performances) and versions tables of the *work* it realizes (nested `MusicComposition` panel).
5. Note: the performance page duplicates the work's Versions data — when merging, key versions by performance ID to deduplicate.

### 5.3 Artist (`/artist/<id>`)

1. **Identity:** H1 `itemprop=name` (plain text, no link — a strong differentiator); itemtype `Person` vs `MusicGroup`.
2. **Infobox dl:** `Personal name` (real name), `Born` (`dd[itemprop=birthDate]`), `Country` (`dd[itemprop=nationality] a[href^="/search/artist?country="]` → ISO code), `IPI` (one or more IPI numbers each with `<em>N works</em>` count), `Affiliation` (performing-rights org, e.g. ASCAP), `Aliases` (`div#root.aliases` lines), `Members` (for groups), `Related` (linked artists), `Ranking` (coverage ranking), `Comments` (biography free text).
3. **Sections:** `Originals` (works they originated), `Covers by <Name>` (cover performances), `Songs written by <Name>` → `Original songs` (works authored), `Releases` → `Albums` / `Singles` / `Performances also appear on` (release links with year), `Tributes` (tribute releases/albums), `Web Covers by <Name>`.
4. G3 saves rewrite in-page links to local `CYT-artist-…`/`CYT-release-…` filenames — recover the numeric ID from the filename tail (`-2072.html`) or fall back to the original URL meta.

### 5.4 Release (`/release/<id>`)

1. **Identity:** H1 = `/release/<id>` link + `<em>by</em>` + artist link; itemtype `MusicRelease`.
2. **Infobox dl:** `Release date` (`dd[itemprop=datePublished]`); `Label` → `span[itemprop=label] a[href^=/label/]` (label ID + name); `EAN` (barcode, spaces inside); `Format` → visible text + `meta[itemprop=musicReleaseFormat]` content (e.g. `CDFormat`).
3. **Tracks table** (`#root.tracks table`): rows `tr[itemprop=recordedAs]`; columns: player, instrumental flag, title (`/performance/<id>`), performer (`/artist/<id>`), `Written by` (artist links), `Info`.

### 5.5 Search-results pages

- Title `Search Results for '<q>'`; sections group hits by entity kind (artists, works, performances, releases, plus `Contributions` for editors).
- No microdata — parse result links and their `/type/id` hrefs. Treat as discovery glue, not entities.

---

## 6. Cross-page graph semantics (why these links matter)

- Work → Performance: `Originals` (`First release`) and Versions tables.
- Performance → Work: `Written by`/work panel header (`recordingOf`); → Release: `Released on`; → Artist: H1/byArtist.
- Release → Performance/Artist: Tracks table rows; → Label: infobox.
- Artist → everything: Originals, Covers, Releases, Tributes sections.
- Search/tag/country pages → filtered lists of the above (`?tag=`, `?country=XX`).

Build nodes keyed by `(entity_type, shs_id)` extracted from **original URLs** (`source-webpage-url`, `saved from url=`, canonical, or `/type/id` hrefs), not from filenames. Edges come from the links listed above. In G3 files where internal links are rewritten to local filenames, parse the trailing `-<id>.html` of the target filename to recover the ID.

---

## 7. Pitfalls and processing recommendations

1. **Never trust filenames for typing** — verify with §4 signals (the `01_the_bridgettes.html` search-page trap).
2. **Dedup by entity ID across all seven directories** — the same `/performance/656` exists in up to 4+ copies (G1 raw, G2 original, G3 transformed). Prefer G2 (cleanest original markup) or G1 (has `source-webpage-url`), keep G3 for its `cyt:` provenance metas.
3. **Watch renamed-site artifacts** — G3 titles say CoverCanvas; the RSS link and copy still say Second Hand Songs. Don't key anything on the brand string.
4. **Multi-valued infobox entries** — ISWC and IPI fields contain several codes, each annotated with societies/work-counts; split on `<br/>` and keep the annotations.
5. **Free-text fields** — `Chart placings` (`#1 in United States`), `Ranking`, `Comments` need regex/loose parsing; dates appear as `May 9, 2006`, `June 26, 1956`, or bare years `(1983)`.
6. **Encoding & tag-style variance** — G1 files may be non-UTF-8 and use `name-then-content` attribute order; G3 uses self-closing tags. Parse with a real HTML parser (BeautifulSoup/lxml), not regex, for production.
7. **Relative vs rewritten links** — G2 root-relative `/work/656`; G3 local `CYT-*.html` (URL-encoded); G1 absolute URLs. One link-normalization function handles all three.
8. **Contamination filtering** — drop non-`.html`, `.mhtml`, `.lnk`, and non-SHS domains before classification (§3.2).
9. **Truncation** — non-`/all` saves may be paginated; the `/all` (ATRA) variants are the complete listings. When both exist, keep `/all`.
10. **Provenance retention** — store, per record: source directory, filename, generation (G1/G2/G3), original URL, and parse timestamp; it makes audits (like `SHS-audit`) reproducible.

---

## 8. Minimal classification pseudocode

```python
def classify(html: str) -> str:
    head = html[:200_000]
    # 1. original URL from any generation's provenance marker
    url = (match(r'saved from url=\(\d+\)(\S+)', head)
           or xpath('//meta[@name="source-webpage-url"]/@content')
           or xpath('//link[@rel="canonical"]/@href')
           or xpath('//meta[@property="og:url"]/@content'))
    if url:
        m = search(r'secondhandsongs\.com/(work|performance|artist|release|label|search|statistics)/?', url)
        if m: return m.group(1)
    # 2. microdata main block
    t = xpath('//*[@id="content"]/ancestor::div[@itemscope]/@itemtype')  # first itemscope before #content
    return {'MusicComposition': 'work', 'MusicRecording': 'performance',
            'MusicRelease': 'release', 'Person': 'artist', 'MusicGroup': 'artist'}[t]
    # 3. fallback: title regexes from §4 Step 2, then dt-label signature from §4 Step 4
```

---

## 9. Companion file

`SHS_metadata_inventory.csv` (same directory) lists every metadata field extractable from SHS pages, where it lives in the markup, and a per-page-type inclusion matrix.
