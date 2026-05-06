"""
Нагрузочный тест Lex Analytica.

Три типа пользователей:
  UserBehavior   — загружают PDF, смотрят заявки, отправляют юристу, дают CSAT/NPS/CES
  LawyerBehavior — берут заявки, отправляют заключения
  AdminBehavior  — смотрят статистику

Запуск (веб UI на http://localhost:8089):
  locust -f load_test.py --host=http://localhost:8000

Headless (рекомендуется для начала: 20 users, 2 юриста, 1 admin):
  locust -f load_test.py --host=http://localhost:8000 \
         --users=23 --spawn-rate=2 --run-time=120s --headless --html=report.html

Перед запуском с юристами:
  1. Запустите хотя бы один раз с флагом --tags setup:
     locust -f load_test.py --host=http://localhost:8000 --tags setup \
            --users=1 --run-time=10s --headless
  2. В admin-панели (http://localhost:5173) назначьте роль lawyer
     для lawyer1@loadtest.com, lawyer2@loadtest.com, lawyer3@loadtest.com
"""

import random
import string
import io
import json
import time
import logging
from locust import HttpUser, task, between, tag
from locust.exception import RescheduleTask

logger = logging.getLogger(__name__)

# ── PDF-генератор ─────────────────────────────────────────────────────────────

CONTRACT_TEXTS = [
    "ДОГОВОР АРЕНДЫ ПОМЕЩЕНИЯ г. Москва 2025. Арендодатель ООО СтройИнвест передаёт "
    "Арендатору ИП Петров помещение площадью 45 кв.м по адресу ул. Ленина 10 офис 5. "
    "Срок аренды 12 месяцев. Арендная плата 75000 рублей в месяц. "
    "При просрочке оплаты пеня 0.5 процента в день. Залог 150000 рублей.",

    "ТРУДОВОЙ ДОГОВОР. Работодатель АО ТехноПром принимает Сидорову Марию на должность "
    "Senior Python Developer. Оклад 280000 рублей. Испытательный срок 3 месяца. "
    "Сверхурочная работа оплачивается по двойной ставке. "
    "Запрет разглашения коммерческой тайны в течение 3 лет после увольнения.",

    "ДОГОВОР ОКАЗАНИЯ УСЛУГ. Исполнитель ИП Козлов разрабатывает корпоративный сайт "
    "для Заказчика ООО МедиаГрупп. Срок 45 рабочих дней. Стоимость 350000 рублей. "
    "Предоплата 50 процентов. Штраф за задержку 1 процент в день. "
    "Приёмка работ в течение 10 дней или автоматическое подписание.",

    "ДОГОВОР ПОСТАВКИ. Поставщик ООО ТоргПлюс поставляет товары Покупателю ЗАО РетейлСеть. "
    "Срок поставки 14 рабочих дней. Отсрочка платежа 30 дней. "
    "Пени за просрочку 0.3 процента в день. "
    "При некачественном товаре замена в течение 5 рабочих дней.",
]


def make_pdf(text: str) -> bytes:
    """
    Генерирует валидный PDF с правильными xref-смещениями.
    Предыдущая версия имела hardcoded startxref=9, что вызывало
    ошибку "trailer can not be read" в PyPDF2.
    """
    # Только ASCII-безопасные символы для PDF-строки
    safe = ''.join(
        c if (32 <= ord(c) < 127 and c not in '()\\') else ' '
        for c in text[:800]
    )

    stream_content = f"BT /F1 9 Tf 40 750 Td 20 TL ({safe}) Tj ET"
    stream_bytes = stream_content.encode('latin-1')
    stream_len = len(stream_bytes)

    parts = []
    offsets = {}

    header = b"%PDF-1.4\n"
    parts.append(header)
    pos = len(header)

    def add_obj(n, content_str):
        nonlocal pos
        offsets[n] = pos
        obj = f"{n} 0 obj\n{content_str}\nendobj\n".encode('latin-1')
        parts.append(obj)
        pos += len(obj)

    add_obj(1, "<</Type /Catalog /Pages 2 0 R>>")
    add_obj(2, "<</Type /Pages /Kids [3 0 R] /Count 1>>")
    add_obj(3, "<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources <</Font <</F1 5 0 R>>>>>>")
    add_obj(4, f"<</Length {stream_len}>>\nstream\n{stream_content}\nendstream")
    add_obj(5, "<</Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding>>")

    xref_offset = pos
    xref = b"xref\n0 6\n0000000000 65535 f \n"
    for i in range(1, 6):
        xref += f"{offsets[i]:010d} 00000 n \n".encode()

    parts.append(xref)
    parts.append(
        f"trailer\n<</Size 6 /Root 1 0 R>>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return b"".join(parts)


# ── Базовый класс ─────────────────────────────────────────────────────────────

class LexBase(HttpUser):
    abstract = True

    def _suffix(self, n=8):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

    def _login(self, email: str, password: str, full_name: str, label: str) -> bool:
        """Регистрация (игнорируем 400=уже есть) + логин."""
        with self.client.post(
            "/api/auth/register",
            json={"email": email, "full_name": full_name, "password": password},
            name=f"POST /auth/register [{label}]",
            catch_response=True
        ) as r:
            # 200 = создан, 400 = уже существует — оба ок
            if r.status_code in (200, 400):
                r.success()
            else:
                r.failure(f"Register unexpected: {r.status_code}")
                return False

        with self.client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
            name=f"POST /auth/login [{label}]",
            catch_response=True
        ) as r:
            if r.status_code == 200:
                r.success()
                return True
            else:
                r.failure(f"Login failed {r.status_code}: {r.text[:100]}")
                return False


