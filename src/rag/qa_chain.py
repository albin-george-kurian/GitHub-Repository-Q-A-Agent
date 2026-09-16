from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from src.llm.groq_client import get_llm

SYSTEM_PROMPT = (
    "You are an assistant that answers questions about a specific GitHub repository "
    "using only the retrieved context below. Do not invent files, functions, or "
    "functionality that isn't shown in the context. If the context doesn't contain "
    "enough information to answer, clearly say the information could not be found "
    "in the indexed repository instead of guessing.\n\n"
    "Context:\n{context}"
)


def _format_docs(docs: list[Document]) -> str:
    return "\n\n".join(f"[{doc.metadata.get('source', 'unknown')}]\n{doc.page_content}" for doc in docs)


def build_qa_chain(vector_store: FAISS, top_k: int) -> RunnableLambda:
    retriever = vector_store.as_retriever(search_kwargs={"k": top_k})
    prompt = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", "{input}")])
    answer_chain = prompt | get_llm() | StrOutputParser()

    def _run(inputs: dict) -> dict:
        docs = retriever.invoke(inputs["input"])
        answer = answer_chain.invoke({"input": inputs["input"], "context": _format_docs(docs)})
        return {"answer": answer, "context": docs}

    return RunnableLambda(_run)


def answer_question(chain: RunnableLambda, question: str) -> dict:
    result = chain.invoke({"input": question})
    sources = sorted({doc.metadata.get("source", "unknown") for doc in result["context"]})
    return {"answer": result["answer"], "sources": sources}
