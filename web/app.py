import csv
import json
import queue
import re
import threading
from io import StringIO
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from config.settings import (
    HEALTH_HISTORY_PATH as CONFIGURED_HEALTH_HISTORY_PATH,
    HEALTH_OFFLINE_AFTER_SECONDS,
    HEALTH_STREAM_KEEPALIVE_SECONDS,
    HEALTH_STREAM_RETRY_MILLISECONDS,
    SENSOR_DATA_PATH,
    WEB_DEBUG,
    WEB_HOST,
    WEB_PORT,
)

BASE_DIR = Path(__file__).resolve().parents[1]
CSV_CANDIDATES = [SENSOR_DATA_PATH]
HEALTH_HISTORY_PATH = CONFIGURED_HEALTH_HISTORY_PATH
HEALTH_OFFLINE_AFTER = timedelta(seconds=HEALTH_OFFLINE_AFTER_SECONDS)
JST = timezone(timedelta(hours=9))
FIELD_LABELS = {
    "client_id": "端末ID",
    "region": "地域",
    "datetime": "日時",
    "session_id": "セッションID",
    "sequence": "送信番号",
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
    "success", "success_count", "received_count", "last_ack_sequence", "fail_count", "consecutive_fail_count", "last_success_at",
    "last_failed_at", "last_status_code", "error",
)
HEALTH_REPORT_FIELDS = (
    "success", "success_count", "fail_count", "consecutive_fail_count",
    "last_success_at", "last_failed_at", "last_status_code", "error",
)
RUNTIME_FIELDS = ("started_at", "last_loop_at", "loop_count", "uptime_seconds")
HEALTH_FIELDS = (
    ["received_at", "client_id", "region"]
    + [f"sensor_{sensor}_{field}" for sensor in SENSOR_NAMES for field in SENSOR_FIELDS]
    + [f"server_send_{field}" for field in SERVER_SEND_FIELDS]
    + [f"health_report_{field}" for field in HEALTH_REPORT_FIELDS]
    + [f"runtime_{field}" for field in RUNTIME_FIELDS]
)
HEALTH_LOCK = threading.Lock()
HEALTH_STREAM_LOCK = threading.Lock()
LATEST_HEALTH = {}
HEALTH_STREAM_SUBSCRIBERS = set()

app = Flask(__name__)
app.json.sort_keys = False


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

    def row_datetime(row):
        try:
            return parse_sensor_datetime(row.get("datetime", ""))
        except (TypeError, ValueError):
            return datetime.min.replace(tzinfo=JST)

    rows.sort(key=row_datetime, reverse=True)
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


def parse_sensor_datetime(value):
    normalized = " ".join(str(value).split())
    parts = normalized.split(" ")
    if len(parts) == 3 and parts[1].isalpha():
        normalized = f"{parts[0]} {parts[2]}"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError("日時は ISO 8601 形式で指定してください") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=JST)


def parse_search_query(args):
    filters = {"text": {}, "numeric": {}, "datetime_from": None, "datetime_to": None}
    for field in ("client_id", "region"):
        value = args.get(field, "").strip()
        match = args.get(f"{field}_match", "contains")
        if match not in {"contains", "equals"}:
            raise ValueError(f"{field}_match は contains または equals を指定してください")
        filters["text"][field] = {"value": value, "match": match}

    for parameter in ("datetime_from", "datetime_to"):
        value = args.get(parameter, "").strip()
        if value:
            filters[parameter] = parse_sensor_datetime(value)
    if filters["datetime_from"] and filters["datetime_to"] and filters["datetime_from"] > filters["datetime_to"]:
        raise ValueError("datetime_from は datetime_to 以下にしてください")

    for field in ("temperature", "humidity", "pressure", "co2"):
        values = {}
        for suffix in ("", "_min", "_max"):
            value = args.get(f"{field}{suffix}", "").strip()
            if not value:
                continue
            try:
                values[suffix.removeprefix("_") or "equals"] = float(value)
            except ValueError as error:
                raise ValueError(f"{field}{suffix} は数値で指定してください") from error
        if "min" in values and "max" in values and values["min"] > values["max"]:
            raise ValueError(f"{field}_min は {field}_max 以下にしてください")
        filters["numeric"][field] = values
    return filters


