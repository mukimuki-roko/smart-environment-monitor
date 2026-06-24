import tempfile
import unittest
from pathlib import Path

import app as web_app


def health_payload(client_id="client-a"):
    sensor = lambda name: {
        "name": name,
        "connect": True,
        "read": True,
        "read_count": 3,
        "fail_count": 0,
        "consecutive_fail_count": 0,
        "last_success_at": "2026-06-21T10:00:00+09:00",
        "last_failed_at": "",
        "error": "",
    }
    return {
        "client": {"client_id": client_id, "region": "tokyo"},
        "sensor": {
            "bme280": sensor("BME280"),
            "dht22": sensor("DHT22"),
            "mhz19c": sensor("MHZ19C"),
        },
        "server_send": {
            "success": True,
            "success_count": 3,
            "received_count": 12,
            "last_ack_sequence": 3,
            "fail_count": 0,
            "consecutive_fail_count": 0,
            "last_success_at": "2026-06-21T10:00:00+09:00",
            "last_failed_at": "",
            "last_status_code": 201,
            "error": "",
        },
        "health_report": {
            "success": True,
            "success_count": 3,
            "fail_count": 0,
            "consecutive_fail_count": 0,
            "last_success_at": "2026-06-21T10:00:00+09:00",
            "last_failed_at": "",
            "last_status_code": 201,
            "error": "",
        },
        "runtime": {
            "started_at": "2026-06-21T09:00:00+09:00",
            "last_loop_at": "2026-06-21T10:00:00+09:00",
            "loop_count": 3,
            "uptime_seconds": 3600,
        },
    }


class HealthApiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_path = web_app.HEALTH_HISTORY_PATH
        self.original_latest = web_app.LATEST_HEALTH.copy()
        web_app.HEALTH_HISTORY_PATH = Path(self.temp_dir.name) / "health_history.csv"
        web_app.LATEST_HEALTH.clear()
        self.client = web_app.app.test_client()

    def tearDown(self):
        web_app.HEALTH_HISTORY_PATH = self.original_path
        web_app.LATEST_HEALTH.clear()
        web_app.LATEST_HEALTH.update(self.original_latest)
        self.temp_dir.cleanup()

    def test_receive_list_and_restore_health(self):
        response = self.client.post("/api/health", json=health_payload())
        self.assertEqual(response.status_code, 201)
        self.assertTrue(web_app.HEALTH_HISTORY_PATH.exists())

        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        client = response.get_json()["clients"][0]
        self.assertEqual(client["status"], "online")
        self.assertEqual(client["sensor"]["dht22"]["read_count"], 3)
        self.assertEqual(client["server_send"]["last_status_code"], 201)
        self.assertEqual(client["server_send"]["success_count"], 3)
        self.assertEqual(client["server_send"]["received_count"], 12)

        restored = web_app.load_latest_health()
        self.assertEqual(restored["client-a"]["payload"]["runtime"]["uptime_seconds"], 3600)

    def test_reject_invalid_health_payload(self):
        response = self.client.post("/api/health", json={"client": {}})
        self.assertEqual(response.status_code, 400)

    def test_filters_health_by_client_id_and_region(self):
        self.client.post("/api/health", json=health_payload("client-tokyo"))
        payload = health_payload("client-osaka")
        payload["client"]["region"] = "osaka"
        self.client.post("/api/health", json=payload)

        response = self.client.get("/api/health?region=osa&client_id=client")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/json")
        data = response.get_json()
        self.assertEqual(data["filters"], {"client_id": "client", "region": "osa"})
        self.assertEqual([client["client"]["client_id"] for client in data["clients"]], ["client-osaka"])

    def test_downloads_all_history_for_one_client_as_csv(self):
        self.client.post("/api/health", json=health_payload("client-a"))
        second = health_payload("client-a")
        second["runtime"]["loop_count"] = 4
        self.client.post("/api/health", json=second)
        self.client.post("/api/health", json=health_payload("client-b"))

        response = self.client.get("/api/health/client-a/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")
        self.assertEqual(response.headers["Content-Disposition"], 'attachment; filename="health-client-a.csv"')
        self.assertTrue(response.data.startswith(b"\xef\xbb\xbf"))
        rows = list(web_app.csv.DictReader(response.data.decode("utf-8-sig").splitlines()))
        self.assertEqual([row["client_id"] for row in rows], ["client-a", "client-a"])
        self.assertEqual([row["runtime_loop_count"] for row in rows], ["3", "4"])

    def test_download_returns_not_found_when_client_has_no_history(self):
        response = self.client.get("/api/health/missing/download")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "health history not found"})

    def test_migrates_history_without_success_count(self):
        old_fields = [field for field in web_app.HEALTH_FIELDS if field != "server_send_success_count"]
        old_row = web_app.flatten_health(health_payload(), "2026-06-21T10:00:00+09:00")
        old_row.pop("server_send_success_count")
        with web_app.HEALTH_HISTORY_PATH.open("w", newline="", encoding="utf-8") as f:
            writer = web_app.csv.DictWriter(f, fieldnames=old_fields)
            writer.writeheader()
            writer.writerow(old_row)

        web_app.append_health_history(health_payload(), "2026-06-21T10:01:00+09:00")

        with web_app.HEALTH_HISTORY_PATH.open("r", newline="", encoding="utf-8") as f:
            rows = list(web_app.csv.DictReader(f))
        self.assertEqual(rows[0]["server_send_success_count"], "0")
        self.assertEqual(rows[1]["server_send_success_count"], "3")

    def test_health_stream_is_event_stream(self):
        response = self.client.get("/api/health/stream", buffered=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/event-stream")
        self.assertEqual(next(response.response), b"retry: 3000\n\n")
        response.close()


if __name__ == "__main__":
    unittest.main()
