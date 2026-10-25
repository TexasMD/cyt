# Saved SecondHandSongs webpage parsing and processing

This guide describes the repository's two distinct saved-page workflows: the **source-preserving metadata archive** and the **offline CYT page transform**. The companion [metadata matrix](SAVED_SHS_METADATA_MATRIX.csv) describes fields and page-type signals; the [26 saved-page examples](SAVED_SHS_EXAMPLE_PAGES.md) cover the observed semantic signal vocabulary in the validated 2026-10-21 archive. The matrix is a schema/recognition guide, not a claim that every field appears on every saved page. The archive's generated `metadata_dictionary.csv` is the observed-key inventory for a particular build.

## Scope and evidence boundary

- Inputs are locally saved SHS `.html` captures. The archive parser does not fetch live pages. Browser `*_files` assets and extensionless files are not HTML inputs.
- Keep source bytes and paths unchanged. The raw capture, its SHA-256, parser run/version, locator, and observed value are the evidence. Derived names, classifications, and normalized strings are separate.
- An SHS page can contain information about *other* entity types: a work page lists performances; a performance page can link a work, artist, and release. The page's type describes its **canonical subject**, not every entity mentioned in it.
- Archive observations and CYT metadata are not canonical MusicDB facts. SHS IDs are provider-scoped. A linked ID is evidence of a reference, not proof that the target page was captured; a name or fuzzy match never establishes identity or a promotion.
- The field vocabulary is open. Unknown `<meta>` names, semantic properties, definition labels, table headings, links, and structured JSON are preserved as generic evidence instead of being silently discarded.

## Which script does what?

| Task | Entry point | Main result |
| --- | --- | --- |
| Archive all extractable evidence | `scripts/extract_shs_html_metadata_archive.py` | `shs_metadata.sqlite`, CSV views, entity JSON, dictionary, validation |
| Export every archive observation without flattening repeats | `scripts/export_shs_html_all_metadata_csv.py` | entity index, observation CSV with typed `payload_json`, linked/captured index |
| Plan names and identify first-release page candidates | `scripts/rename_shs_html_archive.py` | page plan and collision/duplicate review |
| Add searchable `cyt:*` head fields and clean an offline copy | `scripts/process_saved_shs_pages.py` | cleaned HTML plus raw-page catalog and audits |
| Stage, rename, localize, process, and validate a package | `scripts/transform_saved_shs_archive.py` | separate CYT HTML package and checklist |
| Audit cleanup retention without renaming | `scripts/clean_shs_html_with_retention_audit.py` | cleaned copy and retention/idempotence audit |
| Localize and audit entity references | `scripts/localize_shs_entity_links.py`, `scripts/build_shs_entity_reference_set.py`, `scripts/rebuild_shs_exact_id_reference_map.py` | occurrence-level local/external/review decisions |

The archive and offline transform have different purposes. The archive retains technical and source context for analysis. The offline transform intentionally removes live-site code and much presentation markup. Parse the raw page **before** cleanup when building the evidence archive or raw-page catalog.

## Page recognition: subject before details

The archive parser inspects `<link rel="canonical">`, then `cyt:source-webpage-url`, `source-webpage-url`, and `og:url` candidates. A valid SHS URL with a numeric `/artist/ID`, `/work/ID`, `/performance/ID`, or `/release/ID` path yields a typed `entity_key` such as `work/296150`. The ID and type, not the browser filename, are the strongest subject signal. A page title, `<h1>`, `itemprop="name"`, `itemtype`, and the visible sections corroborate or qualify it. The archive records conflicting names for review.

| Subject class | Strong signal | Supporting traits | Important distinction |
| --- | --- | --- | --- |
| Artist | Canonical `/artist/<numeric ID>` | Artist heading; `Person`/`MusicGroup` style microdata; Born, Died, Country, Members, aliases, IPI, related artists | Work/performance tables here describe the artist's associated entities, not the artist's own type. |
| Work | Canonical `/work/<numeric ID>` | Work title, authors, language, ISWC, publisher, composition/copyright dates; versions table and related-work sections | A work is the composition. Performance rows and release references do not turn the page into a performance or release. |
| Performance | Canonical `/performance/<numeric ID>` | Performing artist, work/recording links, date, duration, `recordedAs`/`recordingOf`, `inAlbum`, streaming links | SHS performance identity is separate from MusicDB recording identity. A recording claim needs its own evidence/review. |
| Release | Canonical `/release/<numeric ID>` | Release title, release date, label, catalog number, format, EAN, track listing | A release groups/embodies performances; title overlap does not merge the identities. |
| Other | No recognized canonical entity path | Main content, guidelines, documentation, login form, Cloudflare challenge, or technical page | Keep the captured page and `page_class`; do not force it into a musical entity. |