def search_sensor_rows(rows, filters):
    def matches(row):
        for field, condition in filters["text"].items():
            value = condition["value"]
            if not value:
                continue
            row_value = str(row.get(field, ""))
            if condition["match"] == "equals" and row_value != value:
                return False
            if condition["match"] == "contains" and value.lower() not in row_value.lower():
                return False

        if filters["datetime_from"] or filters["datetime_to"]:
            try:
                row_datetime = parse_sensor_datetime(row.get("datetime", ""))
            except (TypeError, ValueError):
                return False
            if filters["datetime_from"] and row_datetime < filters["datetime_from"]:
                return False
            if filters["datetime_to"] and row_datetime > filters["datetime_to"]:
                return False

        for field, condition in filters["numeric"].items():
            if not condition:
                continue
            try:
                row_value = float(row.get(field, ""))
            except (TypeError, ValueError):
                return False
            if "equals" in condition and row_value != condition["equals"]:
                return False
            if "min" in condition and row_value < condition["min"]:
                return False
            if "max" in condition and row_value > condition["max"]:
                return False
        return True

    return [row for row in rows if matches(row)]


def search_filters_payload(filters):
    return {
        "client_id": filters["text"]["client_id"],
        "region": filters["text"]["region"],
        "datetime_from": filters["datetime_from"].isoformat() if filters["datetime_from"] else None,
        "datetime_to": filters["datetime_to"].isoformat() if filters["datetime_to"] else None,
        **filters["numeric"],
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
    health_report = payload.get("health_report")
    runtime = payload.get("runtime")
    if not all(isinstance(value, dict) for value in (client, sensor, server_send, health_report, runtime)):
        return "client, sensor, server_send, health_report, and runtime objects are required"
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
    if not all(is_int(server_send.get(field)) and server_send[field] >= 0 for field in ("success_count", "received_count", "last_ack_sequence", "fail_count", "consecutive_fail_count", "last_status_code")):
        return "server_send counts and status code must be non-negative integers"
    if not all(isinstance(server_send.get(field), str) for field in ("last_success_at", "last_failed_at", "error")):
        return "server_send timestamps and error must be strings"
    if not is_bool(health_report.get("success")):
        return "health_report.success must be a boolean"
    if not all(is_int(health_report.get(field)) and health_report[field] >= 0 for field in ("success_count", "fail_count", "consecutive_fail_count", "last_status_code")):
        return "health_report counts and status code must be non-negative integers"
    if not all(isinstance(health_report.get(field), str) for field in ("last_success_at", "last_failed_at", "error")):
        return "health_report timestamps and error must be strings"
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
    for field in HEALTH_REPORT_FIELDS:
        row[f"health_report_{field}"] = payload["health_report"][field]
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
        "health_report": {},
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
        value = row.get(f"server_send_{field}", "0" if field in {"success_count", "received_count", "last_ack_sequence"} else "")
        payload["server_send"][field] = (
            parse_csv_bool(value) if field == "success"
            else int(value) if field in {"success_count", "received_count", "last_ack_sequence", "fail_count", "consecutive_fail_count", "last_status_code"}
            else value
        )
    for field in HEALTH_REPORT_FIELDS:
        value = row.get(f"health_report_{field}", "0" if field in {"success_count", "fail_count", "consecutive_fail_count", "last_status_code"} else "")
        payload["health_report"][field] = (
            parse_csv_bool(value) if field == "success"
            else int(value) if field in {"success_count", "fail_count", "consecutive_fail_count", "last_status_code"}
            else value
        )
    for field in RUNTIME_FIELDS:
        value = row[f"runtime_{field}"]
        payload["runtime"][field] = int(value) if field in {"loop_count", "uptime_seconds"} else value
    return payload


def migrate_health_history_schema():
    """Add newly introduced health columns before appending to an existing CSV."""
    if not HEALTH_HISTORY_PATH.exists():
        return
    with HEALTH_HISTORY_PATH.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames == HEALTH_FIELDS:
            return
        rows = list(reader)

    migrated_path = HEALTH_HISTORY_PATH.with_suffix(".migrating")
    with migrated_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEALTH_FIELDS)
        writer.writeheader()
        for old_row in rows:
            row = {field: old_row.get(field, "") for field in HEALTH_FIELDS}
            for field in (
                "server_send_success_count", "server_send_received_count", "server_send_last_ack_sequence",
                "health_report_success_count", "health_report_fail_count",
                "health_report_consecutive_fail_count", "health_report_last_status_code",
            ):
                row[field] = old_row.get(field, "0")
            writer.writerow(row)
    migrated_path.replace(HEALTH_HISTORY_PATH)


