# SHS metadata dictionary merge: rationale and scope

## Deliverable

`SHS_ALL_ENCOMPASSING_METADATA_DICTIONARY.csv` is the merged dictionary. It contains **269 unified concepts** built from **311 source rows** across three source inventories. Every source row is retained verbatim as JSON in `source_records_json`, alongside its file, row number, and source key.

## Inputs

| Source | Rows | Role in the merged dictionary |
|---|---:|---|
| `shs_page_metadata_dictionary.csv` | 85 | Field-oriented schema: normalized output names, definitions, applicability by page type, selectors, examples. |
| `SHS_metadata_inventory.csv` | 87 | Curated inventory: extraction targets, SHS structures, referenced entities, search/facet/editorial page content. |
| `SAVED_SHS_METADATA_MATRIX.csv` | 139 | Locator-oriented matrix: page signals, source locations, interpretation, cautions, capture/parser provenance. |

## Merge logic

1. Preserve every source row in the output, including source key, exact source label, complete original columns, and row position. This makes the merged view reversible and auditable.
2. Merge only exact or explicitly reviewed straightforward synonyms, such as `Work title` with `Composition name`, `Work entity ID` with `work_id`, and `ISWC code(s)` with `ISWC`. The canonical label favors the field schema when it supplies one.
3. Otherwise retain separate concepts. Similar wording alone is not enough to merge fields when subject, relation direction, time meaning, or evidence context differs.
4. Combine applicability signals as a union for discovery only. Blank applicability in a source means “not specified there,” not “not applicable.” The original row retains each source's own flags.
5. Preserve selectors/locators, examples, interpretation text, and cautions as separate aggregate columns; the full originals remain in `source_records_json`. This avoids losing meaningful differences between sources.
6. `merge_status` describes whether a group contains multiple source rows. It does not imply that each source observed a populated value on every example page.

## Why the dictionaries differ

- **Different scope:** the schema names candidate output fields; the curated inventory also includes compound table/list structures and referenced page types; the matrix includes parser provenance, document/page identity, classification evidence, relationship sections, and extraction cautions.
- **Different granularity:** a compound inventory entry such as a track list or “released on” relationship may bundle several values. The schema can split those into release ID, date, performer, title, and format fields. We retain the umbrella and individual fields rather than pretending they are identical.
- **Different context:** a work title, a performance title, and a release title are separate subject names. A performing artist credit differs from an artist page's subject name and a release artist credit. A release date differs from a performance release date, composition date, copyright date, and first-recorded date.
- **Different evidence status:** a canonical URL or page heading is observable source evidence; a page-type classification, first-release flag, counts, normalized ID, or parser status can be derived or pipeline-generated. These remain distinct and should be stored with their method/provenance.
- **Different page coverage:** the sources use different page-type sets (the schema has web-cover; the inventory has search and label; the matrix has other). Their flags are retained per row, and the unified page-type field reports the union of affirmative flags without rewriting source applicability.

## Deliberately separate concepts

The merge does not collapse: author/composer/lyricist/original writer credits; work, performance, artist, and release IDs; artist subject vs linked artist/performer/release-artist credit; work title vs rendition title vs release title; first recording vs first release; composition/copyright/publication/release dates; country vs nationality; source-page metadata vs capture/parser metadata; list/table structures vs individual values; linked page identity vs embedded row data; or provider-native IDs from different services. If future review establishes an exact equivalence, update the alias rules and preserve a new parser/dictionary version rather than discarding old source evidence.

## Interpretation limits

This is an all-encompassing **candidate extraction dictionary**, not a claim that every field occurs on every saved page or is populated reliably. Signals may indicate a linked entity, embedded row, generated/processed-page marker, or blocked/challenge page. Treat a locator as an extraction cue, inspect its semantic scope, and retain raw value, parsed value, source URL/path, page type, and parser provenance.

## Rebuild

Run `python merge_shs_metadata_dictionaries.py` from this directory. The script reads only the three input CSVs listed above and rewrites the two deliverables.
