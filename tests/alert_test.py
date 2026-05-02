#!/usr/bin/env python3
"""
Тест алерта при аварии сервиса.

Сценарий:
  1. Убедиться что сервис работает
  2. Остановить backend контейнер
  3. Подождать срабатывания алерта (до 90 сек)
  4. Запустить backend обратно
  5. Проверить что алерт resolved

Запуск:
  python alert_test.py

Требования:
  - docker-compose up (все контейнеры)
  - Настроенный alertmanager.yml (SMTP)
  - pip install requests
"""

import subprocess
import time
import sys

try:
    import requests
except ImportError:
    print("Установите requests: pip install requests")
    sys.exit(1)

PROMETHEUS_URL = "http://localhost:9090"
BACKEND_URL = "http://localhost:8000"
CONTAINER_NAME = "project-backend-1"  # имя может отличаться — проверьте docker ps


def check_service(url: str, timeout: int = 5) -> bool:
    """Проверить доступность сервиса."""
    try:
        r = requests.get(f"{url}/api/health", timeout=timeout)
        return r.status_code == 200 and r.json().get("status") == "ok"
    except Exception:
        return False


def get_prometheus_alerts() -> list[dict]:
    """Получить активные алерты из Prometheus."""
    try:
        r = requests.get(f"{PROMETHEUS_URL}/api/v1/alerts", timeout=5)
        return r.json().get("data", {}).get("alerts", [])
    except Exception:
        return []


def is_alert_firing(alert_name: str) -> bool:
    """Проверить что конкретный алерт сработал."""
    alerts = get_prometheus_alerts()
    for alert in alerts:
        if (alert.get("labels", {}).get("alertname") == alert_name
                and alert.get("state") == "firing"):
            return True
    return False


def docker(cmd: str) -> tuple[int, str]:
    """Выполнить docker-команду."""
    result = subprocess.run(
        cmd.split(), capture_output=True, text=True
    )
    return result.returncode, result.stdout + result.stderr


def find_backend_container() -> str:
    """Найти имя контейнера бэкенда."""
    code, output = docker("docker ps --format {{.Names}}")
    for name in output.strip().split("\n"):
        if "backend" in name.lower():
            return name.strip()
    return CONTAINER_NAME


def run_alert_test():
    print("=" * 60)
    print("ТЕСТ АЛЕРТА: Авария веб-сервиса")
    print("=" * 60)

    # Шаг 1: Проверить что всё работает
    print("\n[1/6] Проверяем что сервис работает...")
    if not check_service(BACKEND_URL):
        print("❌ Backend недоступен! Запустите: docker-compose up")
        sys.exit(1)
    print("✅ Сервис работает")

    # Шаг 2: Проверить что алертов нет
    print("\n[2/6] Проверяем отсутствие активных алертов...")
    if is_alert_firing("WebServiceDown"):
        print("⚠️  Алерт WebServiceDown уже активен до теста!")
    else:
        print("✅ Алертов нет — начинаем тест")

    # Шаг 3: Остановить backend
    container = find_backend_container()
    print(f"\n[3/6] Останавливаем контейнер: {container}")
    code, output = docker(f"docker stop {container}")
    if code != 0:
        print(f"❌ Ошибка: {output}")
        sys.exit(1)
    print("✅ Контейнер остановлен")

    # Шаг 4: Ждём срабатывания алерта
    print("\n[4/6] Ожидаем срабатывания алерта WebServiceDown...")
    print("    (Prometheus scrape_interval=15s, for=30s → ждём до 90 сек)")
    max_wait = 120
    fired = False
    for elapsed in range(0, max_wait, 5):
        time.sleep(5)
        print(f"    [{elapsed+5}s] Проверяем Prometheus...", end=" ")
        if is_alert_firing("WebServiceDown"):
            print("🚨 АЛЕРТ СРАБОТАЛ!")
            fired = True
            break
        else:
            # Проверим что сервис действительно упал
            if check_service(BACKEND_URL, timeout=2):
                print("⚠️  Сервис всё ещё доступен — неожиданно")
            else:
                print("сервис недоступен, алерт ещё не сработал")

    if not fired:
        print(f"❌ Алерт не сработал за {max_wait} секунд!")
        print("   Проверьте: prometheus/rules.yml подключён к prometheus.yml?")
        print("   URL Prometheus: http://localhost:9090/alerts")
    else:
        print(f"\n✅ ТЕСТ ПРОЙДЕН: Алерт сработал")
        print("   Email отправлен на адрес из alertmanager.yml")
        print("   Проверьте почту!")

    # Шаг 5: Запустить backend обратно
    print(f"\n[5/6] Запускаем контейнер обратно: {container}")
    code, output = docker(f"docker start {container}")
    if code != 0:
        print(f"❌ Ошибка запуска: {output}")
        sys.exit(1)

    # Ждём пока поднимется
    print("    Ждём готовности сервиса...")
    for _ in range(30):
        time.sleep(2)
        if check_service(BACKEND_URL):
            print("✅ Сервис восстановлен")
            break
    else:
        print("⚠️  Сервис не поднялся за 60 секунд")

    # Шаг 6: Проверить resolved
    print("\n[6/6] Ожидаем resolved-алерта (ещё ~60 сек)...")
    time.sleep(60)
    if not is_alert_firing("WebServiceDown"):
        print("✅ Алерт разрешён (resolved). Email о восстановлении отправлен.")
    else:
        print("⚠️  Алерт всё ещё активен — подождите ещё немного")

    print("\n" + "=" * 60)
    print(f"РЕЗУЛЬТАТ: {'✅ ПРОЙДЕН' if fired else '❌ ПРОВАЛЕН'}")
    print("=" * 60)
    print("\nДля проверки email:")
    print("  Письмо 1: '🚨 [АВАРИЯ] WebServiceDown — Lex Analytica'")
    print("  Письмо 2: '[RESOLVED] WebServiceDown — Lex Analytica'")
    print("\nGrafana: http://localhost:3000")
    print("Prometheus alerts: http://localhost:9090/alerts")


if __name__ == "__main__":
    run_alert_test()
