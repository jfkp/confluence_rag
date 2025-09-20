"""
Incremental Confluence sync script:
- Detects new or updated pages
- Detects new attachments
- Detects new comments
- Updates OpenSearch index incrementally

Requires environment variables:
- CONFLUENCE_BASE
- CONFLUENCE_PAT
- OPENAI_API_KEY
- OPENSEARCH_HOST (optional)

Run: python confluence_sync.py
"""
import os, requests, json, datetime, time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from opensearchpy import OpenSearch
from sentence_transformers import SentenceTransformer
import openai

# --- ENV VARS ---
CONFLUENCE_BASE_RAW = os.getenv("CONFLUENCE_BASE", "").strip()
CONFLUENCE_PAT = os.getenv("CONFLUENCE_PAT")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENSEARCH = os.getenv("OPENSEARCH_HOST", "http://localhost:9200")

if not CONFLUENCE_BASE_RAW:
    raise SystemExit("CONFLUENCE_BASE env var required")
CONFLUENCE_BASE = CONFLUENCE_BASE_RAW.rstrip("/")

if not CONFLUENCE_PAT:
    raise SystemExit("CONFLUENCE_PAT env var required")

headers = {"Authorization": f"Bearer {CONFLUENCE_PAT}", "Accept": "application/json"}
openai.api_key = OPENAI_API_KEY

embed_model = SentenceTransformer("all-MiniLM-L6-v2")
os_client = OpenSearch(OPENSEARCH)
INDEX = "confluence"
SYNC_FILE = "last_sync.json"


# --- SYNC TIME MANAGEMENT ---
def get_last_sync():
    if not os.path.exists(SYNC_FILE):
        return datetime.datetime.min
    with open(SYNC_FILE, "r") as f:
        return datetime.datetime.fromisoformat(json.load(f)["last_sync"])


def save_last_sync():
    with open(SYNC_FILE, "w") as f:
        json.dump({"last_sync": datetime.datetime.utcnow().isoformat()}, f)


# --- FETCH HELPERS ---
def fetch_pages_in_space(space_key, limit=25, start=0):
    url = f"{CONFLUENCE_BASE}/rest/api/content"
    params = {"spaceKey": space_key, "limit": limit, "start": start, "expand": "body.storage,history"}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_attachments_for_page(page_id, limit=50):
    url = f"{CONFLUENCE_BASE}/rest/api/content/{page_id}/child/attachment"
    params = {"limit": limit, "expand": "history"}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("results", [])


def fetch_new_comments_for_page(page_id, since, limit=50):
    url = f"{CONFLUENCE_BASE}/rest/api/content/{page_id}/child/comment"
    params = {"limit": limit, "expand": "body.storage,history"}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    new_comments = []
    for c in data.get("results", []):
        created_date = c.get("history", {}).get("createdDate")
        if created_date and datetime.datetime.fromisoformat(created_date.replace("Z", "")) > since:
            body = c.get("body", {}).get("storage", {}).get("value", "")
            soup = BeautifulSoup(body, "html.parser")
            new_comments.append(soup.get_text(" ", strip=True))
    return new_comments


# --- IMAGE DESCRIPTION ---
def describe_image_via_openai(image_url):
    if not OPENAI_API_KEY:
        return "[openai key not set — image not described]"
    try:
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image in detail, including objects, text, charts, and labels."},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }]
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[image description failed: {str(e)}]"


# --- OPENSEARCH UPDATERS ---
def ingest_page(page):
    """Index or re-index a full page (title + body)."""
    page_id = page.get("id")
    title = page.get("title")
    url = urljoin(CONFLUENCE_BASE + "/", page.get("_links", {}).get("webui", "").lstrip("/"))
    html = page.get("body", {}).get("storage", {}).get("value", "")
    soup = BeautifulSoup(html or "", "html.parser")
    text = soup.get_text(" ", strip=True)
    chunks = [text[i:i+1500] for i in range(0, len(text), 1500)] or [""]
    for i, ch in enumerate(chunks):
        emb = embed_model.encode(ch).tolist()
        doc = {
            "title": title,
            "url": url,
            "text": ch,
            "metadata": {"space": page.get("space", {}).get("key"), "page_id": page_id, "chunk": i},
            "embedding": emb,
        }
        os_client.index(index=INDEX, id=f"{page_id}-{i}", body=doc)


def update_page_attachments_in_opensearch(page_id, new_attachments):
    if not new_attachments:
        return
    os_client.update(
        index=INDEX,
        id=f"{page_id}-0",  # assume chunk 0 holds metadata
        body={
            "script": {
                "source": "ctx._source.images.addAll(params.new_images)",
                "lang": "painless",
                "params": {"new_images": new_attachments},
            }
        },
    )


def update_page_comments_in_opensearch(page_id, new_comments):
    if not new_comments:
        return
    os_client.update(
        index=INDEX,
        id=f"{page_id}-0",  # assume chunk 0 holds metadata
        body={
            "script": {
                "source": "ctx._source.comments.addAll(params.new_comments)",
                "lang": "painless",
                "params": {"new_comments": new_comments},
            }
        },
    )


# --- MAIN INCREMENTAL SYNC ---
def incremental_sync(space_key):
    since = get_last_sync()
    print(f"Incremental sync for space {space_key} since {since}")
    start = 0
    while True:
        res = fetch_pages_in_space(space_key, limit=25, start=start)
        results = res.get("results", [])
        if not results:
            break

        for page in results:
            page_id = page.get("id")
            history = page.get("history", {})
            created = history.get("createdDate")
            updated = history.get("lastUpdated", {}).get("when")
            created_dt = datetime.datetime.fromisoformat(created.replace("Z", "")) if created else None
            updated_dt = datetime.datetime.fromisoformat(updated.replace("Z", "")) if updated else None

            # --- New or updated page ---
            if created_dt and created_dt > since:
                print(f"New page {page['title']}")
                ingest_page(page)
            elif updated_dt and updated_dt > since:
                print(f"Updated page {page['title']}")
                ingest_page(page)

            # --- New attachments ---
            new_attachments = []
            attachments = fetch_attachments_for_page(page_id)
            for a in attachments:
                cdate = a.get("history", {}).get("createdDate")
                if cdate and datetime.datetime.fromisoformat(cdate.replace("Z", "")) > since:
                    rel = a.get("_links", {}).get("download")
                    if rel:
                        full = urljoin(CONFLUENCE_BASE + "/", rel.lstrip("/"))
                        desc = describe_image_via_openai(full)
                        new_attachments.append({"url": full, "description": desc})
                        time.sleep(0.2)
            if new_attachments:
                update_page_attachments_in_opensearch(page_id, new_attachments)

            # --- New comments ---
            new_comments = fetch_new_comments_for_page(page_id, since)
            if new_comments:
                update_page_comments_in_opensearch(page_id, new_comments)

        start += 25
        if len(results) < 25:
            break

    save_last_sync()
    print("Incremental sync done.")


if __name__ == "__main__":
    incremental_sync("ENG")  # replace ENG with your space key
