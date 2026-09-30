#!/usr/bin/env bash
# Запуск AqylRoute AI одной командой: ./start.sh
# Скрипт сам проверит окружение, поставит зависимости и поднимет оба сервиса.
set -euo pipefail
cd "$(dirname "$0")"

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'; OFF=$'\033[0m'
ok()   { echo "${GREEN}✓${OFF} $1"; }
info() { echo "${DIM}→${OFF} $1"; }
die()  { echo "${RED}✗ $1${OFF}" >&2; exit 1; }

echo
echo "  AqylRoute AI"
echo "  ${DIM}межведомственный маршрут ребёнка с РАС${OFF}"
echo

# ─────────────────────────── проверки окружения ───────────────────────────

command -v python3 >/dev/null || die "Не найден Python 3.
  macOS:  brew install python@3.12
  Ubuntu: sudo apt install python3 python3-venv
  Или скачать: https://www.python.org/downloads/"

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 11) else 0)')
[ "$PY_OK" = "1" ] || die "Нужен Python 3.11 или новее, а установлен $PY_VER"
ok "Python $PY_VER"

command -v node >/dev/null || die "Не найден Node.js.
  macOS:  brew install node
  Ubuntu: sudo apt install nodejs npm
  Или скачать: https://nodejs.org (версия 20 или новее)"

NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]')
[ "$NODE_MAJOR" -ge 20 ] || die "Нужен Node.js 20 или новее, а установлен $(node -v)"
ok "Node.js $(node -v)"

command -v npm >/dev/null || die "Не найден npm — обычно ставится вместе с Node.js"

# ─────────────────────────── зависимости ───────────────────────────

if [ ! -x backend/.venv/bin/uvicorn ]; then
  info "Создаю окружение Python и ставлю зависимости (1–2 минуты)…"
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q --upgrade pip
  backend/.venv/bin/pip install -q fastapi "uvicorn[standard]" openai pydantic python-multipart \
    || die "Не удалось установить зависимости Python. Проверьте подключение к интернету."
  ok "Зависимости Python установлены"
else
  ok "Окружение Python готово"
fi

if [ ! -d frontend/node_modules ]; then
  info "Ставлю зависимости фронтенда (2–3 минуты)…"
  (cd frontend && npm install --silent) \
    || die "Не удалось установить зависимости фронтенда. Проверьте подключение к интернету."
  ok "Зависимости фронтенда установлены"
else
  ok "Зависимости фронтенда готовы"
fi

# ─────────────────────────── настройки ───────────────────────────

if [ ! -f .env ]; then
  cp .env.example .env
  echo "${YELLOW}!${OFF} Создан файл .env из шаблона."
  echo "  ${DIM}Приложение запустится в демонстрационном режиме.${OFF}"
  echo "  ${DIM}Чтобы включить живую модель, впишите ключ OpenAI в .env и перезапустите.${OFF}"
else
  if grep -qE '^OPENAI_API_KEY=sk-' .env 2>/dev/null; then
    ok "Ключ OpenAI найден — работаем на живой модели"
  else
    echo "${YELLOW}!${OFF} Ключ OpenAI не задан — демонстрационный режим"
  fi
fi

# ─────────────────────────── занятые порты ───────────────────────────

port_busy() { lsof -ti :"$1" >/dev/null 2>&1; }

for PORT in 8000 3000; do
  if port_busy "$PORT"; then
    echo "${YELLOW}!${OFF} Порт $PORT занят другим процессом."
    printf "  Освободить его? [y/N] "
    read -r ANSWER
    case "$ANSWER" in
      [yY]*) lsof -ti :"$PORT" | xargs kill -9 2>/dev/null || true; sleep 1; ok "Порт $PORT освобождён" ;;
      *) die "Порт $PORT занят. Освободите его или запустите на другом порту (см. README)." ;;
    esac
  fi
done

# ─────────────────────────── запуск ───────────────────────────

cleanup() { echo; info "Останавливаю…"; kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo
info "Бэкенд:   http://127.0.0.1:8000   ${DIM}(документация API: /docs)${OFF}"
(cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000) &

info "Фронтенд: http://localhost:3000"
(cd frontend && npm run dev) &

# ждём, пока оба сервиса ответят
for _ in $(seq 1 60); do
  sleep 1
  if curl -sf -m 2 http://127.0.0.1:8000/api/health >/dev/null 2>&1 \
     && curl -sf -m 2 http://localhost:3000 >/dev/null 2>&1; then
    echo
    ok "Приложение готово: ${GREEN}http://localhost:3000${OFF}"
    echo
    echo "  Учётные записи для входа:"
    echo "    ${DIM}родитель${OFF}  parent  / parent123"
    echo "    ${DIM}родитель${OFF}  parent2 / parent123   ${DIM}(кейс с просрочкой)${OFF}"
    echo "    ${DIM}куратор ${OFF}  curator / curator123"
    echo
    echo "  ${DIM}Остановить — Ctrl+C${OFF}"
    echo
    command -v open >/dev/null && open http://localhost:3000 2>/dev/null || true
    break
  fi
done

wait
