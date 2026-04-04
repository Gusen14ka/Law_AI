import httpx
import json
import os
import traceback
from fastapi import HTTPException

# URL для Ollama API, по умолчанию localhost
OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
# Модель для использования, по умолчанию mistral
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
# Размер чанка для анализа
CHUNK_SIZE = 6000

# Системный промпт для AI, указывающий на формат ответа JSON
SYSTEM_PROMPT = """Ты — юридический AI-помощник. Анализируй договоры и юридические документы.

Ответ ОБЯЗАТЕЛЬНО верни ТОЛЬКО в формате JSON (без markdown, без пояснений, только JSON):
{
  "summary": "Краткое описание документа (2-3 предложения)",
  "document_type": "Тип документа",
  "parties": ["Сторона 1", "Сторона 2"],
  "key_terms": [
    {
      "category": "Категория (Сроки / Ответственность / Штрафы / Права / Обязанности / Оплата)",
      "title": "Краткое название условия",
      "description": "Описание простым языком"
    }
  ],
  "risks": [
    {
      "level": "high / medium / low",
      "title": "Название риска",
      "description": "Описание риска простым языком",
      "recommendation": "Рекомендация"
    }
  ],
  "plain_language_summary": "Объяснение всего документа простым языком (4-6 предложений)"
}
Для поля "risks" вычленяй из документа атомарные риски, не старайся оъединить несколько в один
"""

# Промпт для последующих чанков, учитывающий предыдущий анализ
FOLLOWUP_SYSTEM_PROMPT = """Ты — юридический AI-помощник. Продолжаешь анализ договора на основе предыдущего анализа.

Предыдущий анализ: {previous_analysis}

Теперь проанализируй следующий чанк текста и ОБНОВИ анализ. Верни ТОЛЬКО JSON с обновленными полями (без markdown, без пояснений):
{{
  "summary": "Обновленное краткое описание всего документа",
  "document_type": "Тип документа (может остаться прежним)",
  "parties": ["Все стороны из всего документа"],
  "key_terms": [
    {{
      "category": "Категория",
      "title": "Краткое название условия",
      "description": "Описание простым языком"
    }}
  ],
  "risks": [
    {{
      "level": "high / medium / low",
      "title": "Название риска",
      "description": "Описание риска простым языком",
      "recommendation": "Рекомендация"
    }}
  ],
  "plain_language_summary": "Обновленное объяснение всего документа простым языком"
}}
Добавляй новые key_terms и risks из этого чанка, сохраняя предыдущие.
"""


class AIModule:
    # Класс для взаимодействия с AI моделью через Ollama
    
    async def analyze(self, text: str) -> str:
        # Разделение текста на чанки для полного анализа
        if len(text) <= CHUNK_SIZE:
            # Анализ всего текста сразу
            user_prompt = f"Проанализируй следующий документ:\n\n{text}"
            print(f"[AI] Sending to {OLLAMA_BASE_URL}, model={OLLAMA_MODEL}, chars={len(text)}")
            try:
                result = await self._call_ollama_stream_with_prompt(SYSTEM_PROMPT, user_prompt)
                print(f"[AI] Got response, length={len(result)}")
                return result
            except HTTPException:
                raise
            except Exception as e:
                print(f"[AI] Error: {e}")
                traceback.print_exc()
                raise HTTPException(status_code=503, detail=f"Ошибка Ollama: {e}")
        
        # Анализ по чанкам
        chunks = [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
        accumulated_analysis = None
        
        for idx, chunk in enumerate(chunks):
            if idx == 0:
                # Первый чанк
                system_prompt = SYSTEM_PROMPT
                user_prompt = f"Проанализируй следующий документ (часть {idx+1}/{len(chunks)}):\n\n{chunk}"
            else:
                # Последующие чанки
                system_prompt = FOLLOWUP_SYSTEM_PROMPT.format(previous_analysis=json.dumps(accumulated_analysis, ensure_ascii=False))
                user_prompt = f"Продолжи анализ документа. Часть {idx+1}/{len(chunks)}:\n\n{chunk}"
            
            print(f"[AI] Analyzing chunk {idx+1}/{len(chunks)}, chars={len(chunk)}")
            try:
                result = await self._call_ollama_stream_with_prompt(system_prompt, user_prompt)
                chunk_analysis = json.loads(result)
                if accumulated_analysis is None:
                    accumulated_analysis = chunk_analysis
                else:
                    accumulated_analysis = self._merge_analyses(accumulated_analysis, chunk_analysis)
                print(f"[AI] Chunk {idx+1} analyzed")
            except Exception as e:
                print(f"[AI] Error analyzing chunk {idx+1}: {e}")
                # Продолжить с остальными чанками или вернуть накопленное
                continue
        
        if accumulated_analysis:
            return json.dumps(accumulated_analysis, ensure_ascii=False)
        else:
            raise HTTPException(status_code=503, detail="Не удалось проанализировать документ")

    async def _call_ollama_stream_with_prompt(self, system_prompt: str, user_prompt: str) -> str:
        """Использование стриминга с кастомным системным промптом."""
        # Нет таймаута на чтение — мы используем стриминг, так что данные продолжают течь
        timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)

        chunks = []
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "stream": True,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 1500,
                        "num_ctx": 4096,
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

    def _merge_analyses(self, prev: dict, curr: dict) -> dict:
        """Объединение двух анализов."""
        merged = {}
        
        # Summary: конкатенировать
        prev_summary = prev.get("summary", "")
        curr_summary = curr.get("summary", "")
        merged["summary"] = f"{prev_summary} {curr_summary}".strip()
        
        # Document type: взять из curr, если есть
        merged["document_type"] = curr.get("document_type", prev.get("document_type", "Договор"))
        
        # Parties: объединить уникальные
        prev_parties = set(prev.get("parties", []))
        curr_parties = set(curr.get("parties", []))
        merged["parties"] = list(prev_parties | curr_parties)
        
        # Key terms: добавить новые из curr
        prev_terms = prev.get("key_terms", [])
        curr_terms = curr.get("key_terms", [])
        # Простая проверка на дубликаты по title
        existing_titles = {t.get("title") for t in prev_terms}
        new_terms = [t for t in curr_terms if t.get("title") not in existing_titles]
        merged["key_terms"] = prev_terms + new_terms
        
        # Risks: добавить все из curr
        prev_risks = prev.get("risks", [])
        curr_risks = curr.get("risks", [])
        merged["risks"] = prev_risks + curr_risks
        
        # Plain language summary: конкатенировать
        prev_plain = prev.get("plain_language_summary", "")
        curr_plain = curr.get("plain_language_summary", "")
        merged["plain_language_summary"] = f"{prev_plain} {curr_plain}".strip()
        
        return merged