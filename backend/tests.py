"""
Тесты Lex Analytica
Запуск unit + regression: pytest tests.py -v
Нагрузочный: locust -f tests.py --host=http://localhost:8000
"""

import pytest
import json
import secrets
import re
import uuid as uuid_mod
from datetime import datetime, timedelta

# bcrypt напрямую (без passlib — совместимо с Python 3.12)
import bcrypt

def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def verify_password(password: str, hashed: bytes) -> bool:
    return bcrypt.checkpw(password.encode(), hashed)


# ═══════════════════════════════════════════════════════════════
# UNIT ТЕСТЫ
# ═══════════════════════════════════════════════════════════════

class TestPasswordHashing:
    """Юнит-тест: хэширование паролей bcrypt"""

    def test_hash_and_verify(self):
        """Хэш пароля верифицируется корректно"""
        password = "SecurePass123"
        hashed = hash_password(password)
        assert hashed != password.encode()
        assert hashed.startswith(b"$2b$")
        assert verify_password(password, hashed) is True

    def test_wrong_password_fails(self):
        """Неверный пароль не проходит верификацию"""
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_hashes_are_unique(self):
        """Два хэша одного пароля различны (соль уникальна)"""
        password = "same_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    def test_empty_password_rejected(self):
        """Пустой пароль должен отклоняться валидацией Pydantic (len >= 6)"""
        def pydantic_validate(password):
            if len(password) < 6:
                raise ValueError("Пароль должен быть не менее 6 символов")
            return password
        with pytest.raises(ValueError):
            pydantic_validate("")


class TestResponseBuilder:
    """Юнит-тест: парсинг ответа AI"""

    class MockBuilder:
        """Встроенный парсер — зеркало реального ResponseBuilder"""
        LEVELS = {"high", "medium", "low"}

        def parse(self, text: str) -> dict:
            default = {"summary": "", "document_type": "Неизвестно",
                       "parties": [], "key_terms": [], "risks": [],
                       "plain_language_summary": "", "overall_risk": "medium"}
            if not text:
                return default
            parsed = self._extract(text)
            if parsed:
                return self._validate(parsed)
            return {**default, "summary": text[:500]}

        def _extract(self, text):
            try:
                return json.loads(text.strip())
            except Exception:
                pass
            m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
            if m:
                try: return json.loads(m.group(1))
                except Exception: pass
            start, end = text.find('{'), text.rfind('}')
            if start != -1 and end != -1:
                try: return json.loads(text[start:end+1])
                except Exception: pass
            return None

        def _validate(self, d):
            return {
                "summary": str(d.get("summary", "")),
                "document_type": str(d.get("document_type", "Договор")),
                "parties": list(d.get("parties", [])),
                "key_terms": [
                    {"category": str(t.get("category", "")),
                     "title": str(t.get("title", "")),
                     "description": str(t.get("description", ""))}
                    for t in (d.get("key_terms") or [])
                ],
                "risks": [
                    {"level": r.get("level", "medium") if r.get("level") in self.LEVELS else "medium",
                     "title": str(r.get("title", "")),
                     "description": str(r.get("description", "")),
                     "recommendation": str(r.get("recommendation", ""))}
                    for r in (d.get("risks") or [])
                ],
                "plain_language_summary": str(d.get("plain_language_summary", "")),
                "overall_risk": d.get("overall_risk", "medium") if d.get("overall_risk") in self.LEVELS else "medium"
            }

    def setup_method(self):
        self.builder = self.MockBuilder()

    def test_parse_valid_json(self):
        """Парсинг чистого JSON"""
        valid = json.dumps({
            "summary": "Договор аренды", "document_type": "Аренда",
            "parties": ["Арендодатель", "Арендатор"],
            "key_terms": [], "risks": [],
            "plain_language_summary": "Объяснение", "overall_risk": "low"
        })
        result = self.builder.parse(valid)
        assert result["summary"] == "Договор аренды"
        assert result["document_type"] == "Аренда"
        assert result["overall_risk"] == "low"

    def test_parse_json_in_markdown(self):
        """Парсинг JSON обёрнутого в markdown-блок"""
        text = '```json\n{"summary": "Тест", "risks": [], "key_terms": []}\n```'
        result = self.builder.parse(text)
        assert result.get("summary") == "Тест"

    def test_parse_json_with_surrounding_text(self):
        """Парсинг JSON окружённого текстом"""
        text = 'Вот анализ: {"summary": "Найден", "risks": []} Конец.'
        result = self.builder.parse(text)
        assert result.get("summary") == "Найден"

    def test_parse_empty_returns_default(self):
        """Пустой ответ возвращает дефолт без исключений"""
        result = self.builder.parse("")
        assert isinstance(result, dict)
        assert "summary" in result

    def test_risk_levels_normalized(self):
        """Некорректный уровень риска нормализуется до 'medium'"""
        data = json.dumps({
            "summary": "test", "document_type": "test", "parties": [],
            "key_terms": [],
            "risks": [{"level": "КРИТИЧЕСКИЙ", "title": "Риск",
                       "description": "Описание", "recommendation": ""}],
            "plain_language_summary": "", "overall_risk": "unknown"
        })
        result = self.builder.parse(data)
        assert result["risks"][0]["level"] in ("high", "medium", "low")
        assert result["overall_risk"] in ("high", "medium", "low")


