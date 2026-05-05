#!/bin/bash
echo "=== Loki labels ==="
curl -s http://localhost:3100/loki/api/v1/labels | python3 -m json.tool

echo ""
echo "=== Values for label 'service' ==="
curl -s "http://localhost:3100/loki/api/v1/label/service/values" | python3 -m json.tool

echo ""
echo "=== Values for label 'container' ==="
curl -s "http://localhost:3100/loki/api/v1/label/container/values" | python3 -m json.tool

echo ""
echo "=== Recent log streams (last 5 min) ==="
curl -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={job="docker"}' \
  --data-urlencode "start=$(date -d '5 minutes ago' +%s)000000000" \
  --data-urlencode "end=$(date +%s)000000000" \
  --data-urlencode "limit=5" | python3 -m json.tool 2>/dev/null | head -50

echo ""
echo "Запустите этот скрипт когда контейнеры работают:"
echo "  bash scripts/check_loki.sh"
echo ""
echo "Затем вставьте вывод в Grafana Explore -> Loki"
echo "и используйте тот label который видите в выводе выше"
