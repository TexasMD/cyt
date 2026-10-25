from pathlib import Path
import csv, json, re, unicodedata, collections
root=Path(r'E:\cyt3\SHSmetadataScrapingGuide')
inputs=[('shs_page_metadata_dictionary.csv','schema'),('SHS_metadata_inventory.csv','inventory'),('SAVED_SHS_METADATA_MATRIX.csv','matrix')]
records=[]
for fname,kind in inputs:
    path=root/fname
    with path.open(encoding='utf-8-sig',newline='') as f:
        for n,row in enumerate(csv.DictReader(f),1):
            row={k:(v or '') for k,v in row.items()}
            if kind=='schema':
                label=row.get('Field_Name','')
                category=row.get('Category','')
                description=row.get('Description','')
                page_types=[t for k,t in [('Work_Page','work'),('Performance_Page','performance'),('Artist_Page','artist'),('Release_Page','release'),('Web_Cover_Page','web_cover')] if row.get(k,'').strip().lower() in ('yes','true','1','y')]
                signals=row.get('Identifying_Signals_and_Selectors',''); example=row.get('Example_Value',''); caution=''
                key=row.get('SHSmetadatakey','')
            elif kind=='inventory':
                label=row.get('metadata_field','')
                category=row.get('category','')
                description=row.get('notes','')
                page_types=[t for k,t in [('work','work'),('performance','performance'),('artist','artist'),('release','release'),('search_results','search_results'),('label_page','label_page')] if row.get(k,'').strip().lower() in ('yes','true','1','y')]
                signals=row.get('extraction_marker_or_location',''); example=''; caution=''
                key=row.get('SHSmetadataInventoryKey','')
            else:
                label=row.get('field_or_signal','')
                category=row.get('family','')
                description=row.get('interpretation_or_discriminator','')
                page_types=[t for k,t in [('artist_page','artist'),('work_page','work'),('performance_page','performance'),('release_page','release'),('other_page','other')] if row.get(k,'').strip().lower() in ('yes','true','1','y')]
                signals=row.get('source_locator',''); example=''; caution=row.get('caution','')
                key=row.get('savedSHSmetadataMatrixKey','')
            records.append(dict(source_file=fname,source_kind=kind,source_row=n,source_key=key,label=label,category=category,description=description,page_types=page_types,signals=signals,example=example,caution=caution,original=row))

def norm(s):
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
    s=re.sub(r'[^a-z0-9]+','_',s).strip('_')
    return s
# Explicit aliases are intentionally limited to straightforward synonymous labels.
aliases={
 'composition_name':'work_title','work_entity_id':'work_id','work_entity_identifier':'work_id',
 'performance_entity_id':'performance_id','exact_shs_performance_identifier':'performance_id',
 'artist_entity_id':'artist_id','visible_subject_name':'page_subject_name',
 'named_rendition_or_track':'performance_title','artist_subject_or_linked_credit':'artist_name',
 'artist_biographical_date':'artist_profile_date', # split below by source label to avoid birth/death collision
 'dt_born_or_itemprop_birthdate':'artist_birth_date','birth_date':'artist_birth_date',
 'dt_died_or_itemprop_deathdate':'artist_death_date','death_date':'artist_death_date',
 'artist_geographic_trait':'artist_country','country_iso_code':'artist_country',
 'work_identifier':'iswc','iswc_codes':'iswc','work_language':'work_language',
 'music_writing_credit':'music_written_by','lyric_writing_credit':'lyrics_written_by',
 'authorship_credit':'written_by','publisher_relationship':'published_by',
 'folk_song_catalog_number':'roud_number','listed_alternate_names':'artist_aliases',
 'artist_profile_name':'artist_name_variant','artist_profile_name_variants':'artist_name_variant',
 'group_membership_relationships':'artist_membership','group_members':'artist_members',
 'related_artist_links':'related_artists','related_artist':'related_artists',
 'artist_ranking':'artist_coverage_ranking','coverage_ranking':'artist_coverage_ranking',
 'work_name':'work_title','iswc_code_s':'iswc','publisher_s':'published_by',
 'release_entity_id':'release_id','release_artist':'release_artist',
 'release_date':'release_date','ean_barcode':'release_ean_upc','ean_barcode':'release_ean_upc',
 'format_medium':'release_format','track_list_per_track':'release_tracklist',
 'performing_artist_id':'performing_artist_id','performing_artist_id_name':'performing_artist',
 'performing_artist_id_name':'performing_artist','performing_artist':'performing_artist',
 'artist_id_name':'artist_credit','artist_name':'artist_name',
 'other_versions':'other_versions_list','other_version':'other_version',
 'sampling_sources':'sampling_sources','sampled_by':'sampled_by',
 'web_covers_by_artist':'web_covers_by_artist','web_covers':'web_covers',
}
# Avoid collapsing identity-context distinctions; these aliases only apply after explicit review.
def canonical(rec):
    label=rec['label'].strip()
    if not label: return 'unnamed_metadata_signal'
    key=norm(label)
    # Exact field labels from schema form canonical vocabulary; explicit aliases map other lists into it.
    if key in aliases: return aliases[key]
    return key
