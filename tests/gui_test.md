# Сценарий тестирования графического интерфейса
# Lex Analytica — GUI Test Scenarios

## Автоматизированный тест (Playwright)

### Установка
```bash
pip install playwright
playwright install chromium
```

### Запуск
```bash
python gui_test.py
```

---

```python
"""
GUI-тесты на Playwright.
Покрывают: регистрацию, логин, загрузку документа,
просмотр отчёта, работу юриста, панель администратора.
"""

import asyncio
from playwright.async_api import async_playwright, expect

BASE = "http://localhost:5173"
ADMIN_EMAIL = "admin@lexanalytica.ru"
ADMIN_PASS = "admin123"


async def test_full_flow():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        # ── СЦЕНАРИЙ 1: Регистрация нового пользователя ─────────────────────
        print("📋 Сценарий 1: Регистрация")
        await page.goto(f"{BASE}/#/register")
        await page.wait_for_selector(".auth-form")

        await page.fill('input[name="full_name"]', "Тестовый Пользователь")
        await page.fill('input[name="email"]', "gui_test@example.com")
        await page.fill('input[name="password"]', "test123!")
        await page.click('button[type="submit"]')

        # Ожидаем редирект на логин
        await page.wait_for_url(f"{BASE}/#/login", timeout=5000)
        print("  ✅ Регистрация: PASSED")

        # ── СЦЕНАРИЙ 2: Логин ───────────────────────────────────────────────
        print("📋 Сценарий 2: Логин")
        await page.fill('input[name="email"]', "gui_test@example.com")
        await page.fill('input[name="password"]', "test123!")
        await page.click('button[type="submit"]')

        await page.wait_for_url(f"{BASE}/#/dashboard", timeout=5000)
        await expect(page.locator(".sidebar")).to_be_visible()
        print("  ✅ Логин: PASSED")

        # ── СЦЕНАРИЙ 3: Загрузка документа ─────────────────────────────────
        print("📋 Сценарий 3: Загрузка документа")
        await page.goto(f"{BASE}/#/dashboard")

        # Создаём тестовый PDF-файл
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, mode='wb') as f:
            # Минимальный валидный PDF
            f.write(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
                    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
                    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]>>endobj\n"
                    b"xref\n0 4\n0000000000 65535 f\n"
                    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n9\n%%EOF")
            tmp_path = f.name

        file_input = page.locator('input[type="file"]')
        await file_input.set_input_files(tmp_path)
        os.unlink(tmp_path)

        await page.wait_for_selector(".file-preview", timeout=3000)
        filename_el = page.locator(".file-name")
        assert await filename_el.is_visible()

        await page.fill(".textarea", "Тестовый комментарий для GUI-теста")
        await page.click('.btn-primary:has-text("Отправить")')

        # Ожидаем редирект на список заявок
        await page.wait_for_url(f"{BASE}/#/my-requests", timeout=10000)
        print("  ✅ Загрузка документа: PASSED")

        # ── СЦЕНАРИЙ 4: Просмотр списка заявок ──────────────────────────────
        print("📋 Сценарий 4: Список заявок")
        await page.wait_for_selector(".requests-list, .empty-state", timeout=5000)
        print("  ✅ Список заявок отображается: PASSED")

        # ── СЦЕНАРИЙ 5: Навигация (sidebar) ─────────────────────────────────
        print("📋 Сценарий 5: Навигация")
        await page.click('.nav-item:has-text("Загрузить")')
        await page.wait_for_url(f"{BASE}/#/dashboard")
        assert await page.locator(".drop-zone").is_visible()
        print("  ✅ Навигация через sidebar: PASSED")

        # ── СЦЕНАРИЙ 6: Выход ───────────────────────────────────────────────
        print("📋 Сценарий 6: Выход")
        await page.click('.btn-logout')
        await page.wait_for_url(f"{BASE}/#/login", timeout=5000)
        print("  ✅ Выход: PASSED")

        # ── СЦЕНАРИЙ 7: Панель администратора ───────────────────────────────
        print("📋 Сценарий 7: Панель администратора")
        await page.fill('input[name="email"]', ADMIN_EMAIL)
        await page.fill('input[name="password"]', ADMIN_PASS)
        await page.click('button[type="submit"]')
        await page.wait_for_url(f"{BASE}/#/admin", timeout=5000)

        # Статистика
        await page.wait_for_selector(".stats-grid", timeout=5000)
        stat_values = page.locator(".stat-value")
        count = await stat_values.count()
        assert count >= 4, f"Ожидалось 4 статкарточки, получено {count}"
        print("  ✅ Статистика администратора: PASSED")

        # Список пользователей
        await page.click('.nav-item:has-text("Пользователи")')
        await page.wait_for_url(f"{BASE}/#/admin/users")
        await page.wait_for_selector(".table", timeout=5000)
        rows = page.locator(".table tbody tr")
        count = await rows.count()
        assert count >= 1, "Таблица пользователей пустая"
        print("  ✅ Таблица пользователей: PASSED")

        # ── СЦЕНАРИЙ 8: Смена роли пользователя ─────────────────────────────
        print("📋 Сценарий 8: Смена роли")
        selects = page.locator(".select-inline")
        if await selects.count() > 0:
            # Находим пользователя gui_test
            rows = page.locator(".table tbody tr")
            for i in range(await rows.count()):
                row = rows.nth(i)
                text = await row.inner_text()
                if "gui_test@example.com" in text:
                    select = row.locator(".select-inline")
                    await select.select_option("lawyer")
                    await page.wait_for_timeout(1000)
                    # Проверяем toast
                    toast = page.locator(".toast-success")
                    await expect(toast).to_be_visible(timeout=3000)
                    print("  ✅ Смена роли: PASSED")
                    break

        # ── СЦЕНАРИЙ 9: Блокировка пользователя ─────────────────────────────
        print("📋 Сценарий 9: Блокировка пользователя")
        rows = page.locator(".table tbody tr")
        for i in range(await rows.count()):
            row = rows.nth(i)
            text = await row.inner_text()
            if "gui_test@example.com" in text:
                block_btn = row.locator(".btn-ghost")
                await block_btn.click()
                await page.wait_for_timeout(1000)
                toast = page.locator(".toast-success")
                await expect(toast).to_be_visible(timeout=3000)
                print("  ✅ Блокировка пользователя: PASSED")
                break

        # ── СЦЕНАРИЙ 10: Защита роутов ─────────────────────────────────────
        print("📋 Сценарий 10: Защита роутов")
        # Выходим и пробуем зайти на защищённую страницу напрямую
        await page.click('.btn-logout')
        await page.wait_for_url(f"{BASE}/#/login")
        await page.goto(f"{BASE}/#/admin")
        await page.wait_for_url(f"{BASE}/#/login", timeout=3000)
        print("  ✅ Редирект неавторизованного пользователя: PASSED")

        await browser.close()
        print("\n🎉 Все GUI-тесты прошли успешно!")


if __name__ == "__main__":
    asyncio.run(test_full_flow())
```

