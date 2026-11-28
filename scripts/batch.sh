#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 3 ]]; then
    echo "Использование: bash scripts/batch.sh INPUT_DIR REPORT_DIR LOG_DIR" >&2
    exit 2
fi

INPUT_DIR="$1"
REPORT_DIR="$2"
LOG_DIR="$3"
if [[ ! -d "$INPUT_DIR" ]]; then
    echo "Ошибка: входной каталог не существует: $INPUT_DIR" >&2
    exit 2
fi

INPUT_DIR="$(realpath -e -- "$INPUT_DIR")"
REPORT_DIR="$(realpath -m -- "$REPORT_DIR")"
LOG_DIR="$(realpath -m -- "$LOG_DIR")"

if [[ "$INPUT_DIR" == "$REPORT_DIR" ||
      "$INPUT_DIR" == "$LOG_DIR" ||
      "$REPORT_DIR" == "$LOG_DIR" ]]; then
    echo "Ошибка: входная папка, отчёты и логи должны находиться в разных каталогах" >&2
    exit 2
fi

shopt -s nullglob
csv_files=()

for file in "$INPUT_DIR"/*.csv; do
    if [[ -f "$file" && ! -L "$file" ]]; then
        csv_files+=("$file")
    fi
done

if [[ ${#csv_files[@]} -eq 0 ]]; then
    echo "Ошибка: в каталоге нет подходящих CSV-файлов" >&2
    exit 2
fi


SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
ANALYZER="$PROJECT_DIR/app/analyzer.py"

if [[ ! -x "$PYTHON" || ! -f "$ANALYZER" ]]; then
    echo "Ошибка: не найден Python или анализатор" >&2
    exit 2
fi

if ! mkdir -p -- "$REPORT_DIR" "$LOG_DIR"; then
    echo "Ошибка: не удалось создать папки для результатов" >&2
    exit 2
fi

if [[ ! -d "$REPORT_DIR" || ! -w "$REPORT_DIR" || ! -x "$REPORT_DIR" ||
      ! -d "$LOG_DIR" || ! -w "$LOG_DIR" || ! -x "$LOG_DIR" ]]; then
    echo "Ошибка: нет доступа для записи в папки отчётов или логов" >&2
    exit 2
fi

processed=0
failed=0

for file in "${csv_files[@]}"; do
    filename="${file##*/}"
    name="${filename%.csv}"

    report="$REPORT_DIR/$name.json"
    log="$LOG_DIR/$name.log"

    if "$PYTHON" "$ANALYZER" "$file" --output "$report" 2>"$log"; then
        processed=$((processed + 1))
    else
        rm -f -- "$report"
        failed=$((failed + 1))
    fi
done

printf 'processed=%d failed=%d\n' "$processed" "$failed"

if (( failed > 0 )); then
    exit 1
fi

exit 0
