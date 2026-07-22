from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import json
import numpy as np

app = FastAPI()

# ---------------- LOAD DATA ----------------
docs = pd.read_csv("/mnt/data/documents.csv")
with open("/mnt/data/embeddings.json") as f:
    embeddings = json.load(f)

with open("/mnt/data/reranker_scores.json") as f:
    reranker_scores = json.load(f)

# Convert embeddings to numpy
for k in embeddings:
    embeddings[k] = np.array(embeddings[k])

# ---------------- REQUEST SCHEMA ----------------
class QueryRequest(BaseModel):
    query_id: str
    query_vector: list
    top_k: int
    rerank_top_n: int
    filter: dict

# ---------------- HELPER FUNCTIONS ----------------

def apply_filter(df, filt):
    for key, val in filt.items():
        if isinstance(val, dict):
            if "gte" in val:
                df = df[df[key] >= val["gte"]]
            if "lte" in val:
                df = df[df[key] <= val["lte"]]
            if "in" in val:
                df = df[df[key].isin(val["in"])]
        else:
            df = df[df[key] == val]
    return df

def cosine_sim(a, b):
    a = np.array(a)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

# ---------------- API ENDPOINT ----------------

@app.post("/vector-search")
def vector_search(req: QueryRequest):
    
    query_vec = np.array(req.query_vector)

    # 1. FILTER
    filtered_docs = apply_filter(docs.copy(), req.filter)

    # 2. VECTOR SIMILARITY
    sims = []
    for _, row in filtered_docs.iterrows():
        doc_id = row["doc_id"]
        if doc_id not in embeddings:
            continue
        
        sim = cosine_sim(query_vec, embeddings[doc_id])
        sims.append((doc_id, sim))
    
    # Sort by similarity desc, tie → lexicographically smaller doc_id
    sims.sort(key=lambda x: (-x[1], x[0]))
    
    top_k_docs = [doc_id for doc_id, _ in sims[:req.top_k]]

    # 3. RE-RANKING
    rerank_scores = reranker_scores.get(req.query_id, {})
    
    reranked = []
    for doc_id in top_k_docs:
        score = rerank_scores.get(doc_id, 0)
        reranked.append((doc_id, score))
    
    # Sort by rerank score desc, tie → lexicographically smaller doc_id
    reranked.sort(key=lambda x: (-x[1], x[0]))

    final_docs = [doc_id for doc_id, _ in reranked[:req.rerank_top_n]]

    # 4. RESPONSE
    return {"matches": final_docs}
