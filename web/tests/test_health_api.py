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

        restored = web_app.load_latest_health()
        self.assertEqual(restored["client-a"]["payload"]["runtime"]["uptime_seconds"], 3600)

    def test_reject_invalid_health_payload(self):
        response = self.client.post("/api/health", json={"client": {}})
        self.assertEqual(response.status_code, 400)

    def test_health_stream_is_event_stream(self):
        response = self.client.get("/api/health/stream", buffered=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/event-stream")
        self.assertEqual(next(response.response), b"retry: 3000\n\n")
        response.close()


if __name__ == "__main__":
    unittest.main()
