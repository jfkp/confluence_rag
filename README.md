# confluence_rag

# Confluence → OpenSearch Ingestion & Sync

This repo provides tools to index Confluence content (pages, comments, attachments) into OpenSearch with support for OpenAI-based image descriptions.

## Features
- Full ingestion of Confluence spaces/pages (`confluence_ingest.py`)
- Incremental sync of new/updated pages, comments, and attachments (`confluence_sync.py`)
- Embeddings via `sentence-transformers`
- Image description via OpenAI GPT models
- Docker & Airflow integration

---

## ⚙️ Setup

1. **Environment Variables**

```bash
export CONFLUENCE_BASE="https://your-domain.atlassian.net"
export CONFLUENCE_PAT="your_personal_access_token"
export OPENAI_API_KEY="your_openai_key"
export OPENSEARCH_HOST="http://localhost:9200"


2. **Run full ingestion**

python confluence_ingest.py


3. **Run incremental sync**

python confluence_sync.py


## On first run, sync will just initialize last_sync.json and skip re-indexing. Subsequent runs only index new/updated content.


docker build -t confluence-sync .

docker run --rm \
  -e CONFLUENCE_BASE="https://your-domain.atlassian.net" \
  -e CONFLUENCE_PAT="your_pat" \
  -e OPENAI_API_KEY="your_openai_key" \
  -e OPENSEARCH_HOST="http://localhost:9200" \
  confluence-sync python confluence_sync.py


docker run --rm \
  -e CONFLUENCE_BASE=$CONFLUENCE_BASE \
  -e CONFLUENCE_PAT=$CONFLUENCE_PAT \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e OPENSEARCH_HOST=$OPENSEARCH_HOST \
  confluence-sync
