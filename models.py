from pydantic import BaseModel
from typing import Any, List, Optional, Dict

class User(BaseModel):
    id: str
    email: str
    displayName: Optional[str] = None

    class Config:
        from_attributes = True

class Response(BaseModel):
    id: str
    source: str
    responseType: str
    payload: Optional[Any]
    requestedAt: Optional[int] = None
    respondedAt: Optional[int] = None

    class Config:
        from_attributes = True

class PartialResponse(BaseModel):
    source: str
    responseType: str
    payload: Optional[Any] = {}
    requestedAt: Optional[int] = None
    respondedAt: Optional[int] = None


class Block(BaseModel):
    id: str
    inputText: str
    responseIds: List[str]
    createdBy: User
    createdAt: int
    responses: Optional[List[Response]] = None

    class Config:
        from_attributes = True

class Conversation(BaseModel):
    id: str
    createdBy: User
    createdAt: int
    updatedAt: int
    status: str
    summaryText: Optional[str]
    summaryType: Optional[str]
    blockIds: List[str]
    blocks: Optional[List[Block]] = None

    class Config:
        from_attributes = True

class PartialConversation(BaseModel):
    createdBy: User
    status: Optional[str] = None
    summaryText: Optional[str] = None
    summaryType: Optional[str] = None
    blockIds: Optional[List[str]] = None
    users: Optional[List[Dict]] = None
    session: Optional[Dict] = None
    blocks: Optional[List[Dict]] = None
