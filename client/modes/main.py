import logging
import time
from datetime import datetime, timedelta, timezone

from config.settings import (
    CLIENT_ID,
    CLIENT_REGION,
    DEFAULT_SEND_INTERVAL,
    DHT22_GPIO,
    DISCORD_WEBHOOK_URL,
    HEARTBEAT_INTERVAL,
)
from sensor.bme280 import BME280Sensor
from sensor.dht22 import DHT22Sensor
from sensor.mhz19c import MHZ19CSensor
from services.heartbeart import send_heartbeat
from services.notification.discord import notify_discord
from services.payload import build_payload, build_server_disconnect_error_embed
from services.sender import send_to_server
from utils.data_class import ClientHeartBeat, ClientMetaData, ClientRuntimeHealth

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))


def now_string() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def update_sensor_health(sensor_health, read_ok: bool, error: str = ""):
    if read_ok:
        sensor_health.connect = True
        sensor_health.read = True
        sensor_health.read_count += 1
        sensor_health.consecutive_fail_count = 0
        sensor_health.last_success_at = now_string()
        sensor_health.error = ""
        return

    sensor_health.read = False
    sensor_health.fail_count += 1
    sensor_health.consecutive_fail_count += 1
    sensor_health.last_failed_at = now_string()
    sensor_health.error = error


def run_main_mode(args):
    started_at = now_string()
    health = ClientHeartBeat(
        client=ClientMetaData(client_id=CLIENT_ID, region=CLIENT_REGION),
        runtime=ClientRuntimeHealth(started_at=started_at),
    )
    dht22 = DHT22Sensor(gpio=DHT22_GPIO)
    bme280 = BME280Sensor()
    mhz19c = MHZ19CSensor()
    last_heartbeat_at = time.monotonic()

    logger.info("start main mode")

    try:
        while True:
            health.runtime.loop_count += 1
            health.runtime.last_loop_at = now_string()
            health.runtime.uptime_seconds = int(
                datetime.now(JST).timestamp()
                - datetime.fromisoformat(started_at).timestamp()
            )

            dht_health = health.sensor.dht22
            dht_data = dht22.read()
            dht_read_ok = dht_data is not None

            bme_health = health.sensor.bme280
            bme_data = bme280.read()
            bme_read_ok = bme_data["pressure"] is not None

            mhz19c_health = health.sensor.mhz19c
            mhz19c_data = mhz19c.read()
            mhz19c_read_ok = mhz19c_data["co2"] is not None

            sensor_read_ok = dht_read_ok and bme_read_ok and mhz19c_read_ok
            update_sensor_health(
                dht_health,
                dht_read_ok,
                "DHT22 read failed",
            )
            update_sensor_health(
                bme_health,
                bme_read_ok,
                "BME280 read failed",
            )
            update_sensor_health(
                mhz19c_health,
                mhz19c_read_ok,
                "MH-Z19C read failed",
            )

            if not dht_read_ok:
                logger.warning(
                    "DHT22 read failed: consecutive_fail_count=%d",
                    dht_health.consecutive_fail_count,
                )
            if not bme_read_ok:
                logger.warning(
                    "BME280 read failed: consecutive_fail_count=%d",
                    bme_health.consecutive_fail_count,
                )
            if not mhz19c_read_ok:
                logger.warning(
                    "MH-Z19C read failed: consecutive_fail_count=%d",
                    mhz19c_health.consecutive_fail_count,
                )

            if sensor_read_ok:
                sensor_data = {
                    "temperature": dht_data["temperature"],
                    "humidity": dht_data["humidity"],
                    "pressure": bme_data["pressure"],
                    "co2": mhz19c_data["co2"],
                }
                try:
                    payload = build_payload(sensor_data)
                    send_to_server(payload, args.server_addr, args.server_port)

                    health.server_send.success = True
                    health.server_send.consecutive_fail_count = 0
                    health.server_send.last_success_at = now_string()
                    health.server_send.error = ""
                    logger.info("sensor data sent")

                except OSError as e:
                    health.server_send.success = False
                    health.server_send.fail_count += 1
                    health.server_send.consecutive_fail_count += 1
                    health.server_send.last_failed_at = now_string()
                    health.server_send.error = str(e)
                    logger.error("socket send failed: %s", e)
                    notify_discord(
                        DISCORD_WEBHOOK_URL,
                        build_server_disconnect_error_embed(
                            payload, args.server_addr, args.server_port
                        ),
                    )

            now = time.monotonic()
            if now - last_heartbeat_at >= HEARTBEAT_INTERVAL:
                send_heartbeat(health)
                last_heartbeat_at = now

            time.sleep(DEFAULT_SEND_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Ctrl + C: stop main mode")

    finally:
        dht22.close()
        if mhz19c.ser is not None:
            mhz19c.ser.close()
