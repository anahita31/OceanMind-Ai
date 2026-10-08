"""
ChromaDB vector store ops. ARGO profiles are chunked into short text
summaries (one per profile) and embedded so the RAG pipeline can retrieve
relevant floats by semantic similarity to the user's question.

Uses Chroma's built-in default embedding function (all-MiniLM-L6-v2) so no
extra embedding API/key is required beyond Groq for the chat model itself.
"""
import logging

import chromadb

from config import settings
from models.argo_cache import ArgoProfile

logger = logging.getLogger("oceanmind.embeddings")

_client = None
_collection = None


def get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        _collection = _client.get_or_create_collection(name="argo_profiles")
    return _collection


def _profile_to_text(p: ArgoProfile) -> str:
    def avg(vals):
        # depth/temp/salinity arrays are index-aligned and may contain None
        # where a given ARGO row didn't report that field — filter before
        # averaging.
        clean = [v for v in (vals or []) if v is not None]
        return round(sum(clean) / len(clean), 2) if clean else None

    return (
        f"ARGO float {p.wmo_id}, profile date {p.profile_date}, "
        f"location ({p.lat:.2f}, {p.lon:.2f}). "
        f"Avg temperature: {avg(p.temp_arr)} C. "
        f"Avg salinity (PSU): {avg(p.salinity_arr)}. "
        f"Avg pressure: {avg(p.pressure_arr)} dbar. "
        f"Depth levels sampled: {len(p.depth_arr)}."
    )


def index_profiles(profiles: list[ArgoProfile]) -> int:
    """Embeds and upserts a batch of ArgoProfile rows into Chroma."""
    if not profiles:
        return 0
    collection = get_collection()
    ids = [p.id for p in profiles]
    docs = [_profile_to_text(p) for p in profiles]
    metadatas = [
        {"wmo_id": p.wmo_id, "profile_date": str(p.profile_date), "lat": p.lat, "lon": p.lon}
        for p in profiles
    ]
    collection.upsert(ids=ids, documents=docs, metadatas=metadatas)
    logger.info("Indexed %d ARGO profiles into ChromaDB", len(profiles))
    return len(profiles)


def retrieve_relevant_chunks(query: str, top_k: int = 5) -> list[dict]:
    """Returns top_k most relevant ARGO profile summaries for a user query."""
    collection = get_collection()
    if collection.count() == 0:
        return []
    results = collection.query(query_texts=[query], n_results=min(top_k, collection.count()))
    chunks = []
    for doc, meta, dist in zip(
        results.get("documents", [[]])[0],
        results.get("metadatas", [[]])[0],
        results.get("distances", [[]])[0],
    ):
        chunks.append({"text": doc, "metadata": meta, "distance": dist})
    return chunks
