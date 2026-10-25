import csv
import os

target_dir = r"D:\Music\MusicDB\basket\SHS-HTML"
csv_path = os.path.join(target_dir, "metadatafields_shs.csv")

fields_data = [
    # Artist Metadata
    {
        "Field_Name": "artist_name",
        "Category": "Artist Metadata",
        "Description": "Name of the artist, performer, or writer",
        "Example_Value": "Ellie Goulding, Depeche Mode, Martin Gore",
        "Schema_ItemType": "https://schema.org/MusicGroup",
        "Schema_ItemProp": "name",
        "HTML_Selector_or_Location": "h1.title / a[href^=\"/artist/\"]",
        "Source_Page_Type": "Artist Main Page, Performance Page, Work Page"
    },
    {
        "Field_Name": "artist_id",
        "Category": "Artist Metadata",
        "Description": "Numeric ID of the artist in SecondHandSongs",
        "Example_Value": "616",
        "Schema_ItemType": "https://schema.org/MusicGroup",
        "Schema_ItemProp": "url",
        "HTML_Selector_or_Location": 'a[href^="/artist/"] (Extracted path /artist/<ID>)',
        "Source_Page_Type": "All Pages"
    },
    {
        "Field_Name": "artist_slug",
        "Category": "Artist Metadata",
        "Description": "URL slug or normalized name of the artist profile",
        "Example_Value": "Depeche-Mode",
        "Schema_ItemType": "https://schema.org/MusicGroup",
        "Schema_ItemProp": "url",
        "HTML_Selector_or_Location": 'a[href^="/artist/"]',
        "Source_Page_Type": "All Pages"
    },
    {
        "Field_Name": "artist_birth_date",
        "Category": "Artist Metadata",
        "Description": "Birth date of individual person artist",
        "Example_Value": "December 30, 1986",
        "Schema_ItemType": "http://schema.org/Person",
        "Schema_ItemProp": "birthDate",
        "HTML_Selector_or_Location": "dd[itemprop=\"birthDate\"]",
        "Source_Page_Type": "Artist Main Page"
    },
    {
        "Field_Name": "artist_nationality",
        "Category": "Artist Metadata",
        "Description": "Nationality / Country of origin of artist",
        "Example_Value": "United Kingdom",
        "Schema_ItemType": "http://schema.org/Person",
        "Schema_ItemProp": "nationality",
        "HTML_Selector_or_Location": "dd[itemprop=\"nationality\"]",
        "Source_Page_Type": "Artist Main Page"
    },

    # Work / Composition Metadata
    {
        "Field_Name": "work_title",
        "Category": "Work / Composition Metadata",
        "Description": "Title of the musical composition / written work",
        "Example_Value": "Enjoy the Silence, #1 Crush",
        "Schema_ItemType": "http://schema.org/MusicComposition",
        "Schema_ItemProp": "name",
        "HTML_Selector_or_Location": "h1.title / a[href^=\"/work/\"]",
        "Source_Page_Type": "Work Main Page, Performance Page"
    },
    {
        "Field_Name": "work_id",
        "Category": "Work / Composition Metadata",
        "Description": "Numeric ID of the work in SecondHandSongs",
        "Example_Value": "1153",
        "Schema_ItemType": "http://schema.org/MusicComposition",
        "Schema_ItemProp": "url",
        "HTML_Selector_or_Location": 'a[href^="/work/"] (Extracted path /work/<ID>)',
        "Source_Page_Type": "All Pages"
    },
    {
        "Field_Name": "work_author_writer_name",
        "Category": "Work / Composition Metadata",
        "Description": "Songwriter / Composer credited for writing the work",
        "Example_Value": "Martin Gore, Kurt Cobain, Sting",
        "Schema_ItemType": "http://schema.org/Person",
        "Schema_ItemProp": "author",
        "HTML_Selector_or_Location": 'span[itemprop="author"] > a[href^="/artist/"]',
        "Source_Page_Type": "Work Main Page, Performance Page"
    },
    {
        "Field_Name": "work_author_writer_id",
        "Category": "Work / Composition Metadata",
        "Description": "Numeric artist ID of the songwriter",
        "Example_Value": "1204",
        "Schema_ItemType": "http://schema.org/Person",
        "Schema_ItemProp": "url",
        "HTML_Selector_or_Location": 'span[itemprop="author"] > a[href^="/artist/"]',
        "Source_Page_Type": "Work Main Page, Performance Page"
    },
    {
        "Field_Name": "work_language",
        "Category": "Work / Composition Metadata",
        "Description": "Original language of the work lyrics",
        "Example_Value": "English",
        "Schema_ItemType": "http://schema.org/MusicComposition",
        "Schema_ItemProp": "inLanguage",
        "HTML_Selector_or_Location": "dd[itemprop=\"inLanguage\"]",
        "Source_Page_Type": "Work Main Page"
    },

    # Performance / Recording Metadata
    {
        "Field_Name": "performance_title",
        "Category": "Performance Metadata",
        "Description": "Title of the specific performance / recording version",
        "Example_Value": "Enjoy the Silence",
        "Schema_ItemType": "http://schema.org/MusicRecording",
        "Schema_ItemProp": "name",
        "HTML_Selector_or_Location": 'table.data td:nth-child(3) a[href^="/performance/"]',
        "Source_Page_Type": "Work Page, Performance Page, Cover List Page"
    },
    {
        "Field_Name": "performance_id",
        "Category": "Performance Metadata",
        "Description": "Numeric ID of the performance recording",
        "Example_Value": "1153, 151574, 1567551",
        "Schema_ItemType": "http://schema.org/MusicRecording",
        "Schema_ItemProp": "url",
        "HTML_Selector_or_Location": 'a[href^="/performance/"] (Extracted path /performance/<ID>)',
        "Source_Page_Type": "All List Pages, Performance Page"
    },
    {
        "Field_Name": "performer_name",
        "Category": "Performance Metadata",
        "Description": "Name of the performing artist or group for this recording",
        "Example_Value": "Depeche Mode, Tori Amos, Failure, Brokenstra",
        "Schema_ItemType": "https://schema.org/MusicGroup",
        "Schema_ItemProp": "byArtist",
        "HTML_Selector_or_Location": "table.data td:nth-child(4) a[href^=\"/artist/\"]",
        "Source_Page_Type": "Work Page, Cover List Page"
    },
    {
        "Field_Name": "performer_id",
        "Category": "Performance Metadata",
        "Description": "Numeric ID of the performing artist",
        "Example_Value": "616",
        "Schema_ItemType": "https://schema.org/MusicGroup",
        "Schema_ItemProp": "url",
        "HTML_Selector_or_Location": 'table.data td:nth-child(4) a[href^="/artist/"]',
        "Source_Page_Type": "Work Page, Cover List Page"
    },
    {
        "Field_Name": "performance_release_date",
        "Category": "Performance Metadata",
        "Description": "Exact release date or year of the performance",
        "Example_Value": "February 5, 1990, September 18, 2001, January 2022",
        "Schema_ItemType": "http://schema.org/MusicRecording",
        "Schema_ItemProp": "datePublished",
        "HTML_Selector_or_Location": "table.data td:nth-child(5)",
        "Source_Page_Type": "Work Page, Cover List Page"
    },
    {
        "Field_Name": "performance_info_badge",
        "Category": "Performance Metadata",
        "Description": "Flags and badges (First release, Hit song, First recording, Instrumental, Live)",
        "Example_Value": "First release, Hit song, Instrumental",
        "Schema_ItemType": "N/A",
        "Schema_ItemProp": "N/A",
        "HTML_Selector_or_Location": "table.data td:nth-child(6) span.badge",
        "Source_Page_Type": "Work Page, Cover List Page"
    },
    {
        "Field_Name": "performance_is_original",
        "Category": "Performance Metadata",
        "Description": "Boolean / Flag indicating if this recording is the original 1st release",
        "Example_Value": "True / 1st in 1990",
        "Schema_ItemType": "N/A",
        "Schema_ItemProp": "N/A",
        "HTML_Selector_or_Location": "table.data td:nth-child(1) span.badge-original / [1st]",
        "Source_Page_Type": "Work Page, Cover List Page"
    },

    # Navigation & Relationship Sub-Tabs
    {
        "Field_Name": "total_versions_count",
        "Category": "Navigation / Summary",
        "Description": "Total recorded versions / covers of the work",
        "Example_Value": "152",
        "Schema_ItemType": "N/A",
        "Schema_ItemProp": "N/A",
        "HTML_Selector_or_Location": 'ul.nav-tabs a[href*="/versions"]',
        "Source_Page_Type": "Work Page"
    },
    {
        "Field_Name": "total_samples_count",
        "Category": "Navigation / Summary",
        "Description": "Total samples referencing or originating from the work",
        "Example_Value": "14",
        "Schema_ItemType": "N/A",
        "Schema_ItemProp": "N/A",
        "HTML_Selector_or_Location": 'ul.nav-tabs a[href*="/samples"]',
        "Source_Page_Type": "Work Page"
    },
    {
        "Field_Name": "total_adaptations_count",
        "Category": "Navigation / Summary",
        "Description": "Total adaptations / translated versions of the work",
        "Example_Value": "8",
        "Schema_ItemType": "N/A",
        "Schema_ItemProp": "N/A",
        "HTML_Selector_or_Location": 'ul.nav-tabs a[href*="/adaptations"]',
        "Source_Page_Type": "Work Page"
    },

    # Pagination & Search Metadata
    {
        "Field_Name": "pagination_page_number",
        "Category": "Pagination Metadata",
        "Description": "Page offset parameter for paginated tables",
        "Example_Value": "?page=2",
        "Schema_ItemType": "N/A",
        "Schema_ItemProp": "N/A",
        "HTML_Selector_or_Location": 'ul.pagination a[href*="page="]',
        "Source_Page_Type": "All List Pages"
    },
    {
        "Field_Name": "pagination_sort_parameter",
        "Category": "Pagination Metadata",
        "Description": "Sort column parameter (date, title, performer)",
        "Example_Value": "?sort=date",
        "Schema_ItemType": "N/A",
        "Schema_ItemProp": "N/A",
        "HTML_Selector_or_Location": 'table.data th a[href*="sort="]',
        "Source_Page_Type": "All List Pages"
    }
]

with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(fields_data[0].keys()))
    writer.writeheader()
    writer.writerows(fields_data)

print(f"Successfully generated {csv_path} with {len(fields_data)} fields.")