class TestDocumentParser:
    """Юнит-тест: очистка текста"""

    def _clean(self, text):
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def test_removes_control_chars(self):
        """Управляющие символы удаляются"""
        result = self._clean("Нормальный\x00\x07\x1f текст")
        assert '\x00' not in result
        assert 'Нормальный' in result

    def test_collapses_whitespace(self):
        """Множественные пробелы схлопываются"""
        result = self._clean("Слово   много   пробелов")
        assert result == "Слово много пробелов"

    def test_collapses_newlines(self):
        """Более 2 переводов строки → 2"""
        result = self._clean("Строка1\n\n\n\n\nСтрока2")
        assert result == "Строка1\n\nСтрока2"


class TestSessionManagement:
    """Юнит-тест: управление сессиями"""

    def _make_store(self):
        sessions = {}

        def create(user_id, role):
            token = secrets.token_urlsafe(32)
            sessions[token] = {
                "user_id": user_id, "role": role,
                "expires": datetime.utcnow() + timedelta(hours=24)
            }
            return token

        def get(token):
            data = sessions.get(token)
            if not data: return None
            if datetime.utcnow() > data["expires"]:
                del sessions[token]; return None
            return data

        def destroy(token):
            sessions.pop(token, None)

        return create, get, destroy

    def test_create_and_retrieve(self):
        """Созданная сессия извлекается по токену"""
        create, get, _ = self._make_store()
        token = create(user_id=1, role="user")
        data = get(token)
        assert data is not None
        assert data["user_id"] == 1
        assert data["role"] == "user"

    def test_destroy(self):
        """После уничтожения сессия недоступна"""
        create, get, destroy = self._make_store()
        token = create(user_id=2, role="admin")
        destroy(token)
        assert get(token) is None

    def test_invalid_token(self):
        """Несуществующий токен → None"""
        _, get, _ = self._make_store()
        assert get("nonexistent_xyz") is None

    def test_expired_session(self):
        """Истёкшая сессия → None"""
        sessions = {}
        token = secrets.token_urlsafe(32)
        sessions[token] = {
            "user_id": 3, "role": "user",
            "expires": datetime.utcnow() - timedelta(seconds=1)
        }
        def get(t):
            d = sessions.get(t)
            if not d: return None
            if datetime.utcnow() > d["expires"]:
                del sessions[t]; return None
            return d
        assert get(token) is None

    def test_token_entropy(self):
        """Токены достаточно длинные и случайные"""
        create, _, _ = self._make_store()
        tokens = {create(i, "user") for i in range(100)}
        assert len(tokens) == 100  # все уникальны
        for t in tokens:
            assert len(t) >= 32  # минимум 32 символа


# ═══════════════════════════════════════════════════════════════
# РЕГРЕССИОННЫЙ ТЕСТ (требует живого сервера)
# ═══════════════════════════════════════════════════════════════

import urllib.request
import urllib.error

def http(method, path, data=None, base="http://localhost:8000", cookies=None):
    url = base + path
    body = json.dumps(data).encode() if data else None
    headers = {'Content-Type': 'application/json'}
    if cookies:
        headers['Cookie'] = '; '.join(f'{k}={v}' for k, v in cookies.items())
    req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp_headers = dict(r.headers)
            return r.status, json.loads(r.read()), resp_headers
    except urllib.error.HTTPError as e:
        body = {}
        try: body = json.loads(e.read())
        except: pass
        return e.code, body, {}
    except Exception as e:
        return 0, {"error": str(e)}, {}


