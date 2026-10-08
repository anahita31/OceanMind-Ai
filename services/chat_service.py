from sqlalchemy.orm import Session
from sqlalchemy import desc

from models.conversation import ChatSession, ChatMessage
from models.sensor import SensorReading
from models.anomaly import Anomaly
from core.rag_pipeline import answer_question


def get_or_create_session(db: Session, session_id: str | None) -> ChatSession:
    if session_id:
        existing = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        if existing:
            return existing
    session = ChatSession()
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _reading_to_context(r: SensorReading | None) -> dict | None:
    if not r:
        return None
    return {
        "id": r.id, "device_id": r.device_id, "lat": r.lat, "lon": r.lon,
        "temp_c": r.temp_c, "tds_ppm": r.tds_ppm, "pressure_hpa": r.pressure_hpa,
        "created_at": r.created_at.isoformat(),
    }


def _anomaly_to_context(a: Anomaly) -> dict:
    return {
        "anomaly_type": a.anomaly_type, "severity": a.severity,
        "description": a.description, "created_at": a.created_at.isoformat(),
    }


def handle_message(db: Session, message: str, session_id: str | None) -> dict:
    session = get_or_create_session(db, session_id)

    history_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in history_rows[-10:]]

    latest_reading = (
        db.query(SensorReading).order_by(desc(SensorReading.created_at)).first()
    )
    active_anomalies = (
        db.query(Anomaly).filter(Anomaly.resolved.is_(False)).order_by(desc(Anomaly.created_at)).limit(5).all()
    )

    sensor_context = _reading_to_context(latest_reading)
    anomaly_context = [_anomaly_to_context(a) for a in active_anomalies]

    result = answer_question(message, history, sensor_context, anomaly_context)

    db.add(ChatMessage(session_id=session.session_id, role="user", content=message))
    db.add(
        ChatMessage(
            session_id=session.session_id, role="assistant",
            content=result["answer"], sources=result["sources"],
        )
    )
    db.commit()

    return {"session_id": session.session_id, **result}


def get_history(db: Session, session_id: str) -> list[ChatMessage]:
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )


def clear_history(db: Session, session_id: str) -> None:
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.commit()
