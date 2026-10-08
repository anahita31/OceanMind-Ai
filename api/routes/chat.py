from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db
from schemas.chat import (
    ChatMessageRequest, ChatMessageResponse, ChatHistoryResponse, ChatHistoryItem, SourceRef,
)
from services.chat_service import handle_message, get_history, clear_history
from models.conversation import ChatSession

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/message", response_model=ChatMessageResponse)
def send_message(payload: ChatMessageRequest, db: Session = Depends(get_db)):
    result = handle_message(db, payload.message, payload.session_id)
    sources = [SourceRef(**s) for s in result["sources"]]
    return ChatMessageResponse(
        session_id=result["session_id"], answer=result["answer"],
        sources=sources, anomaly_context=result["anomaly_context"],
    )


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
def history(session_id: str, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = get_history(db, session_id)
    return ChatHistoryResponse(
        session_id=session_id,
        messages=[ChatHistoryItem.model_validate(m) for m in messages],
    )


@router.delete("/history/{session_id}")
def delete_history(session_id: str, db: Session = Depends(get_db)):
    clear_history(db, session_id)
    return {"status": "cleared", "session_id": session_id}