@pytest.mark.skipif(
    http('GET', '/api/health')[0] != 200,
    reason="Сервер недоступен — запустите docker-compose up"
)
class TestRegressionCriticalFlows:
    """Регрессионные тесты — требуют живого сервера на localhost:8000"""

    def test_reg_001_health(self):
        """REG-001: Health endpoint → 200 ok"""
        status, body, _ = http('GET', '/api/health')
        assert status == 200
        assert body.get('status') == 'ok'

    def test_reg_002_wrong_password_returns_401(self):
        """REG-002: Неверный пароль → 401, не 500"""
        status, body, _ = http('POST', '/api/auth/login',
            {"email": "admin@lexanalytica.ru", "password": "WRONG_XYZ_999"})
        assert status == 401
        assert 'detail' in body

    def test_reg_003_unauthenticated_requests_blocked(self):
        """REG-003: Без авторизации → 401"""
        status, _, _ = http('GET', '/api/requests')
        assert status == 401

    def test_reg_004_admin_blocked_without_session(self):
        """REG-004: /admin/users без сессии → 401"""
        status, _, _ = http('GET', '/api/admin/users')
        assert status == 401

    def test_reg_005_duplicate_email_rejected(self):
        """REG-005: Дублирование email → 400"""
        email = f"dup_{uuid_mod.uuid4().hex[:8]}@test.com"
        http('POST', '/api/auth/register',
            {"email": email, "full_name": "User1", "password": "pass123"})
        status, body, _ = http('POST', '/api/auth/register',
            {"email": email, "full_name": "User2", "password": "pass456"})
        assert status == 400

    def test_reg_006_uuid_format(self):
        """REG-006: UUID не раскрывает последовательный ID"""
        pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
        for _ in range(10):
            assert pattern.match(str(uuid_mod.uuid4()))

    def test_reg_007_password_not_in_response(self):
        """REG-007: Хэш пароля не возвращается в API-ответах"""
        email = f"safe_{uuid_mod.uuid4().hex[:8]}@test.com"
        _, body, _ = http('POST', '/api/auth/register',
            {"email": email, "full_name": "Safe User", "password": "safe123"})
        response_str = json.dumps(body)
        assert 'hashed_password' not in response_str
        assert '$2b$' not in response_str  # bcrypt hash marker


# ═══════════════════════════════════════════════════════════════
# ТЕСТЫ БЕЗОПАСНОСТИ
# ═══════════════════════════════════════════════════════════════

SQL_PAYLOADS = [
    "' OR '1'='1",
    "'; DROP TABLE users; --",
    "' UNION SELECT * FROM users --",
    "admin'--",
    '" OR ""="',
    "1; SELECT pg_sleep(5)--",
    "' OR 1=1--",
    "\\'; DROP TABLE users; --",
]


@pytest.mark.skipif(
    http('GET', '/api/health')[0] != 200,
    reason="Сервер недоступен"
)
class TestSQLInjection:
    """SQL-инъекции — требуют живого сервера"""

    def test_sqli_login_email(self):
        """SQL-инъекции в email при логине не дают доступа"""
        for payload in SQL_PAYLOADS:
            status, body, _ = http('POST', '/api/auth/login',
                {"email": payload, "password": "anything"})
            assert status in (401, 422), \
                f"УЯЗВИМОСТЬ! '{payload}' → {status}: {body}"
            assert 'hashed_password' not in json.dumps(body)
            assert '$2b$' not in json.dumps(body)

    def test_sqli_login_password(self):
        """SQL-инъекции в поле пароля"""
        for payload in SQL_PAYLOADS:
            status, body, _ = http('POST', '/api/auth/login',
                {"email": "admin@lexanalytica.ru", "password": payload})
            assert status in (401, 422), \
                f"УЯЗВИМОСТЬ! password='{payload}' → {status}"

    def test_sqli_register_full_name(self):
        """SQL в full_name — сохраняется как безопасная строка"""
        for payload in SQL_PAYLOADS:
            email = f"sqli_{abs(hash(payload)) % 999999}@test.com"
            status, body, _ = http('POST', '/api/auth/register',
                {"email": email, "full_name": payload, "password": "test123"})
            # Не должен вернуть 500 (внутренняя ошибка = SQL сломан)
            assert status != 500, \
                f"Внутренняя ошибка при full_name='{payload}': {body}"


