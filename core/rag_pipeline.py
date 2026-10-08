"""
Core conversational AI pipeline. Not using LangChain — a direct Groq call
plus a manual Chroma retrieval step is simpler to debug under hackathon
time pressure and has fewer moving dependency parts.

Flow per message:
  1. Classify audience (student vs researcher) with the fast 8B model
  2. Retrieve top-5 relevant ARGO profile chunks from ChromaDB
  3. Build a system prompt with live sensor state + active anomalies + chunks
  4. Call the 70B model for the final answer
  5. Return answer + structured source references
"""
import logging

from groq import Groq

from config import settings
from core.embeddings import retrieve_relevant_chunks

logger = logging.getLogger("oceanmind.rag_pipeline")

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=settings.GROQ_API_KEY)
    return _client


def classify_audience(message: str) -> str:
    """Quick keyword/LLM classification: 'researcher' or 'student'. Cheap 8B call."""
    if not settings.GROQ_API_KEY:
        return "student"  # safe default when no key configured (e.g. local dev)
    try:
        resp = _get_client().chat.completions.create(
            model=settings.CLASSIFIER_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify the following message as either 'researcher' or 'student' "
                        "based on its technical vocabulary and phrasing. Reply with exactly "
                        "one word: researcher or student."
                    ),
                },
                {"role": "user", "content": message},
            ],
            max_tokens=5,
            temperature=0,
        )
        label = resp.choices[0].message.content.strip().lower()
        return "researcher" if "research" in label else "student"
    except Exception as exc:
        logger.warning("Audience classification failed (%s), defaulting to student", exc)
        return "student"


def _build_system_prompt(audience: str, sensor_context: dict | None, anomalies: list[dict]) -> str:
    sensor_block = "No live sensor reading available." if not sensor_context else (
        f"Latest coastal sensor reading — device {sensor_context['device_id']} "
        f"at ({sensor_context['lat']:.4f}, {sensor_context['lon']:.4f}): "
        f"temperature {sensor_context['temp_c']}C, TDS {sensor_context['tds_ppm']}ppm "
        f"(salinity proxy), pressure {sensor_context['pressure_hpa']}hPa, "
        f"recorded at {sensor_context['created_at']}."
    )

    anomaly_block = "No active anomalies." if not anomalies else "\n".join(
        f"- [{a['severity']}] {a['anomaly_type']}: {a['description']}" for a in anomalies
    )

    tone_instruction = (
        "The user appears to be a researcher — you may use precise oceanographic "
        "terminology and cite exact figures."
        if audience == "researcher" else
        "The user appears to be a student or general public — explain concepts in clear, "
        "simple language, avoiding unnecessary jargon."
    )

    return f"""You are OceanMind AI, an ocean science assistant with access to public ARGO
float data for the Indian Ocean, extended with live readings from a coastal
sensor node that fills the shallow-water gap ARGO floats cannot reach.

{tone_instruction}

CURRENT LIVE SENSOR READING:
{sensor_block}

ACTIVE ANOMALIES:
{anomaly_block}

RULES:
- Always cite which ARGO float (by WMO ID) or which live sensor reading supports your answer.
- If you do not know something or the retrieved data doesn't cover it, say so plainly.
  Do not invent ocean data, float IDs, or measurements.
- Keep answers focused and readable — use short paragraphs or bullet points for clarity.
"""


def answer_question(
    message: str,
    history: list[dict],
    sensor_context: dict | None,
    anomalies: list[dict],
) -> dict:
    """
    Returns {"answer": str, "sources": [...], "anomaly_context": bool}
    history: list of {"role": "user"|"assistant", "content": str}, most recent last.
    """
    audience = classify_audience(message)
    chunks = retrieve_relevant_chunks(message, top_k=5)

    system_prompt = _build_system_prompt(audience, sensor_context, anomalies)

    context_block = "\n\n".join(f"[ARGO context {i+1}] {c['text']}" for i, c in enumerate(chunks)) or \
        "No matching ARGO profiles found in the local cache for this query."

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-10:])  # last 10 turns
    messages.append(
        {
            "role": "user",
            "content": f"Relevant ARGO data retrieved for this question:\n{context_block}\n\nQuestion: {message}",
        }
    )

    if not settings.GROQ_API_KEY:
        return {
            "answer": (
                "GROQ_API_KEY is not configured, so I can't generate a live answer yet. "
                "Set it in your .env file to enable the chatbot."
            ),
            "sources": [],
            "anomaly_context": bool(anomalies),
        }

    try:
        resp = _get_client().chat.completions.create(
            model=settings.CHAT_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=800,
        )
        answer = resp.choices[0].message.content
    except Exception as exc:
        import traceback
        traceback.print_exc()
        logger.exception("Groq chat completion failed")
        answer = f"Groq error: {exc}"

    

    sources = [
        {
            "type": "argo_float",
            "ref": c["metadata"].get("wmo_id", "unknown"),
            "label": f"ARGO Float {c['metadata'].get('wmo_id', '?')} — {c['metadata'].get('profile_date', '?')}",
        }
        for c in chunks
    ]
    if sensor_context:
        sources.append(
            {
                "type": "sensor_reading",
                "ref": sensor_context.get("id", ""),
                "label": f"Live sensor {sensor_context['device_id']} @ {sensor_context['created_at']}",
            }
        )

    return {"answer": answer, "sources": sources, "anomaly_context": bool(anomalies)}
