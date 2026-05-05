#!/bin/bash
# Автоматически импортирует дашборд в Grafana через API.
# Запускать ПОСЛЕ docker-compose up, когда Grafana поднялась.

GRAFANA_URL="http://localhost:3000"
GRAFANA_USER="admin"
GRAFANA_PASS="admin123"
DASHBOARD_FILE="./monitoring/grafana/dashboards/1_executive.json"

echo "[1/4] Ждём готовности Grafana..."
for i in $(seq 1 30); do
    if curl -sf "$GRAFANA_URL/api/health" > /dev/null 2>&1; then
        echo "      Grafana готова."
        break
    fi
    echo "      Попытка $i/30..."
    sleep 3
done

echo "[2/4] Создаём папку 'Lex Analytica'..."
curl -sf -X POST "$GRAFANA_URL/api/folders" \
    -u "$GRAFANA_USER:$GRAFANA_PASS" \
    -H "Content-Type: application/json" \
    -d '{"title":"Lex Analytica","uid":"lex-analytica"}' > /dev/null 2>&1
echo "      Готово (папка уже может существовать — это нормально)."

echo "[3/4] Импортируем дашборд..."
# Оборачиваем JSON в формат Grafana import API
DASHBOARD_JSON=$(cat "$DASHBOARD_FILE")
PAYLOAD=$(python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
d.pop('id', None)
d.pop('uid', None)
result = {
    'dashboard': d,
    'folderUid': 'lex-analytica',
    'overwrite': True,
    'message': 'Auto-imported by setup_grafana.sh'
}
print(json.dumps(result))
" <<< "$DASHBOARD_JSON")

RESULT=$(curl -sf -X POST "$GRAFANA_URL/api/dashboards/import" \
    -u "$GRAFANA_USER:$GRAFANA_PASS" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

if echo "$RESULT" | grep -q '"status":"success"'; then
    URL=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('importedUrl',''))" 2>/dev/null)
    echo "      ✅ Дашборд импортирован!"
    echo "      Ссылка: $GRAFANA_URL$URL"
else
    echo "      ⚠ Ответ Grafana: $RESULT"
fi

echo "[4/4] Устанавливаем дашборд как домашний..."
# Получаем uid импортированного дашборда
DASH_UID=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('uid',''))" 2>/dev/null)
if [ -n "$DASH_UID" ]; then
    curl -sf -X PUT "$GRAFANA_URL/api/org/preferences" \
        -u "$GRAFANA_USER:$GRAFANA_PASS" \
        -H "Content-Type: application/json" \
        -d "{\"homeDashboardUID\":\"$DASH_UID\",\"theme\":\"\",\"timezone\":\"browser\"}" > /dev/null
    echo "      ✅ Установлен как домашний дашборд."
fi

echo ""
echo "======================================"
echo "Grafana:      $GRAFANA_URL"
echo "Логин:        $GRAFANA_USER / $GRAFANA_PASS"
echo "Дашборд:      $GRAFANA_URL/dashboards"
echo "======================================"