---

## Ручной сценарий тестирования GUI

### Тест GUI-001: Регистрация

| Шаг | Действие | Ожидаемый результат |
|-----|---------|---------------------|
| 1 | Открыть http://localhost:5173 | Редирект на /login |
| 2 | Нажать "Зарегистрироваться" | Форма регистрации |
| 3 | Заполнить все поля корректно | Поля заполнены |
| 4 | Нажать "Зарегистрироваться" | Toast "Регистрация успешна", редирект на /login |
| 5 | Попробовать тот же email снова | Toast с ошибкой "Email уже зарегистрирован" |

### Тест GUI-002: Загрузка документа

| Шаг | Действие | Ожидаемый результат |
|-----|---------|---------------------|
| 1 | Войти как пользователь | Dashboard с drop-zone |
| 2 | Перетащить PDF в drop-zone | Preview файла с именем и размером |
| 3 | Добавить комментарий | Текст в textarea |
| 4 | Нажать "Отправить на анализ" | Редирект на /my-requests |
| 5 | Найти заявку в списке | Статус "⏳ Анализ AI" |
| 6 | Подождать и обновить | Статус меняется на "✅ AI готов" |

### Тест GUI-003: Работа юриста

| Шаг | Действие | Ожидаемый результат |
|-----|---------|---------------------|
| 1 | Войти как юрист | Sidebar с разделами юриста |
| 2 | Перейти "Новые заявки" | Список заявок со статусом "Ожидает юриста" |
| 3 | Кликнуть на заявку | Форма с AI-отчётом и редактором |
| 4 | Изменить один из рисков | Значение в поле изменилось |
| 5 | Нажать "Сохранить заключение" | Toast "Заключение сохранено", редирект |
| 6 | Перейти "Завершённые" | Заявка появилась в списке |