# ── Пользователь ─────────────────────────────────────────────────────────────

class UserBehavior(LexBase):
    wait_time = between(2, 5)
    weight = 8

    _ok = False
    _uuids: list = []          # все мои заявки
    _ai_done: list = []        # готовы к отправке юристу

    def on_start(self):
        email = f"u_{self._suffix()}@load.test"
        self._ok = self._login(email, "pass1234", f"User {self._suffix(4)}", "user")

    # ── Загрузка документа ────────────────────────────────────────────────────
    @task(4)
    def upload_document(self):
        if not self._ok:
            raise RescheduleTask()

        text = random.choice(CONTRACT_TEXTS)
        pdf = make_pdf(text)
        fname = f"contract_{self._suffix(6)}.pdf"

        with self.client.post(
            "/api/requests",
            files={"file": (fname, io.BytesIO(pdf), "application/pdf")},
            data={"comment": random.choice([
                "Прошу проверить", "Нужен анализ рисков",
                "Проверьте ответственность", ""
            ])},
            name="POST /requests [upload]",
            catch_response=True
        ) as r:
            if r.status_code == 200:
                r.success()
                uuid = r.json().get("uuid")
                if uuid:
                    self._uuids = (self._uuids + [uuid])[-20:]
            elif r.status_code == 401:
                r.failure("Unauthorized"); self._ok = False
            else:
                r.failure(f"Upload {r.status_code}: {r.text[:80]}")

    # ── Список заявок ─────────────────────────────────────────────────────────
    @task(6)
    def list_requests(self):
        if not self._ok:
            raise RescheduleTask()

        with self.client.get(
            "/api/requests",
            name="GET /requests [list]",
            catch_response=True
        ) as r:
            if r.status_code == 200:
                r.success()
                data = r.json()
                self._uuids = [x["uuid"] for x in data[:15]]
                self._ai_done = [x["uuid"] for x in data if x["status"] == "ai_done"]
            elif r.status_code == 401:
                r.failure("Unauthorized"); self._ok = False
            else:
                r.failure(f"List {r.status_code}")

    # ── Детали заявки ─────────────────────────────────────────────────────────
    @task(3)
    def view_detail(self):
        if not self._ok or not self._uuids:
            raise RescheduleTask()

        uuid = random.choice(self._uuids)
        with self.client.get(
            f"/api/requests/{uuid}",
            name="GET /requests/{uuid} [detail]",
            catch_response=True
        ) as r:
            if r.status_code == 200:
                r.success()
                # Обновляем статус из детального ответа
                body = r.json()
                if body.get("status") == "ai_done" and uuid not in self._ai_done:
                    self._ai_done.append(uuid)
            elif r.status_code == 404:
                # UUID устарел — убираем из списка
                r.success()
                self._uuids = [u for u in self._uuids if u != uuid]
            elif r.status_code == 401:
                r.failure("Unauthorized"); self._ok = False
            else:
                r.failure(f"Detail {r.status_code}")

    # ── Отправить юристу ──────────────────────────────────────────────────────
    @task(2)
    def send_to_lawyer(self):
        if not self._ok or not self._ai_done:
            raise RescheduleTask()

        uuid = self._ai_done.pop(0)
        with self.client.post(
            f"/api/requests/{uuid}/send-to-lawyer",
            name="POST /requests/{uuid}/send-to-lawyer",
            catch_response=True
        ) as r:
            if r.status_code == 200:
                r.success()
            elif r.status_code == 400:
                # 400 = статус не ai_done (AI ещё думает или уже у юриста) — не ошибка теста
                r.success()
            elif r.status_code == 404:
                r.success()  # UUID устарел между list и send
            elif r.status_code == 403:
                r.success()  # нет доступа к чужой заявке — race condition при параллельных users
            elif r.status_code == 401:
                r.failure("Unauthorized"); self._ok = False
            else:
                r.failure(f"SendToLawyer {r.status_code}: {r.text[:80]}")

    # ── Обратная связь (NPS + CSAT + CES) ────────────────────────────────────
    @task(1)
    def submit_feedback(self):
        if not self._ok:
            raise RescheduleTask()

        # NPS: 0–10, насколько вероятно порекомендуете
        self.client.post("/api/feedback/nps",
            json={"score": random.randint(0, 10), "comment": "load test"},
            name="POST /feedback/nps")

        # CSAT: 1–5, удовлетворённость анализом
        self.client.post("/api/feedback/csat",
            json={"score": round(random.uniform(3.0, 5.0), 1)},
            name="POST /feedback/csat")

        # CES: 1–7, насколько легко пользоваться (1=легко, 7=сложно)
        self.client.post("/api/feedback/ces",
            json={"score": round(random.uniform(1.0, 4.0), 1),
                  "feature": "document_upload"},
            name="POST /feedback/ces")

    @task(1)
    def check_profile(self):
        if not self._ok:
            raise RescheduleTask()
        with self.client.get("/api/auth/me", name="GET /auth/me", catch_response=True) as r:
            if r.status_code == 200:
                r.success()
            elif r.status_code == 401:
                r.failure("Session expired"); self._ok = False
            else:
                r.failure(f"Me {r.status_code}")


