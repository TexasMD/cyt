import csv
from pathlib import Path

pages_data = [
    {
        "index": 1,
        "page_type": "Work",
        "entity_name": "Wicked Game",
        "entity_id": 1051,
        "shs_canonical_url": "https://secondhandsongs.com/work/1051/all",
        "example_file_in_archive": "02_wicked_game.html",
        "primary_focus_archetype": "Standard Musical Work with Full Cover Registry",
        "key_metadata_fields_demonstrated": "work_title, work_id, written_by, work_language, iswc, published_by, licensing_status, total_covers_count, total_samples_count, table_cells_count, badge-original [1st] marker",
        "special_signals_and_traits": "Comprehensive unpaginated covers table (/all view); PRO publishing splits (ASCAP, BMI, GEMA); canonical earliest original marker; high metadata density.",
        "external_identifiers_present": "ISWC (T-070.205.906-0), YouTube Video IDs in covers table"
    },
    {
        "index": 2,
        "page_type": "Work",
        "entity_name": "Down in the Valley to Pray",
        "entity_id": 100868,
        "shs_canonical_url": "https://secondhandsongs.com/work/100868/all",
        "example_file_in_archive": "SHS_AUTO_Down_To_The_River_To_Pray_Alison_Krauss.html",
        "primary_focus_archetype": "Traditional / Folk Song with Roud Number",
        "key_metadata_fields_demonstrated": "work_title, work_id, roud_number, written_by (Traditional / Public Domain), work_language, total_covers_count",
        "special_signals_and_traits": "Presence of rare 'Roud number' folk song index tag (#18833); absence of commercial PRO publishing rows; traditional public domain authorship handling.",
        "external_identifiers_present": "Roud Folk Song Index #18833"
    },
    {
        "index": 3,
        "page_type": "Work",
        "entity_name": "Take on Me",
        "entity_id": 26,
        "shs_canonical_url": "https://secondhandsongs.com/work/26/all",
        "example_file_in_archive": "06_take_on_me.html",
        "primary_focus_archetype": "Multilingual Translation & Derivative Adaptation",
        "key_metadata_fields_demonstrated": "work_title, work_id, written_by, adapted_from, total_adaptations_count, work_language, published_by",
        "special_signals_and_traits": "'Adapted from' link back to parent composition; dedicated 'Adaptations' navigation tab with translated lyric versions (German, French, Spanish, Finnish).",
        "external_identifiers_present": "ISWC, Outbound links to localized translated work IDs"
    },
    {
        "index": 4,
        "page_type": "Work",
        "entity_name": "Crazy",
        "entity_id": 63296,
        "shs_canonical_url": "https://secondhandsongs.com/work/63296/all",
        "example_file_in_archive": "03_crazy.html",
        "primary_focus_archetype": "Work with Quotation & Sampling (Uses Parts From)",
        "key_metadata_fields_demonstrated": "work_title, work_id, written_by, uses_parts_from, original_music_written_by, total_samples_count, published_by",
        "special_signals_and_traits": "Explicit 'Uses parts from' quotation tag pointing to Gian Piero Reverberi's 'Last Man Standing'; separate attribution for 'Original music written by'.",
        "external_identifiers_present": "ISWC, Parent work SHS IDs"
    },
    {
        "index": 5,
        "page_type": "Work",
        "entity_name": "Bitter Sweet Symphony",
        "entity_id": 10471,
        "shs_canonical_url": "https://secondhandsongs.com/work/10471/all",
        "example_file_in_archive": "129_bittersweet_symphony.html",
        "primary_focus_archetype": "Work with Direct Interpolation (Original Lyrics Written By)",
        "key_metadata_fields_demonstrated": "work_title, work_id, written_by, original_lyrics_written_by, uses_parts_from, iswc, published_by",
        "special_signals_and_traits": "Split legal songwriting credits resulting from copyright settlement (Mick Jagger & Keith Richards alongside Richard Ashcroft); 'Original lyrics written by' metadata entry.",
        "external_identifiers_present": "ISWC, Multiple PRO affiliation tags (ABKCO, BMI)"
    },
    {
        "index": 6,
        "page_type": "Work",
        "entity_name": "Titanium",
        "entity_id": 134347,
        "shs_canonical_url": "https://secondhandsongs.com/work/134347/all",
        "example_file_in_archive": "089_titanium.html",
        "primary_focus_archetype": "Work with Split Composer and Lyricist Roles",
        "key_metadata_fields_demonstrated": "work_title, work_id, music_written_by, lyrics_written_by, published_by, work_language, total_covers_count",
        "special_signals_and_traits": "Definitive separation between musical composition ('Music written by': David Guetta, Giorgio Tuinfort, Afrojack) and lyricist ('Lyrics written by': Sia).",
        "external_identifiers_present": "ISWC, Multiple PRO publisher tags (SACEM, BMI)"
    },
    {
        "index": 7,
        "page_type": "Work",
        "entity_name": "Creep",
        "entity_id": 8673,
        "shs_canonical_url": "https://secondhandsongs.com/work/8673/all",
        "example_file_in_archive": "04_creep.html",
        "primary_focus_archetype": "Multi-Author Work with Intermediate Derivative Credits",
        "key_metadata_fields_demonstrated": "work_title, work_id, written_by, originally_written_by, uses_parts_from, licensing_status, total_covers_count",
        "special_signals_and_traits": "Retroactively attributed songwriting field 'Originally written by' referencing Albert Hammond and Mike Hazlewood (composers of 'The Air That I Breathe').",
        "external_identifiers_present": "ISWC, Multi-party PRO publisher administration codes"
    },
    {
        "index": 8,
        "page_type": "Work",
        "entity_name": "Torn",
        "entity_id": 1419,
        "shs_canonical_url": "https://secondhandsongs.com/work/1419/all",
        "example_file_in_archive": "61_torn.html",
        "primary_focus_archetype": "Work with Historical Composition Date",
        "key_metadata_fields_demonstrated": "work_title, work_id, written_by, composition_date, work_language, total_covers_count, total_adaptations_count",
        "special_signals_and_traits": "Explicit 'Composition date' field (1991), showing historical creation prior to first commercial release (1993 in Danish as 'Brændt', 1997 by Natalie Imbruglia).",
        "external_identifiers_present": "ISWC, Cross-language performance links"
    },
    {
        "index": 9,
        "page_type": "Work",
        "entity_name": "(There's) Always Something There to Remind Me",
        "entity_id": 1447,
        "shs_canonical_url": "https://secondhandsongs.com/work/1447/all",
        "example_file_in_archive": "Original versions of (There's) Always Something There to Remind Me written by Burt Bacharach, Hal David _ SecondHandSongs.html",
        "primary_focus_archetype": "Work with Legal Copyright Registration & Multiple PROs",
        "key_metadata_fields_demonstrated": "work_title, work_id, written_by, copyright_date, published_by, iswc, work_language, total_covers_count",
        "special_signals_and_traits": "'Copyright date' entry documenting official Library of Congress registration; dual-PRO administrative split between ASCAP and BMI publishers.",
        "external_identifiers_present": "ISWC, ASCAP work registration, BMI work code"
    },
    {
        "index": 10,
        "page_type": "Work",
        "entity_name": "Another Brick in the Wall Part 3",
        "entity_id": 120816,
        "shs_canonical_url": "https://secondhandsongs.com/work/120816/all",
        "example_file_in_archive": "Original versions of Another Brick in the Wall Part 3 written by Roger Waters _ SecondHandSongs.html",
        "primary_focus_archetype": "Multi-Part Composition Suite (Part Of)",
        "key_metadata_fields_demonstrated": "work_title, work_id, written_by, part_of, iswc, published_by, total_covers_count",
        "special_signals_and_traits": "'Part of' structural hierarchical link anchoring movement to parent concept cycle ('Another Brick in the Wall' suite on 'The Wall').",
        "external_identifiers_present": "ISWC, Parent suite SHS Work ID link"
    },
    {
        "index": 11,
        "page_type": "Performance",
        "entity_name": "Every Breath You Take",
        "entity_id": 656,
        "shs_canonical_url": "https://secondhandsongs.com/performance/656/all",
        "example_file_in_archive": "01_every_breath_you_take__perf656.html",
        "primary_focus_archetype": "Canonical 1st Release Performance with Commercial Charts",
        "key_metadata_fields_demonstrated": "performance_title, performance_id, performing_artist, performing_artist_id, is_first_release, chart_placings, user_rating, released_on_title, released_on_release_id, performance_release_date, performance_release_year",
        "special_signals_and_traits": "Canonical original release marker ('is_first_release = True'); detailed 'Chart placings' (US #1, UK #1); community star ratings and total vote count.",
        "external_identifiers_present": "Spotify Track ID, YouTube Video ID, Link to Release /release/472"
    },
    {
        "index": 12,
        "page_type": "Performance",
        "entity_name": "Miss Eerie",
        "entity_id": 1072101,
        "shs_canonical_url": "https://secondhandsongs.com/performance/1072101/all",
        "example_file_in_archive": "06_take_on_me__perf1072101.html",
        "primary_focus_archetype": "Performance with Historical Studio Recording Date",
        "key_metadata_fields_demonstrated": "performance_title, performance_id, performing_artist, first_recorded_in, performance_release_date, performance_release_year, work_title, work_id",
        "special_signals_and_traits": "'First recorded in' field documenting studio date (1981-1982 demo session as 'Bridges') prior to commercial album debut; variant track title for underlying work.",
        "external_identifiers_present": "Parent Work ID (work/26), Performing Artist ID (artist/392)"
    },
    {
        "index": 13,
        "page_type": "Performance",
        "entity_name": "Blackbird",
        "entity_id": 1983,
        "shs_canonical_url": "https://secondhandsongs.com/performance/1983/all",
        "example_file_in_archive": "090_blackbird__perf1983.html",
        "primary_focus_archetype": "Studio Performance with Streaming Identifiers",
        "key_metadata_fields_demonstrated": "performance_title, performance_id, performing_artist, first_recorded_on, youtube_video_id, spotify_track_id, released_on_title, performance_release_date",
        "special_signals_and_traits": "Exact day 'First recorded on' (June 11, 1968 at EMI Abbey Road); dual active streaming identifiers for both Spotify and YouTube.",
        "external_identifiers_present": "Spotify Track ID (open.spotify.com/track/...), YouTube Video ID"
    },
    {
        "index": 14,
        "page_type": "Performance",
        "entity_name": "Wicked Game",
        "entity_id": 1051,
        "shs_canonical_url": "https://secondhandsongs.com/performance/1051/all",
        "example_file_in_archive": "02_wicked_game__perf1051.html",
        "primary_focus_archetype": "Performance with Alternate Mixes & Formats",
        "key_metadata_fields_demonstrated": "performance_title, performance_id, performing_artist, other_versions_list, other_releases_list, released_on_title, user_rating, licensing_status",
        "special_signals_and_traits": "Populated 'Other version' list linking instrumental, edit, and remix performance IDs; 'Other release' list documenting 7\" single, 12\" single, and soundtrack appearances.",
        "external_identifiers_present": "Alternate Performance IDs, Associated Release IDs"
    },
    {
        "index": 15,
        "page_type": "Performance",
        "entity_name": "Sweet Pompeii",
        "entity_id": 478476,
        "shs_canonical_url": "https://secondhandsongs.com/performance/478476/all",
        "example_file_in_archive": "64_pompeii__perf478476.html",
        "primary_focus_archetype": "Medley / Multipart Performance Combining Multiple Works",
        "key_metadata_fields_demonstrated": "performance_title, performance_id, performing_artist, parts, is_medley, is_live, user_rating, other_versions_list",
        "special_signals_and_traits": "'Parts' metadata field linking multiple distinct parent works ('Pompeii' and 'Sweet Nothing'); live concert broadcast flags; medley classification badge.",
        "external_identifiers_present": "Parent Work IDs for each medley component"
    },
    {
        "index": 16,
        "page_type": "Artist",
        "entity_name": "Natalie Cole",
        "entity_id": 9513,
        "shs_canonical_url": "https://secondhandsongs.com/artist/9513/all",
        "example_file_in_archive": "078_natalie_cole.html",
        "primary_focus_archetype": "Solo Artist with Family Lineage, IPI & Societies",
        "key_metadata_fields_demonstrated": "artist_name, artist_id, artist_personal_name, artist_birth_date, artist_death_date, artist_country, artist_ipi, artist_affiliation, artist_family, artist_member_of",
        "special_signals_and_traits": "'Family' lineage links with role labels (Nat King Cole [Father], Maria Cole [Mother]); CAE/IPI numbers with registered work tallies; PRO society affiliations.",
        "external_identifiers_present": "IPI numbers (00065979203), Affiliation PROs (BMI, ASCAP)"
    },
    {
        "index": 17,
        "page_type": "Artist",
        "entity_name": "Karmin",
        "entity_id": 71756,
        "shs_canonical_url": "https://secondhandsongs.com/artist/71756/all",
        "example_file_in_archive": "076_karmin.html",
        "primary_focus_archetype": "Musical Group / Band with Member Roster",
        "key_metadata_fields_demonstrated": "artist_name, artist_id, artist_members, artist_country, artist_ranking, total_covers_count",
        "special_signals_and_traits": "'Members' definition row enumerating hyperlinked band members (Amy Heidemann, Nick Noonan) with individual artist entity keys; musical group classification.",
        "external_identifiers_present": "Individual band member SHS artist IDs"
    },
    {
        "index": 18,
        "page_type": "Artist",
        "entity_name": "Patti Smith",
        "entity_id": 2074,
        "shs_canonical_url": "https://secondhandsongs.com/artist/2074/all",
        "example_file_in_archive": "102_patti_smith.html",
        "primary_focus_archetype": "Artist with Disambiguation Warning & Years Active",
        "key_metadata_fields_demonstrated": "artist_name, artist_id, not_to_be_confused_with, artist_years_active, artist_aliases, artist_birth_date, artist_country, artist_ranking",
        "special_signals_and_traits": "Crucial curatorial disambiguation 'Not to be confused with' linking to Patty Smyth (artist/12176); 'Years active' span (1974 - present); performer vs composer ranking badges.",
        "external_identifiers_present": "Disambiguated target entity ID, IPI number"
    },
    {
        "index": 19,
        "page_type": "Artist",
        "entity_name": "Sia",
        "entity_id": 22802,
        "shs_canonical_url": "https://secondhandsongs.com/artist/22802/all",
        "example_file_in_archive": "082_sia.html",
        "primary_focus_archetype": "Artist with Legal/Birth Names & Vanity Labels",
        "key_metadata_fields_demonstrated": "artist_name, artist_id, artist_personal_name, artist_birth_date, artist_country, artist_ipi, artist_affiliation, related_labels, spotify_artist_id, musicbrainz_artist_id",
        "special_signals_and_traits": "Full personal/legal name ('Sia Kate Isobelle Furler'); 'Related labels' record imprint links (Monkey Puzzle Records); external artist authority links.",
        "external_identifiers_present": "Spotify Artist ID, MusicBrainz Artist UUID, APRA / BMI IPI"
    },
    {
        "index": 20,
        "page_type": "Release",
        "entity_name": "Listen to Me: Buddy Holly",
        "entity_id": 64414,
        "shs_canonical_url": "https://secondhandsongs.com/release/64414/all",
        "example_file_in_archive": "CYT-release-Listen to Me - Buddy Holly-Chris Isaak-2011-64414.html",
        "primary_focus_archetype": "Commercial Album Release with Physical Barcodes & Tribute Tag",
        "key_metadata_fields_demonstrated": "release_title, release_id, release_date, release_format, release_label, release_catalog_number, release_ean_upc, tribute_to_artist, buy_links, release_tracklist",
        "special_signals_and_traits": "Tribute album metadata linking 'Tribute to' honored artist (Buddy Holly); physical product barcode (EAN/UPC); manufacturer catalog number; commercial retail buy links.",
        "external_identifiers_present": "EAN-13 Barcode, Catalog Number, Label entity link"
    }
]

output_file = Path(r"C:\Users\sethm\Documents\antigravity\nifty-meitner\shs_20_archetype_example_pages.csv")
with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=list(pages_data[0].keys()))
    writer.writeheader()
    writer.writerows(pages_data)

print(f"Successfully generated {output_file} with {len(pages_data)} pages.")
