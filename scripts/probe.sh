#!/usr/bin/env bash

if [[ "$#" -ne 1 ]]; then
    echo "Использование: bash scripts/probe.sh URL" >&2
    exit 2
fi

URL="$1"

if HTTP_STATUS=$(curl --silent --show-error --max-time 3 \
    --output /dev/null \
    --write-out '%{http_code}' \
    "$URL"); then
    :
else
    echo "Ошибка: запрос не завершился успешно" >&2
    exit 1
fi

if [[ "$HTTP_STATUS" != "200" ]]; then
    echo "Ошибка: сервер вернул HTTP $HTTP_STATUS вместо 200" >&2
    exit 1
fi

exit 0