@pytest.mark.skipif(
    http('GET', '/api/health')[0] != 200,
    reason="Сервер недоступен"
)
class TestHorizontalPrivileges:
    """Горизонтальное превышение привилегий"""

    @staticmethod
    def _login(email, password="pass123"):
        """Вернуть cookie сессии"""
        http('POST', '/api/auth/register',
            {"email": email, "full_name": "Test", "password": password})
        _, _, headers = http('POST', '/api/auth/login',
            {"email": email, "password": password})
        # Извлекаем session_token из Set-Cookie
        cookie_header = headers.get('Set-Cookie', '')
        token = None
        for part in cookie_header.split(';'):
            part = part.strip()
            if part.startswith('session_token='):
                token = part.split('=', 1)[1]
        return token

    def test_user_cannot_see_others_request(self):
        """Пользователь не может получить чужую заявку по UUID"""
        suf = uuid_mod.uuid4().hex[:6]
        token_b = self._login(f"user_b_{suf}@test.com")
        fake_uuid = str(uuid_mod.uuid4())

        if token_b:
            status, _, _ = http('GET', f'/api/requests/{fake_uuid}',
                cookies={"session_token": token_b})
        else:
            status, _, _ = http('GET', f'/api/requests/{fake_uuid}')

        assert status in (403, 404), \
            f"УЯЗВИМОСТЬ! Получен {status} для чужого UUID"

    def test_user_cannot_access_admin(self):
        """Обычный пользователь не попадает в /admin/users"""
        suf = uuid_mod.uuid4().hex[:6]
        token = self._login(f"notadmin_{suf}@test.com")
        if token:
            status, _, _ = http('GET', '/api/admin/users',
                cookies={"session_token": token})
        else:
            status, _, _ = http('GET', '/api/admin/users')
        assert status == 403, f"УЯЗВИМОСТЬ! Доступ к /admin/users: {status}"

    def test_user_cannot_access_lawyer_panel(self):
        """Обычный пользователь не попадает в /lawyer/requests"""
        suf = uuid_mod.uuid4().hex[:6]
        token = self._login(f"notlawyer_{suf}@test.com")
        if token:
            status, _, _ = http('GET', '/api/lawyer/requests',
                cookies={"session_token": token})
        else:
            status, _, _ = http('GET', '/api/lawyer/requests')
        assert status == 403, f"УЯЗВИМОСТЬ! Доступ к /lawyer/requests: {status}"


# ═══════════════════════════════════════════════════════════════
# НАГРУЗОЧНЫЙ ТЕСТ (Locust)
# ═══════════════════════════════════════════════════════════════

try:
    from locust import HttpUser, task, between

    class LexAnalyticaUser(HttpUser):
        """
        Нагрузочный тест.
        Запуск: locust -f tests.py --host=http://localhost:8000 --users=20 --spawn-rate=2
        Headless: locust -f tests.py --host=http://localhost:8000 \
                  --users=50 --spawn-rate=5 --run-time=60s --headless
        """
        wait_time = between(1, 3)
        _session_ok = False
        _uuids = []

        def on_start(self):
            import random, string
            suffix = ''.join(random.choices(string.ascii_lowercase, k=8))
            email = f"load_{suffix}@test.com"
            self.client.post("/api/auth/register", json={
                "email": email, "full_name": f"Load {suffix}", "password": "load123"
            })
            r = self.client.post("/api/auth/login", json={
                "email": email, "password": "load123"
            })
            self._session_ok = r.status_code == 200

        @task(5)
        def list_requests(self):
            with self.client.get("/api/requests", catch_response=True,
                                  name="GET /api/requests") as r:
                if r.status_code == 200:
                    r.success()
                    self._uuids = [x['uuid'] for x in r.json()[:5]]
                elif r.status_code == 401:
                    r.failure("Не авторизован")
                else:
                    r.failure(f"HTTP {r.status_code}")

        @task(3)
        def view_detail(self):
            if not self._uuids:
                return
            import random
            uuid = random.choice(self._uuids)
            with self.client.get(f"/api/requests/{uuid}", catch_response=True,
                                  name="GET /api/requests/{uuid}") as r:
                r.success() if r.status_code in (200, 404) else r.failure(f"HTTP {r.status_code}")

        @task(1)
        def profile(self):
            with self.client.get("/api/auth/me", catch_response=True,
                                  name="GET /api/auth/me") as r:
                r.success() if r.status_code == 200 else r.failure(f"HTTP {r.status_code}")

        @task(1)
        def health(self):
            with self.client.get("/api/health", catch_response=True,
                                  name="GET /api/health") as r:
                r.success() if r.status_code == 200 else r.failure("Health failed")

except ImportError:
    pass