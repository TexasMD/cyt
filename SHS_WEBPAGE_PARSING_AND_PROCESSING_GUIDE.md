# Comprehensive Guide to Parsing, Categorizing, and Processing SecondHandSongs (SHS) Webpages

---

## 1. Executive Architecture & Overview

SecondHandSongs (SHS) is an authoritative database indexing musical relationships: compositions, historical performances, studio recordings, cover versions, samples, adaptations, and artist discographies.

Offline-saved SHS HTML pages represent a heterogeneous corpus of captures collected across different site versions, responsive templates, and download modalities (single-page saves, complete webpage dumps with asset bundles, wget mirrors, and headless browser captures). 

Processing this corpus requires a deterministic multi-stage pipeline:
1. **Intake & Fingerprinting:** Identify document boundaries, encoding, and source provenance.
2. **Page Categorization & Entity Classification:** Route each page to its domain entity class (`work`, `performance`, `artist`, `release`, `web_cover`, or administrative/search).
3. **Lossless Structural Extraction:** Extract schema microdata, definition lists (`<dl>`), content badges, data tables (`<table>`), external resource hyperlinks, and provider identifiers (ISWC, IPI, Spotify IDs, YouTube IDs, MusicBrainz UUIDs).
4. **Music Metadata Normalization & Business Rules:** Apply canonical rules for release dates, composition disambiguation, title collision resolution, and collaborative performance categorization (`1strel`, `cover`, `aarw`).
5. **Relational Assembly & Quality Auditing:** Populate relational schemas, detect truncated paginations, isolate non-Latin or translation works, and write audit queues for unresolved anomalies.

```
+----------------------------------------------------------------------------------------------------+
|                                    Saved SHS HTML Document Corpus                                  |
+----------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
                     +----------------------------------------------------------+
                     | STAGE 1: Intake, Sanitization & Provenance Fingerprinting |
                     | - Detect Encoding (UTF-8 / ISO-8859-1)                   |
                     | - Extract Canonical URL, og:url, Source-URL Comments     |
                     | - Determine Hydration Level (/all view vs paginated)     |
                     +----------------------------------------------------------+
                                                  |
                                                  v
                     +----------------------------------------------------------+
                     | STAGE 2: Multi-Signal Entity Categorization & Routing    |
                     | [Work]        [Performance]    [Artist]    [Release]     |
                     +----------------------------------------------------------+
                                                  |
                                                  v
                     +----------------------------------------------------------+
                     | STAGE 3: Semantic & Tabular Metadata Extraction          |
                     | - Definition Lists (<dl>, <dt>, <dd>)                    |
                     | - Microdata & JSON-LD (Schema.org)                       |
                     | - Tables (Responsive Rows, Badges, Dates, Links)         |
                     | - External Identifiers (ISWC, IPI, Spotify, YouTube, MB) |
                     +----------------------------------------------------------+
                                                  |
                                                  v
                     +----------------------------------------------------------+
                     | STAGE 4: Music Data Integrity & Classification Engine    |
                     | - Canonical Earliest Original Harmonization              |
                     | - Disambiguation of Colliding Titles & Short Titles      |
                     | - Subsequent Collaboration Classification (AARW)         |
                     | - Year & Floating-Point Sanitization (1985.0 -> 1985)    |
                     +----------------------------------------------------------+
                                                  |
                                                  v
                     +----------------------------------------------------------+
                     | STAGE 5: Structured Relational Output & Audit Queues     |
                     | - Relational SQLite & Parquet/CSV Export                 |
                     | - Adaptations / Non-Latin Exclusions Audit               |
                     | - Truncation & Unresolved Status Queues                  |
                     +----------------------------------------------------------+
```

---

## 2. Multi-Signal Page Categorization Logic

Because saved HTML filenames may be arbitrary or sanitized differently depending on the scraper or browser that captured them, entity classification relies on a **cascading priority hierarchy** of signals.

