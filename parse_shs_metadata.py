import os
import glob
import csv
import re
from bs4 import BeautifulSoup

def parse_shs_html(filepath):
    """
    Parses a SecondHandSongs HTML file and extracts relevant metadata,
    ensuring 'Title', 'Performing Artist', 'Original Artist', and 'Release Date' are explicitly pulled.
    """
    filename = os.path.basename(filepath)
    metadata = {
        'Filename': filename,
        'Canonical URL': '',
        'Entity ID': '',
        'Entity Type': '',
        'Page Title': '',
        'Title': '',
        'Performing Artist': '',
        'Original Artist': '',
        'Release Date': ''
    }
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filename}: {e}")
        return None
        
    soup = BeautifulSoup(content, 'html.parser')
    
    # 1. Page Title
    title_tag = soup.find('title')
    if title_tag:
        metadata['Page Title'] = title_tag.get_text(strip=True)
        
    # 2. Canonical URL & ID Extraction
    canonical = soup.find('link', rel='canonical')
    if canonical and canonical.has_attr('href'):
        metadata['Canonical URL'] = canonical['href']
        
        match = re.search(r'secondhandsongs\.com/(work|performance|artist|release)/(\d+)', canonical['href'])
        if match:
            metadata['Entity Type'] = match.group(1).capitalize()
            metadata['Entity ID'] = match.group(2)
            
    # 3. Entity Name (Title) & Performing Artist
    h1 = soup.find('h1')
    if h1:
        # Title is usually in span[itemprop="name"]
        name_span = h1.find(attrs={"itemprop": "name"})
        if name_span:
            metadata['Title'] = name_span.get_text(strip=True)
        else:
            # Fallback
            metadata['Title'] = h1.get_text(strip=True)
            
        # Performing artist often follows an <em>by</em> tag in performances
        em_by = h1.find('em')
        if em_by and 'by' in em_by.get_text(strip=True).lower():
            artist_a = em_by.find_next_sibling('a')
            if artist_a:
                metadata['Performing Artist'] = artist_a.get_text(strip=True)
            
    # 4. Definition List Metadata (<dt> and <dd>)
    dl_tags = soup.find_all('dl')
    for dl in dl_tags:
        dt_tags = dl.find_all('dt')
        dd_tags = dl.find_all('dd')
        
        for dt, dd in zip(dt_tags, dd_tags):
            key = dt.get_text(strip=True).replace(':', '')
            key = re.sub(r'International Standard Musical Work Code.*$', '', key).strip()
            value = dd.get_text(separator=' | ', strip=True)
            
            # Map specific fields to requested columns
            if key.lower() == 'written by':
                metadata['Original Artist'] = value
            elif key.lower() == 'released on':
                metadata['Release Date'] = value
                
            metadata[key] = value

    # 5. Fallback for Release Date and Original Artist from Meta Description if still empty
    if not metadata['Release Date'] or not metadata['Original Artist']:
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.has_attr('content'):
            desc_text = meta_desc['content']
            # Example: "... was written by Chris Isaak and was first released by Chris Isaak in 1989."
            if not metadata['Release Date']:
                year_match = re.search(r'in (\d{4})', desc_text)
                if year_match:
                    metadata['Release Date'] = year_match.group(1)
            
            if not metadata['Original Artist']:
                written_match = re.search(r'written by (.*?) and was first released', desc_text)
                if written_match:
                    metadata['Original Artist'] = written_match.group(1).strip()

    # Clean up empty Performing Artist for Work pages (where Original Artist is the main artist)
    if not metadata['Performing Artist'] and metadata['Entity Type'] == 'Work':
        metadata['Performing Artist'] = metadata['Original Artist']

    return metadata

def main():
    directory = r'D:\Music\MusicDB\basket'
    output_csv = r'C:\Users\sethm\Documents\antigravity\nifty-meitner\shs_metadata_extracted.csv'
    
    html_files = glob.glob(os.path.join(directory, '*SecondHandSongs*.html'))
    
    if not html_files:
        print(f"No SecondHandSongs HTML files found in {directory}.")
        return

    all_metadata = []
    all_keys = set()
    
    print(f"Found {len(html_files)} files. Extracting metadata...")
    for filepath in html_files:
        data = parse_shs_html(filepath)
        if data:
            all_metadata.append(data)
            all_keys.update(data.keys())
            
    if not all_metadata:
        print("No metadata extracted.")
        return
        
    # Ensure specific requested columns are at the front
    standard_cols = ['Filename', 'Title', 'Performing Artist', 'Original Artist', 'Release Date', 'Canonical URL', 'Entity Type', 'Entity ID', 'Page Title']
    other_cols = sorted([k for k in all_keys if k not in standard_cols])
    fieldnames = standard_cols + other_cols
    
    # Write to CSV
    print(f"Writing output to {output_csv}...")
    with open(output_csv, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_metadata:
            writer.writerow(row)
            
    print("Done!")

if __name__ == '__main__':
    main()