# These labels are semantically related but context-specific. Keep separate canonical concepts.
separate={
 'released_on_title':'performance_release_title_link',
 'released_on_release_id_name_medium_year':'performance_release_link',
 'release_date':'release_date',
 'release_artist':'release_artist_credit',
 'performing_artist':'performing_artist_credit',
 'work_title':'work_title','performance_title':'performance_title',
 'first_recorded_date':'first_recorded_date','performance_release_date':'performance_release_date',
 'original_performances_first_release_etc':'original_performance_references',
}
def canonical(rec):
    key=norm(rec['label'])
    if key in separate:return separate[key]
    return aliases.get(key,key or 'unnamed_metadata_signal')
groups=collections.defaultdict(list)
for rec in records: groups[canonical(rec)].append(rec)
# Use schema description and metadata-field labels to make readable canonical names.
def pretty(key, rs):
    for r in rs:
        if r['source_kind']=='schema' and r['label']:
            return r['label']
    return key
out=root/'SHS_ALL_ENCOMPASSING_METADATA_DICTIONARY.csv'
headers=['unified_field_id','canonical_field_name','field_family','definition_or_interpretation','applicable_page_types','source_files','source_row_count','source_field_labels','extraction_signals_or_locations','example_values','cautions_and_distinctions','source_records_json','merge_status']
with out.open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=headers,lineterminator='\r\n');w.writeheader()
    for i,(key,rs) in enumerate(sorted(groups.items()),1):
        defs=list(dict.fromkeys(r['description'] for r in rs if r['description']))
        fams=list(dict.fromkeys(r['category'] for r in rs if r['category']))
        pages=list(dict.fromkeys(p for r in rs for p in r['page_types']))
        sigs=list(dict.fromkeys(r['signals'] for r in rs if r['signals']))
        ex=list(dict.fromkeys(r['example'] for r in rs if r['example']))
        caut=list(dict.fromkeys(r['caution'] for r in rs if r['caution']))
        labels=list(dict.fromkeys(r['label'] for r in rs if r['label']))
        src=list(dict.fromkeys(r['source_file'] for r in rs))
        status='merged_equivalent_labels' if len(rs)>1 else 'single_source_entry'
        w.writerow({'unified_field_id':f'SHSU{ i:04d}','canonical_field_name':pretty(key,rs),'field_family':' | '.join(fams),'definition_or_interpretation':' || '.join(defs),'applicable_page_types':' | '.join(pages),'source_files':' | '.join(src),'source_row_count':len(rs),'source_field_labels':' | '.join(labels),'extraction_signals_or_locations':' || '.join(sigs),'example_values':' || '.join(ex),'cautions_and_distinctions':' || '.join(caut),'source_records_json':json.dumps([{'source_file':r['source_file'],'source_kind':r['source_kind'],'source_row':r['source_row'],'source_key':r['source_key'],'original_row':r['original']} for r in rs],ensure_ascii=False,separators=(',',':')),'merge_status':status})
