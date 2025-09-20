import os
from fastapi import FastAPI, Query
from pydantic import BaseModel
from opensearchpy import OpenSearch
from sentence_transformers import SentenceTransformer
import openai

# --- ENV ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENSEARCH = os.getenv("OPENSEARCH_HOST", "http://localhost:9200")
INDEX = "confluence"

# --- Clients ---
embed_model = SentenceTransformer("all-MiniLM-L6-v2")
os_client = OpenSearch(OPENSEARCH)
openai.api_key = OPENAI_API_KEY

app = FastAPI(title="Confluence Q&A Service")

class QAResponse(BaseModel):
    question: str
    answer: str
    sources: list[str]

# --- Search ---
def search_opensearch(query, top_k=5):
    emb = embed_model.encode(query).tolist()
    resp = os_client.search(
        index=INDEX,
        body={
            "size": top_k,
            "query": {
                "script_score": {
                    "query": {"match_all": {}},
                    "script": {
                        "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                        "params": {"query_vector": emb}
                    }
                }
            }
        }
    )
    hits = resp["hits"]["hits"]
    return [
        {
            "text": h["_source"]["text"],
            "url": h["_source"].get("url"),
            "title": h["_source"].get("title"),
        }
        for h in hits
    ]

# --- LLM Answer ---
def ask_llm(question, docs):
    context = "\n\n".join([f"[{i+1}] {d['title']}: {d['text']}" for i, d in enumerate(docs)])
    messages = [
        {"role": "system", "content": "You are a helpful assistant answering questions based on Confluence knowledge."},
        {"role": "user", "content": f"Question: {question}\n\nContext:\n{context}\n\nAnswer with references [1], [2], etc."}
    ]
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
    )
    return resp.choices[0].message.content.strip()

# --- API Endpoint ---
@app.get("/qa", response_model=QAResponse)
def qa_endpoint(q: str = Query(..., description="User question")):
    docs = search_opensearch(q, top_k=5)
    if not docs:
        return QAResponse(question=q, answer="No relevant results found.", sources=[])
    answer = ask_llm(q, docs)
    sources = list({d["url"] for d in docs if d.get("url")})
    return QAResponse(question=q, answer=answer, sources=sources)
