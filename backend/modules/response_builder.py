import json
import re

DEFAULT = {
    "summary": "",
    "document_type": "Неизвестно",
    "parties": [],
    "key_terms": [],
    "risks": [],
    "plain_language_summary": "",
    "overall_risk": "medium"
}


class ResponseBuilder:
    def parse(self, text: str) -> dict:
        if not text:
            return DEFAULT.copy()
        parsed = self._extract_json(text)
        if parsed:
            return self._validate(parsed)
        return {**DEFAULT, "summary": text[:500]}

    def _extract_json(self, text: str) -> dict | None:
        try:
            return json.loads(text.strip())
        except Exception:
            pass

        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass

        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
        return None

    def _validate(self, d: dict) -> dict:
        levels = {"high", "medium", "low"}
        return {
            "summary": str(d.get("summary", "")),
            "document_type": str(d.get("document_type", "Договор")),
            "parties": list(d.get("parties", [])),
            "key_terms": [
                {
                    "category": str(t.get("category", "")),
                    "title": str(t.get("title", "")),
                    "description": str(t.get("description", ""))
                }
                for t in (d.get("key_terms") or [])
            ],
            "risks": [
                {
                    "level": r.get("level", "medium") if r.get("level") in levels else "medium",
                    "title": str(r.get("title", "")),
                    "description": str(r.get("description", "")),
                    "recommendation": str(r.get("recommendation", ""))
                }
                for r in (d.get("risks") or [])
            ],
            "plain_language_summary": str(d.get("plain_language_summary", "")),
            "overall_risk": d.get("overall_risk", "medium") if d.get("overall_risk") in levels else "medium"
        }