#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    echo "Ошибка: виртуальное окружение не найдено: $PROJECT_DIR/.venv" >&2
    exit 1
fi

DATA_DIR="${DATA_DIR:-$PROJECT_DIR/work/data}"

if [[ "$DATA_DIR" != /* ]]; then
    echo "Ошибка: DATA_DIR должен содержать абсолютный путь: $DATA_DIR" >&2
    exit 1
fi

if ! mkdir -p -- "$DATA_DIR"; then
    echo "Ошибка: не удалось создать каталог данных: $DATA_DIR" >&2
    exit 1
fi
export DATA_DIR

cd "$PROJECT_DIR"
exec "$PYTHON" "$PROJECT_DIR/app/server.py"
