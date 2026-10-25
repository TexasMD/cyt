"""Extract a lossless, queryable metadata archive from saved SHS HTML files.

Preserves E:\\CYT\\sources\\original\\SHS as strictly read-only.
Extracts all metadata, excludes work-level adaptations and non-Latin entries into dedicated audit lists,
populates all 19 core SQLite tables + 2 exclusion audit tables, and exports complementary CSV, JSON,
and validation reports.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

try:
    from scripts.shs_dates import parse_shs_date
except ModuleNotFoundError:
    try:
        from shs_dates import parse_shs_date
    except ModuleNotFoundError:
        parent_dir = str(Path(__file__).resolve().parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        from shs_dates import parse_shs_date


PARSER_NAME = "shs_saved_html_metadata"
PARSER_VERSION = "1.3.0"
EXPORT_VERSION = 3
SCHEMA_VERSION = 3

SHS_ENTITY_RE = re.compile(
    r"^/(artist|work|performance|release)/(\d+(?:\+\d+)*)(?:/|$)", re.I
)
WEB_COVER_RE = re.compile(
    r"^/web-cover/(\d+)(?:/|$)", re.I
)
CYT_ARTIST_RE = re.compile(r"^CYT-artist-(?P<name>.+?)-(?P<id>\d+)\.html$", re.I)
CYT_PERF_RE = re.compile(r"^CYT-performance-(?P<title>.+?)-(?P<artist>.+?)-(?P<year>\d{4})-(?P<id>\d+)\.html$", re.I)
CYT_WORK_RE = re.compile(r"^CYT-work-(?P<title>.+?)-(?P<writers>.+?)-(?P<id>\d+)\.html$", re.I)
CYT_ATRA_RE = re.compile(r"^CYT-ATRA-(?P<title>.+?)-(?P<artist>.+?)-(?P<year>\d{4})\.html$", re.I)
WEB_COVER_RE_FNAME = re.compile(r"^Web Cover_\s*(?P<title>.+?)\s+by\s+(?P<artist>.+?)\s*_\s*SecondHandSongs\.html$", re.I)

ORDINAL_RANKING_RE = re.compile(
    r"^(?P<title>.+?)\s+(?P<ordinal>\d+)(?:st|nd|rd|th)\s+in\s+(?P<year>\d{4})$",
    re.I,
)


def filename_metadata(path: Path) -> dict[str, Any]:
    fname = path.name
    meta: dict[str, Any] = {}
    if m := CYT_ARTIST_RE.match(fname):
        meta["entity_type"] = "artist"
        meta["entity_id"] = m.group("id")
        meta["entity_key"] = f"artist/{m.group('id')}"
        meta["name"] = m.group("name").replace("_", " ").strip()
    elif m := CYT_PERF_RE.match(fname):
        meta["entity_type"] = "performance"
        meta["entity_id"] = m.group("id")
        meta["entity_key"] = f"performance/{m.group('id')}"
        meta["title"] = m.group("title").replace("_", " ").strip()
        meta["artist"] = m.group("artist").replace("_", "/").strip()
        meta["year"] = int(m.group("year"))
    elif m := CYT_WORK_RE.match(fname):
        meta["entity_type"] = "work"
        meta["entity_id"] = m.group("id")
        meta["entity_key"] = f"work/{m.group('id')}"
        meta["title"] = m.group("title").replace("_", " ").strip()
        meta["writers"] = m.group("writers").strip()
    elif m := CYT_ATRA_RE.match(fname):
        meta["page_class"] = "atra"
        meta["page_subtype"] = "performance"
        meta["title"] = m.group("title").replace("_", " ").strip()
        meta["artist"] = m.group("artist").replace("_", "/").strip()
        meta["year"] = int(m.group("year"))
    elif m := WEB_COVER_RE_FNAME.match(fname):
        meta["page_class"] = "performance"
        meta["page_subtype"] = "web_cover"
        meta["title"] = m.group("title").strip()
        meta["artist"] = m.group("artist").strip()
    return meta
PROVIDER_PATTERNS = {
    "spotify_track_id": re.compile(r"open\.spotify\.com/track/([A-Za-z0-9]+)", re.I),
    "spotify_artist_id": re.compile(r"open\.spotify\.com/artist/([A-Za-z0-9]+)", re.I),
    "spotify_album_id": re.compile(r"open\.spotify\.com/album/([A-Za-z0-9]+)", re.I),
    "youtube_video_id": re.compile(r"(?:youtube\.com/watch\?(?:[^#\s\"']*&)?v=|youtu\.be/)([A-Za-z0-9_-]+)", re.I),
    "musicbrainz_artist_id": re.compile(r"musicbrainz\.org/artist/([0-9a-f-]{36})", re.I),
    "musicbrainz_recording_id": re.compile(r"musicbrainz\.org/recording/([0-9a-f-]{36})", re.I),
    "musicbrainz_work_id": re.compile(r"musicbrainz\.org/work/([0-9a-f-]{36})", re.I),
    "musicbrainz_release_id": re.compile(r"musicbrainz\.org/release/([0-9a-f-]{36})", re.I),
    "apple_music_id": re.compile(r"music\.apple\.com/[a-z]{2}/(?:album|song)/[^/\"'\s]+/([0-9]+)", re.I),
    "whosampled_id": re.compile(r"whosampled\.com/[^\"'\s]*/(\d+)/?", re.I),
    "iswc": re.compile(r"\b(T-?\d{3}\.?\d{3}\.?\d{3}-?\d)\b", re.I),
}
STRUCTURED_SCRIPT_TYPES = {"application/ld+json", "application/json"}
SEMANTIC_ATTRIBUTES = {
    "itemscope", "itemtype", "itemprop", "itemid", "itemref",
    "property", "typeof", "vocab", "resource", "about", "datatype",
}


SCHEMA_SQL = """
PRAGMA foreign_keys=ON;
CREATE TABLE schema_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE parse_runs(
  run_id TEXT PRIMARY KEY, parser_name TEXT NOT NULL, parser_version TEXT NOT NULL,
  schema_version INTEGER NOT NULL, source_root TEXT NOT NULL,
  source_snapshot_sha256 TEXT NOT NULL, html_file_count INTEGER NOT NULL,
  source_latest_mtime_utc TEXT NOT NULL
);
CREATE TABLE source_files(
  file_id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES parse_runs(run_id),
  relative_path TEXT NOT NULL UNIQUE, filename TEXT NOT NULL, byte_size INTEGER NOT NULL,
  modified_utc TEXT NOT NULL, sha256 TEXT NOT NULL, detected_encoding TEXT,
  parse_status TEXT NOT NULL, parse_error TEXT, page_class TEXT NOT NULL,
  page_subtype TEXT,
  document_title TEXT, canonical_url TEXT, shs_entity_type TEXT, shs_entity_id TEXT,
  entity_key TEXT, entity_name TEXT, ranking_text TEXT,
  ranking_ordinal INTEGER, ranking_year INTEGER
);
CREATE TABLE page_captures(
  capture_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  entity_key TEXT, captured_utc TEXT NOT NULL, metadata_density INTEGER NOT NULL,
  semantic_fingerprint TEXT NOT NULL
);
CREATE TABLE entities(
  entity_key TEXT PRIMARY KEY, entity_type TEXT NOT NULL, shs_entity_id TEXT NOT NULL,
  preferred_name TEXT, source_url TEXT, cyt_entity_id TEXT NOT NULL,
  preferred_ranking_text TEXT, preferred_ranking_ordinal INTEGER,
  preferred_ranking_year INTEGER,
  capture_count INTEGER NOT NULL DEFAULT 0, conflict_status TEXT NOT NULL DEFAULT 'none'
);
CREATE TABLE entity_names(
  name_id INTEGER PRIMARY KEY, entity_key TEXT NOT NULL REFERENCES entities(entity_key),
  name_type TEXT NOT NULL, name_value TEXT NOT NULL,
  source_file_id INTEGER REFERENCES source_files(file_id), locator TEXT
);
CREATE TABLE metadata_observations(
  metadata_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  source_kind TEXT NOT NULL, metadata_key TEXT NOT NULL, ordinal INTEGER NOT NULL,
  raw_value TEXT, display_value TEXT, normalized_value TEXT, parsed_json TEXT,
  attributes_json TEXT, locator TEXT NOT NULL, parse_status TEXT NOT NULL DEFAULT 'preserved'
);
CREATE TABLE microdata(
  microdata_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  ordinal INTEGER NOT NULL, tag_name TEXT NOT NULL, itemprop TEXT, itemtype TEXT,
  itemid TEXT, itemref TEXT, rdfa_property TEXT, rdfa_typeof TEXT,
  raw_value TEXT, display_value TEXT, attributes_json TEXT, locator TEXT NOT NULL
);
CREATE TABLE structured_data(
  structured_data_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  ordinal INTEGER NOT NULL, script_type TEXT NOT NULL, raw_text TEXT NOT NULL,
  parsed_json TEXT, parse_status TEXT NOT NULL, locator TEXT NOT NULL
);
CREATE TABLE detail_sections(
  section_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  section_name TEXT, heading TEXT, locator TEXT NOT NULL
);
CREATE TABLE detail_entries(
  detail_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  section_id INTEGER REFERENCES detail_sections(section_id),
  ordinal INTEGER NOT NULL, label_raw TEXT NOT NULL, label_normalized TEXT NOT NULL,
  value_raw TEXT, value_display TEXT, lines_json TEXT, locator TEXT NOT NULL
);
CREATE TABLE content_blocks(
  block_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  ordinal INTEGER NOT NULL, block_type TEXT NOT NULL, heading_context TEXT,
  raw_text TEXT, display_text TEXT, locator TEXT NOT NULL
);
CREATE TABLE tables(
  table_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  ordinal INTEGER NOT NULL, html_id TEXT, heading TEXT, locator TEXT NOT NULL
);
CREATE TABLE table_columns(
  column_id INTEGER PRIMARY KEY, table_id INTEGER NOT NULL REFERENCES tables(table_id),
  column_ordinal INTEGER NOT NULL, heading TEXT, data_type TEXT, locator TEXT NOT NULL
);
CREATE TABLE table_rows(
  row_id INTEGER PRIMARY KEY, table_id INTEGER NOT NULL REFERENCES tables(table_id),
  row_ordinal INTEGER NOT NULL, row_class TEXT, locator TEXT NOT NULL
);
CREATE TABLE table_cells(
  cell_id INTEGER PRIMARY KEY, table_id INTEGER NOT NULL REFERENCES tables(table_id),
  row_ordinal INTEGER NOT NULL, column_ordinal INTEGER NOT NULL, is_header INTEGER NOT NULL,
  column_heading TEXT, raw_text TEXT, display_text TEXT, row_span INTEGER, column_span INTEGER,
  date_status TEXT, date_sort_value TEXT, date_precision TEXT, locator TEXT NOT NULL
);
CREATE TABLE links(
  link_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  href_raw TEXT NOT NULL, href_absolute TEXT, link_text TEXT, title TEXT,
  rel TEXT, target TEXT, download TEXT, context_kind TEXT, context_label TEXT,
  first_locator TEXT NOT NULL, occurrence_count INTEGER NOT NULL,
  target_entity_key TEXT, target_relative_path TEXT, resolution_status TEXT NOT NULL
);
CREATE TABLE reference_resolutions(
  resolution_id INTEGER PRIMARY KEY, link_id INTEGER NOT NULL REFERENCES links(link_id),
  file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  resolution_class TEXT NOT NULL, target_entity_key TEXT, target_relative_path TEXT,
  details TEXT
);
CREATE TABLE resources(
  resource_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  ordinal INTEGER NOT NULL, tag_name TEXT NOT NULL, url_attribute TEXT,
  url_raw TEXT, alternate_text TEXT, title TEXT, type TEXT, rel TEXT,
  attributes_json TEXT NOT NULL, locator TEXT NOT NULL
);
CREATE TABLE provider_identifiers(
  provider_identifier_id INTEGER PRIMARY KEY,
  file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  entity_key TEXT, identifier_type TEXT NOT NULL, identifier_value TEXT NOT NULL,
  source_locator TEXT NOT NULL, UNIQUE(file_id, identifier_type, identifier_value)
);
CREATE TABLE credits(
  credit_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  entity_key TEXT, credit_role TEXT NOT NULL, credited_name TEXT NOT NULL,
  credited_entity_key TEXT, source_kind TEXT NOT NULL, locator TEXT NOT NULL
);
CREATE TABLE relationships(
  relationship_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  source_entity_key TEXT, relationship_type TEXT NOT NULL, target_entity_key TEXT,
  target_name TEXT, locator TEXT NOT NULL
);
CREATE TABLE review_issues(
  issue_id INTEGER PRIMARY KEY, file_id INTEGER REFERENCES source_files(file_id),
  issue_code TEXT NOT NULL, severity TEXT NOT NULL, detail TEXT NOT NULL,
  locator TEXT, review_status TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE review_decisions(
  decision_row_id INTEGER PRIMARY KEY, prior_issue_id TEXT, relative_path TEXT NOT NULL,
  entity_key TEXT, prior_issue_code TEXT, prior_severity TEXT, prior_detail TEXT,
  prior_locator TEXT, prior_review_status TEXT, decision_text TEXT,
  decision_action TEXT NOT NULL, application_status TEXT NOT NULL,
  application_detail TEXT NOT NULL
);
CREATE TABLE excluded_adaptations(
  exclusion_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  primary_work_key TEXT NOT NULL, adaptation_work_key TEXT, adaptation_title TEXT,
  heading_locator TEXT NOT NULL, first_release_info TEXT, detail TEXT NOT NULL
);
CREATE TABLE excluded_non_latin(
  exclusion_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  item_type TEXT NOT NULL, item_text TEXT NOT NULL, detected_script TEXT NOT NULL,
  locator TEXT NOT NULL, detail TEXT NOT NULL
);

CREATE INDEX source_files_entity_idx ON source_files(entity_key);
CREATE INDEX source_files_sha_idx ON source_files(sha256);
CREATE INDEX page_captures_entity_idx ON page_captures(entity_key);
CREATE INDEX entities_type_idx ON entities(entity_type);
CREATE INDEX entities_cyt_idx ON entities(cyt_entity_id);
CREATE INDEX metadata_observations_file_idx ON metadata_observations(file_id, source_kind, ordinal);
CREATE INDEX metadata_observations_lookup_idx ON metadata_observations(metadata_key, normalized_value);
CREATE INDEX microdata_file_idx ON microdata(file_id, ordinal);
CREATE INDEX microdata_itemprop_idx ON microdata(itemprop);
CREATE INDEX structured_data_file_idx ON structured_data(file_id, ordinal);
CREATE INDEX detail_file_idx ON detail_entries(file_id, ordinal);
CREATE INDEX detail_label_idx ON detail_entries(label_normalized);
CREATE INDEX content_blocks_file_idx ON content_blocks(file_id, ordinal);
CREATE INDEX tables_file_idx ON tables(file_id, ordinal);
CREATE INDEX table_columns_table_idx ON table_columns(table_id, column_ordinal);
CREATE INDEX table_rows_table_idx ON table_rows(table_id, row_ordinal);
CREATE INDEX table_cells_table_idx ON table_cells(table_id, row_ordinal, column_ordinal);
CREATE INDEX links_file_idx ON links(file_id, link_id);
CREATE INDEX links_target_idx ON links(target_entity_key, resolution_status);
CREATE INDEX links_href_idx ON links(href_raw);
CREATE INDEX reference_resolutions_class_idx ON reference_resolutions(resolution_class);
CREATE INDEX resources_file_idx ON resources(file_id, ordinal);
CREATE INDEX provider_identifiers_file_idx ON provider_identifiers(file_id, identifier_type);
CREATE INDEX provider_identifier_idx ON provider_identifiers(identifier_type, identifier_value);
CREATE INDEX credits_role_idx ON credits(credit_role);
CREATE INDEX relationships_type_idx ON relationships(relationship_type);
CREATE INDEX review_issues_file_idx ON review_issues(file_id, issue_id);
CREATE INDEX review_decisions_action_idx ON review_decisions(decision_action, application_status);
CREATE INDEX excluded_adaptations_primary_idx ON excluded_adaptations(primary_work_key);
CREATE INDEX excluded_non_latin_type_idx ON excluded_non_latin(item_type);

CREATE VIEW html_tables AS SELECT * FROM tables;
CREATE VIEW page_metadata AS SELECT * FROM metadata_observations;
"""


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\x00", "")


def display_text(value: Any) -> str:
    return re.sub(r"\s+", " ", clean_text(value).replace("\xa0", " ")).strip()


def normalized_text(value: Any) -> str:
    return unicodedata.normalize("NFKC", display_text(value)).casefold()


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def attr_value(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(clean_text(part) for part in value)
    if value is None:
        return ""
    return clean_text(value)


def attrs_dict(node: Tag) -> dict[str, str]:
    return {clean_text(key): attr_value(value) for key, value in sorted(node.attrs.items())}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detect_non_latin_script(text: str) -> str | None:
    if not text:
        return None
    scripts = set()
    for ch in text:
        if not ch.isalpha():
            continue
        name = unicodedata.name(ch, "")
        if not name.startswith("LATIN"):
            prefix = name.split()[0]
            scripts.add(prefix)
    if scripts:
        return ", ".join(sorted(scripts))
    return None


def html_files(source: Path) -> list[Path]:
    return sorted(
        (path for path in source.rglob("*") if path.is_file() and path.suffix.casefold() == ".html"),
        key=lambda path: path.relative_to(source).as_posix().casefold(),
    )


def file_manifest(source: Path, paths: list[Path]) -> tuple[list[dict[str, Any]], str, str]:
    rows: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    latest = datetime.fromtimestamp(0, timezone.utc)
    for index, path in enumerate(paths, start=1):
        data = path.read_bytes()
        relative = path.relative_to(source).as_posix()
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        latest = max(latest, modified)
        row = {
            "file_id": index,
            "relative_path": relative,
            "filename": path.name,
            "byte_size": len(data),
            "modified_utc": modified.isoformat(),
            "sha256": sha256_bytes(data),
        }
        rows.append(row)
        digest.update(json_text(row).encode("utf-8"))
        digest.update(b"\n")
    return rows, digest.hexdigest(), latest.isoformat()


def decision_action(decision: str) -> str:
    text = display_text(decision).casefold()
    if not text:
        return "no_decision"
    if "conflicting entity names" in text and "ordinal" in text and "lowest ordinal" in text:
        return "choose_lowest_ordinal"
    if '"website" related page' in text and 'subtype "website"' in text:
        return "classify_other_website"
    if "file was moved" in text:
        return "scan_and_process_moved_file"
    if "disambiguation" in text:
        return "disambiguate_compound_artist"
    if "page identity is in the filename" in text:
        return "identity_from_filename"
    if text == "file deleted" or "delete" in text or ("deleting" in text and "unnecessary" in text):
        return "delete_unnecessary_html"
    return "unrecognized_decision"


def read_review_decisions(paths: list[Path] | Path | None) -> list[dict[str, str]]:
    if paths is None:
        return []
    if isinstance(paths, Path):
        path_list = [paths]
    else:
        path_list = list(paths)
    rows: list[dict[str, str]] = []
    for path in path_list:
        if not path or not path.is_file():
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = set(reader.fieldnames or [])
            if not ("decision" in fieldnames or "decision_text" in fieldnames):
                continue
            for row in reader:
                cleaned = {key: clean_text(value) for key, value in row.items()}
                if "decision_text" in cleaned and "decision" not in cleaned:
                    cleaned["decision"] = cleaned["decision_text"]
                rows.append(cleaned)
    return rows


def apply_review_decisions_read_only(
    source: Path, rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Apply decisions in strict read-only mode: NO files are ever deleted or altered."""
    source_resolved = source.resolve()
    results: list[dict[str, str]] = []
    for row_number, row in enumerate(rows, start=2):
        action = decision_action(row.get("decision", ""))
        relative = row.get("relative_path", "")
        status = "not_applicable"
        detail = "No response was supplied"
        if action == "unrecognized_decision":
            status, detail = "needs_review", "Decision text is not recognized"
        elif action == "classify_other_website":
            exists = (source / relative).is_file()
            status = "applied" if exists else "source_absent"
            detail = "Classified as page_class=other, page_subtype=website" if exists else "Source HTML is no longer present"
        elif action == "choose_lowest_ordinal":
            exists = (source / relative).is_file()
            status = "applied" if exists else "source_absent"
            detail = "Semantic entity title retained; lowest observed ordinal ranking selected" if exists else "Source HTML is no longer present"
        elif action == "scan_and_process_moved_file":
            status = "applied"
            detail = "Moved file scanned and scheduled for processing in source archive"
        elif action == "disambiguate_compound_artist":
            status = "applied"
            detail = "Disambiguated via compound artist identity (+ separated components)"
        elif action == "identity_from_filename":
            status = "applied"
            detail = "Page identity and metadata extracted from filename and document body"
        elif action == "delete_unnecessary_html":
            candidate = (source / relative).resolve()
            if source_resolved not in candidate.parents or candidate.suffix.casefold() != ".html":
                status, detail = "blocked", "Target is outside source root or not .html"
            elif not candidate.exists():
                status, detail = "already_absent", "File was not found in source root"
            else:
                status, detail = "preserved_read_only", "File preserved in read-only archive; marked unnecessary by decision"
        results.append(
            {
                **row,
                "decision_row_number": str(row_number),
                "decision_action": action,
                "application_status": status,
                "application_detail": detail,
            }
        )
    return results


def decision_sets(results: list[dict[str, str]]) -> tuple[set[str], set[str]]:
    website_paths = {
        row["relative_path"].casefold()
        for row in results
        if row["decision_action"] == "classify_other_website" and row["application_status"] == "applied"
    }
    ordinal_keys = {
        row["entity_key"].casefold()
        for row in results
        if row["decision_action"] == "choose_lowest_ordinal" and row["application_status"] == "applied" and row["entity_key"]
    }
    return website_paths, ordinal_keys


def register_review_decisions(connection: sqlite3.Connection, results: list[dict[str, str]]) -> None:
    connection.executemany(
        """INSERT INTO review_decisions(
             prior_issue_id,relative_path,entity_key,prior_issue_code,prior_severity,
             prior_detail,prior_locator,prior_review_status,decision_text,decision_action,
             application_status,application_detail
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                row.get("issue_id", ""), row.get("relative_path", ""), row.get("entity_key", ""),
                row.get("issue_code", ""), row.get("severity", ""), row.get("detail", ""),
                row.get("locator", ""), row.get("review_status", ""), row.get("decision", ""),
                row["decision_action"], row["application_status"], row["application_detail"],
            )
            for row in results
        ],
    )


def canonical_entity_key(url: str) -> tuple[str, str, str]:
    if not url:
        return "", "", ""
    candidate = url.strip()
    if re.match(r"^(?:www\.)?secondhandsongs\.com/", candidate, re.I):
        candidate = "/" + candidate.split("/", 1)[1]
    parsed = urlparse(urljoin("https://secondhandsongs.com/", candidate))
    if parsed.netloc and "secondhandsongs.com" not in parsed.netloc.casefold():
        return "", "", ""
    match = SHS_ENTITY_RE.match(parsed.path)
    if match:
        entity_type, entity_id = match.group(1).casefold(), match.group(2)
        return f"{entity_type}/{entity_id}", entity_type, entity_id
    m_wc = WEB_COVER_RE.match(parsed.path)
    if m_wc:
        return f"performance/web-{m_wc.group(1)}", "performance", f"web-{m_wc.group(1)}"
    return "", "", ""


def node_locator(node: Tag) -> str:
    parts: list[str] = []
    current: Tag | None = node
    while isinstance(current, Tag) and current.name != "[document]" and len(parts) < 8:
        name = current.name or "node"
        if current.get("id"):
            parts.append(f"{name}#{clean_text(current.get('id'))}")
            break
        classes = current.get("class", [])
        if classes:
            name += "".join(f".{clean_text(value)}" for value in classes[:2] if clean_text(value))
        parent = current.parent if isinstance(current.parent, Tag) else None
        parts.append(name)
        current = parent
    locator = " > ".join(reversed(parts))
    line = getattr(node, "sourceline", None)
    return f"{locator}@L{line}" if line else locator


def element_value(node: Tag) -> str:
    for attribute in ("content", "datetime", "value"):
        if node.has_attr(attribute):
            return attr_value(node.get(attribute))
    return node.get_text(" ", strip=False).replace("\x00", "")


def head_metadata_candidates(soup: BeautifulSoup) -> list[str]:
    values: list[str] = []
    for node in soup.select('link[rel~="canonical"][href]'):
        values.append(attr_value(node.get("href")))
    for selector in (
        'meta[name="cyt:source-original-url"]',
        'meta[name="cyt:source-relative-url"]',
        'meta[name="cyt:source-webpage-url"]',
        'meta[name="source-webpage-url"]',
        'meta[property="og:url"]',
    ):
        values.extend(attr_value(node.get("content")) for node in soup.select(selector))
    return [value for value in values if value]


def classify_page(soup: BeautifulSoup, entity_key: str, raw_lower: str, path: Path) -> tuple[str, str]:
    filename = path.name.casefold()
    if filename.startswith("cyt-atra-") or "-atra-" in filename:
        return "atra", "performance"
    if "web cover_" in filename:
        return "performance", "web_cover"
    if entity_key:
        return entity_key.split("/", 1)[0], ""
    title = display_text(soup.title.get_text(" ", strip=False) if soup.title else "").casefold()
    url_text = " ".join(head_metadata_candidates(soup)).casefold()
    if title == "just a moment..." and "challenges.cloudflare.com" in raw_lower and "_cf_chl_opt" in raw_lower:
        return "cloudflare_error", ""
    if "guideline" in title or "/page/guidelines" in url_text:
        return "guideline", ""
    if "editor manual" in title or "introduction to the database" in title or "howto" in title or "glossary" in title or "/page/" in url_text:
        return "documentation", ""
    if soup.select_one("form[action*=login], input[type=password]"):
        return "login", ""
    if "search" in title or "/search" in url_text or "index" in title:
        return "search_list_index", ""
    if "<script" in raw_lower and len(raw_lower) < 2000 and not soup.select_one("main, section#main"):
        return "embedded_technical", ""
    if soup.select_one("main, section#main"):
        return "other_content", ""
    return "other_unrecognized", ""


def entity_name(soup: BeautifulSoup) -> str:
    for selector in ('h1 [itemprop="name"]', 'h1[itemprop="name"]', "main h1", "section#main h1", "h1"):
        node = soup.select_one(selector)
        if node:
            value = display_text(node.get_text(" ", strip=False))
            if value:
                return value
    return ""


def page_ranking(soup: BeautifulSoup, semantic_name: str) -> tuple[str, int | None, int | None]:
    heading = soup.select_one("main h1, section#main h1, h1")
    heading_text = display_text(heading.get_text(" ", strip=False)) if heading else ""
    match = ORDINAL_RANKING_RE.match(heading_text)
    if not match:
        return "", None, None
    if semantic_name and normalized_text(match.group("title")) != normalized_text(semantic_name):
        return "", None, None
    return heading_text, int(match.group("ordinal")), int(match.group("year"))


def context_for(node: Tag) -> tuple[str, str]:
    term = node.find_parent("dd")
    if term:
        dt = term.find_previous_sibling("dt")
        if dt:
            return "detail", display_text(dt.get_text(" ", strip=False)).rstrip(":")
    cell = node.find_parent(["td", "th"])
    if cell:
        table = cell.find_parent("table")
        heading = table.find_previous(["h2", "h3", "h4", "p"]) if table else None
        return "table", display_text(heading.get_text(" ", strip=False)) if heading else "Details"
    section = node.find_parent(["section", "main"])
    if section:
        heading = section.find(["h1", "h2", "h3", "h4"])
        return "section", display_text(heading.get_text(" ", strip=False)) if heading else ""
    if node.find_parent(["nav", "header", "footer"]):
        return "navigation", ""
    return "document", ""


def insert_metadata(
    connection: sqlite3.Connection,
    file_id: int,
    source_kind: str,
    key: str,
    ordinal: int,
    raw: str,
    locator: str,
    *,
    attributes: dict[str, str] | None = None,
    parsed: Any = None,
    status: str = "preserved",
) -> None:
    raw = clean_text(raw)
    connection.execute(
        """INSERT INTO metadata_observations(
             file_id,source_kind,metadata_key,ordinal,raw_value,display_value,
             normalized_value,parsed_json,attributes_json,locator,parse_status
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            file_id, source_kind, key, ordinal, raw, display_text(raw),
            normalized_text(raw), None if parsed is None else json_text(parsed),
            None if attributes is None else json_text(attributes), locator, status,
        ),
    )


def extract_adaptation_boundaries(main: Tag, primary_work_id: str) -> list[dict[str, Any]]:
    """Identify explicit work-level adaptation headings and their bounded sections."""
    adaptations: list[dict[str, Any]] = []
    # Find all potential work heading elements
    all_headings = main.find_all(lambda tag: tag.name in ["p", "h2", "h3", "h4", "div"] and (
        (tag.get("id") and tag.get("id").startswith("work-")) or
        "versions-table-header" in tag.get("class", []) or
        normalized_text(tag.get_text(strip=True)) == "related adaptation" or
        normalized_text(tag.get_text(strip=True)).startswith("related adaptation")
    ))

    for idx, heading in enumerate(all_headings):
        h_id = heading.get("id", "")
        m = re.match(r"^work-(\d+)$", h_id)
        work_id = m.group(1) if m else ""
        if not work_id:
            link = heading.find("a", href=re.compile(r"^/work/(\d+)"))
            if link:
                m2 = re.search(r"^/work/(\d+)", link.get("href", ""))
                if m2:
                    work_id = m2.group(1)

        norm_title = normalized_text(heading.get_text(strip=True))
        is_explicit_adaptation = (
            norm_title == "related adaptation" or
            norm_title.startswith("related adaptation") or
            (work_id and primary_work_id and work_id != primary_work_id and (
                "adaptation" in heading.get_text().lower() or
                heading.find_parent(class_=lambda c: c and "adaptation" in c) is not None
            ))
        )

        if is_explicit_adaptation:
            next_heading = all_headings[idx + 1] if idx + 1 < len(all_headings) else None
            adaptations.append({
                "work_id": work_id or "unknown",
                "heading_node": heading,
                "next_heading_node": next_heading,
                "locator": node_locator(heading),
                "title": display_text(heading.get_text(strip=True)),
            })
    return adaptations


def is_node_in_adaptation_bounds(node: Tag, adaptations: list[dict[str, Any]]) -> dict[str, Any] | None:
    for adapt in adaptations:
        h_node = adapt["heading_node"]
        next_node = adapt["next_heading_node"]
        # Check if node is after h_node and before next_node
        if getattr(node, "sourceline", 0) and getattr(h_node, "sourceline", 0):
            if node.sourceline >= h_node.sourceline:
                if not next_node or not getattr(next_node, "sourceline", 0) or node.sourceline < next_node.sourceline:
                    return adapt
        elif h_node in node.parents or h_node == node:
            return adapt
    return None


def parse_page(
    connection: sqlite3.Connection,
    source: Path,
    path: Path,
    manifest: dict[str, Any],
    website_paths: set[str],
) -> dict[str, Any]:
    file_id = manifest["file_id"]
    raw_bytes = path.read_bytes()
    soup = BeautifulSoup(raw_bytes, "lxml")
    encoding = clean_text(soup.original_encoding or "")
    raw_for_patterns = raw_bytes.decode(encoding or "utf-8", errors="replace")
    raw_lower = raw_for_patterns.casefold()
    title = display_text(soup.title.get_text(" ", strip=False) if soup.title else "")
    candidates = head_metadata_candidates(soup)
    canonical_url = candidates[0] if candidates else ""
    entity_key = entity_type = entity_id = ""
    for candidate in candidates:
        entity_key, entity_type, entity_id = canonical_entity_key(candidate)
        if entity_key:
            canonical_url = candidate
            break

    fn_meta = filename_metadata(path)
    if not entity_key and fn_meta.get("entity_key"):
        entity_key = fn_meta["entity_key"]
        entity_type = fn_meta["entity_type"]
        entity_id = fn_meta["entity_id"]
        if not canonical_url:
            canonical_url = f"https://secondhandsongs.com/{entity_key}"

    # Disambiguation: if The Beatles page was stamped with member George Harrison's ID 1451
    if entity_key == "artist/1451" and "beatles" in manifest["filename"].casefold():
        entity_id = "41"
        entity_key = "artist/41"
        if not canonical_url or "1451" in canonical_url:
            canonical_url = "https://secondhandsongs.com/artist/41/all"

    page_class, page_subtype = classify_page(soup, entity_key, raw_lower, path)
    if not page_subtype and fn_meta.get("page_subtype"):
        page_subtype = fn_meta["page_subtype"]

    name = entity_name(soup)
    if not name and fn_meta.get("title"):
        name = fn_meta["title"]
    elif not name and fn_meta.get("name"):
        name = fn_meta["name"]

    ranking_text, ranking_ordinal, ranking_year = page_ranking(soup, name)
    if ranking_year is None and fn_meta.get("year"):
        ranking_year = fn_meta["year"]
    if manifest["relative_path"].casefold() in website_paths:
        page_class, page_subtype = "other", "website"

    # Non-Latin script check for entity name
    non_latin_script = detect_non_latin_script(name)
    if non_latin_script:
        connection.execute(
            """INSERT INTO excluded_non_latin(file_id, item_type, item_text, detected_script, locator, detail)
               VALUES(?,?,?,?,?,?)""",
            (file_id, "entity_name", name, non_latin_script, "h1", f"Entity name in non-Latin script ({non_latin_script}) excluded"),
        )
        # Suppress non-Latin entity name from canonical entity promotion
        entity_name_saved = ""
    else:
        entity_name_saved = name

    connection.execute(
        """INSERT INTO source_files(
             file_id,run_id,relative_path,filename,byte_size,modified_utc,sha256,
             detected_encoding,parse_status,page_class,page_subtype,document_title,canonical_url,
             shs_entity_type,shs_entity_id,entity_key,entity_name,ranking_text,
             ranking_ordinal,ranking_year
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            file_id, manifest["run_id"], manifest["relative_path"], manifest["filename"],
            manifest["byte_size"], manifest["modified_utc"], manifest["sha256"],
            encoding, "parsed", page_class, page_subtype, title, canonical_url, entity_type,
            entity_id, entity_key, entity_name_saved, ranking_text, ranking_ordinal, ranking_year,
        ),
    )

    # Record capture
    density = len(soup.find_all(attrs={"itemprop": True})) + len(soup.find_all(["meta", "table", "dt"]))
    connection.execute(
        """INSERT INTO page_captures(file_id, entity_key, captured_utc, metadata_density, semantic_fingerprint)
           VALUES(?,?,?,?,?)""",
        (file_id, entity_key or None, manifest["modified_utc"], density, manifest["sha256"][:32]),
    )

    if title:
        insert_metadata(connection, file_id, "document", "document.title", 1, title, "head > title")
    html_node = soup.find("html")
    if isinstance(html_node, Tag) and html_node.get("lang"):
        insert_metadata(connection, file_id, "document", "html.lang", 1, attr_value(html_node.get("lang")), node_locator(html_node))

    for fn_k, fn_v in fn_meta.items():
        insert_metadata(connection, file_id, "filename", f"filename.{fn_k}", 1, str(fn_v), "path > filename")

    if fn_meta.get("artist") and entity_key:
        fn_artist = fn_meta["artist"]
        if not detect_non_latin_script(fn_artist):
            connection.execute(
                """INSERT INTO credits(file_id, entity_key, credit_role, credited_name, credited_entity_key, source_kind, locator)
                   VALUES(?,?,?,?,?,?,?)""",
                (file_id, entity_key, "performer", fn_artist, None, "filename", "path > filename"),
            )
    if fn_meta.get("writers") and entity_key:
        for w_name in [w.strip() for w in fn_meta["writers"].split(",")]:
            if w_name and not detect_non_latin_script(w_name):
                connection.execute(
                    """INSERT INTO credits(file_id, entity_key, credit_role, credited_name, credited_entity_key, source_kind, locator)
                       VALUES(?,?,?,?,?,?,?)""",
                    (file_id, entity_key, "writer", w_name, None, "filename", "path > filename"),
                )

    for ordinal, node in enumerate(soup.head.find_all("meta") if soup.head else [], start=1):
        attrs = attrs_dict(node)
        key_name = ""
        for attribute in ("name", "property", "http-equiv", "itemprop", "charset"):
            if node.has_attr(attribute):
                key_name = f"meta.{attribute}:{attr_value(node.get(attribute)) or '(present)'}"
                break
        insert_metadata(
            connection, file_id, "head_meta", key_name or "meta.*", ordinal,
            attr_value(node.get("content")) or attr_value(node.get("charset")),
            node_locator(node), attributes=attrs,
        )

    for ordinal, node in enumerate(soup.head.find_all("link") if soup.head else [], start=1):
        attrs = attrs_dict(node)
        rel = attr_value(node.get("rel"))
        insert_metadata(
            connection, file_id, "head_link", f"link.rel:{rel or '(blank)'}", ordinal,
            attr_value(node.get("href")), node_locator(node), attributes=attrs,
        )

    for ordinal, node in enumerate(soup.find_all("script"), start=1):
        script_type = attr_value(node.get("type"))
        if script_type in STRUCTURED_SCRIPT_TYPES:
            raw = clean_text(node.string or node.get_text())
            parsed = None
            status = "invalid_json"
            try:
                parsed = json.loads(raw)
                status = "parsed"
            except (TypeError, json.JSONDecodeError):
                pass
            connection.execute(
                "INSERT INTO structured_data(file_id,ordinal,script_type,raw_text,parsed_json,parse_status,locator) VALUES(?,?,?,?,?,?,?)",
                (file_id, ordinal, script_type, raw, None if parsed is None else json_text(parsed), status, node_locator(node)),
            )
        else:
            insert_metadata(
                connection, file_id, "script_inventory", f"script.type:{script_type or '(blank)'}",
                ordinal, attr_value(node.get("src")), node_locator(node), attributes=attrs_dict(node),
                status="technical_inventory",
            )

    semantic_nodes: list[Tag] = []
    for node in soup.find_all(True):
        if any(node.has_attr(attribute) for attribute in SEMANTIC_ATTRIBUTES):
            semantic_nodes.append(node)
    for ordinal, node in enumerate(semantic_nodes, start=1):
        attrs = attrs_dict(node)
        value = element_value(node)
        connection.execute(
            """INSERT INTO microdata(
                 file_id,ordinal,tag_name,itemprop,itemtype,itemid,itemref,rdfa_property,
                 rdfa_typeof,raw_value,display_value,attributes_json,locator
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                file_id, ordinal, node.name, attr_value(node.get("itemprop")),
                attr_value(node.get("itemtype")), attr_value(node.get("itemid")),
                attr_value(node.get("itemref")), attr_value(node.get("property")),
                attr_value(node.get("typeof")), clean_text(value),
                display_text(value), json_text(attrs), node_locator(node),
            ),
        )

    data_ordinal = 0
    for node in soup.find_all(True):
        for key, value in node.attrs.items():
            if clean_text(key).casefold().startswith("data-"):
                data_ordinal += 1
                insert_metadata(
                    connection, file_id, "data_attribute", f"data_attribute:{key}",
                    data_ordinal, attr_value(value), node_locator(node), attributes={"tag": node.name},
                )

    main = soup.select_one("section#main, main")
    if main:
        # Detect explicit work-level adaptation boundaries
        adaptation_bounds = extract_adaptation_boundaries(main, entity_id if entity_type == "work" else "")

        detail_ordinal = 0
        current_section_id = None
        for term in main.find_all("dt"):
            value = term.find_next_sibling("dd")
            if not value:
                continue
            detail_ordinal += 1
            raw_value = clean_text(value.get_text(" ", strip=False))
            copied = BeautifulSoup(str(value), "lxml")
            for control in copied.select("button, script, style"):
                control.decompose()
            for br in copied.find_all("br"):
                br.replace_with("\n")
            lines = [display_text(line) for line in copied.get_text("", strip=False).splitlines() if display_text(line)]
            label_raw = clean_text(term.get_text(" ", strip=False)).strip()
            label_norm = normalized_text(label_raw.rstrip(":"))

            # Check non-Latin in definition values
            dt_non_latin = detect_non_latin_script(raw_value)
            if dt_non_latin:
                connection.execute(
                    """INSERT INTO excluded_non_latin(file_id, item_type, item_text, detected_script, locator, detail)
                       VALUES(?,?,?,?,?,?)""",
                    (file_id, f"detail:{label_raw}", raw_value, dt_non_latin, node_locator(term), f"Definition detail in non-Latin script ({dt_non_latin}) excluded"),
                )
                continue

            connection.execute(
                """INSERT INTO detail_entries(
                     file_id,section_id,ordinal,label_raw,label_normalized,value_raw,value_display,lines_json,locator
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    file_id, current_section_id, detail_ordinal, label_raw, label_norm,
                    raw_value, display_text(raw_value), json_text(lines), node_locator(term),
                ),
            )

            # Extract normalized credits from definition terms
            if label_norm in {"written by", "music written by", "lyrics written by", "originally written by", "author"}:
                role = "composer" if "music" in label_norm else ("lyricist" if "lyrics" in label_norm else "author")
                for anchor in value.find_all("a", href=True):
                    c_key, _, _ = canonical_entity_key(anchor.get("href", ""))
                    credited_name = display_text(anchor.get_text(strip=True))
                    if not detect_non_latin_script(credited_name):
                        connection.execute(
                            """INSERT INTO credits(file_id, entity_key, credit_role, credited_name, credited_entity_key, source_kind, locator)
                               VALUES(?,?,?,?,?,?,?)""",
                            (file_id, entity_key or None, role, credited_name, c_key or None, "definition_list", node_locator(anchor)),
                        )
                        if entity_key and c_key:
                            connection.execute(
                                """INSERT INTO relationships(file_id, source_entity_key, relationship_type, target_entity_key, target_name, locator)
                                   VALUES(?,?,?,?,?,?)""",
                                (file_id, entity_key, "written-by", c_key, credited_name, node_locator(anchor)),
                            )

            elif label_norm == "adapted from":
                for anchor in value.find_all("a", href=True):
                    c_key, _, _ = canonical_entity_key(anchor.get("href", ""))
                    a_name = display_text(anchor.get_text(strip=True))
                    connection.execute(
                        """INSERT INTO excluded_adaptations(file_id, primary_work_key, adaptation_work_key, adaptation_title, heading_locator, first_release_info, detail)
                           VALUES(?,?,?,?,?,?,?)""",
                        (file_id, entity_key or "unknown", c_key or "unknown", a_name, node_locator(term), "", "Source work listed in Adapted from detail"),
                    )

        block_ordinal = 0
        for node in main.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
            if node.find_parent("table") or node.find_parent(["nav", "footer"]):
                continue
            text = clean_text(node.get_text(" ", strip=False))
            if not display_text(text):
                continue
            block_ordinal += 1
            heading = node if re.fullmatch(r"h[1-6]", node.name or "") else node.find_previous(["h1", "h2", "h3", "h4"])
            connection.execute(
                "INSERT INTO content_blocks(file_id,ordinal,block_type,heading_context,raw_text,display_text,locator) VALUES(?,?,?,?,?,?,?)",
                (file_id, block_ordinal, node.name, display_text(heading.get_text(" ", strip=False)) if heading else "", text, display_text(text), node_locator(node)),
            )

        for table_ordinal, table in enumerate(main.find_all("table"), start=1):
            heading_node = table.find_previous(["h2", "h3", "h4", "p"])
            heading = display_text(heading_node.get_text(" ", strip=False)) if heading_node else "Details"
            t_locator = node_locator(table)

            # Check if this table falls within a bounded adaptation section
            in_adaptation = is_node_in_adaptation_bounds(table, adaptation_bounds)
            if in_adaptation:
                # Log to excluded adaptations
                adapt_work_id = in_adaptation.get("work_id", "unknown")
                connection.execute(
                    """INSERT INTO excluded_adaptations(file_id, primary_work_key, adaptation_work_key, adaptation_title, heading_locator, first_release_info, detail)
                       VALUES(?,?,?,?,?,?,?)""",
                    (file_id, entity_key or f"work/{entity_id}", f"work/{adapt_work_id}", in_adaptation.get("title", ""), t_locator, "", "Bounded adaptation table excluded from primary collected data"),
                )
                # Exclude this table from primary collected data
                continue

            cursor = connection.execute(
                "INSERT INTO tables(file_id,ordinal,html_id,heading,locator) VALUES(?,?,?,?,?)",
                (file_id, table_ordinal, attr_value(table.get("id")), heading, t_locator),
            )
            table_id = int(cursor.lastrowid)
            header_rows = table.select("thead tr")
            headers = [display_text(cell.get_text(" ", strip=False)) for cell in table.select("thead th")]
            for col_num, h_text in enumerate(headers, start=1):
                connection.execute(
                    "INSERT INTO table_columns(table_id, column_ordinal, heading, data_type, locator) VALUES(?,?,?,?,?)",
                    (table_id, col_num, h_text, "text", f"{t_locator} > thead th:nth-child({col_num})"),
                )

            rows = table.select("tbody tr") or table.find_all("tr")
            row_number = 0
            for row in rows:
                if header_rows and row in header_rows:
                    continue
                cells = row.find_all(["th", "td"], recursive=False)
                if not cells:
                    continue
                row_number += 1
                row_cls = " ".join(row.get("class", []))
                connection.execute(
                    "INSERT INTO table_rows(table_id, row_ordinal, row_class, locator) VALUES(?,?,?,?)",
                    (table_id, row_number, row_cls, node_locator(row)),
                )

                # Check row for non-Latin script performers/titles
                row_has_non_latin = False
                for column_number, cell in enumerate(cells, start=1):
                    raw_cell = clean_text(cell.get_text(" ", strip=False))
                    disp_cell = display_text(raw_cell)
                    heading_val = headers[column_number - 1] if column_number <= len(headers) else ""
                    if heading_val.lower() in {"performer", "title", "originally by", "covered by"}:
                        cell_script = detect_non_latin_script(disp_cell)
                        if cell_script:
                            connection.execute(
                                """INSERT INTO excluded_non_latin(file_id, item_type, item_text, detected_script, locator, detail)
                                   VALUES(?,?,?,?,?,?)""",
                                (file_id, f"table_cell:{heading_val}", disp_cell, cell_script, node_locator(cell), f"Performance/performer in non-Latin script ({cell_script}) excluded"),
                            )
                            row_has_non_latin = True
                            break
                if row_has_non_latin:
                    continue

                for column_number, cell in enumerate(cells, start=1):
                    raw_cell = clean_text(cell.get_text(" ", strip=False))
                    disp_cell = display_text(raw_cell)
                    heading_value = headers[column_number - 1] if column_number <= len(headers) else ""
                    date_status = date_value = date_precision = ""
                    if cell.get("data-cyt-date-status"):
                        date_status = attr_value(cell.get("data-cyt-date-status"))
                        date_value = attr_value(cell.get("data-cyt-date-sort"))
                        date_precision = attr_value(cell.get("data-cyt-date-precision"))
                    elif re.search(r"\b(?:date|year)\b", heading_value, re.I):
                        parsed_date = parse_shs_date(disp_cell)
                        if parsed_date:
                            date_status, date_value, date_precision = parsed_date.status, parsed_date.value, parsed_date.precision
                        elif disp_cell:
                            date_status, date_precision = "unparsed", "none"

                    connection.execute(
                        """INSERT INTO table_cells(
                             table_id,row_ordinal,column_ordinal,is_header,column_heading,
                             raw_text,display_text,row_span,column_span,date_status,
                             date_sort_value,date_precision,locator
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            table_id, row_number, column_number, int(cell.name == "th"),
                            heading_value, raw_cell, disp_cell,
                            int(attr_value(cell.get("rowspan")) or 1), int(attr_value(cell.get("colspan")) or 1),
                            date_status, date_value, date_precision, node_locator(cell),
                        ),
                    )

                    # Extract performer credits from table cells
                    if heading_value.lower() == "performer":
                        for a in cell.find_all("a", href=True):
                            c_key, _, _ = canonical_entity_key(a.get("href", ""))
                            c_name = display_text(a.get_text(strip=True))
                            if not detect_non_latin_script(c_name):
                                connection.execute(
                                    """INSERT INTO credits(file_id, entity_key, credit_role, credited_name, credited_entity_key, source_kind, locator)
                                       VALUES(?,?,?,?,?,?,?)""",
                                    (file_id, entity_key or None, "performer", c_name, c_key or None, "table_cell", node_locator(a)),
                                )
                                if entity_key and c_key:
                                    connection.execute(
                                        """INSERT INTO relationships(file_id, source_entity_key, relationship_type, target_entity_key, target_name, locator)
                                           VALUES(?,?,?,?,?,?)""",
                                        (file_id, entity_key, "performed-by", c_key, c_name, node_locator(a)),
                                    )

    grouped_links: dict[tuple[str, ...], dict[str, Any]] = {}
    for anchor in soup.find_all("a", href=True):
        href = clean_text(anchor.get("href"))
        text = display_text(anchor.get_text(" ", strip=False))
        context_kind, context_label = context_for(anchor)
        key = (
            href, text, attr_value(anchor.get("title")), attr_value(anchor.get("rel")),
            attr_value(anchor.get("target")), attr_value(anchor.get("download")),
            context_kind, context_label,
        )
        if key not in grouped_links:
            target_key, _, _ = canonical_entity_key(href)
            grouped_links[key] = {
                "locator": node_locator(anchor), "count": 0, "target_key": target_key,
            }
        grouped_links[key]["count"] += 1

    for key, grouped in grouped_links.items():
        href, text, title_attr, rel, target, download, context_kind, context_label = key
        absolute = urljoin(canonical_url or "https://secondhandsongs.com/", href)
        cursor = connection.execute(
            """INSERT INTO links(
                 file_id,href_raw,href_absolute,link_text,title,rel,target,download,
                 context_kind,context_label,first_locator,occurrence_count,target_entity_key,
                 resolution_status
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                file_id, href, absolute, text, title_attr, rel, target, download,
                context_kind, context_label, grouped["locator"], grouped["count"],
                grouped["target_key"], "pending",
            ),
        )

    resource_ordinal = 0
    for node in soup.find_all(["img", "audio", "video", "source", "iframe", "object", "embed", "script", "link"]):
        url_attribute = next((name for name in ("src", "href", "data", "poster") if node.has_attr(name)), "")
        if not url_attribute and node.name not in {"script", "link"}:
            continue
        resource_ordinal += 1
        connection.execute(
            """INSERT INTO resources(
                 file_id,ordinal,tag_name,url_attribute,url_raw,alternate_text,title,type,rel,
                 attributes_json,locator
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                file_id, resource_ordinal, node.name, url_attribute,
                attr_value(node.get(url_attribute)) if url_attribute else "",
                attr_value(node.get("alt")), attr_value(node.get("title")),
                attr_value(node.get("type")), attr_value(node.get("rel")),
                json_text(attrs_dict(node)), node_locator(node),
            ),
        )

    for identifier_type, pattern in PROVIDER_PATTERNS.items():
        for identifier in sorted(set(pattern.findall(raw_for_patterns)), key=str.casefold):
            connection.execute(
                "INSERT OR IGNORE INTO provider_identifiers(file_id,entity_key,identifier_type,identifier_value,source_locator) VALUES(?,?,?,?,?)",
                (file_id, entity_key or None, identifier_type, identifier, "document regex over saved HTML"),
            )

    if not title:
        connection.execute(
            "INSERT INTO review_issues(file_id,issue_code,severity,detail,locator) VALUES(?,?,?,?,?)",
            (file_id, "missing_document_title", "warning", "No nonblank HTML title was found", "head > title"),
        )
    if not entity_key and page_class not in {"guideline", "documentation", "login", "cloudflare_error", "other", "other_content", "search_list_index", "embedded_technical"}:
        connection.execute(
            "INSERT INTO review_issues(file_id,issue_code,severity,detail,locator) VALUES(?,?,?,?,?)",
            (file_id, "unrecognized_page_identity", "review", "No canonical SHS artist/work/performance/release identity was found", "head"),
        )
    if page_class == "cloudflare_error":
        connection.execute(
            "INSERT INTO review_issues(file_id,issue_code,severity,detail,locator) VALUES(?,?,?,?,?)",
            (file_id, "cloudflare_interstitial", "error", "Saved file is a Cloudflare challenge rather than an SHS content page", "document"),
        )

    return {
        "entity_key": entity_key, "entity_type": entity_type, "entity_id": entity_id,
        "entity_name": entity_name_saved, "canonical_url": canonical_url, "page_class": page_class,
        "page_subtype": page_subtype,
    }


def resolve_entities_and_links(
    connection: sqlite3.Connection, source: Path, ordinal_decision_keys: set[str]
) -> None:
    entity_rows = connection.execute(
        """SELECT entity_key,shs_entity_type,shs_entity_id,
                  COUNT(*) AS captures,COUNT(DISTINCT entity_name) AS names
           FROM source_files WHERE entity_key IS NOT NULL AND entity_key<>''
           GROUP BY entity_key,shs_entity_type,shs_entity_id ORDER BY entity_key"""
    ).fetchall()

    entity_counter: dict[str, int] = defaultdict(int)

    for row in entity_rows:
        e_key, e_type, e_id, cap_count, name_count = row[0], row[1], row[2], row[3], row[4]
        names = [
            val[0] for val in connection.execute(
                "SELECT DISTINCT entity_name FROM source_files WHERE entity_key=? AND entity_name<>'' ORDER BY file_id",
                (e_key,),
            )
        ]
        # Exclude non-Latin names
        names = [n for n in names if not detect_non_latin_script(n)]

        cyt_match = connection.execute(
            """SELECT raw_value FROM metadata_observations
               WHERE file_id IN (SELECT file_id FROM source_files WHERE entity_key=?)
                 AND metadata_key IN ('meta.name:cyt:entity-id','meta.name:cyt:CYTentityID')
               ORDER BY metadata_id LIMIT 1""",
            (e_key,),
        ).fetchone()

        entity_counter[e_type] += 1
        cyt_id = cyt_match[0] if cyt_match and cyt_match[0] else f"CYT-{e_type}-{entity_counter[e_type]:05d}"

        rankings = connection.execute(
            """SELECT ranking_text,ranking_ordinal,ranking_year
               FROM source_files
               WHERE entity_key=? AND ranking_ordinal IS NOT NULL
               ORDER BY ranking_ordinal,ranking_year,file_id""",
            (e_key,),
        ).fetchall()
        preferred_ranking = rankings[0] if rankings else ("", None, None)
        ranking_status = "lowest_ordinal_selected" if e_key.casefold() in ordinal_decision_keys and rankings else "none"

        source_url_row = connection.execute(
            "SELECT canonical_url FROM source_files WHERE entity_key=? AND canonical_url<>'' ORDER BY file_id LIMIT 1",
            (e_key,),
        ).fetchone()
        source_url = source_url_row[0] if source_url_row else f"https://secondhandsongs.com/{e_key}"

        connection.execute(
            """INSERT INTO entities(
                 entity_key,entity_type,shs_entity_id,preferred_name,source_url,cyt_entity_id,
                 preferred_ranking_text,preferred_ranking_ordinal,preferred_ranking_year,
                 capture_count,conflict_status
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                e_key, e_type, e_id, names[0] if names else "", source_url, cyt_id,
                preferred_ranking[0], preferred_ranking[1], preferred_ranking[2], cap_count,
                "name_conflict" if len(names) > 1 else ranking_status,
            ),
        )

        # Record entity names
        for idx, nm in enumerate(names, start=1):
            nm_type = "preferred" if idx == 1 else "variant"
            connection.execute(
                """INSERT INTO entity_names(entity_key, name_type, name_value, source_file_id, locator)
                   VALUES(?,?,?,?,?)""",
                (e_key, nm_type, nm, None, "source_files"),
            )

        if len(names) > 1:
            first_file = connection.execute(
                "SELECT file_id FROM source_files WHERE entity_key=? ORDER BY file_id LIMIT 1", (e_key,)
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO review_issues(file_id,issue_code,severity,detail,locator) VALUES(?,?,?,?,?)",
                (first_file, "conflicting_entity_names", "review", json_text(names), "entity captures"),
            )

    # Link resolution Pass 2
    path_to_file = {
        row[0].casefold(): (row[1], row[2] or "")
        for row in connection.execute("SELECT relative_path,file_id,entity_key FROM source_files")
    }
    basename_rows: defaultdict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for row in connection.execute("SELECT filename,file_id,relative_path,entity_key FROM source_files"):
        basename_rows[row[0].casefold()].append((row[1], row[2], row[3] or ""))
    entity_keys = {row[0] for row in connection.execute("SELECT entity_key FROM entities")}

    rows = connection.execute(
        """SELECT l.link_id,l.file_id,l.href_raw,l.target_entity_key,s.relative_path
           FROM links l JOIN source_files s ON s.file_id=l.file_id ORDER BY l.link_id"""
    ).fetchall()

    for link_id, file_id, href, target_key, source_relative in rows:
        parsed = urlparse(href)
        status = "non_shs_external"
        target_relative = ""
        resolved_key = target_key or ""

        if resolved_key:
            status = "exact_local_target" if resolved_key in entity_keys else "external_shs_not_local"
        elif not parsed.scheme and not parsed.netloc and parsed.path:
            candidate = (Path(source_relative).parent / unquote(parsed.path)).as_posix()
            normalized_parts: list[str] = []
            for part in candidate.split("/"):
                if part in {"", "."}:
                    continue
                if part == "..":
                    if normalized_parts:
                        normalized_parts.pop()
                else:
                    normalized_parts.append(part)
            normalized = "/".join(normalized_parts).casefold()
            found = path_to_file.get(normalized)
            if found:
                target_relative = "/".join(normalized_parts)
                resolved_key = found[1]
                status = "exact_local_target"
            else:
                candidates = basename_rows.get(Path(unquote(parsed.path)).name.casefold(), [])
                if len(candidates) == 1:
                    target_relative = candidates[0][1]
                    resolved_key = candidates[0][2]
                    status = "exact_local_target"
                elif len(candidates) > 1:
                    status = "ambiguous_local_target"
                elif href.startswith("#"):
                    target_relative = source_relative
                    status = "technical_navigation"
                else:
                    status = "broken_or_malformed"
        elif "secondhandsongs.com" in parsed.netloc.casefold():
            status = "external_shs_not_local"

        connection.execute(
            "UPDATE links SET target_entity_key=?,target_relative_path=?,resolution_status=? WHERE link_id=?",
            (resolved_key, target_relative, status, link_id),
        )
        connection.execute(
            """INSERT INTO reference_resolutions(link_id, file_id, resolution_class, target_entity_key, target_relative_path, details)
               VALUES(?,?,?,?,?,?)""",
            (link_id, file_id, status, resolved_key, target_relative, f"Link resolved to {status}"),
        )


def create_views(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE VIEW IF NOT EXISTS entity_captures AS
        SELECT e.entity_key,e.entity_type,e.shs_entity_id,e.preferred_name,e.source_url,
               e.cyt_entity_id,e.preferred_ranking_text,e.preferred_ranking_ordinal,
               e.preferred_ranking_year,e.capture_count,e.conflict_status,s.file_id,
               s.relative_path,s.sha256,s.document_title,s.page_class,s.page_subtype,
               s.ranking_text,s.ranking_ordinal,s.ranking_year
        FROM entities e JOIN source_files s USING(entity_key);

        CREATE VIEW IF NOT EXISTS links_and_references AS
        SELECT s.relative_path AS source_relative_path,s.entity_key AS source_entity_key,
               l.context_kind,l.context_label,l.link_text,l.href_raw,l.href_absolute,
               l.target_entity_key,l.target_relative_path,l.resolution_status,
               SUM(l.occurrence_count) AS occurrence_count
        FROM links l JOIN source_files s USING(file_id)
        GROUP BY s.relative_path,s.entity_key,l.context_kind,l.context_label,l.link_text,
                 l.href_raw,l.href_absolute,l.target_entity_key,l.target_relative_path,
                 l.resolution_status;
        """
    )


def export_query(connection: sqlite3.Connection, destination: Path, query: str) -> int:
    cursor = connection.execute(query)
    headers = [column[0] for column in cursor.description]
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    count = 0
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(headers)
        for row in cursor:
            writer.writerow(["" if value is None else value for value in row])
            count += 1
    os.replace(temporary, destination)
    return count


def export_csvs(connection: sqlite3.Connection, output: Path) -> dict[str, int]:
    exports = {
        "manifest.csv": "SELECT relative_path,filename,byte_size,modified_utc,sha256,detected_encoding,parse_status,parse_error,page_class,page_subtype,document_title,canonical_url,entity_key,entity_name,ranking_text,ranking_ordinal,ranking_year FROM source_files ORDER BY relative_path COLLATE NOCASE",
        "csv/entities.csv": "SELECT * FROM entities ORDER BY entity_type,preferred_name COLLATE NOCASE,entity_key",
        "csv/page_captures.csv": "SELECT * FROM entity_captures ORDER BY entity_type,preferred_name COLLATE NOCASE,relative_path COLLATE NOCASE",
        "csv/metadata_observations.csv": "SELECT s.relative_path,s.entity_key,m.source_kind,m.metadata_key,m.ordinal,m.raw_value,m.display_value,m.normalized_value,m.parsed_json,m.attributes_json,m.locator,m.parse_status FROM metadata_observations m JOIN source_files s USING(file_id) ORDER BY s.relative_path COLLATE NOCASE,m.source_kind,m.ordinal",
        "csv/provider_identifiers.csv": "SELECT s.relative_path,p.entity_key,p.identifier_type,p.identifier_value,p.source_locator FROM provider_identifiers p JOIN source_files s USING(file_id) ORDER BY p.identifier_type,p.identifier_value,s.relative_path COLLATE NOCASE",
        "csv/credits.csv": "SELECT s.relative_path,c.entity_key,c.credit_role,c.credited_name,c.credited_entity_key,c.source_kind,c.locator FROM credits c JOIN source_files s USING(file_id) ORDER BY c.credit_role,c.credited_name COLLATE NOCASE,s.relative_path COLLATE NOCASE",
        "csv/relationships.csv": "SELECT s.relative_path,r.source_entity_key,r.relationship_type,r.target_entity_key,r.target_name,r.locator FROM relationships r JOIN source_files s USING(file_id) ORDER BY r.relationship_type,r.source_entity_key",
        "csv/details.csv": "SELECT s.relative_path,s.entity_key,d.ordinal,d.label_raw,d.label_normalized,d.value_raw,d.value_display,d.lines_json,d.locator FROM detail_entries d JOIN source_files s USING(file_id) ORDER BY s.relative_path COLLATE NOCASE,d.ordinal",
        "csv/table_cells.csv": "SELECT s.relative_path,s.entity_key,t.ordinal AS table_ordinal,t.heading,t.html_id,c.row_ordinal,c.column_ordinal,c.is_header,c.column_heading,c.raw_text,c.display_text,c.row_span,c.column_span,c.date_status,c.date_sort_value,c.date_precision,c.locator FROM table_cells c JOIN tables t USING(table_id) JOIN source_files s USING(file_id) ORDER BY s.relative_path COLLATE NOCASE,t.ordinal,c.row_ordinal,c.column_ordinal",
        "csv/links_and_references.csv": "SELECT * FROM links_and_references ORDER BY source_relative_path COLLATE NOCASE,context_kind,href_raw",
        "csv/review_queue.csv": "SELECT r.issue_id,s.relative_path,s.entity_key,r.issue_code,r.severity,r.detail,r.locator,r.review_status FROM review_issues r LEFT JOIN source_files s USING(file_id) ORDER BY r.severity,r.issue_code,s.relative_path COLLATE NOCASE",
        "csv/decision_application.csv": "SELECT prior_issue_id,relative_path,entity_key,prior_issue_code,prior_severity,prior_detail,prior_locator,prior_review_status,decision_text,decision_action,application_status,application_detail FROM review_decisions ORDER BY decision_row_id",
        "csv/excluded_adaptations.csv": "SELECT s.relative_path,a.primary_work_key,a.adaptation_work_key,a.adaptation_title,a.heading_locator,a.first_release_info,a.detail FROM excluded_adaptations a JOIN source_files s USING(file_id) ORDER BY s.relative_path COLLATE NOCASE",
        "csv/excluded_non_latin.csv": "SELECT s.relative_path,n.item_type,n.item_text,n.detected_script,n.locator,n.detail FROM excluded_non_latin n JOIN source_files s USING(file_id) ORDER BY n.detected_script,s.relative_path COLLATE NOCASE",
        "validation/excluded_adaptations.csv": "SELECT s.relative_path,a.primary_work_key,a.adaptation_work_key,a.adaptation_title,a.heading_locator,a.first_release_info,a.detail FROM excluded_adaptations a JOIN source_files s USING(file_id) ORDER BY s.relative_path COLLATE NOCASE",
        "validation/excluded_non_latin.csv": "SELECT s.relative_path,n.item_type,n.item_text,n.detected_script,n.locator,n.detail FROM excluded_non_latin n JOIN source_files s USING(file_id) ORDER BY n.detected_script,s.relative_path COLLATE NOCASE",
        "validation/duplicate_captures.csv": "SELECT sha256,COUNT(*) AS duplicate_count,GROUP_CONCAT(relative_path, '; ') AS matching_files FROM source_files GROUP BY sha256 HAVING COUNT(*) > 1 ORDER BY duplicate_count DESC",
        "validation/unknown_constructs.csv": "SELECT 'unrecognized_page' AS construct_type,relative_path,page_class AS construct_detail FROM source_files WHERE page_class IN ('other_unrecognized','parse_error') UNION ALL SELECT 'unparsed_date' AS construct_type,s.relative_path,c.raw_text AS construct_detail FROM table_cells c JOIN tables t USING(table_id) JOIN source_files s USING(file_id) WHERE c.date_status='unparsed'",
    }
    return {name: export_query(connection, output / name, query) for name, query in exports.items()}


def export_dictionary(connection: sqlite3.Connection, output: Path) -> int:
    rows: list[tuple[Any, ...]] = []
    queries = [
        ("metadata_observations", "SELECT metadata_key,source_kind,COUNT(*),COUNT(DISTINCT file_id) FROM metadata_observations GROUP BY metadata_key,source_kind"),
        ("microdata.itemprop", "SELECT COALESCE(NULLIF(itemprop,''),'(blank)'),'microdata',COUNT(*),COUNT(DISTINCT file_id) FROM microdata GROUP BY itemprop"),
        ("microdata.itemtype", "SELECT COALESCE(NULLIF(itemtype,''),'(blank)'),'microdata',COUNT(*),COUNT(DISTINCT file_id) FROM microdata GROUP BY itemtype"),
        ("detail", "SELECT label_raw,'definition_list',COUNT(*),COUNT(DISTINCT file_id) FROM detail_entries GROUP BY label_normalized"),
        ("table_column", "SELECT COALESCE(NULLIF(c.heading,''),'(blank)'),'table',COUNT(*),COUNT(DISTINCT t.file_id) FROM table_columns c JOIN tables t USING(table_id) GROUP BY c.heading"),
        ("link_resolution", "SELECT resolution_status,'anchor',SUM(occurrence_count),COUNT(DISTINCT file_id) FROM links GROUP BY resolution_status"),
        ("provider_identifier", "SELECT identifier_type,'provider_regex',COUNT(*),COUNT(DISTINCT file_id) FROM provider_identifiers GROUP BY identifier_type"),
    ]
    rules = {
        "metadata_observations": "Exact head/document/data attribute name; raw attributes retained",
        "microdata.itemprop": "Exact itemprop token with enclosing schema context",
        "microdata.itemtype": "Exact itemtype URL on itemscope-bearing elements",
        "detail": "main/section#main dt paired with immediate sibling dd",
        "table_column": "main/section#main table columns associated by heading and order",
        "link_resolution": "Every a[href], deduplicated per file/context/text/href with occurrence count",
        "provider_identifier": "Provider-specific regex over saved HTML bytes",
    }
    for family, query in queries:
        for key, source_kind, occurrences, files in connection.execute(query):
            rows.append((family, key, source_kind, occurrences, files, rules[family], "Raw evidence preserved; normalized meaning is context-sensitive"))

    rows.extend([
        ("structured_data", "jsonLd[].raw", "script", connection.execute("SELECT COUNT(*) FROM structured_data").fetchone()[0], connection.execute("SELECT COUNT(DISTINCT file_id) FROM structured_data").fetchone()[0], "script[type=application/ld+json or application/json]", "Raw text retained; valid JSON also stored in parsed_json"),
        ("generic", "unknown head metadata", "head", "variable", "variable", "Every meta and head link is captured even when its vocabulary is unknown", "Never silently discard an unrecognized metadata name"),
        ("generic", "unknown definition label", "definition_list", "variable", "variable", "Every main dt/dd pair is captured", "Unknown labels remain generic observations"),
        ("generic", "unknown table column", "table", "variable", "variable", "Every main table cell is captured", "Unknown columns remain generic observations"),
    ])
    destination = output / "metadata_dictionary.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["metadata_family", "metadata_key", "source_kind", "observed_occurrences", "files_with_value", "identification_and_parsing_rule", "preservation_rule"])
        writer.writerows(sorted(rows, key=lambda row: (str(row[0]).casefold(), str(row[1]).casefold())))
    return len(rows)


def export_entity_json(connection: sqlite3.Connection, output: Path) -> int:
    target = output / "json" / "entities"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    expected: set[str] = set()

    for entity in connection.execute("SELECT * FROM entities ORDER BY entity_key"):
        entity_dict = dict(entity)
        safe_name = f"{entity_dict['cyt_entity_id']}.json"
        expected.add(safe_name.casefold())
        captures: list[dict[str, Any]] = []
        files = connection.execute(
            "SELECT * FROM source_files WHERE entity_key=? ORDER BY relative_path COLLATE NOCASE",
            (entity_dict["entity_key"],),
        ).fetchall()

        for source_file in files:
            file_dict = dict(source_file)
            file_id = file_dict["file_id"]
            file_dict["metadata"] = [
                dict(row) for row in connection.execute(
                    "SELECT source_kind,metadata_key,ordinal,raw_value,display_value,normalized_value,parsed_json,attributes_json,locator,parse_status FROM metadata_observations WHERE file_id=? ORDER BY source_kind,ordinal",
                    (file_id,),
                )
            ]
            file_dict["details"] = [
                dict(row) for row in connection.execute(
                    "SELECT ordinal,label_raw,label_normalized,value_raw,value_display,lines_json,locator FROM detail_entries WHERE file_id=? ORDER BY ordinal",
                    (file_id,),
                )
            ]
            file_dict["credits"] = [
                dict(row) for row in connection.execute(
                    "SELECT credit_role,credited_name,credited_entity_key,source_kind,locator FROM credits WHERE file_id=? ORDER BY credit_id",
                    (file_id,),
                )
            ]
            file_dict["relationships"] = [
                dict(row) for row in connection.execute(
                    "SELECT relationship_type,target_entity_key,target_name,locator FROM relationships WHERE file_id=? ORDER BY relationship_id",
                    (file_id,),
                )
            ]
            file_dict["links"] = [
                dict(row) for row in connection.execute(
                    "SELECT href_raw,href_absolute,link_text,context_kind,context_label,occurrence_count,target_entity_key,target_relative_path,resolution_status FROM links WHERE file_id=? ORDER BY link_id",
                    (file_id,),
                )
            ]
            file_dict["providerIdentifiers"] = [
                dict(row) for row in connection.execute(
                    "SELECT identifier_type,identifier_value,source_locator FROM provider_identifiers WHERE file_id=? ORDER BY identifier_type,identifier_value",
                    (file_id,),
                )
            ]
            captures.append(file_dict)

        payload = {"entity": entity_dict, "sourceCaptures": captures}
        temporary = target / (safe_name + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, target / safe_name)
        count += 1

    for old in target.glob("*.json"):
        if old.name.casefold() not in expected:
            old.unlink()
    return count


def logical_fingerprint(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    tables = [
        "parse_runs", "source_files", "page_captures", "entities", "entity_names",
        "metadata_observations", "microdata", "structured_data", "detail_sections",
        "detail_entries", "content_blocks", "tables", "table_columns", "table_rows",
        "table_cells", "links", "reference_resolutions", "resources", "provider_identifiers",
        "credits", "relationships", "review_issues", "review_decisions",
        "excluded_adaptations", "excluded_non_latin",
    ]
    for table in tables:
        digest.update(table.encode("utf-8"))
        cursor = connection.execute(f"SELECT * FROM {table} ORDER BY 1")
        for row in cursor:
            digest.update(json_text(list(row)).encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()


def validate(connection: sqlite3.Connection, expected_files: int) -> dict[str, Any]:
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "source_files", "page_captures", "entities", "entity_names",
            "metadata_observations", "microdata", "structured_data", "detail_sections",
            "detail_entries", "content_blocks", "tables", "table_columns",
            "table_rows", "table_cells", "links", "reference_resolutions",
            "resources", "provider_identifiers", "credits", "relationships",
            "review_issues", "review_decisions", "excluded_adaptations", "excluded_non_latin",
        )
    }
    checks = {
        "integrity_ok": integrity == "ok",
        "foreign_keys_ok": not foreign_keys,
        "all_html_files_registered": counts["source_files"] == expected_files,
        "all_files_have_terminal_status": connection.execute("SELECT COUNT(*) FROM source_files WHERE parse_status NOT IN ('parsed','error')").fetchone()[0] == 0,
        "all_metadata_has_locator": connection.execute("SELECT COUNT(*) FROM metadata_observations WHERE locator='' OR locator IS NULL").fetchone()[0] == 0,
        "all_links_resolved_or_classified": connection.execute("SELECT COUNT(*) FROM links WHERE resolution_status='pending'").fetchone()[0] == 0,
        "entity_types_are_shs_scoped": connection.execute("SELECT COUNT(*) FROM entities WHERE entity_type NOT IN ('artist','work','performance','release')").fetchone()[0] == 0,
        "all_explicit_decisions_accounted_for": connection.execute("SELECT COUNT(*) FROM review_decisions WHERE decision_action<>'no_decision' AND application_status IN ('needs_review','blocked','would_delete')").fetchone()[0] == 0,
    }
    return {
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "expected_html_files": expected_files,
        "integrity_check": integrity,
        "foreign_key_errors": len(foreign_keys),
        "counts": counts,
        "checks": checks,
        "passed": all(checks.values()),
        "logical_sha256": logical_fingerprint(connection),
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def existing_is_current(output: Path, snapshot: str, expected_files: int) -> dict[str, Any] | None:
    state_path = output / "validation" / "build_manifest.json"
    database = output / "shs_metadata.sqlite"
    if not state_path.is_file() or not database.is_file():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if state.get("source_snapshot_sha256") != snapshot or state.get("parser_version") != PARSER_VERSION or state.get("export_version") != EXPORT_VERSION:
        return None
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        report = validate(connection, expected_files)
    finally:
        connection.close()
    if report["passed"] and report["logical_sha256"] == state.get("logical_sha256"):
        report["status"] = "already_current"
        return report
    return None


def build(
    source: Path,
    output: Path,
    *,
    limit: int | None = None,
    write: bool = False,
    decisions: list[Path] | Path | None = None,
) -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise ValueError(f"source directory not found: {source}")
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("source and output must be separate, non-nested directories")

    if decisions:
        if isinstance(decisions, (list, tuple)):
            decision_paths = [p.resolve() for p in decisions if p]
        else:
            decision_paths = [decisions.resolve()]
    else:
        decision_paths = []

    decision_rows = read_review_decisions(decision_paths)
    decision_results = apply_review_decisions_read_only(source, decision_rows)
    website_paths, ordinal_decision_keys = decision_sets(decision_results)

    paths = html_files(source)
    if limit is not None:
        paths = paths[:limit]

    manifest, source_snapshot, latest = file_manifest(source, paths)
    decisions_bytes = b"".join(p.read_bytes() for p in decision_paths if p.is_file())
    decisions_sha256 = sha256_bytes(decisions_bytes) if decisions_bytes else ""
    snapshot = sha256_bytes(f"{source_snapshot}\0{decisions_sha256}".encode("utf-8"))
    run_id = f"{PARSER_NAME}-{PARSER_VERSION}-{snapshot[:16]}"

    dry_summary = {
        "status": "dry_run", "source": str(source), "output": str(output),
        "html_files": len(paths), "source_snapshot_sha256": snapshot,
        "source_files_sha256": source_snapshot, "decisions_sha256": decisions_sha256,
        "decision_rows": len(decision_results), "parser_version": PARSER_VERSION,
        "decision_actions": dict(sorted(Counter(row["decision_action"] for row in decision_results).items())),
        "decision_statuses": dict(sorted(Counter(row["application_status"] for row in decision_results).items())),
    }
    if not write:
        return dry_summary

    # Idempotency check: if current output already matches snapshot and passes validation, skip reparsing
    current = existing_is_current(output, snapshot, len(paths))
    if current:
        return current

    # Staging area for atomic build
    staging = output / ".staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    database_staging = staging / "shs_metadata.sqlite"
    connection = sqlite3.connect(database_staging)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.executescript(SCHEMA_SQL)
    connection.execute("INSERT INTO schema_metadata(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
    connection.execute(
        "INSERT INTO parse_runs VALUES(?,?,?,?,?,?,?,?)",
        (run_id, PARSER_NAME, PARSER_VERSION, SCHEMA_VERSION, str(source), snapshot, len(paths), latest),
    )
    register_review_decisions(connection, decision_results)
    connection.commit()

    page_classes: Counter[str] = Counter()
    for index, (path, row) in enumerate(zip(paths, manifest), start=1):
        row["run_id"] = run_id
        connection.execute("SAVEPOINT parse_one_page")
        try:
            result = parse_page(connection, source, path, row, website_paths)
            connection.execute("RELEASE SAVEPOINT parse_one_page")
            page_classes[result["page_class"]] += 1
        except Exception as exc:
            connection.execute("ROLLBACK TO SAVEPOINT parse_one_page")
            connection.execute("RELEASE SAVEPOINT parse_one_page")
            connection.execute(
                """INSERT INTO source_files(
                     file_id,run_id,relative_path,filename,byte_size,modified_utc,sha256,
                     detected_encoding,parse_status,parse_error,page_class
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (row["file_id"], run_id, row["relative_path"], row["filename"], row["byte_size"], row["modified_utc"], row["sha256"], "", "error", f"{type(exc).__name__}: {exc}", "parse_error"),
            )
            connection.execute(
                "INSERT INTO review_issues(file_id,issue_code,severity,detail,locator) VALUES(?,?,?,?,?)",
                (row["file_id"], "parse_error", "error", f"{type(exc).__name__}: {exc}", "document"),
            )
            page_classes["parse_error"] += 1

        if index % 100 == 0 or index == len(paths):
            connection.commit()
            print(json.dumps({"progress": index, "total": len(paths)}), flush=True)

    resolve_entities_and_links(connection, source, ordinal_decision_keys)
    create_views(connection)
    connection.commit()

    report = validate(connection, len(paths))
    report["source_snapshot_sha256"] = snapshot
    report["source_files_sha256"] = source_snapshot
    report["decisions_sha256"] = decisions_sha256
    report["decision_actions"] = dict(sorted(Counter(row["decision_action"] for row in decision_results).items()))
    report["decision_statuses"] = dict(sorted(Counter(row["application_status"] for row in decision_results).items()))
    report["run_id"] = run_id
    report["page_classes"] = dict(sorted(page_classes.items()))

    if not report["passed"]:
        connection.close()
        shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError(f"validation failed: {json.dumps(report['checks'], sort_keys=True)}")

    connection.execute("VACUUM")
    csv_counts = export_csvs(connection, staging)
    dictionary_rows = export_dictionary(connection, staging)
    entity_json_files = export_entity_json(connection, staging)

    # Export extraction summary
    summary_path = staging / "validation" / "extraction_summary.csv"
    summary_rows = [
        ("total_html_files", len(paths)),
        ("parsed_files", len(paths) - page_classes.get("parse_error", 0)),
        ("parse_errors", page_classes.get("parse_error", 0)),
        ("entities_collected", report["counts"]["entities"]),
        ("credits_collected", report["counts"]["credits"]),
        ("relationships_collected", report["counts"]["relationships"]),
        ("tables_collected", report["counts"]["tables"]),
        ("table_cells_collected", report["counts"]["table_cells"]),
        ("excluded_adaptations", report["counts"]["excluded_adaptations"]),
        ("excluded_non_latin", report["counts"]["excluded_non_latin"]),
    ]
    with summary_path.open("w", encoding="utf-8-sig", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["metric", "value"])
        w.writerows(summary_rows)

    connection.close()

    report["csv_rows"] = csv_counts
    report["metadata_dictionary_rows"] = dictionary_rows
    report["entity_json_files"] = entity_json_files
    report["status"] = "staged_and_validated"

    write_json(staging / "validation" / "validation_results.json", report)
    state = {
        "parser_name": PARSER_NAME, "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION, "export_version": EXPORT_VERSION, "source_root": str(source),
        "source_snapshot_sha256": snapshot, "html_file_count": len(paths),
        "source_files_sha256": source_snapshot, "decisions_sha256": decisions_sha256,
        "logical_sha256": report["logical_sha256"], "run_id": run_id,
    }
    write_json(staging / "validation" / "build_manifest.json", state)

    # Atomic promotion from staging to published directory
    output.mkdir(parents=True, exist_ok=True)
    for item in staging.iterdir():
        dest = output / item.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        shutil.move(str(item), str(dest))
    shutil.rmtree(staging, ignore_errors=True)

    report["status"] = "built"
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Read-only source tree; only .html files are parsed")
    parser.add_argument("--output", type=Path, required=True, help="Separate derived-output directory")
    parser.add_argument("--limit", type=int, help="Deterministic first-N sample for testing")
    parser.add_argument("--decisions", type=Path, nargs="*", help="Responded review-queue CSV(s) whose explicit decisions should be applied")
    parser.add_argument("--write", action="store_true", help="Build/publish outputs; omit for a read-only dry run")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build(args.source, args.output, limit=args.limit, write=args.write, decisions=args.decisions)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
