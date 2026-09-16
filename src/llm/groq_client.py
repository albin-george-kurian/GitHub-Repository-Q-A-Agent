from langchain_groq import ChatGroq

from src.config import settings


def get_llm() -> ChatGroq:
    return ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key, temperature=0)
