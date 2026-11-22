"""Проверить один сценарий ДЗ на своей машине."""
import argparse
from contextlib import closing, suppress
from http.client import HTTPConnection, HTTPException
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "samples/clean.csv"


class CheckFailed(Exception):
    pass


def expect(condition, message):
    if not condition:
        raise CheckFailed(message)


def student_script(name, temp_dir, *args):
    command = ["bash", ROOT / "scripts" / name, *args]
    with subprocess.Popen(command, cwd=ROOT, env={**os.environ, "TMPDIR": str(temp_dir)},
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          errors="replace", start_new_session=True) as process:
        try:
            stdout, stderr = process.communicate(timeout=15)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            if isinstance(error, KeyboardInterrupt):
                raise
            raise CheckFailed(f"{name} не завершился за 15 секунд.") from error
        return process.returncode, stdout.splitlines(), stderr.strip()


def clean_report():
    analyzer = runpy.run_path(str(ROOT / "app/analyzer.py"))
    return analyzer["analyze_bytes"](CLEAN.read_bytes())


def read_json(data, source):
    try:
        return json.loads(data)
    except ValueError as error:
        raise CheckFailed(f"Ожидался JSON ({source}).") from error


def check_batch(directory):
    inputs, reports, logs = (directory / name for name in ("input", "reports", "logs"))
    inputs.mkdir()
    temp_dir = directory / "tmp"
    temp_dir.mkdir()
    csv = inputs / "clean.csv"
    report = reports / "clean.json"
    log = logs / "clean.log"

    csv.write_bytes(CLEAN.read_bytes())
    code, lines, stderr = student_script("batch.sh", temp_dir, inputs, reports, logs)
    expect(code == 0, f"Для корректного CSV ожидался код 0, получен {code}. {stderr}".rstrip())
    expect(lines[-1:] == ["processed=1 failed=0"], "Для корректного CSV ожидалась строка processed=1 failed=0.")
    expect(report.is_file(), "После первой обработки отсутствует clean.json.")
    expect(read_json(report.read_bytes(), "clean.json") == clean_report(), "Данные в clean.json отличаются от отчёта анализатора.")
    expect(log.is_file() and log.stat().st_size == 0, "Для корректного CSV ожидался пустой clean.log.")

    csv.write_bytes((ROOT / "samples/batch/broken.csv").read_bytes())
    code, lines, _ = student_script("batch.sh", temp_dir, inputs, reports, logs)
    expect(code == 1, f"Для повреждённого CSV ожидался код 1, получен {code}.")
    expect(not report.exists(), "После повторного запуска остался старый clean.json.")
    expect(log.is_file() and log.stat().st_size > 0, "Ошибка анализатора должна попасть в clean.log.")
    expect(lines[-1:] == ["processed=0 failed=1"], "Для повреждённого CSV ожидалась строка processed=0 failed=1.")
    print("batch.sh обработал CSV, записал ошибку и удалил устаревший отчёт.")


def check_http(directory):
    fixture = runpy.run_path(str(ROOT / "tools/http-fixture.py"))
    temp_dir = directory / "tmp"
    temp_dir.mkdir()
    output = directory / "report.json"

    class QuietHandler(fixture["Handler"]):
        def log_request(self, code="-", size="-"):
            pass

    with fixture["FixtureServer"](("127.0.0.1", 0), "complete") as server:
        server.RequestHandlerClass = QuietHandler
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            code, _, stderr = student_script("submit.sh", temp_dir, url, CLEAN, output)
            expect(code == 0, f"Для полного ответа HTTP 201 ожидался код 0, получен {code}. {stderr}".rstrip())
            expect(output.is_file(), "После полного ответа HTTP 201 отсутствует report.json.")
            previous = output.read_bytes()
            expect(read_json(previous, "report.json") == {"id": "fixture", "row_count": 1},
                   "Сохранённый JSON отличается от полного ответа сервера.")

            server.upload_mode = "truncated"
            code, _, _ = student_script("submit.sh", temp_dir, url, CLEAN, output)
            expect(code != 0, "Сервер оборвал HTTP 201, но submit.sh сообщил об успехе.")
            expect(output.is_file() and output.read_bytes() == previous, "При обрыве прежний report.json изменился или исчез.")
            expect(not any(temp_dir.iterdir()), "После загрузки в TMPDIR остались временные файлы.")
        finally:
            server.shutdown()
            thread.join()
    print("submit.sh сохранил полный ответ. После обрыва прежний файл остался цел.")


def check_compose():
    port = subprocess.run(["docker", "compose", "-p", "hw3-lab", "port", "gateway", "80"],
                          cwd=ROOT, capture_output=True, text=True, timeout=15)
    expect(port.returncode == 0, "Не удалось узнать порт gateway. Проверьте docker compose -p hw3-lab ps.")
    host, _, number = port.stdout.strip().rpartition(":")
    expect(host == "127.0.0.1" and number.isdecimal(), "Ожидался опубликованный порт gateway на 127.0.0.1.")

    # Отправляем готовый CSV тем же полем file, что и браузер.
    boundary = "hw3-self-check"
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="clean.csv"\r\n'
            'Content-Type: text/csv\r\n\r\n').encode() + CLEAN.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    with closing(HTTPConnection(host, int(number), timeout=10)) as gateway:
        gateway.request("POST", "/reports", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        response = gateway.getresponse()
        expect(response.status == 201, f"POST /reports через gateway вернул HTTP {response.status}, ожидался 201.")
        report = read_json(response.read(), "ответ на POST /reports")
        location = response.getheader("Location")
        expect(isinstance(report, dict) and isinstance(report.get("id"), str)
               and report["id"] and location == f"/reports/{report['id']}",
               "В ответе на загрузку ожидались ID и соответствующий ему путь в Location.")
        expected = {**clean_report(), "filename": "clean.csv"}
        expect(all(report.get(key) == value for key, value in expected.items()),
               "Ответ на загрузку отличается от отчёта для clean.csv.")
        gateway.request("GET", location)
        response = gateway.getresponse()
        expect(response.status == 200, f"GET {location} вернул HTTP {response.status}, ожидался 200.")
        expect(read_json(response.read(), f"ответ на GET {location}") == report, "По пути из Location вернулся другой отчёт.")
    print(f"Отчёт создан и прочитан через gateway. ID: {report['id']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part", choices=("batch", "http", "compose"))
    part = parser.parse_args().part
    try:
        if part == "compose":
            check_compose()
        else:
            with tempfile.TemporaryDirectory(prefix="hw3-self-check-") as directory:
                {"batch": check_batch, "http": check_http}[part](Path(directory))
    except (CheckFailed, OSError, ValueError, HTTPException, subprocess.TimeoutExpired) as error:
        print(f"Проверка {part} не прошла: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
