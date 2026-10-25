# Jules Handoff: Unified parser for saved SHS webpages

## Request

The directory `SHSmetadataScrapingGuide` has already been uploaded to your Jules workspace. Use the uploaded directory as the working package and source of examples. Do not assume that the Windows path `E:\cyt3\SHSmetadataScrapingGuide` is mounted or accessible in your execution environment. If the uploaded directory appears under a different workspace path, locate it and use that copy. Do not ask for another upload.

Inspect the existing saved-page parsers, metadata dictionaries, guides, and HTML examples in that package. Build one reliable, deterministic, efficient Python CLI that analyzes saved SHS HTML offline, classifies each page, extracts metadata, and exports a comprehensive, well-designed CSV. Name the new program `shs_universal_page_parser.py`. Preserve existing package files and create new outputs alongside them in a clearly named subdirectory such as `output/`.

## Intake: inventory the uploaded package first

At handoff preparation, the uploaded directory contained 67 top-level `.html` files, a 20-row archetype mapping, a separate 26-row saved-page example list, an 85-row field dictionary, and a 139-row metadata matrix. Re-inventory the uploaded copy before implementation and report what is actually present; counts can differ if the package changed during upload. Process HTML captures as inputs, not `__pycache__`, generated output, scripts, or backups.

The package includes these relevant guides and CSVs:

- `SHS_WEBPAGE_PARSING_AND_PROCESSING_GUIDE.md`
- `SHS_parsing_guide.md`
- `SAVED_SHS_PAGE_PARSING_GUIDE.md`
- `shs_page_metadata_dictionary.csv` (85 data rows at handoff preparation)
- `SHS_metadata_inventory.csv`
- `SAVED_SHS_METADATA_MATRIX.csv` (139 data rows at handoff preparation)
- `shs_20_archetype_example_pages.csv` (20 example mappings)
- `SHS_example_pages_coverage.csv`
- `SAVED_SHS_EXAMPLE_PAGES.csv` (26 examples, including local filenames and SHS URLs)

Relevant parser and utility scripts present at handoff preparation:

- `extract_shs_html_metadata_archive.py` (older variant; its header describes adaptation/non-Latin exclusion policies)
- `extract_shs_html_metadata_archive_20261024.py` (newer repository copy)
- `shs_local_html_parser.py`
- `parse_shs_metadata.py`
- `shs_dates.py`
- `generate_dictionary_csv.py`
- `generate_shs_metadata_csv.py` (inspect its hard-coded paths before considering any use)
- `generate_20_archetypes_csv.py`
- `shs_marker_scan.py`
- `shs_survey.py`

Compare the two archive-extractor versions and inspect relevant code, CSV headers/rows, and representative HTML before selecting behavior. Do not assume a script header, dictionary, filename, or old output policy is correct simply because it exists. Treat the uploaded package as the immediate evidence base; the examples and field inventories are references, not proof that a field occurs on every page.

## Parsing and classification requirements

1. Parse saved HTML bytes locally. Do not make network requests, scrape live SHS, or use online pages to fill gaps.
2. Keep source files read-only. Record source-relative path, filename, byte size, SHA-256, detected encoding, parse status, and errors. Account for every eligible HTML file, including malformed, blocked, and unrecognized pages.
3. Classify the **page subject**, separately from entities mentioned within its content. Use this evidence order and retain the evidence used:
   - Valid SHS canonical/source URL and typed numeric entity route, such as `/artist/ID`, `/work/ID`, `/performance/ID`, or `/release/ID`.
   - Other SHS routes and explicit page markers, categorized as `other` with a useful subtype where supported, such as `web_cover`, `submission`, `edit_review`, `documentation`, `guideline`, `login`, `challenge`, or `technical`.
   - OpenGraph/schema metadata and page structure as corroborating evidence.
   - Visible heading and filename only as weaker fallback evidence.
