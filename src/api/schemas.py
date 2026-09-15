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
    question: str = Field(..., min_length=1)


class QueryResponse(BaseModel):
    answer: str
    sources: list[str]


class ErrorResponse(BaseModel):
    detail: str
