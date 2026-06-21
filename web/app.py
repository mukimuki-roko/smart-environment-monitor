import csv
import json
import queue
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

BASE_DIR = Path(__file__).resolve().parents[1]
CSV_CANDIDATES = [BASE_DIR / "data" / "sensor_data.csv"]
HEALTH_HISTORY_PATH = BASE_DIR / "data" / "health_history.csv"
HEALTH_OFFLINE_AFTER = timedelta(seconds=30)
JST = timezone(timedelta(hours=9))
FIELD_LABELS = {
    "client_id": "端末ID",
    "region": "地域",
    "datetime": "日時",
    "temperature": "温度",
    "humidity": "湿度",
    "pressure": "気圧",
    "co2": "CO2",
}

SENSOR_NAMES = ("bme280", "dht22", "mhz19c")
SENSOR_FIELDS = (
    "name", "connect", "read", "read_count", "fail_count",
    "consecutive_fail_count", "last_success_at", "last_failed_at", "error",
)
SERVER_SEND_FIELDS = (
    "success", "fail_count", "consecutive_fail_count", "last_success_at",
    "last_failed_at", "last_status_code", "error",
)
RUNTIME_FIELDS = ("started_at", "last_loop_at", "loop_count", "uptime_seconds")
HEALTH_FIELDS = (
    ["received_at", "client_id", "region"]
    + [f"sensor_{sensor}_{field}" for sensor in SENSOR_NAMES for field in SENSOR_FIELDS]
    + [f"server_send_{field}" for field in SERVER_SEND_FIELDS]
    + [f"runtime_{field}" for field in RUNTIME_FIELDS]
)
HEALTH_LOCK = threading.Lock()
HEALTH_STREAM_LOCK = threading.Lock()
LATEST_HEALTH = {}
HEALTH_STREAM_SUBSCRIBERS = set()

app = Flask(__name__)


def find_csv_path():
    for path in CSV_CANDIDATES:
        if path.exists():
            return path
    return CSV_CANDIDATES[0]


def load_sensor_rows():
    csv_path = find_csv_path()
    if not csv_path.exists():
        return csv_path, [], []

    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    rows.reverse()
    return csv_path, fieldnames, rows


def sensor_payload():
    csv_path, fieldnames, rows = load_sensor_rows()
    return {
        "csv_path": str(csv_path.relative_to(BASE_DIR)),
        "fieldnames": fieldnames,
        "field_labels": FIELD_LABELS,
        "rows": rows,
        "row_count": len(rows),
    }


def is_bool(value):
    return isinstance(value, bool)


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate_health_payload(payload):
    if not isinstance(payload, dict):
        return "JSON object is required"

    client = payload.get("client")
    sensor = payload.get("sensor")
    server_send = payload.get("server_send")
    runtime = payload.get("runtime")
    if not all(isinstance(value, dict) for value in (client, sensor, server_send, runtime)):
        return "client, sensor, server_send, and runtime objects are required"
    if not all(isinstance(client.get(field), str) and client[field] for field in ("client_id", "region")):
        return "client.client_id and client.region must be non-empty strings"

    for sensor_name in SENSOR_NAMES:
        value = sensor.get(sensor_name)
        if not isinstance(value, dict):
            return f"sensor.{sensor_name} object is required"
        if not isinstance(value.get("name"), str):
            return f"sensor.{sensor_name}.name must be a string"
        if not all(is_bool(value.get(field)) for field in ("connect", "read")):
            return f"sensor.{sensor_name}.connect and read must be booleans"
        if not all(is_int(value.get(field)) and value[field] >= 0 for field in ("read_count", "fail_count", "consecutive_fail_count")):
            return f"sensor.{sensor_name} counts must be non-negative integers"
        if not all(isinstance(value.get(field), str) for field in ("last_success_at", "last_failed_at", "error")):
            return f"sensor.{sensor_name} timestamps and error must be strings"

    if not is_bool(server_send.get("success")):
        return "server_send.success must be a boolean"
    if not all(is_int(server_send.get(field)) and server_send[field] >= 0 for field in ("fail_count", "consecutive_fail_count", "last_status_code")):
        return "server_send counts and status code must be non-negative integers"
    if not all(isinstance(server_send.get(field), str) for field in ("last_success_at", "last_failed_at", "error")):
        return "server_send timestamps and error must be strings"
    if not isinstance(runtime.get("started_at"), str) or not runtime["started_at"]:
        return "runtime.started_at must be a non-empty string"
    if not isinstance(runtime.get("last_loop_at"), str):
        return "runtime.last_loop_at must be a string"
    if not all(is_int(runtime.get(field)) and runtime[field] >= 0 for field in ("loop_count", "uptime_seconds")):
        return "runtime counts must be non-negative integers"
    return None