The archive's fallback `page_class` values include `guideline`, `documentation`, `login`, `cloudflare_error`, `other_content`, and `technical_or_unrecognized`; a reviewed website decision can yield `other`/`website`. Missing identity on a content page produces a review issue. The rename planner has additional **filename-only** fallbacks (for example, “Cover versions of ...”) and a `CYT-other-...` name. Those fallbacks are not equivalent to a canonical SHS ID.

### First release, first recording, and relationship labels

`1STREL` is an offline CYT *performance-page designation*, not a fifth SHS entity path. The renamer finds `First release` or `First recording` in the versions table scoped to the canonical work/performance. For a work it starts at `p#work-<work ID>` and stops at the next versions header; for a performance it seeks the row linked to that exact performance ID (with a confined legacy fallback). It takes the performer and date from that row. A related adaptation's first release must not leak into the subject work. The planner marks a performance page `CYT-1STREL-...` only when its performer is consistent with that first-event row. The `cyt:page-type` becomes `1STREL`; ordinary pages remain `performance`. Older `ATRA` labels may be read during migration.

SHS `First recording` and `First release` are distinct source phrases, although the current renamer accepts either phrase for its `1STREL` file designation. That designation therefore must not be interpreted as a reviewed MusicDB first-release assertion. MusicDB's accepted `first_release` definition additionally needs an official public release and a dated release relationship; adaptations cannot be first releases under that definition. Preserve the exact SHS phrase, row, date precision, work/performance IDs, and any later review decision.

Other role/relationship evidence includes `Originally by`, `Covers by`, `Adapted from`, `Uses parts from`, `Uses samples from`, `recordedAs`, `recordingOf`, versions-table `Info`, and native first-performance/first-recording markers. These are **typed, directional observations**. Keep the source work and target work/performance IDs, section/table context, and text; do not infer a cover, adaptation, sample, or original solely from a title, performer string, ranking, or proximity to an unrelated row. A performance linked only from a work table is a referenced performance, not a captured performance page.

## Source-preserving archive procedure

1. Inventory the actual source tree. Confirm the HTML count and any new captures, including duplicate bytes under different names. Avoid indexing browser resource directories or old processed/audit copies as active source pages.
2. Run the archive command **without** `--write` to obtain the file count and source snapshot fingerprint:

   ```powershell
   python scripts\extract_shs_html_metadata_archive.py --source "E:\CYT\sources\original\SHS" --output "E:\CYT\sources\derived\SHS"
   ```

3. Build only into a separate output tree. The script hashes source files, records the parser version and decision file in its run identity, creates a temporary SQLite database, and publishes it after validation:

   ```powershell
   python scripts\extract_shs_html_metadata_archive.py --source "E:\CYT\sources\original\SHS" --output "E:\CYT\sources\derived\SHS" --write
   ```

4. For each file, Beautiful Soup/lxml detects encoding and extracts: title/language and all head meta/link attributes; JSON-LD and JSON scripts; semantic microdata/RDFa and `data-*` attributes; `main`/`section#main` `dt`/`dd` pairs, headings/text blocks, full table structure and cells; every anchor with context and occurrence count; resources; provider identifiers found in saved URLs; and source locators. Values are stored as raw, display, normalized, and parsed forms where supported. Date/year table columns receive parsed sort value, precision, and status without replacing their display text.
5. The archive groups multiple captures by exact `entity_key`, retains each source capture, and records name conflicts. It classifies links as exact local entity/file, unique local basename, same-document fragment, external SHS entity/nonentity, ambiguous basename, unresolved relative, or other external. A local-link resolution is not an assertion of musical equivalence.
6. Inspect `validation/validation_results.json`: `passed`, file/accounting counts, integrity and foreign-key checks, locators, link statuses, entity scope, and decision accounting. Inspect `csv/review_queue.csv` for parse failures, missing titles, unrecognized identity, Cloudflare captures, and conflicting names. A progress line or PID is not proof of a completed build.
7. Use `metadata_dictionary.csv` for exact observed tokens and counts. Use `csv/metadata_observations.csv`, `csv/details.csv`, `csv/table_cells.csv`, `csv/links_and_references.csv`, `csv/provider_identifiers.csv`, and `json/entities/` to trace any value. The dictionary includes dynamic keys; `cyt:source-reference:*` should be treated as a family in a conceptual matrix rather than one schema column per reference.

