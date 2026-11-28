#!/usr/bin/env bash

if [[ "$#" -ne 3 ]]; then
    echo "Использование: bash scripts/submit.sh BASE_URL CSV_FILE OUTPUT_JSON" >&2
    exit 2
fi

BASE_URL="$1"
CSV_FILE="$2"
OUTPUT_FILE="$3"

if [[ ! -f "$CSV_FILE" ]]; then
    echo "Ошибка: CSV-файл не найден: $CSV_FILE" >&2
    exit 1
fi

OUTPUT_DIR="$(dirname -- "$OUTPUT_FILE")"
OUTPUT_NAME="$(basename -- "$OUTPUT_FILE")"

if [[ ! -d "$OUTPUT_DIR" ]]; then
    echo "Ошибка: каталог для отчёта не существует: $OUTPUT_DIR" >&2
    exit 1
fi

TEMP_FILE=""

cleanup() {
    if [[ -n "$TEMP_FILE" ]]; then
        rm -f -- "$TEMP_FILE"
    fi
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

TEMP_FILE="$(mktemp "$OUTPUT_DIR/.${OUTPUT_NAME}.XXXXXX")" || {
    echo "Ошибка: не удалось создать временный файл" >&2
    exit 1
}

if HTTP_STATUS=$(curl --silent --show-error --max-time 10 \
    --output "$TEMP_FILE" \
    --write-out '%{http_code}' \
    --form "file=@$CSV_FILE" \
    "$BASE_URL/reports"); then
    :
else
    echo "Ошибка: передача данных не завершилась успешно" >&2
    exit 1
fi

if [[ "$HTTP_STATUS" != "201" ]]; then
    echo "Ошибка: сервер вернул HTTP $HTTP_STATUS вместо 201" >&2
    exit 1
fi

if ! mv -f -- "$TEMP_FILE" "$OUTPUT_FILE"; then
    echo "Ошибка: не удалось сохранить отчёт" >&2
    exit 1
fi

TEMP_FILE=""
exit 0