def flatten_health(payload, received_at):
    row = {"received_at": received_at, **payload["client"]}
    for sensor_name in SENSOR_NAMES:
        for field in SENSOR_FIELDS:
            row[f"sensor_{sensor_name}_{field}"] = payload["sensor"][sensor_name][field]
    for field in SERVER_SEND_FIELDS:
        row[f"server_send_{field}"] = payload["server_send"][field]
    for field in RUNTIME_FIELDS:
        row[f"runtime_{field}"] = payload["runtime"][field]
    return row


def parse_csv_bool(value):
    return value.lower() == "true"


def expand_health(row):
    payload = {
        "client": {"client_id": row["client_id"], "region": row["region"]},
        "sensor": {},
        "server_send": {},
        "runtime": {},
    }
    for sensor_name in SENSOR_NAMES:
        sensor = {}
        for field in SENSOR_FIELDS:
            value = row[f"sensor_{sensor_name}_{field}"]
            sensor[field] = (
                parse_csv_bool(value) if field in {"connect", "read"}
                else int(value) if field in {"read_count", "fail_count", "consecutive_fail_count"}
                else value
            )
        payload["sensor"][sensor_name] = sensor
    for field in SERVER_SEND_FIELDS:
        value = row[f"server_send_{field}"]
        payload["server_send"][field] = (
            parse_csv_bool(value) if field == "success"
            else int(value) if field in {"fail_count", "consecutive_fail_count", "last_status_code"}
            else value
        )
    for field in RUNTIME_FIELDS:
        value = row[f"runtime_{field}"]
        payload["runtime"][field] = int(value) if field in {"loop_count", "uptime_seconds"} else value
    return payload


def append_health_history(payload, received_at):
    HEALTH_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = flatten_health(payload, received_at)
    file_exists = HEALTH_HISTORY_PATH.exists()
    with HEALTH_HISTORY_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEALTH_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def load_latest_health():
    if not HEALTH_HISTORY_PATH.exists():
        return {}
    latest = {}
    with HEALTH_HISTORY_PATH.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                payload = expand_health(row)
                latest[payload["client"]["client_id"]] = {"received_at": row["received_at"], "payload": payload}
            except (KeyError, TypeError, ValueError):
                continue
    return latest


def health_status(received_at):
    try:
        received = datetime.fromisoformat(received_at)
        if received.tzinfo is None:
            received = received.replace(tzinfo=JST)
    except ValueError:
        return "offline"
    return "online" if datetime.now(JST) - received <= HEALTH_OFFLINE_AFTER else "offline"


def health_payload():
    with HEALTH_LOCK:
        records = list(LATEST_HEALTH.values())
    records.sort(key=lambda record: record["payload"]["client"]["client_id"])
    return {
        "offline_after_seconds": int(HEALTH_OFFLINE_AFTER.total_seconds()),
        "clients": [
            {**record["payload"], "received_at": record["received_at"], "status": health_status(record["received_at"])}
            for record in records
        ],
    }


def publish_health_update():
    with HEALTH_STREAM_LOCK:
        subscribers = tuple(HEALTH_STREAM_SUBSCRIBERS)
    for subscriber in subscribers:
        subscriber.put_nowait("health")


@app.route("/")
def index():
    return render_template("index.html", **sensor_payload())


@app.route("/api/sensor-data")
def sensor_data():
    return jsonify(sensor_payload())


@app.route("/api/health", methods=["POST"])
def receive_health():
    payload = request.get_json(silent=True)
    error = validate_health_payload(payload)
    if error:
        return jsonify({"error": error}), 400

    received_at = datetime.now(JST).isoformat(timespec="seconds")
    client_id = payload["client"]["client_id"]
    with HEALTH_LOCK:
        append_health_history(payload, received_at)
        LATEST_HEALTH[client_id] = {"received_at": received_at, "payload": payload}
    publish_health_update()
    return jsonify({"client_id": client_id, "received_at": received_at}), 201


@app.route("/api/health")
def health_data():
    return jsonify(health_payload())


@app.route("/api/health/stream")
def health_stream():
    subscriber = queue.SimpleQueue()

    def events():
        with HEALTH_STREAM_LOCK:
            HEALTH_STREAM_SUBSCRIBERS.add(subscriber)
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    subscriber.get(timeout=15)
                    yield "event: health\ndata: updated\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with HEALTH_STREAM_LOCK:
                HEALTH_STREAM_SUBSCRIBERS.discard(subscriber)

    return Response(
        stream_with_context(events()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


LATEST_HEALTH.update(load_latest_health())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