```
                       +---------------------------------------+
                       |       Inspect HTML Document Head      |
                       +---------------------------------------+
                                           |
                   +-----------------------+-----------------------+
                   |                                               |
                   v                                               v
    [link rel="canonical" href]                     [meta property="og:url"]
                   |                                               |
                   +-----------------------+-----------------------+
                                           |
                                           v
                       +---------------------------------------+
                       |  Match Regex: ^/(entity_type)/(\d+)   |
                       +---------------------------------------+
                                           |
        +------------------+---------------+------------------+------------------+
        |                  |                                  |                  |
        v                  v                                  v                  v
     /work/          /performance/                         /artist/          /release/
   [WORK PAGE]    [PERFORMANCE PAGE]                    [ARTIST PAGE]     [RELEASE PAGE]
        |                  |                                  |                  |
        +------------------+---------------+------------------+------------------+
                                           |
                               (If Head Signals Absent)
                                           v
                       +---------------------------------------+
                       |    Fallback to Document Body Signals  |
                       | - data-controller="/work/..."         |
                       | - breadcrumbs & h1.title microdata    |
                       | - filename pattern (CYT-work-*)       |
                       +---------------------------------------+
```

### 2.1 The Priority Signal Hierarchy

1. **Canonical Header URL (`link[rel="canonical"]`):**  
   The primary ground truth. SecondHandSongs outputs `<link rel="canonical" href="https://secondhandsongs.com/{type}/{id}...">`.
   - Pattern: `^https?://secondhandsongs\.com/(work|performance|artist|release|medium|web-cover)/(\d+)`
2. **OpenGraph & Twitter Meta Tags (`meta[property="og:url"]`):**  
   SecondHandSongs mirrors the canonical entity in `<meta property="og:url" content="...">`.
3. **Wrapper Controller Data Attribute (`div#root_wrapper[data-controller]` or `body[data-route]`):**  
   Modern SHS SPA/SSR templates tag root containers:
   - `data-controller="/work/1051/all"`
   - `data-route="work_show"`, `data-route="performer_show"`, `data-route="release_show"`
4. **Filename Pattern Parsing (Archival Fallback):**  
   When headers are stripped by archiving tools:
   - `CYT-work-{title}-{writers}-{id}.html` $\rightarrow$ `work`
   - `CYT-performance-{title}-{artist}-{year}-{id}.html` $\rightarrow$ `performance`
   - `CYT-ATRA-{title}-{artist}-{year}.html` $\rightarrow$ `performance` (ATRA track context)
   - `CYT-artist-{name}-{id}.html` $\rightarrow$ `artist`
   - `CYT-release-{title}-{artist}-{year}-{id}.html` $\rightarrow$ `release`
   - `Web Cover_ {title} by {artist} _ SecondHandSongs.html` $\rightarrow$ `web_cover`
5. **DOM Semantic Breadcrumbs & Schema Types:**  
   - Work: `ol.breadcrumb li a[href^="/work/"]`, Schema `MusicComposition`
   - Performance: `ol.breadcrumb li a[href^="/performance/"]`, Schema `MusicRecording`
   - Artist: Schema `MusicGroup` or `Person`
   - Release: Schema `MusicAlbum` or `MusicRelease`

---

## 3. Defining Traits & Differential Matrix of SHS Page Types

