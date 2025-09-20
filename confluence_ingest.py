"""
Confluence ingestion script (PAT only) with OpenAI image descriptions + comments.

Set environment variables:
- CONFLUENCE_BASE
- CONFLUENCE_PAT
- OPENAI_API_KEY
- OPENSEARCH_HOST (optional)

Run: python confluence_ingest.py
"""
import os, requests, time
from bs4 import BeautifulSoup
from opensearchpy import OpenSearch
from sentence_transformers import SentenceTransformer
import openai
from urllib.parse import urljoin

# --- ENV VARS ---
CONFLUENCE_BASE_RAW = os.getenv('CONFLUENCE_BASE', '').strip()
CONFLUENCE_PAT = os.getenv('CONFLUENCE_PAT')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENSEARCH = os.getenv('OPENSEARCH_HOST', 'http://localhost:9200')

if not CONFLUENCE_BASE_RAW:
    raise SystemExit('CONFLUENCE_BASE env var required')
CONFLUENCE_BASE = CONFLUENCE_BASE_RAW.rstrip('/')

if not CONFLUENCE_PAT:
    raise SystemExit('CONFLUENCE_PAT env var required')

headers = {'Authorization': f'Bearer {CONFLUENCE_PAT}', 'Accept': 'application/json'}
openai.api_key = OPENAI_API_KEY

embed_model = SentenceTransformer('all-MiniLM-L6-v2')
os_client = OpenSearch(OPENSEARCH)
INDEX = 'confluence'


# --- FETCH HELPERS ---
def fetch_spaces(limit=50, start=0):
    url = f"{CONFLUENCE_BASE}/rest/api/space"
    params = {'limit': limit, 'start': start}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def fetch_pages_in_space(space_key, limit=25, start=0):
    url = f"{CONFLUENCE_BASE}/rest/api/content"
    params = {'spaceKey': space_key, 'limit': limit, 'start': start, 'expand': 'body.storage'}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def fetch_attachments_for_page(page_id, limit=50):
    url = f"{CONFLUENCE_BASE}/rest/api/content/{page_id}/child/attachment"
    params = {'limit': limit}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get('results', [])

def fetch_comments_for_page(page_id, limit=50, start=0):
    url = f"{CONFLUENCE_BASE}/rest/api/content/{page_id}/child/comment"
    params = {'limit': limit, 'start': start, 'expand': 'body.storage'}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    comments = []
    for c in data.get("results", []):
        body = c.get("body", {}).get("storage", {}).get("value", "")
        soup = BeautifulSoup(body, "html.parser")
        comments.append(soup.get_text(" ", strip=True))
    return comments


# --- IMAGE DESCRIPTION ---
def describe_image_via_openai(image_url):
    if not OPENAI_API_KEY:
        return '[openai key not set — image not described]'
    try:
        resp = openai.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': 'Describe this image in detail, including objects, text, charts, and labels.'},
                    {'type': 'image_url', 'image_url': {'url': image_url}}
                ]
            }]
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f'[image description failed: {str(e)}]'


def clean_html_and_describe_images(html, page_id):
    soup = BeautifulSoup(html or '', 'html.parser')
    images = []
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or ''
        full = src if src.startswith('http') else urljoin(CONFLUENCE_BASE + '/', src.lstrip('/'))
        desc = describe_image_via_openai(full)
        images.append({'url': full, 'description': desc})
        img.replace_with(f'[Image description: {desc}]')
        time.sleep(0.2)
    try:
        attachments = fetch_attachments_for_page(page_id)
        for a in attachments:
            rel = a.get('_links', {}).get('download')
            if not rel:
                continue
            full = urljoin(CONFLUENCE_BASE + '/', rel.lstrip('/'))
            desc = describe_image_via_openai(full)
            images.append({'url': full, 'description': desc})
            time.sleep(0.2)
    except Exception:
        pass
    text = soup.get_text(' ', strip=True)
    return text, images


# --- INDEXING ---
def index_chunk(title, url, space, page_id, chunk_idx, text, images, comments):
    emb = embed_model.encode(text).tolist()
    doc = {
        'title': title,
        'url': url,
        'text': text,
        'metadata': {'space': space, 'page_id': page_id, 'chunk': chunk_idx},
        'embedding': emb,
        'images': images,
        'comments': comments or []
    }
    os_client.index(index=INDEX, body=doc)


# --- INGESTION ---
def ingest_space_by_key(space_key, max_pages=200):
    print(f'Ingesting space {space_key} (max_pages={max_pages})')
    start = 0
    seen = 0
    while seen < max_pages:
        res = fetch_pages_in_space(space_key, limit=25, start=start)
        results = res.get('results', [])
        if not results:
            break
        for page in results:
            seen += 1
            page_id = page.get('id')
            title = page.get('title')
            url = urljoin(CONFLUENCE_BASE + '/', page.get('_links', {}).get('webui','').lstrip('/'))
            html = page.get('body', {}).get('storage', {}).get('value', '')
            text, images = clean_html_and_describe_images(html, page_id)
            comments = fetch_comments_for_page(page_id)
            chunks = [text[i:i+1500] for i in range(0, len(text), 1500)] or ['']
            for i,ch in enumerate(chunks):
                index_chunk(title, url, space_key, page_id, i, ch, images, comments)
        start += 25
        if len(results) < 25:
            break
    print('Done')


def ingest_all_spaces(max_spaces=50):
    print('Listing spaces...')
    start = 0
    seen = 0
    while seen < max_spaces:
        res = fetch_spaces(limit=25, start=start)
        results = res.get('results', [])
        if not results:
            break
        for sp in results:
            key = sp.get('key')
            print('->', key, sp.get('name'))
            ingest_space_by_key(key, max_pages=200)
            seen += 1
            if seen >= max_spaces:
                break
        start += 25
        if len(results) < 25:
            break
    print('Finished ingesting spaces')


if __name__ == '__main__':
    ingest_all_spaces(max_spaces=10)
