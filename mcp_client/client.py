import os
import json
from typing import Dict, Any
from langchain_mcp_adapters.client import MultiServerMCPClient


class LawChatClient:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.client = None
        self.servers = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """config.json에서 MCP 서버 설정 로드"""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get("mcpServers", {})

    async def initialize(self):
        """MCP 클라이언트 초기화"""
        if not self.client:
            self.client = MultiServerMCPClient(self.servers)

    async def search_cases(self, query: str, max_results: int = 3) -> Dict[str, Any]:
        """판례 검색"""
        if not self.client:
            await self.initialize()

        try:
            async with self.client.session("lawchat") as session:
                result = await session.call_tool(
                    "chromadb_search",
                    user_question=query,
                    n_results=max_results
                )

                if hasattr(result, 'content') and result.content:
                    if isinstance(result.content, list) and len(result.content) > 0:
                        text_content = result.content[0]
                        if hasattr(text_content, 'text'):
                            json_str = text_content.text
                        else:
                            json_str = str(text_content)
                    else:
                        json_str = str(result.content)

                    try:
                        import json as json_module
                        parsed_result = json_module.loads(json_str)
                        return parsed_result
                    except json_module.JSONDecodeError:
                        return {
                            "analysis": json_str,
                            "documents": [[]],
                            "metadatas": [],
                            "distances": []
                        }
                else:
                    return {
                        "analysis": "MCP 서버에서 빈 응답을 받았습니다.",
                        "documents": [[]],
                        "metadatas": [],
                        "distances": []
                    }
        except Exception as e:
            return {
                "analysis": f"검색 중 오류가 발생했습니다: {e}",
                "documents": [[]],
                "metadatas": [],
                "distances": []
            }

    async def openai_consult(self, prompt: str, model: str = "gpt-4o-mini") -> str:
        if not self.client:
            await self.initialize()

        try:
            async with self.client.session("lawchat") as session:
                result = await session.call_tool(
                    "openai_chat",
                    prompt=prompt,
                    model=model
                )
                return result
        except Exception as e:
            return f"상담 중 오류가 발생했습니다: {e}"

    async def close(self):
        """MCP 클라이언트 연결 종료"""
        if self.client and hasattr(self.client, 'close'):
            await self.client.close()