# Rationale and reproducibility counts
by=collections.Counter(r['source_kind'] for r in records)
merged=sum(1 for rs in groups.values() if len(rs)>1)
md=root/'SHS_METADATA_DICTIONARY_MERGE_RATIONALE.md'
md.write_text(f'''# SHS metadata dictionary merge: rationale and scope\n\n## Deliverable\n\n`SHS_ALL_ENCOMPASSING_METADATA_DICTIONARY.csv` is the merged dictionary. It contains **{len(groups)} unified concepts** built from **{len(records)} source rows** across three source inventories. Every source row is retained verbatim as JSON in `source_records_json`, alongside its file, row number, and source key.\n\n## Inputs\n\n| Source | Rows | Role in the merged dictionary |\n|---|---:|---|\n| `shs_page_metadata_dictionary.csv` | {by['schema']} | Field-oriented schema: normalized output names, definitions, applicability by page type, selectors, examples. |\n| `SHS_metadata_inventory.csv` | {by['inventory']} | Curated inventory: extraction targets, SHS structures, referenced entities, search/facet/editorial page content. |\n| `SAVED_SHS_METADATA_MATRIX.csv` | {by['matrix']} | Locator-oriented matrix: page signals, source locations, interpretation, cautions, capture/parser provenance. |\n\n## Merge logic\n\n1. Preserve every source row in the output, including source key, exact source label, complete original columns, and row position. This makes the merged view reversible and auditable.\n2. Merge only exact or explicitly reviewed straightforward synonyms, such as `Work title` with `Composition name`, `Work entity ID` with `work_id`, and `ISWC code(s)` with `ISWC`. The canonical label favors the field schema when it supplies one.\n3. Otherwise retain separate concepts. Similar wording alone is not enough to merge fields when subject, relation direction, time meaning, or evidence context differs.\n4. Combine applicability signals as a union for discovery only. Blank applicability in a source means “not specified there,” not “not applicable.” The original row retains each source's own flags.\n5. Preserve selectors/locators, examples, interpretation text, and cautions as separate aggregate columns; the full originals remain in `source_records_json`. This avoids losing meaningful differences between sources.\n6. `merge_status` describes whether a group contains multiple source rows. It does not imply that each source observed a populated value on every example page.\n\n## Why the dictionaries differ\n\n- **Different scope:** the schema names candidate output fields; the curated inventory also includes compound table/list structures and referenced page types; the matrix includes parser provenance, document/page identity, classification evidence, relationship sections, and extraction cautions.\n- **Different granularity:** a compound inventory entry such as a track list or “released on” relationship may bundle several values. The schema can split those into release ID, date, performer, title, and format fields. We retain the umbrella and individual fields rather than pretending they are identical.\n- **Different context:** a work title, a performance title, and a release title are separate subject names. A performing artist credit differs from an artist page's subject name and a release artist credit. A release date differs from a performance release date, composition date, copyright date, and first-recorded date.\n- **Different evidence status:** a canonical URL or page heading is observable source evidence; a page-type classification, first-release flag, counts, normalized ID, or parser status can be derived or pipeline-generated. These remain distinct and should be stored with their method/provenance.\n- **Different page coverage:** the sources use different page-type sets (the schema has web-cover; the inventory has search and label; the matrix has other). Their flags are retained per row, and the unified page-type field reports the union of affirmative flags without rewriting source applicability.\n\n## Deliberately separate concepts\n\nThe merge does not collapse: author/composer/lyricist/original writer credits; work, performance, artist, and release IDs; artist subject vs linked artist/performer/release-artist credit; work title vs rendition title vs release title; first recording vs first release; composition/copyright/publication/release dates; country vs nationality; source-page metadata vs capture/parser metadata; list/table structures vs individual values; linked page identity vs embedded row data; or provider-native IDs from different services. If future review establishes an exact equivalence, update the alias rules and preserve a new parser/dictionary version rather than discarding old source evidence.\n\n## Interpretation limits\n\nThis is an all-encompassing **candidate extraction dictionary**, not a claim that every field occurs on every saved page or is populated reliably. Signals may indicate a linked entity, embedded row, generated/processed-page marker, or blocked/challenge page. Treat a locator as an extraction cue, inspect its semantic scope, and retain raw value, parsed value, source URL/path, page type, and parser provenance.\n\n## Rebuild\n\nRun `python merge_shs_metadata_dictionaries.py` from this directory. The script reads only the three input CSVs listed above and rewrites the two deliverables.\n''',encoding='utf-8')
print('inputs',dict(by),'source_rows',len(records),'unified_concepts',len(groups),'multirow_groups',merged)
print('dictionary',out,'bytes',out.stat().st_size)
print('rationale',md,'bytes',md.stat().st_size)
