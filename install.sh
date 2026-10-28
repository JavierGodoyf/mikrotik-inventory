#!/usr/bin/env sh
# Instalador para macOS y Linux. Crea .venv, instala el paquete y la base de datos.
set -eu
cd "$(dirname "$0")"

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON="$candidate"
      break
    fi
  done
fi

if [ -z "$PYTHON" ]; then
  echo "No encuentro Python. Instala Python 3.10 o superior." >&2
  exit 1
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Se necesita Python >= 3.10 (encontrado: $("$PYTHON" -V 2>&1))." >&2
  exit 1
fi

echo "Usando $("$PYTHON" -V 2>&1)"
"$PYTHON" -m venv .venv
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet -e .

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Creado .env a partir de .env.example"
fi

mkdir -p data
./.venv/bin/python -c "from app.db import init_db; init_db()"

echo
echo "Instalado. Arranca el panel con: ./run.sh"
echo "  CLI: ./.venv/bin/mikrotik-inventory --help"
