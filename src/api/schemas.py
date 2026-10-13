from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class IndexRequest(BaseModel):
    repo_url: HttpUrl = Field(..., description="URL of a public GitHub repository")
    force_reindex: bool = Field(False, description="Rebuild the index even if one already exists")


class IndexResponse(BaseModel):
    repo_url: str
    reused_existing: bool
    num_chunks: int | None


class QueryRequest(BaseModel):
    repo_url: HttpUrl = Field(..., description="URL of a previously indexed GitHub repository")
    question: str = Field(..., min_length=1, max_length=2000)
    chat_id: str | None = Field(None, description="Continue this chat; omit to start a new one")


class QueryResponse(BaseModel):
    answer: str
    sources: list[str]
    chat_id: str
    standalone_question: str | None = Field(None, description="The rewritten question used for search, if any")
    memory_saved: str | None = Field(None, description="Fact stored by an explicit 'remember …' message")


class ChatSummary(BaseModel):
    id: str
    repo_url: str
    title: str
    updated_at: float


class MessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    sources: list[str]
    standalone_question: str | None
    created_at: float


class ChatDetail(ChatSummary):
    messages: list[MessageOut]


class MemoryOut(BaseModel):
    id: str
    content: str
    source: Literal["explicit", "auto"]
    created_at: float


class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=3, max_length=300)


class ErrorResponse(BaseModel):
    detail: str
