#!/usr/bin/env bash
# Запуск AqylRoute AI одной командой: ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d backend/.venv ]; then
  echo "→ Создаю окружение Python…"
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q --upgrade pip
  backend/.venv/bin/pip install -q fastapi "uvicorn[standard]" openai pydantic python-multipart
fi
if [ ! -d frontend/node_modules ]; then
  echo "→ Ставлю зависимости фронтенда…"
  (cd frontend && npm install --silent)
fi

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "→ Бэкенд:  http://127.0.0.1:8000  (документация: /docs)"
(cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000) &

echo "→ Фронтенд: http://localhost:3000"
(cd frontend && npm run dev) &

sleep 3
command -v open >/dev/null && open http://localhost:3000 || true
wait