| Feature / Trait | Work Page (`/work/`) | Performance Page (`/performance/`) | Artist Page (`/artist/`) | Release Page (`/release/`) | Web Cover (`/web-cover/`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Core Entity Model** | Abstract musical composition / copyright work | Specific historical sound recording / rendition | Human person, band, or ensemble | Physical or digital commercial product package | User-uploaded video rendition (YouTube) |
| **Title Format in `<h1>`** | Title of song / work | Title of performance *by* Artist | Artist / Performer name | Album title *by* Artist | Performance title *by* Artist |
| **Primary Breadcrumb** | Home $\rightarrow$ Work | Home $\rightarrow$ Work $\rightarrow$ Performance | Home $\rightarrow$ Artist | Home $\rightarrow$ Artist $\rightarrow$ Release | Home $\rightarrow$ Work $\rightarrow$ Web Covers |
| **Definition List (`<dl>`) Traits** | `Written by`, `ISWC`, `Language`, `Published by`, `Composition date` | `Released on`, `First recorded in`, `Chart placings`, `Rating` | `Born`, `Died`, `Country`, `IPI`, `Affiliation`, `Member of` | `Release date`, `Format`, `Label`, `Catalog number`, `EAN/UPC` | `Uploaded on`, `Platform`, `Channel name` |
| **Primary Tabular Data** | Table of all cover versions, adaptations, and samples | Single recording focus; lists releases containing track | Tables of: Originals, Covers, Written Works, Discography | Sequenced tracklist table with durations and track numbers | Minimal tabular data; embedded media player |
| **Unique Identifiers** | ISWC (`T-xxx.xxx.xxx-x`) | Spotify Track ID, YouTube Video ID | IPI / CAE number (`\d{9,11}`) | Catalog Number, EAN/UPC barcode | YouTube Video alphanumeric ID |
| **Navigation Tabs** | `Versions`, `Samples`, `Adaptations`, `Translations`, `Discussion` | `Details`, `Releases`, `Lyrics`, `Discussion` | `Performances`, `Works`, `Releases`, `Statistics` | `Tracklist`, `Credits`, `Releases` | `Video`, `Original Work`, `Performer` |
| **Original Marker Signal** | Designates the canonical `[1st]` recording row | Denotes whether this specific page is the original release | Labels songs as `Originals by` vs `Covered by` | Indicates original album vs tribute / reissue | Links to canonical work's original release |

---

## 4. Extraction Mechanics by HTML Block

### 4.1 Header Metadata & Definition Lists (`<dl>`, `<dt>`, `<dd>`)
The entity overview panel (`div#entity-info`, `div.entity-data`) groups primary facts in `<dl>` tags:

```python
def extract_definition_list(soup: BeautifulSoup) -> dict[str, str]:
    details = {}
    for dl in soup.find_all("dl"):
        for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
            label = dt.get_text(strip=True).replace(":", "").lower()
            # Normalize whitespace and preserve inter-item separators
            val = dd.get_text(separator=" | ", strip=True)
            details[label] = val
    return details
```

Key normalizations for `<dt>` fields:
- `written by`: Parse individual author anchor tags (`dd.find_all('a', href=re.compile(r'^/artist/'))`) to extract both author names and author numeric IDs.
- `iswc`: Clean string using regex `r'T-?\d{3}\.?\d{3}\.?\d{3}-?\d'`.
- `released on`: Extract both release title and release ID from the hyperlink `/release/(\d+)`.
- `ipi`: Extract 9 to 11 digit standard identifier along with the number of registered works.

### 4.2 Tabular Version Parsing (`table.data`)
On `/work/{id}/all` pages, the table of performances is the core data asset:
- `td:nth-child(1)`: Original marker. If it contains `span.badge-original` or `[1st]`, flag recording as `is_first_release = True`.
- `td:nth-child(3)`: Performance title and `/performance/{id}` link.
- `td:nth-child(4)`: Performing artist name and `/artist/{id}` link.
- `td:nth-child(5)`: Release date string (`YYYY`, `Month YYYY`, or `Month DD, YYYY`).
- `td:nth-child(6)`: Badges and metadata flags (`Instrumental`, `Live`, `Medley`, `Uncredited`, `Hit song`).

```python
def parse_versions_table(table: Tag) -> list[dict]:
    performances = []
    for tr in table.find_all("tr", class_=re.compile(r"refresh-click-select-row|object")):
        title_td = tr.find("td", class_=re.compile(r"field-title"))
        perf_td = tr.find("td", class_=re.compile(r"field-performer"))
        date_td = tr.find("td", class_=re.compile(r"field-creationDate"))
        badge_td = tr.find("td", class_=re.compile(r"field-info|field-badges"))
        
        if not title_td or not perf_td:
            continue
            
        is_first = bool(tr.find("span", class_=re.compile(r"badge-original|first-release"))) or "[1st]" in tr.text
        perf_a = title_td.find("a", href=re.compile(r"^/performance/\d+"))
        artist_a = perf_td.find("a", href=re.compile(r"^/artist/\d+"))
        
        if not perf_a or not artist_a:
            continue
            
        performances.append({
            "performance_id": perf_a["href"].split("/")[-1],
            "performance_title": perf_a.get_text(strip=True),
            "performing_artist_id": artist_a["href"].split("/")[-1],
            "performing_artist": artist_a.get_text(strip=True),
            "release_date": date_td.get_text(strip=True) if date_td else "",
            "is_first_release": is_first,
            "badges": badge_td.get_text(separator="; ", strip=True) if badge_td else ""
        })
    return performances
```

### 4.3 External Identifier Harvesting
Saved pages embed outbound references to external music registries in player widgets, track links, and attribution anchors:
- **YouTube:** Extract from `iframe[src*="youtube.com/embed/"]`, `a[href*="watch?v="]`, or `a[href*="youtu.be/"]`. Matches 11-character video ID `r"([A-Za-z0-9_-]{11})"`.
- **Spotify:** Extract from `a[href*="open.spotify.com/track/"]`, `/artist/`, or `/album/`. Matches 22-character base62 ID `r"open\.spotify\.com/(track|artist|album)/([A-Za-z0-9]{22})"`.
- **MusicBrainz:** Extract UUIDs from external authority links matching `r"musicbrainz\.org/(artist|work|recording|release)/([0-9a-f-]{36})"`.
- **WhoSampled:** Extract matching slugs or IDs from `a[href*="whosampled.com"]`.

---

## 5. Music Metadata Integrity & Permanent Verification Rules

When parsing and loading SecondHandSongs data into active music databases, the following operational integrity rules must be strictly enforced:

### 5.1 Strict Disambiguation for Short & Numeric Titles ($\le 4$ Characters)
- Titles such as "19", "22", "24", "40", "53", "212", "679", "1234", "A1", "No", "Try" **must never** be joined using loose substring matching or fuzzy ratio algorithms.
- **Rule:** Require normalized string exact equality (`norm(title) == norm(candidate)`) **plus** artist cross-verification against verified MusicBrainz recordings or SecondHandSongs Performance IDs.

### 5.2 Word Boundary Anchoring & Substring Matching Protection
- Single-word titles must never be matched to compound titles unless explicitly joined via verified catalog identifiers (ISRC, MusicBrainz MBID, or SHS Performance ID).
- **Rule:** Explicitly reject containment matches (e.g. matching "Broken" to "Everything Is Broken" or "Fly" to "Fly, Robin, Fly").

### 5.3 Title Collision & Composition Disambiguation (`(performing_artist, song_title)`)
- Identical song titles frequently represent completely distinct musical compositions (e.g. Ellie Goulding's "On My Mind" vs Hoagy Carmichael's standard; U2's "Bad" vs Michael Jackson; ODESZA's "Behind The Sun" vs Red Hot Chili Peppers; The Alarm's "Blaze of Glory" vs Jon Bon Jovi; Citizen King's "Better Days" vs Bruce Springsteen).
- **Rule:** Never attribute a recording to a work or original performer using title alone. Cross-reference `(song_title, performing_artist)` alongside release year, author/composer credits, and album metadata to resolve the exact composition.

### 5.4 Subsequent Collaborations & Original Group Member Classification (`AARW`)
- Subsequent performances or re-recordings of a work by the original artist or an original group member with other artists (e.g. duets, features, collaborative remixes, tribute ensembles, or solo performances by group members like Mike Peters performing The Alarm, or Jimmy Page with Chapter Eleven) **must be classified as `AARW`** (Artist Autocover / Re-recording With), **not `Cover` and not `Original`**.

### 5.5 Canonical Original Harmony Across Work Covers
- All verified covers of the same underlying composition must be harmonized to share the exact same canonical original performer and earliest release year across the entire catalog (e.g. all covers of "Black Betty" attribute the canonical original release to James "Iron Head" Baker / Traditional 1933; all covers of "Billie Jean" attribute Michael Jackson 1982).
- **Rule:** Disallow fragmented or localized attributions to intermediate cover artists.

### 5.6 Data Sanitization & Excel Formatting Protection
- Strip trailing `.0` decimal formatting from calendar year fields (`1985.0` $\rightarrow$ `1985`).
- Guard against spreadsheet serial conversions of times/dates into decimals (e.g. `0.465972222` $\rightarrow$ `11:11`).
- Disallow circular cover definitions where `original_artist == performing_artist` on a cover track without explicit re-recording / self-cover verification.

---

## 6. End-to-End Processing & Storage Architecture

### 6.1 Database Target Schema
Extracted data should be loaded into a relational engine (SQLite / DuckDB / PostgreSQL) with the following structure:

```sql
-- 1. Master entities (Work, Performance, Artist, Release)
CREATE TABLE shs_entities (
    entity_key TEXT PRIMARY KEY,          -- e.g. 'work/1051', 'artist/665'
    entity_type TEXT NOT NULL,           -- 'work', 'performance', 'artist', 'release'
    shs_id INTEGER NOT NULL,
    canonical_name TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    iswc TEXT,
    ipi TEXT,
    country TEXT,
    release_date TEXT,
    release_year INTEGER
);

-- 2. Performance relationships (Work <-> Performance <-> Performer)
CREATE TABLE shs_performances (
    performance_id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL REFERENCES shs_entities(shs_id),
    performance_title TEXT NOT NULL,
    performer_id INTEGER NOT NULL REFERENCES shs_entities(shs_id),
    performer_name TEXT NOT NULL,
    release_date TEXT,
    release_year INTEGER,
    classification TEXT NOT NULL,        -- '1strel', 'cover', 'aarw', 'instrumental'
    is_first_release BOOLEAN NOT NULL,
    is_instrumental BOOLEAN NOT NULL,
    is_live BOOLEAN NOT NULL,
    is_medley BOOLEAN NOT NULL,
    spotify_track_id TEXT,
    youtube_video_id TEXT
);

-- 3. Authorship & Composition Credits
CREATE TABLE shs_credits (
    credit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id INTEGER NOT NULL,
    artist_id INTEGER NOT NULL,
    credit_role TEXT NOT NULL,           -- 'author', 'composer', 'lyricist', 'writer'
    credited_name TEXT NOT NULL
);

-- 4. External Provider Mapping
CREATE TABLE shs_provider_identifiers (
    entity_key TEXT NOT NULL,
    provider_name TEXT NOT NULL,         -- 'spotify', 'youtube', 'musicbrainz', 'iswc'
    identifier_value TEXT NOT NULL,
    PRIMARY KEY (entity_key, provider_name, identifier_value)
);
```

### 6.2 Data Exclusion & Audit Queues
To maintain pristine catalog integrity, the parsing pipeline automatically branches anomalous or non-canonical rows into separate audit lists:
1. **Work-Level Adaptations (`excluded_adaptations.csv`):** Translated or non-original foreign lyric adaptations are held in an audit queue until mapped to parent compositions.
2. **Non-Latin Script Catalog Entries (`excluded_non_latin.csv`):** Non-Latin titles (Cyrillic, Kanji, Arabic) lacking transliterated English equivalents are isolated for manual review.
3. **Duplicate Captures & Overwrites (`duplicate_captures.csv`):** When multiple HTML captures of the same entity exist across archival dates, compare `metadata_density` (total parsed cells and links) and retain the richest capture.

---

## 7. Artifact Summary

The accompanying metadata dictionary has been generated and saved:
- **Guide:** [`SHS_WEBPAGE_PARSING_AND_PROCESSING_GUIDE.md`](file:///C:/Users/sethm/Documents/antigravity/nifty-meitner/SHS_WEBPAGE_PARSING_AND_PROCESSING_GUIDE.md)
- **Metadata Dictionary CSV:** [`shs_page_metadata_dictionary.csv`](file:///C:/Users/sethm/Documents/antigravity/nifty-meitner/shs_page_metadata_dictionary.csv)

The CSV contains **85 comprehensively documented metadata fields**, classifying each field by:
- `Field_Name`
- `Category`
- `Description`
- Presence across page types: `Work_Page`, `Performance_Page`, `Artist_Page`, `Release_Page`, `Web_Cover_Page`
- `Identifying_Signals_and_Selectors` (DOM selectors, attributes, regex patterns)
- `Example_Value`
