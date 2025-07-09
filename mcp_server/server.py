from mcp.server.fastmcp import FastMCP
import os
import json
from typing import Dict, Any
from dotenv import load_dotenv
load_dotenv(override=True)

import chromadb
from openai import OpenAI

from llama_index.core import Settings, VectorStoreIndex, StorageContext
from llama_index.core.node_parser import SentenceSplitter
from llama_index.llms.openai import OpenAI as LlamaOpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.response_synthesizers import get_response_synthesizer, ResponseMode
from llama_index.core.prompts import PromptTemplate

# MCP 서버 생성
mcp = FastMCP("LawChat MCP Server")

# LlamaIndex 설정
llm = LlamaOpenAI(model="gpt-4o-mini", temperature=0.3, max_tokens=3500)
embed_model = OpenAIEmbedding(model="text-embedding-3-small")
Settings.llm = llm
Settings.embed_model = embed_model
Settings.node_parser = SentenceSplitter(chunk_size=1000, chunk_overlap=200)
Settings.num_output = 2000
Settings.context_window = 3900

# ChromaDB 연결
CHROMA_DB_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
chroma_collection = chroma_client.get_or_create_collection("law_cases")
vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
storage_context = StorageContext.from_defaults(vector_store=vector_store)
index = VectorStoreIndex.from_vector_store(vector_store=vector_store, storage_context=storage_context)

retriever = VectorIndexRetriever(index=index, similarity_top_k=10)

def get_legal_qa_prompt():
    """환경변수에서 법률 상담 프롬프트를 가져옵니다."""
    prompt_template = os.getenv("LEGAL_QA_PROMPT_TEMPLATE")

def get_openai_system_prompt():
    """환경변수에서 OpenAI 시스템 프롬프트를 가져옵니다."""
    return os.getenv("OPENAI_SYSTEM_PROMPT")


custom_qa_template = PromptTemplate(get_legal_qa_prompt())
response_synthesizer = get_response_synthesizer(
    response_mode=ResponseMode.COMPACT,
    llm=llm,
    text_qa_template=custom_qa_template
)
query_engine = RetrieverQueryEngine(
    retriever=retriever,
    response_synthesizer=response_synthesizer,
)

#판례 데이터 경로
LAW_DATA_PATH = os.path.join(os.path.dirname(__file__), "law_data")

@mcp.tool()
async def openai_chat(prompt: str, model: str = "gpt-4o-mini", temperature: float = 0.3, max_tokens: int = 1000) -> str:
    """OpenAI LLM 호출"""
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": get_openai_system_prompt()},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"OpenAI 호출 오류: {e}"


@mcp.tool()
async def chromadb_search(user_question: str, n_results: int = 3) -> Dict[
    str, Any]:
    """판례 검색 및 분석"""
    response_obj = await query_engine.aquery(user_question)
    analysis = response_obj.response

    # 중복 제거를 위한 딕셔너리
    unique_cases = {}
    seen_content = set()
    seen_case_numbers = set()

    for node in response_obj.source_nodes:
        meta = dict(node.metadata)
        file_path = meta.get("file")
        case_number = meta.get("case_number", "")
        content = node.get_content()

        content_hash = hash(content[:200])

        # 중복 체크: 파일명, 사건번호, 내용 해시
        if file_path:
            filename = os.path.basename(file_path)

            # 이미 같은 파일, 사건번호, 또는 내용이 있으면 건너뛰기
            if (filename in unique_cases or
                (case_number and case_number in seen_case_numbers) or
                content_hash in seen_content):
                continue

            # 중복 체크 기록
            if case_number:
                seen_case_numbers.add(case_number)
            seen_content.add(content_hash)

            # 파일 검색 및 case_data 추가
            possible_paths = [
                os.path.join(LAW_DATA_PATH, "civil_law_details", filename),
                os.path.join(LAW_DATA_PATH, "commercial_law_details", filename),
                os.path.join(LAW_DATA_PATH, filename)
            ]

            file_found = False
            for abs_path in possible_paths:
                if os.path.exists(abs_path):
                    try:
                        with open(abs_path, "r", encoding="utf-8") as f:
                            meta["case_data"] = json.load(f)
                        file_found = True
                        break
                    except Exception as e:
                        meta["case_data"] = {"error": f"원문 로드 실패: {e}"}
                        file_found = True
                        break

            if not file_found:
                meta["case_data"] = {"error": f"law_data에 해당 파일이 없습니다."}

            # 중복되지 않은 경우만 추가
            unique_cases[filename] = {
                "document": content,
                "metadata": meta,
                "distance": (1 - node.score) if node.score is not None else 0.5
            }
        else:
            # file 정보가 없는 경우
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique_key = f"no_file_{len(unique_cases)}"
                meta["case_data"] = {"error": "메타데이터에 file 정보가 없습니다."}
                unique_cases[unique_key] = {
                    "document": content,
                    "metadata": meta,
                    "distance": (
                            1 - node.score) if node.score is not None else 0.5
                }

        if len(unique_cases) >= n_results:
            break

    # 최대 n_results개까지만 반환
    unique_list = list(unique_cases.values())[:n_results]

    documents = [case["document"] for case in unique_list]
    metadatas = [case["metadata"] for case in unique_list]
    distances = [case["distance"] for case in unique_list]

    return {
        "analysis": analysis,
        "documents": [documents],
        "metadatas": metadatas,
        "distances": distances
    }


if __name__ == "__main__":
    mcp.run()