The parser can apply an explicit review-decision CSV, but decisions that remove source HTML change the input set. Review the exact paths and decision application before using that mode. `--preserve-source-evidence` changes the recording-exclusion behavior; document that choice when comparing builds. A repeat build with the same source snapshot, decisions, parser, and export version may return `already_current`.

### What the archive stores

`source_files` and `parse_runs` establish lineage. `entities` is a typed SHS-ID index, while `entity_captures` retains each capture. `page_metadata`, `microdata`, `structured_data`, `detail_entries`, `content_blocks`, `html_tables`/`table_cells`, `links`, `resources`, and `provider_identifiers` retain the observed fields. `review_issues` and `review_decisions` preserve exceptions and responses. The all-metadata exporter writes an observation row per typed record with its complete SQLite row in `payload_json`; it avoids collapsing repeated values into one spreadsheet cell. `shs_all_linked_and_captured_entities.csv` explicitly distinguishes a captured entity page from an ID seen only in a link.

## Offline CYT processing procedure

`docs/SHS_PROCESS.md` is the detailed operational specification. The normal transform stages copies from a source directory, plans `CYT-artist`, `CYT-work`, `CYT-performance`, `CYT-release`, `CYT-1STREL`, or `CYT-other` filenames, checks duplicate/collision evidence, rewrites exact known entity links, adds the `html-derived-v4` `cyt:*` head block, writes `shs_page_catalog.csv` from the raw page, cleans markup, installs approved local CSS, and validates the package. Run the wrapper without `--write` first; it is a plan/audit. `--write` processes a separate output directory. Backups and audits stay beside the package. An empty HTML set cannot complete the checklist.

The head block is a compact **search index**, not a replacement for the archive. It may contain page type and filename; artist, born/country, work, author, year, first-release performer, performing artist, release; SHS type/ID and original URL; IDs found in Spotify, YouTube, MusicBrainz, or WhoSampled links; and tags. Fields with no evidence can be blank; provider IDs are emitted only when their links are present. The current marker plus required fields gives an idempotent no-op. Older/incomplete blocks are refreshed from page evidence, before cleanup destroys context.

Cleanup keeps visible musical text, relevant tables, semantic attributes, structured JSON, material references, and useful streaming destinations. It removes live scripts, tracking/ads, overlays, embedded players, imagery and unsupported navigation. Entity links can be made local only through exact unique targets; missing or ambiguous targets remain external/review. A second pass should report `modified_files: 0`. For a cleanup-only copy, the retention-audit script compares definition entries, textual table cells, and structured JSON before and after, then supports `--verify-only` idempotence checking.

## Reading the metadata matrix

Each CSV row names a **field or signal**, its source locator, and its applicability to artist, work, performance, release, and other pages. Codes: `S` = describes the page's subject; `R` = may describe a linked/embedded entity on that page; `G` = generic capture/page metadata; `-` = no supported expectation. These are potential locations supported by the parser and observed SHS structure, **not per-class occurrence counts or guaranteed populated fields**. A field may appear on additional pages through generic markup; the raw archive remains authoritative. “Other” includes nonentity pages and exceptional captures, not a single musical entity type.

For new or changed SHS layouts, add raw fixtures, keep parser version and regression expectations together, compare the extracted values and locators, and leave prior observations intact as their own parser run. No parsing or cleanup step authorizes bulk registry ingestion or automatic promotion.

## Source pointers

- `scripts/extract_shs_html_metadata_archive.py`: classification, schema, extraction, link resolution, dictionary, validation.
- `scripts/rename_shs_html_archive.py`: naming and scoped first-event detection.
- `scripts/process_saved_shs_pages.py` and `docs/SHS_PROCESS.md`: `cyt:*` derivation, catalog, cleanup, transform invariants.
- `scripts/export_shs_html_all_metadata_csv.py`: lossless observation export.
- `tests/test_extract_shs_html_metadata_archive.py`, `tests/test_process_saved_shs_pages.py`, `tests/test_transform_saved_shs_archive.py`: representative behavior and regressions.
- `docs/registry/CLASSIFICATION_DEFINITIONS.md`, `docs/registry/SOURCE_AUTHORITY.md`, and `docs/registry/PROMOTION_RULES.md`: MusicDB interpretation and promotion boundary.
