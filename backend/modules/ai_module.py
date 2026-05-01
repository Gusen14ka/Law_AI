import httpx
import json
import os
import traceback
from fastapi import HTTPException

OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral-nemo:12b")

SYSTEM_PROMPT = """Ты — юридический AI-помощник. Анализируй договоры и юридические документы на русском языке.

Ответ верни ТОЛЬКО в формате JSON (без markdown, без пояснений):
{
  "summary": "Краткое описание документа (2-3 предложения)",
  "document_type": "Тип документа",
  "parties": ["Сторона 1", "Сторона 2"],
  "key_terms": [
    {
      "category": "Сроки / Ответственность / Штрафы / Права / Обязанности / Оплата",
      "title": "Краткое название условия",
      "description": "Описание простым языком"
    }
  ],
  "risks": [
    {
      "level": "high / medium / low",
      "title": "Название риска",
      "description": "Описание риска простым языком",
      "recommendation": "Конкретная рекомендация"
    }
  ],
  "plain_language_summary": "Объяснение всего документа простым языком (4-6 предложений)",
  "overall_risk": "high / medium / low"
}"""


class AIModule:
    async def check_model(self) -> bool:
        """Check if model is available in Ollama."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
                models = [m["name"] for m in r.json().get("models", [])]
                return any(OLLAMA_MODEL.split(":")[0] in m for m in models)
        except Exception:
            return False

    async def analyze(self, text: str) -> str:
        max_chars = 10000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[Документ обрезан]"

        user_prompt = f"Проанализируй следующий документ:\n\n{text}"

        print(f"[AI] model={OLLAMA_MODEL} url={OLLAMA_BASE_URL} chars={len(text)}")

        try:
            result = await self._stream(user_prompt)
            print(f"[AI] Done, response_len={len(result)}")
            return result
        except HTTPException:
            raise
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=503, detail=f"Ошибка AI: {e}")

    async def _stream(self, user_prompt: str) -> str:
        timeout = httpx.Timeout(connect=15.0, read=None, write=30.0, pool=10.0)
        chunks = []

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    "stream": True,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 2048,
                        "num_ctx": 8192,
                    }
                }
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        token = data.get("message", {}).get("content", "")
                        if token:
                            chunks.append(token)
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

        return "".join(chunks)