def append_health_history(payload, received_at):
    HEALTH_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    migrate_health_history_schema()
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


def health_payload(client_id="", region=""):
    with HEALTH_LOCK:
        records = list(LATEST_HEALTH.values())
    records.sort(key=lambda record: record["payload"]["client"]["client_id"])
    client_query = client_id.strip().lower()
    region_query = region.strip().lower()
    clients = [
        {**record["payload"], "received_at": record["received_at"], "status": health_status(record["received_at"])}
        for record in records
        if (not client_query or client_query in record["payload"]["client"]["client_id"].lower())
        and (not region_query or region_query in record["payload"]["client"]["region"].lower())
    ]
    return {
        "offline_after_seconds": int(HEALTH_OFFLINE_AFTER.total_seconds()),
        "filters": {"client_id": client_id.strip(), "region": region.strip()},
        "clients": clients,
    }


def health_history_csv(client_id):
    if not HEALTH_HISTORY_PATH.exists():
        return None

    with HEALTH_HISTORY_PATH.open("r", newline="", encoding="utf-8") as f:
        rows = [
            {field: row.get(field, "") for field in HEALTH_FIELDS}
            for row in csv.DictReader(f)
            if row.get("client_id") == client_id
        ]
    if not rows:
        return None

    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HEALTH_FIELDS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return "\ufeff" + output.getvalue()


def health_download_filename(client_id):
    safe_client_id = re.sub(r"[^A-Za-z0-9._-]+", "_", client_id).strip("._")
    return f"health-{safe_client_id or 'client'}.csv"


def publish_health_update():
    with HEALTH_STREAM_LOCK:
        subscribers = tuple(HEALTH_STREAM_SUBSCRIBERS)
    for subscriber in subscribers:
        subscriber.put_nowait("health")


@app.route("/")
def index():
    return render_template("index.html", **sensor_payload())


@app.route("/api/docs")
def api_docs():
    return render_template("api_docs.html")


@app.route("/api/sensor-data")
def sensor_data():
    return jsonify(sensor_payload())


@app.route("/api/sensor-data/search")
def search_sensor_data():
    try:
        filters = parse_search_query(request.args)
        csv_path, fieldnames, rows = load_sensor_rows()
        rows = search_sensor_rows(rows, filters)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({
        "csv_path": str(csv_path.relative_to(BASE_DIR)),
        "fieldnames": fieldnames,
        "field_labels": FIELD_LABELS,
        "filters": search_filters_payload(filters),
        "rows": rows,
        "row_count": len(rows),
    })


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
    return jsonify(health_payload(
        client_id=request.args.get("client_id", ""),
        region=request.args.get("region", ""),
    ))


@app.route("/api/health/<client_id>/download")
def download_health_history(client_id):
    with HEALTH_LOCK:
        content = health_history_csv(client_id)
    if content is None:
        return jsonify({"error": "health history not found"}), 404
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{health_download_filename(client_id)}"'},
    )


@app.route("/api/health/stream")
def health_stream():
    subscriber = queue.SimpleQueue()

    def events():
        with HEALTH_STREAM_LOCK:
            HEALTH_STREAM_SUBSCRIBERS.add(subscriber)
        try:
            yield f"retry: {HEALTH_STREAM_RETRY_MILLISECONDS}\n\n"
            while True:
                try:
                    subscriber.get(timeout=HEALTH_STREAM_KEEPALIVE_SECONDS)
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
    app.run(host=WEB_HOST, port=WEB_PORT, debug=WEB_DEBUG)
