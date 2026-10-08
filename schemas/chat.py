from datetime import datetime
from pydantic import BaseModel


class ChatMessageRequest(BaseModel):
    message: str
    session_id: str | None = None  # if omitted, a new session is created


class SourceRef(BaseModel):
    type: str  # "argo_float" | "sensor_reading"
    ref: str
    label: str


class ChatMessageResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[SourceRef]
    anomaly_context: bool


class ChatHistoryItem(BaseModel):
    role: str
    content: str
    sources: dict | list | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatHistoryItem]