4. Do not classify a work page as a performance page because it lists performances, or a release page as a performance page because it has track rows. A referenced SHS ID does not prove that its target page is present in the input collection.
5. Preserve unresolved or conflicting cases with an explicit status, evidence, and review reason. Never force a page into `artist`, `work`, `performance`, or `release` based on title similarity alone.
6. Treat `First release` and `First recording` as distinct source phrases and preserve their exact row, work/performance context, performer, date text, and date precision. A filename marker such as `1STREL` is a derived label, not proof of a canonical first-release fact. Do not infer cover/AARW/original status or harmonize original artists/releases across works.
7. Capture standard and uncommon evidence, including:
   - Document title, language, canonical and source URLs, and all head metadata.
   - Microdata, RDFa, JSON-LD/JSON scripts, and `data-*` attributes.
   - All definition-list labels/values, headings, paragraphs, and content blocks.
   - Table headings, headers, cells, row/column positions, dates, badges, and row context.
   - Links with href, text, title, rel, context, occurrence count, SHS target IDs, and resolution status.
   - Resources and provider IDs actually present in saved links or markup.
   - Parser warnings, conflicts, and review decisions when present.
8. Keep raw, display, normalized, and parsed forms separate. Unknown metadata names, labels, properties, and table headings must remain in the output as generic observations. Do not drop foreign-language, adaptation, non-Latin, or rare content by default; preserve it and add a sourced flag when appropriate.

## CSV design

Produce one primary, UTF-8-with-BOM CSV with a stable schema and RFC-compliant quoting. Use **one row per metadata observation** so repeated credits, links, table cells, and values remain separate and traceable. Add a page-level row for every input page so that pages with no extracted values and parse failures are still represented. Repeat page provenance and classification context on observation rows.

Include, at minimum:

- Run/parser version and source page provenance: relative path, filename, SHA-256, size, encoding, parse status/error.
- Page class, subtype, classification status/evidence, canonical/source URL, SHS entity type and ID, document title, and entity name.
- Record family, stable field name from the dictionary when mapped, original metadata key/label, ordinal, raw/display/normalized/parsed value.
- Section/table heading, table/row/column coordinates, link context, locator, and observation status.

Map the 85 dictionary fields where evidence supports a mapping, but keep the original source key and all unmapped observations. Do not use 85 hard-coded columns as a reason to discard repeated values or unknown metadata. If a spreadsheet-safe display value is needed, add a separate field; never alter the raw value. Document the row model and fields in a concise README.

## CLI, reliability, and performance

- Provide `--input-dir`, `--input-file`, `--output-csv`, and optional `--workers`, plus `--dry-run` or equivalent preflight.
- Support malformed HTML and common encodings, but retain decode/parse warnings instead of silently replacing evidence.
- Make output deterministic for identical inputs and parser version. Exclude output, backup, `__pycache__`, and browser asset directories from discovery.
- Use streaming or bounded-memory processing for thousands of files. Add multiprocessing only if measurement shows a benefit; preserve deterministic output ordering.
- Write to a temporary output and publish atomically after validation. Never overwrite source files or pre-existing package artifacts. Put reports and test outputs under a new output/test subdirectory.
- Validate input accounting, output row widths, source hashes, required locators, page-type evidence, and CSV readability. Log counts by page type, parse status, and observation family.
- Do not create or modify a live MusicDB registry, infer canonical assertions, or promote fuzzy/name-only matches.

## Tests and deliverables

Create focused regression tests from the uploaded examples for artist, work, performance, release, `other` subtypes, first-release/first-recording context, unusual metadata, missing fields, malformed HTML, encoding variation, duplicate observations, and unknown keys. Use the 20-row archetype map and 26-row example list as separate references; verify the mapped files actually exist before relying on either list. Run the focused tests and parse the uploaded HTML corpus in a separate output directory if runtime permits. Do not claim 100% classification accuracy unless every case has been checked against its saved-page evidence.

Deliver in the uploaded package:

1. `shs_universal_page_parser.py`
2. One primary comprehensive CSV generated from the uploaded HTML corpus, with a run manifest/report and clear source scope.
3. Concise usage/schema README.
4. Focused regression tests and their actual results.

Before editing, summarize the scripts and evidence you found, note any conflicts between extractor versions or dictionaries, and state the proposed CSV row model. Then implement and validate. In the final report, give output paths relative to the uploaded package, counts, checks actually run, unresolved pages/fields, and any dependencies needed to run the script. Do not assume `E:\cyt3\...` is accessible from Jules.