# ── Юрист ─────────────────────────────────────────────────────────────────────

LAWYERS = [
    {"email": "lawyer1@loadtest.com", "password": "lawyer123", "name": "Юрист Иванова А."},
    {"email": "lawyer2@loadtest.com", "password": "lawyer123", "name": "Юрист Петров Б."},
    {"email": "lawyer3@loadtest.com", "password": "lawyer123", "name": "Юрист Сидоров В."},
]


class LawyerBehavior(LexBase):
    """
    Симулирует юриста. Требует предварительной настройки ролей:
      1. Запустите тест хотя бы раз — юристы зарегистрируются
      2. В admin-панели назначьте роль 'lawyer' для lawyer1-3@loadtest.com
    """
    wait_time = between(8, 20)
    weight = 2

    _ok = False
    _account: dict = {}
    _pending: list = []
    _in_review: list = []
    _is_lawyer = False  # становится True когда 403 не приходит

    def on_start(self):
        self._account = random.choice(LAWYERS)
        self._ok = self._login(
            self._account["email"], self._account["password"],
            self._account["name"], "lawyer"
        )

    @task(4)
    def fetch_new_requests(self):
        if not self._ok:
            raise RescheduleTask()

        with self.client.get(
            "/api/lawyer/requests?status=new",
            name="GET /lawyer/requests?status=new",
            catch_response=True
        ) as r:
            if r.status_code == 200:
                r.success()
                self._is_lawyer = True
                data = r.json()
                self._pending = [x["uuid"] for x in data[:5]]
            elif r.status_code == 403:
                # Роль ещё не назначена — не считаем ошибкой
                r.success()
                if not self._is_lawyer:
                    logger.warning(
                        f"[Lawyer] {self._account['email']} got 403 — "
                        "назначьте роль 'lawyer' через admin-панель"
                    )
            elif r.status_code == 401:
                r.failure("Unauthorized"); self._ok = False
            else:
                r.failure(f"FetchNew {r.status_code}")

    @task(2)
    def take_request(self):
        if not self._ok or not self._pending:
            raise RescheduleTask()

        uuid = self._pending.pop(0)
        with self.client.post(
            f"/api/lawyer/requests/{uuid}/take",
            name="POST /lawyer/requests/{uuid}/take",
            catch_response=True
        ) as r:
            if r.status_code == 200:
                r.success()
                self._in_review.append(uuid)
            elif r.status_code in (400, 403, 404):
                # 400=уже взята, 403=нет роли, 404=не найдена — всё ок
                r.success()
            elif r.status_code == 401:
                r.failure("Unauthorized"); self._ok = False
            else:
                r.failure(f"Take {r.status_code}: {r.text[:80]}")

    @task(2)
    def submit_review(self):
        if not self._ok or not self._in_review:
            raise RescheduleTask()

        uuid = self._in_review.pop(0)
        risk = random.choice(["low", "medium", "high"])

        payload = {
            "summary": f"Документ проверен. Общий риск: {risk}.",
            "document_type": random.choice([
                "Договор аренды", "Трудовой договор",
                "Договор услуг", "Договор поставки"
            ]),
            "parties": [
                random.choice(["ООО Ромашка", "АО СтройГрупп", "ИП Иванов"]),
                random.choice(["ООО Василёк", "ЗАО МедиаПлюс", "ИП Петров"])
            ],
            "key_terms": [
                {"category": "Сроки",
                 "title": "Срок действия договора",
                 "description": f"{random.choice([6,12,24])} месяцев"},
                {"category": "Оплата",
                 "title": "Размер оплаты",
                 "description": f"{random.randint(50,500)*1000} рублей"}
            ],
            "risks": [
                {"level": risk,
                 "title": random.choice([
                     "Нечёткие условия расторжения",
                     "Высокие штрафные санкции",
                     "Риск автоматической пролонгации",
                     "Неопределённые обязательства сторон"
                 ]),
                 "description": "Требует дополнительного согласования с контрагентом.",
                 "recommendation": "Рекомендуется внести уточнения до подписания."}
            ],
            "plain_language_summary": (
                "Договор содержит стандартные условия. "
                "Обратите внимание на раздел об ответственности. "
                f"Общий уровень риска: {risk}."
            ),
            "lawyer_comment": (
                f"Проверено {self._account['name']}. "
                f"Замечания: {'отсутствуют' if risk == 'low' else 'см. раздел рисков'}."
            ),
            "overall_risk": risk
        }

        with self.client.post(
            f"/api/lawyer/requests/{uuid}/submit",
            json=payload,
            name="POST /lawyer/requests/{uuid}/submit",
            catch_response=True
        ) as r:
            if r.status_code in (200, 400):
                r.success()
            elif r.status_code in (403, 404):
                r.success()  # нет роли или не найдена
            elif r.status_code == 401:
                r.failure("Unauthorized"); self._ok = False
            else:
                r.failure(f"Submit {r.status_code}: {r.text[:80]}")

    @task(1)
    def view_done(self):
        if not self._ok:
            raise RescheduleTask()
        with self.client.get(
            "/api/lawyer/requests?status=done",
            name="GET /lawyer/requests?status=done",
            catch_response=True
        ) as r:
            if r.status_code in (200, 403):
                r.success()
            elif r.status_code == 401:
                r.failure("Unauthorized"); self._ok = False
            else:
                r.failure(f"Done {r.status_code}")


