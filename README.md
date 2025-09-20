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
