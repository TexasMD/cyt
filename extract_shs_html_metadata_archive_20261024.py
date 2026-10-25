"""Extract a lossless, queryable metadata archive from saved SHS HTML files.

The source tree is read-only. Only files whose suffix is exactly .html
(case-insensitive) are parsed. SQLite is authoritative; deterministic CSV and
per-entity JSON files are accessibility exports.
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
import tempfile
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from musicdb_registry.recording_exclusions import (  # noqa: E402
    POLICY_VERSION as RECORDING_EXCLUSION_POLICY_VERSION,
    purge_shs_output,
)

try:
    from scripts.shs_dates import parse_shs_date
except ModuleNotFoundError:
    from shs_dates import parse_shs_date


PARSER_NAME = "shs_saved_html_metadata"
PARSER_VERSION = "1.2.0"
EXPORT_VERSION = 2
SCHEMA_VERSION = 2
SHS_ENTITY_RE = re.compile(
    r"^/(artist|work|performance|release)/(\d+)(?:/|$)", re.I
)
ORDINAL_RANKING_RE = re.compile(
    r"^(?P<title>.+?)\s+(?P<ordinal>\d+)(?:st|nd|rd|th)\s+in\s+(?P<year>\d{4})$",
    re.I,
)
PROVIDER_PATTERNS = {
    "spotify_track_id": re.compile(r"open\.spotify\.com/track/([A-Za-z0-9]+)", re.I),
    "youtube_video_id": re.compile(r"(?:youtube\.com/watch\?(?:[^#\s\"']*&)?v=|youtu\.be/)([A-Za-z0-9_-]+)", re.I),
    "musicbrainz_artist_id": re.compile(r"musicbrainz\.org/artist/([0-9a-f-]{36})", re.I),
    "musicbrainz_recording_id": re.compile(r"musicbrainz\.org/recording/([0-9a-f-]{36})", re.I),
    "musicbrainz_work_id": re.compile(r"musicbrainz\.org/work/([0-9a-f-]{36})", re.I),
    "musicbrainz_release_id": re.compile(r"musicbrainz\.org/release/([0-9a-f-]{36})", re.I),
    "whosampled_id": re.compile(r"whosampled\.com/[^\"'\s]*/(\d+)/?", re.I),
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
CREATE TABLE entities(
  entity_key TEXT PRIMARY KEY, entity_type TEXT NOT NULL, shs_entity_id TEXT NOT NULL,
  preferred_name TEXT, source_url TEXT, cyt_entity_id TEXT,
  preferred_ranking_text TEXT, preferred_ranking_ordinal INTEGER,
  preferred_ranking_year INTEGER,
  capture_count INTEGER NOT NULL DEFAULT 0, conflict_status TEXT NOT NULL DEFAULT 'none'
);
CREATE TABLE page_metadata(
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
CREATE TABLE detail_entries(
  detail_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  ordinal INTEGER NOT NULL, label_raw TEXT NOT NULL, label_normalized TEXT NOT NULL,
  value_raw TEXT, value_display TEXT, lines_json TEXT, locator TEXT NOT NULL
);
CREATE TABLE content_blocks(
  block_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  ordinal INTEGER NOT NULL, block_type TEXT NOT NULL, heading_context TEXT,
  raw_text TEXT, display_text TEXT, locator TEXT NOT NULL
);
CREATE TABLE html_tables(
  table_id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES source_files(file_id),
  ordinal INTEGER NOT NULL, html_id TEXT, heading TEXT, locator TEXT NOT NULL
);
CREATE TABLE table_cells(
  cell_id INTEGER PRIMARY KEY, table_id INTEGER NOT NULL REFERENCES html_tables(table_id),
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
CREATE INDEX source_files_entity_idx ON source_files(entity_key);
CREATE INDEX source_files_sha_idx ON source_files(sha256);
CREATE INDEX page_metadata_file_idx ON page_metadata(file_id, source_kind, ordinal);
CREATE INDEX page_metadata_lookup_idx ON page_metadata(metadata_key, normalized_value);
CREATE INDEX microdata_file_idx ON microdata(file_id, ordinal);
CREATE INDEX microdata_itemprop_idx ON microdata(itemprop);
CREATE INDEX structured_data_file_idx ON structured_data(file_id, ordinal);
CREATE INDEX detail_file_idx ON detail_entries(file_id, ordinal);
CREATE INDEX detail_label_idx ON detail_entries(label_normalized);
CREATE INDEX content_blocks_file_idx ON content_blocks(file_id, ordinal);
CREATE INDEX html_tables_file_idx ON html_tables(file_id, ordinal);
CREATE INDEX table_cells_table_idx ON table_cells(table_id, row_ordinal, column_ordinal);
CREATE INDEX table_heading_idx ON html_tables(heading);
CREATE INDEX links_file_idx ON links(file_id, link_id);
CREATE INDEX links_target_idx ON links(target_entity_key, resolution_status);
CREATE INDEX links_href_idx ON links(href_raw);
CREATE INDEX resources_file_idx ON resources(file_id, ordinal);
CREATE INDEX provider_identifiers_file_idx ON provider_identifiers(file_id, identifier_type);
CREATE INDEX provider_identifier_idx ON provider_identifiers(identifier_type, identifier_value);
CREATE INDEX review_issues_file_idx ON review_issues(file_id, issue_id);
CREATE INDEX review_decisions_action_idx ON review_decisions(decision_action, application_status);
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


def utc_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


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
    if text == "file deleted" or "delete" in text or ("deleting" in text and "unnecessary" in text):
        return "delete_unnecessary_html"
    return "unrecognized_decision"


def read_review_decisions(path: Path | None) -> list[dict[str, str]]:
    if path is None:
        return []
    if not path.is_file():
        raise ValueError(f"decision CSV not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "issue_id", "relative_path", "entity_key", "issue_code", "severity",
            "detail", "locator", "review_status", "decision",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"decision CSV missing columns: {sorted(missing)}")
        return [{key: clean_text(value) for key, value in row.items()} for row in reader]


def apply_decision_deletions(
    source: Path, rows: list[dict[str, str]], *, write: bool
) -> list[dict[str, str]]:
    source_resolved = source.resolve()
    results: list[dict[str, str]] = []
    deleted_paths: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        action = decision_action(row.get("decision", ""))
        relative = row.get("relative_path", "")
        status = "not_applicable"
        detail = "No response was supplied"
        if action == "unrecognized_decision":
            status, detail = "needs_review", "Decision text is not recognized by parser version 1.1.0"
        elif action == "classify_other_website":
            exists = (source / relative).is_file()
            status = "applied" if exists else "source_absent"
            detail = "Classified as page_class=other, page_subtype=website" if exists else "Source HTML is no longer present"
        elif action == "choose_lowest_ordinal":
            exists = (source / relative).is_file()
            status = "applied" if exists else "source_absent"
            detail = "Semantic entity title retained; lowest observed ordinal ranking selected" if exists else "Source HTML is no longer present"
        elif action == "delete_unnecessary_html":
            candidate = (source / relative).resolve()
            if source_resolved not in candidate.parents or candidate.suffix.casefold() != ".html":
                status, detail = "blocked", "Deletion target is outside the source root or is not an .html file"
            elif not candidate.exists():
                status, detail = "already_absent", "File was already deleted before this run"
            elif relative.casefold() in deleted_paths:
                status, detail = "already_applied_this_run", "Duplicate decision row for a file already deleted in this run"
            elif write:
                candidate.unlink()
                deleted_paths.add(relative.casefold())
                status, detail = "deleted", "Deleted by explicit responded-review decision"
            else:
                status, detail = "would_delete", "Explicit decision authorizes deletion; dry run made no change"
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
    # Saved SHS pages commonly store source URLs without a scheme, e.g.
    # ``secondhandsongs.com/work/296150``.  Normalize that host-form before
    # resolving it against the SHS origin; otherwise urljoin treats the host
    # as a path segment and the entity is missed.
    candidate = url.strip()
    if re.match(r"^(?:www\.)?secondhandsongs\.com/", candidate, re.I):
        candidate = "/" + candidate.split("/", 1)[1]
    parsed = urlparse(urljoin("https://secondhandsongs.com/", candidate))
    if parsed.netloc and "secondhandsongs.com" not in parsed.netloc.casefold():
        return "", "", ""
    match = SHS_ENTITY_RE.match(parsed.path)
    if not match:
        return "", "", ""
    entity_type, entity_id = match.group(1).casefold(), match.group(2)
    return f"{entity_type}/{entity_id}", entity_type, entity_id


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
    for node in soup.select('head link[rel~="canonical"][href]'):
        values.append(attr_value(node.get("href")))
    for selector in (
        'head meta[name="cyt:source-webpage-url"]',
        'head meta[name="source-webpage-url"]',
        'head meta[property="og:url"]',
    ):
        values.extend(attr_value(node.get("content")) for node in soup.select(selector))
    return [value for value in values if value]


def classify_page(soup: BeautifulSoup, entity_key: str, raw_lower: str) -> str:
    if entity_key:
        return entity_key.split("/", 1)[0]
    title = display_text(soup.title.get_text(" ", strip=False) if soup.title else "").casefold()
    url_text = " ".join(head_metadata_candidates(soup)).casefold()
    if title == "just a moment..." and "challenges.cloudflare.com" in raw_lower and "_cf_chl_opt" in raw_lower:
        return "cloudflare_error"
    if "guideline" in title or "/page/guidelines" in url_text:
        return "guideline"
    if "editor manual" in title or "introduction to the database" in title or "howto" in title:
        return "documentation"
    if soup.select_one("form[action*=login], input[type=password]"):
        return "login"
    if soup.select_one("main, section#main"):
        return "other_content"
    return "technical_or_unrecognized"


def entity_name(soup: BeautifulSoup) -> str:
    # Selector-list document ordering would return the outer h1 before its
    # semantically precise descendant. Probe selectors in evidence order.
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
        """INSERT INTO page_metadata(
             file_id,source_kind,metadata_key,ordinal,raw_value,display_value,
             normalized_value,parsed_json,attributes_json,locator,parse_status
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            file_id, source_kind, key, ordinal, raw, display_text(raw),
            normalized_text(raw), None if parsed is None else json_text(parsed),
            None if attributes is None else json_text(attributes), locator, status,
        ),
    )


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
    page_class = classify_page(soup, entity_key, raw_lower)
    name = entity_name(soup)
    ranking_text, ranking_ordinal, ranking_year = page_ranking(soup, name)
    page_subtype = ""
    if manifest["relative_path"].casefold() in website_paths:
        page_class, page_subtype = "other", "website"
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
            entity_id, entity_key, name, ranking_text, ranking_ordinal, ranking_year,
        ),
    )

    if title:
        insert_metadata(connection, file_id, "document", "document.title", 1, title, "head > title")
    html_node = soup.find("html")
    if isinstance(html_node, Tag) and html_node.get("lang"):
        insert_metadata(connection, file_id, "document", "html.lang", 1, attr_value(html_node.get("lang")), node_locator(html_node))

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
        detail_ordinal = 0
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
            connection.execute(
                """INSERT INTO detail_entries(
                     file_id,ordinal,label_raw,label_normalized,value_raw,value_display,lines_json,locator
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    file_id, detail_ordinal, label_raw, normalized_text(label_raw.rstrip(":")),
                    raw_value, display_text(raw_value), json_text(lines), node_locator(term),
                ),
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
            cursor = connection.execute(
                "INSERT INTO html_tables(file_id,ordinal,html_id,heading,locator) VALUES(?,?,?,?,?)",
                (file_id, table_ordinal, attr_value(table.get("id")), heading, node_locator(table)),
            )
            table_id = int(cursor.lastrowid)
            header_rows = table.select("thead tr")
            headers = [display_text(cell.get_text(" ", strip=False)) for cell in table.select("thead th")]
            rows = table.select("tbody tr") or table.find_all("tr")
            row_number = 0
            for row in rows:
                if header_rows and row in header_rows:
                    continue
                cells = row.find_all(["th", "td"], recursive=False)
                if not cells:
                    continue
                row_number += 1
                for column_number, cell in enumerate(cells, start=1):
                    raw_cell = clean_text(cell.get_text(" ", strip=False))
                    date_status = date_value = date_precision = ""
                    heading_value = headers[column_number - 1] if column_number <= len(headers) else ""
                    if cell.get("data-cyt-date-status"):
                        date_status = attr_value(cell.get("data-cyt-date-status"))
                        date_value = attr_value(cell.get("data-cyt-date-sort"))
                        date_precision = attr_value(cell.get("data-cyt-date-precision"))
                    elif re.search(r"\b(?:date|year)\b", heading_value, re.I):
                        parsed_date = parse_shs_date(display_text(raw_cell))
                        if parsed_date:
                            date_status, date_value, date_precision = parsed_date.status, parsed_date.value, parsed_date.precision
                        elif display_text(raw_cell):
                            date_status, date_precision = "unparsed", "none"
                    connection.execute(
                        """INSERT INTO table_cells(
                             table_id,row_ordinal,column_ordinal,is_header,column_heading,
                             raw_text,display_text,row_span,column_span,date_status,
                             date_sort_value,date_precision,locator
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            table_id, row_number, column_number, int(cell.name == "th"),
                            heading_value, raw_cell, display_text(raw_cell),
                            int(attr_value(cell.get("rowspan")) or 1), int(attr_value(cell.get("colspan")) or 1),
                            date_status, date_value, date_precision, node_locator(cell),
                        ),
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
        connection.execute(
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
    if not entity_key and page_class not in {"guideline", "documentation", "login", "cloudflare_error", "other"}:
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
        "entity_name": name, "canonical_url": canonical_url, "page_class": page_class,
        "page_subtype": page_subtype,
    }


def resolve_entities_and_links(
    connection: sqlite3.Connection, source: Path, ordinal_decision_keys: set[str]
) -> None:
    entity_rows = connection.execute(
        """SELECT entity_key,shs_entity_type,shs_entity_id,entity_name,canonical_url,
                  COUNT(*) AS captures,COUNT(DISTINCT entity_name) AS names
           FROM source_files WHERE entity_key IS NOT NULL AND entity_key<>''
           GROUP BY entity_key,shs_entity_type,shs_entity_id ORDER BY entity_key"""
    ).fetchall()
    for row in entity_rows:
        names = [
            value[0] for value in connection.execute(
                "SELECT DISTINCT entity_name FROM source_files WHERE entity_key=? AND entity_name<>'' ORDER BY file_id",
                (row[0],),
            )
        ]
        cyt = connection.execute(
            """SELECT raw_value FROM page_metadata
               WHERE file_id IN (SELECT file_id FROM source_files WHERE entity_key=?)
                 AND metadata_key IN ('meta.name:cyt:entity-id','meta.name:cyt:CYTentityID')
               ORDER BY metadata_id LIMIT 1""",
            (row[0],),
        ).fetchone()
        rankings = connection.execute(
            """SELECT ranking_text,ranking_ordinal,ranking_year
               FROM source_files
               WHERE entity_key=? AND ranking_ordinal IS NOT NULL
               ORDER BY ranking_ordinal,ranking_year,file_id""",
            (row[0],),
        ).fetchall()
        preferred_ranking = rankings[0] if rankings else ("", None, None)
        ranking_status = "lowest_ordinal_selected" if row[0].casefold() in ordinal_decision_keys and rankings else "none"
        connection.execute(
            """INSERT INTO entities(
                 entity_key,entity_type,shs_entity_id,preferred_name,source_url,cyt_entity_id,
                 preferred_ranking_text,preferred_ranking_ordinal,preferred_ranking_year,
                 capture_count,conflict_status
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row[0], row[1], row[2], names[0] if names else "", row[4], cyt[0] if cyt else "",
                preferred_ranking[0], preferred_ranking[1], preferred_ranking[2], row[5],
                "name_conflict" if len(names) > 1 else ranking_status,
            ),
        )
        if len(names) > 1:
            first_file = connection.execute("SELECT file_id FROM source_files WHERE entity_key=? ORDER BY file_id LIMIT 1", (row[0],)).fetchone()[0]
            connection.execute(
                "INSERT INTO review_issues(file_id,issue_code,severity,detail,locator) VALUES(?,?,?,?,?)",
                (first_file, "conflicting_entity_names", "review", json_text(names), "entity captures"),
            )

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
        status = "external_other"
        target_relative = ""
        resolved_key = target_key or ""
        if resolved_key:
            status = "exact_local_entity" if resolved_key in entity_keys else "external_shs_entity"
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
                status = "exact_local_file"
            else:
                candidates = basename_rows.get(Path(unquote(parsed.path)).name.casefold(), [])
                if len(candidates) == 1:
                    target_relative = candidates[0][1]
                    resolved_key = candidates[0][2]
                    status = "unique_local_basename"
                elif len(candidates) > 1:
                    status = "ambiguous_local_basename"
                elif href.startswith("#"):
                    target_relative = source_relative
                    status = "same_document_fragment"
                else:
                    status = "unresolved_relative"
        elif "secondhandsongs.com" in parsed.netloc.casefold():
            status = "external_shs_nonentity"
        connection.execute(
            "UPDATE links SET target_entity_key=?,target_relative_path=?,resolution_status=? WHERE link_id=?",
            (resolved_key, target_relative, status, link_id),
        )


def create_views(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE VIEW entity_captures AS
        SELECT e.entity_key,e.entity_type,e.shs_entity_id,e.preferred_name,e.source_url,
               e.cyt_entity_id,e.preferred_ranking_text,e.preferred_ranking_ordinal,
               e.preferred_ranking_year,e.capture_count,e.conflict_status,s.file_id,
               s.relative_path,s.sha256,s.document_title,s.page_class,s.page_subtype,
               s.ranking_text,s.ranking_ordinal,s.ranking_year
        FROM entities e JOIN source_files s USING(entity_key);
        CREATE VIEW links_and_references AS
        SELECT s.relative_path AS source_relative_path,s.entity_key AS source_entity_key,
               l.context_kind,l.context_label,l.link_text,l.href_raw,l.href_absolute,
               l.target_entity_key,l.target_relative_path,l.resolution_status,
               SUM(l.occurrence_count) AS occurrence_count
        FROM links l JOIN source_files s USING(file_id)
        GROUP BY s.relative_path,s.entity_key,l.context_kind,l.context_label,l.link_text,
                 l.href_raw,l.href_absolute,l.target_entity_key,l.target_relative_path,
                 l.resolution_status;
        CREATE VIEW reference_review_queue AS
        SELECT l.target_entity_key,l.resolution_status,l.href_raw,l.href_absolute,
               COUNT(DISTINCT l.file_id) AS source_file_count,
               SUM(l.occurrence_count) AS occurrence_count,
               MIN(s.relative_path) AS sample_source_relative_path,
               MIN(l.context_kind) AS sample_context_kind,
               MIN(l.context_label) AS sample_context_label
        FROM links l JOIN source_files s USING(file_id)
        WHERE l.resolution_status IN (
          'external_shs_entity','external_shs_nonentity','ambiguous_local_basename',
          'unresolved_relative'
        )
        GROUP BY l.target_entity_key,l.resolution_status,l.href_raw,l.href_absolute;
        CREATE VIEW metadata_observations AS
        SELECT s.relative_path,s.entity_key,p.source_kind,p.metadata_key,p.ordinal,
               p.raw_value,p.display_value,p.normalized_value,p.parsed_json,
               p.attributes_json,p.locator,p.parse_status
        FROM page_metadata p JOIN source_files s USING(file_id);
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
        "csv/metadata_observations.csv": "SELECT * FROM metadata_observations ORDER BY relative_path COLLATE NOCASE,source_kind,ordinal",
        "csv/provider_identifiers.csv": "SELECT s.relative_path,p.entity_key,p.identifier_type,p.identifier_value,p.source_locator FROM provider_identifiers p JOIN source_files s USING(file_id) ORDER BY p.identifier_type,p.identifier_value,s.relative_path COLLATE NOCASE",
        "csv/details.csv": "SELECT s.relative_path,s.entity_key,d.ordinal,d.label_raw,d.label_normalized,d.value_raw,d.value_display,d.lines_json,d.locator FROM detail_entries d JOIN source_files s USING(file_id) ORDER BY s.relative_path COLLATE NOCASE,d.ordinal",
        "csv/table_cells.csv": "SELECT s.relative_path,s.entity_key,t.ordinal AS table_ordinal,t.heading,t.html_id,c.row_ordinal,c.column_ordinal,c.is_header,c.column_heading,c.raw_text,c.display_text,c.row_span,c.column_span,c.date_status,c.date_sort_value,c.date_precision,c.locator FROM table_cells c JOIN html_tables t USING(table_id) JOIN source_files s USING(file_id) ORDER BY s.relative_path COLLATE NOCASE,t.ordinal,c.row_ordinal,c.column_ordinal",
        "csv/links_and_references.csv": "SELECT * FROM links_and_references ORDER BY source_relative_path COLLATE NOCASE,context_kind,href_raw",
        "csv/reference_review_queue.csv": "SELECT * FROM reference_review_queue ORDER BY resolution_status,target_entity_key,href_raw",
        "csv/review_queue.csv": "SELECT r.issue_id,s.relative_path,s.entity_key,r.issue_code,r.severity,r.detail,r.locator,r.review_status FROM review_issues r LEFT JOIN source_files s USING(file_id) ORDER BY r.severity,r.issue_code,s.relative_path COLLATE NOCASE",
        "csv/decision_application.csv": "SELECT prior_issue_id,relative_path,entity_key,prior_issue_code,prior_severity,prior_detail,prior_locator,prior_review_status,decision_text,decision_action,application_status,application_detail FROM review_decisions ORDER BY decision_row_id",
    }
    return {name: export_query(connection, output / name, query) for name, query in exports.items()}


def export_dictionary(connection: sqlite3.Connection, output: Path) -> int:
    rows: list[tuple[Any, ...]] = []
    queries = [
        ("page_metadata", "SELECT metadata_key,source_kind,COUNT(*),COUNT(DISTINCT file_id) FROM page_metadata GROUP BY metadata_key,source_kind"),
        ("microdata.itemprop", "SELECT COALESCE(NULLIF(itemprop,''),'(blank)'),'microdata',COUNT(*),COUNT(DISTINCT file_id) FROM microdata GROUP BY itemprop"),
        ("microdata.itemtype", "SELECT COALESCE(NULLIF(itemtype,''),'(blank)'),'microdata',COUNT(*),COUNT(DISTINCT file_id) FROM microdata GROUP BY itemtype"),
        ("detail", "SELECT label_raw,'definition_list',COUNT(*),COUNT(DISTINCT file_id) FROM detail_entries GROUP BY label_normalized"),
        ("table_column", "SELECT COALESCE(NULLIF(column_heading,''),'(blank)'),'table',COUNT(*),COUNT(DISTINCT t.file_id) FROM table_cells c JOIN html_tables t USING(table_id) GROUP BY column_heading"),
        ("link_resolution", "SELECT resolution_status,'anchor',SUM(occurrence_count),COUNT(DISTINCT file_id) FROM links GROUP BY resolution_status"),
        ("provider_identifier", "SELECT identifier_type,'provider_regex',COUNT(*),COUNT(DISTINCT file_id) FROM provider_identifiers GROUP BY identifier_type"),
    ]
    rules = {
        "page_metadata": "Exact head/document/data attribute name; raw attributes retained",
        "microdata.itemprop": "Exact itemprop token with enclosing schema context",
        "microdata.itemtype": "Exact itemtype URL on itemscope-bearing elements",
        "detail": "main/section#main dt paired with immediate sibling dd",
        "table_column": "main/section#main table cells associated by column position",
        "link_resolution": "Every a[href], deduplicated per file/context/text/href with occurrence count",
        "provider_identifier": "Provider-specific URL pattern over the saved HTML bytes",
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
        safe_name = entity_dict["entity_key"].replace("/", "-") + ".json"
        expected.add(safe_name.casefold())
        captures: list[dict[str, Any]] = []
        files = connection.execute("SELECT * FROM source_files WHERE entity_key=? ORDER BY relative_path COLLATE NOCASE", (entity_dict["entity_key"],)).fetchall()
        for source_file in files:
            file_dict = dict(source_file)
            file_id = file_dict["file_id"]
            file_dict["metadata"] = [dict(row) for row in connection.execute("SELECT source_kind,metadata_key,ordinal,raw_value,display_value,normalized_value,parsed_json,attributes_json,locator,parse_status FROM page_metadata WHERE file_id=? ORDER BY source_kind,ordinal", (file_id,))]
            file_dict["details"] = [dict(row) for row in connection.execute("SELECT ordinal,label_raw,label_normalized,value_raw,value_display,lines_json,locator FROM detail_entries WHERE file_id=? ORDER BY ordinal", (file_id,))]
            file_dict["links"] = [dict(row) for row in connection.execute("SELECT href_raw,href_absolute,link_text,context_kind,context_label,occurrence_count,target_entity_key,target_relative_path,resolution_status FROM links WHERE file_id=? ORDER BY link_id", (file_id,))]
            file_dict["providerIdentifiers"] = [dict(row) for row in connection.execute("SELECT identifier_type,identifier_value,source_locator FROM provider_identifiers WHERE file_id=? ORDER BY identifier_type,identifier_value", (file_id,))]
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
        "parse_runs", "source_files", "entities", "page_metadata", "microdata",
        "structured_data", "detail_entries", "content_blocks", "html_tables",
        "table_cells", "links", "resources", "provider_identifiers", "review_issues",
        "review_decisions",
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
            "source_files", "entities", "page_metadata", "microdata", "structured_data",
            "detail_entries", "content_blocks", "html_tables", "table_cells", "links",
            "resources", "provider_identifiers", "review_issues",
            "review_decisions",
        )
    }
    checks = {
        "integrity_ok": integrity == "ok",
        "foreign_keys_ok": not foreign_keys,
        "all_html_files_registered": counts["source_files"] == expected_files,
        "all_files_have_terminal_status": connection.execute("SELECT COUNT(*) FROM source_files WHERE parse_status NOT IN ('parsed','error')").fetchone()[0] == 0,
        "all_metadata_has_locator": connection.execute("SELECT COUNT(*) FROM page_metadata WHERE locator='' OR locator IS NULL").fetchone()[0] == 0,
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


def resume_published_database(output: Path, snapshot: str, expected_files: int) -> dict[str, Any] | None:
    """Finish exports after interruption that occurred after atomic DB publication."""
    database = output / "shs_metadata.sqlite"
    if not database.is_file():
        return None
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    run = connection.execute(
        "SELECT run_id,parser_version,source_snapshot_sha256,html_file_count,source_root FROM parse_runs ORDER BY run_id LIMIT 1"
    ).fetchone()
    if not run or run["parser_version"] != PARSER_VERSION or run["source_snapshot_sha256"] != snapshot or run["html_file_count"] != expected_files:
        connection.close()
        return None
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS page_metadata_file_idx ON page_metadata(file_id, source_kind, ordinal);
        CREATE INDEX IF NOT EXISTS microdata_file_idx ON microdata(file_id, ordinal);
        CREATE INDEX IF NOT EXISTS structured_data_file_idx ON structured_data(file_id, ordinal);
        CREATE INDEX IF NOT EXISTS detail_file_idx ON detail_entries(file_id, ordinal);
        CREATE INDEX IF NOT EXISTS content_blocks_file_idx ON content_blocks(file_id, ordinal);
        CREATE INDEX IF NOT EXISTS html_tables_file_idx ON html_tables(file_id, ordinal);
        CREATE INDEX IF NOT EXISTS table_cells_table_idx ON table_cells(table_id, row_ordinal, column_ordinal);
        CREATE INDEX IF NOT EXISTS links_file_idx ON links(file_id, link_id);
        CREATE INDEX IF NOT EXISTS resources_file_idx ON resources(file_id, ordinal);
        CREATE INDEX IF NOT EXISTS provider_identifiers_file_idx ON provider_identifiers(file_id, identifier_type);
        CREATE INDEX IF NOT EXISTS review_issues_file_idx ON review_issues(file_id, issue_id);
        DROP VIEW IF EXISTS reference_review_queue;
        CREATE VIEW reference_review_queue AS
        SELECT l.target_entity_key,l.resolution_status,l.href_raw,l.href_absolute,
               COUNT(DISTINCT l.file_id) AS source_file_count,
               SUM(l.occurrence_count) AS occurrence_count,
               MIN(s.relative_path) AS sample_source_relative_path,
               MIN(l.context_kind) AS sample_context_kind,
               MIN(l.context_label) AS sample_context_label
        FROM links l JOIN source_files s USING(file_id)
        WHERE l.resolution_status IN (
          'external_shs_entity','external_shs_nonentity','ambiguous_local_basename',
          'unresolved_relative'
        )
        GROUP BY l.target_entity_key,l.resolution_status,l.href_raw,l.href_absolute;
        """
    )
    connection.commit()
    report = validate(connection, expected_files)
    if not report["passed"]:
        connection.close()
        raise RuntimeError("published database exists but does not pass validation")
    report["source_snapshot_sha256"] = snapshot
    report["run_id"] = run["run_id"]
    report["csv_rows"] = export_csvs(connection, output)
    report["metadata_dictionary_rows"] = export_dictionary(connection, output)
    report["entity_json_files"] = export_entity_json(connection, output)
    connection.close()
    report["status"] = "resumed_exports"
    write_json(output / "validation" / "validation_results.json", report)
    write_json(
        output / "validation" / "build_manifest.json",
        {
            "parser_name": PARSER_NAME, "parser_version": PARSER_VERSION,
            "schema_version": SCHEMA_VERSION, "export_version": EXPORT_VERSION,
            "source_root": run["source_root"],
            "source_snapshot_sha256": snapshot, "html_file_count": expected_files,
            "logical_sha256": report["logical_sha256"], "run_id": run["run_id"],
        },
    )
    return report


def build(
    source: Path,
    output: Path,
    *,
    limit: int | None = None,
    write: bool = False,
    decisions: Path | None = None,
    preserve_source_evidence: bool = False,
) -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise ValueError(f"source directory not found: {source}")
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("source and output must be separate, non-nested directories")
    decision_path = decisions.resolve() if decisions else None
    decision_rows = read_review_decisions(decision_path)
    decision_results = apply_decision_deletions(source, decision_rows, write=write)
    website_paths, ordinal_decision_keys = decision_sets(decision_results)
    paths = html_files(source)
    if limit is not None:
        paths = paths[:limit]
    manifest, source_snapshot, latest = file_manifest(source, paths)
    decisions_sha256 = sha256_bytes(decision_path.read_bytes()) if decision_path else ""
    snapshot_input = f"{source_snapshot}\0{decisions_sha256}"
    if preserve_source_evidence:
        snapshot_input += "\0preserve_source_evidence"
    snapshot = sha256_bytes(snapshot_input.encode("utf-8"))
    run_id = f"{PARSER_NAME}-{PARSER_VERSION}-{snapshot[:16]}"
    dry_summary = {
        "status": "dry_run", "source": str(source), "output": str(output),
        "html_files": len(paths), "source_snapshot_sha256": snapshot,
        "source_files_sha256": source_snapshot, "decisions_sha256": decisions_sha256,
        "decision_rows": len(decision_results), "parser_version": PARSER_VERSION,
        "preserve_source_evidence": preserve_source_evidence,
        "decision_actions": dict(sorted(Counter(row["decision_action"] for row in decision_results).items())),
        "decision_statuses": dict(sorted(Counter(row["application_status"] for row in decision_results).items())),
    }
    if not write:
        return dry_summary
    output.mkdir(parents=True, exist_ok=True)
    current = existing_is_current(output, snapshot, len(paths))
    if current:
        return current
    resumed = resume_published_database(output, snapshot, len(paths))
    if resumed:
        return resumed

    database = output / "shs_metadata.sqlite"
    temporary_database = output / f".shs_metadata.{os.getpid()}.sqlite"
    if temporary_database.exists():
        temporary_database.unlink()
    connection = sqlite3.connect(temporary_database)
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
        except Exception as exc:  # retain a terminal record; never silently skip a source page
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
    excluded_recordings = (
        {"embedded_rows": 0, "source_files": 0}
        if preserve_source_evidence else purge_shs_output(connection)
    )
    retained_files = len(paths) - excluded_recordings["source_files"]
    connection.execute(
        "UPDATE parse_runs SET html_file_count=? WHERE run_id=?", (retained_files, run_id)
    )
    connection.execute(
        "INSERT INTO schema_metadata(key,value) VALUES('recording_exclusion_policy',?)",
        ("not_applied_source_evidence_inventory" if preserve_source_evidence else RECORDING_EXCLUSION_POLICY_VERSION,),
    )
    resolve_entities_and_links(connection, source, ordinal_decision_keys)
    create_views(connection)
    connection.commit()
    report = validate(connection, retained_files)
    report["excluded_recordings"] = excluded_recordings
    report["preserve_source_evidence"] = preserve_source_evidence
    report["source_snapshot_sha256"] = snapshot
    report["source_files_sha256"] = source_snapshot
    report["decisions_sha256"] = decisions_sha256
    report["decision_actions"] = dict(sorted(Counter(row["decision_action"] for row in decision_results).items()))
    report["decision_statuses"] = dict(sorted(Counter(row["application_status"] for row in decision_results).items()))
    report["run_id"] = run_id
    report["page_classes"] = dict(sorted(page_classes.items()))
    if not report["passed"]:
        connection.close()
        temporary_database.unlink(missing_ok=True)
        raise RuntimeError(f"validation failed: {json.dumps(report['checks'], sort_keys=True)}")
    connection.execute("VACUUM")
    connection.close()
    os.replace(temporary_database, database)

    published = sqlite3.connect(database)
    published.row_factory = sqlite3.Row
    csv_counts = export_csvs(published, output)
    dictionary_rows = export_dictionary(published, output)
    entity_json_files = export_entity_json(published, output)
    published.close()
    report["csv_rows"] = csv_counts
    report["metadata_dictionary_rows"] = dictionary_rows
    report["entity_json_files"] = entity_json_files
    report["status"] = "built"
    write_json(output / "validation" / "validation_results.json", report)
    state = {
        "parser_name": PARSER_NAME, "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION, "export_version": EXPORT_VERSION, "source_root": str(source),
        "source_snapshot_sha256": snapshot, "html_file_count": len(paths),
        "source_files_sha256": source_snapshot, "decisions_sha256": decisions_sha256,
        "preserve_source_evidence": preserve_source_evidence,
        "logical_sha256": report["logical_sha256"], "run_id": run_id,
    }
    write_json(output / "validation" / "build_manifest.json", state)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Read-only source tree; only .html files are parsed")
    parser.add_argument("--output", type=Path, required=True, help="Separate derived-output directory")
    parser.add_argument("--limit", type=int, help="Deterministic first-N sample for testing")
    parser.add_argument("--decisions", type=Path, help="Responded review-queue CSV whose explicit decisions should be applied")
    parser.add_argument("--write", action="store_true", help="Build/publish outputs; omit for a read-only dry run")
    parser.add_argument("--preserve-source-evidence", action="store_true", help="Retain every parsed HTML observation for an all-source evidence inventory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build(args.source, args.output, limit=args.limit, write=args.write, decisions=args.decisions, preserve_source_evidence=args.preserve_source_evidence)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