# ── Администратор ─────────────────────────────────────────────────────────────

class AdminBehavior(LexBase):
    wait_time = between(15, 40)
    weight = 1

    _ok = False

    def on_start(self):
        self._ok = self._login(
            "admin@lexanalytica.ru", "admin123",
            "Администратор", "admin"
        )

    @task(3)
    def view_stats(self):
        if not self._ok:
            raise RescheduleTask()
        with self.client.get("/api/admin/stats", name="GET /admin/stats", catch_response=True) as r:
            if r.status_code == 200:
                r.success()
            elif r.status_code == 403:
                r.failure("Not admin — check credentials")
            elif r.status_code == 401:
                r.failure("Unauthorized"); self._ok = False
            else:
                r.failure(f"Stats {r.status_code}")

    @task(1)
    def view_users(self):
        if not self._ok:
            raise RescheduleTask()
        with self.client.get("/api/admin/users", name="GET /admin/users", catch_response=True) as r:
            if r.status_code in (200, 403):
                r.success()
            elif r.status_code == 401:
                r.failure("Unauthorized"); self._ok = False
            else:
                r.failure(f"Users {r.status_code}")

    @task(1)
    def health(self):
        with self.client.get("/api/health", name="GET /health", catch_response=True) as r:
            if r.status_code == 200 and r.json().get("status") == "ok":
                r.success()
            else:
                r.failure("Health failed")


# ── Точка входа ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║          НАГРУЗОЧНЫЙ ТЕСТ LEX ANALYTICA                  ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  Запуск с веб-интерфейсом:                               ║
║    locust -f load_test.py --host=http://localhost:8000   ║
║    Открыть: http://localhost:8089                         ║
║                                                          ║
║  Headless (рекомендуется для начала):                    ║
║    locust -f load_test.py --host=http://localhost:8000 \\ ║
║      --users=23 --spawn-rate=2 --run-time=120s \\         ║
║      --headless --html=report.html                       ║
║                                                          ║
║  Настройка юристов:                                      ║
║    1. Запустить тест один раз (юристы зарегистрируются)  ║
║    2. Зайти в admin-панель: http://localhost:5173         ║
║    3. Назначить роль lawyer для:                         ║
║       • lawyer1@loadtest.com                             ║
║       • lawyer2@loadtest.com                             ║
║       • lawyer3@loadtest.com                             ║
║                                                          ║
║  Состав нагрузки (weight):                               ║
║    8 × UserBehavior  — загружают PDF, смотрят заявки     ║
║    2 × LawyerBehavior — проверяют заявки                 ║
║    1 × AdminBehavior  — статистика                       ║
╚══════════════════════════════════════════════════════════╝
""")
