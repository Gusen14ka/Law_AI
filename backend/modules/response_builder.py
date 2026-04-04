import json
import re
from datetime import datetime
from typing import Any

# Ответ по умолчанию, если анализ не удался
DEFAULT_RESPONSE = {
    "summary": "Анализ не удался. Попробуйте ещё раз.",
    "document_type": "Неизвестно",
    "parties": [],
    "key_terms": [],
    "risks": [],
    "plain_language_summary": ""
}


class ResponseBuilder:
    # Класс для построения ответа API из данных анализа AI
    
    def parse_ai_response(self, ai_text: str) -> dict:
        """Извлечение структурированного JSON из ответа AI."""
        
        if not ai_text or not ai_text.strip():
            return DEFAULT_RESPONSE.copy()
        
        # Попытка найти JSON блок в ответе
        parsed = self._try_extract_json(ai_text)
        if parsed:
            return self._validate_structure(parsed)
        
        # Fallback: вернуть сырой текст как summary
        return {
            **DEFAULT_RESPONSE,
            "summary": ai_text[:500],
            "plain_language_summary": ai_text[:1000]
        }

    def _try_extract_json(self, text: str) -> dict | None:
        """Попытка извлечь JSON из текста с использованием нескольких стратегий."""
        
        # Стратегия 1: парсинг всего текста
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # Стратегия 2: поиск JSON в блоках кода
        code_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1))
            except json.JSONDecodeError:
                pass
        
        # Стратегия 3: поиск наибольшего блока {...}
        matches = list(re.finditer(r'\{', text))
        for match in reversed(matches):
            start = match.start()
            # Поиск соответствующей закрывающей скобки
            depth = 0
            for i, ch in enumerate(text[start:]):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        candidate = text[start:start + i + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break
        
        return None

    def _validate_structure(self, data: dict) -> dict:
        """Обеспечение наличия требуемых полей с правильными типами."""
        result = {}
        
        result["summary"] = str(data.get("summary", ""))
        result["document_type"] = str(data.get("document_type", "Договор"))
        
        parties = data.get("parties", [])
        result["parties"] = parties if isinstance(parties, list) else []
        
        key_terms = data.get("key_terms", [])
        result["key_terms"] = [
            {
                "category": str(t.get("category", "Условие")),
                "title": str(t.get("title", "")),
                "description": str(t.get("description", ""))
            }
            for t in (key_terms if isinstance(key_terms, list) else [])
        ]
        
        risks = data.get("risks", [])
        result["risks"] = [
            {
                "level": r.get("level", "medium") if r.get("level") in ("high", "medium", "low") else "medium",
                "title": str(r.get("title", "")),
                "description": str(r.get("description", "")),
                "recommendation": str(r.get("recommendation", ""))
            }
            for r in (risks if isinstance(risks, list) else [])
        ]
        
        result["plain_language_summary"] = str(data.get("plain_language_summary", ""))
        
        return result

    def build_response(self, filename: str, text_length: int, structured: dict) -> dict:
        """Сборка финального ответа API."""
        return {
            "success": True,
            "filename": filename,
            "analyzed_at": datetime.utcnow().isoformat() + "Z",
            "document_stats": {
                "characters": text_length,
                "words": text_length // 5  # приблизительно
            },
            "analysis": structured
        }
