import logging
import time
from datetime import datetime,timezone,timedelta
from config.settings import (
    DEFAULT_SEND_INTERVAL,
    DISCORD_WEBHOOK_URL,
    HEARTBEAT_INTERVAL,
    CLIENT_ID,
    CLIENT_REGION
)
from services.notification.discord import notify_discord
from sensor.dummy import get_dummy_data
from services.payload import build_payload, build_server_disconnect_error_embed
from services.sender import send_to_server
from services.heartbeart import send_heartbeat
from utils.data_class import (
    ClientHeartBeat,
    ClientMetaData,
    ClientRuntimeHealth,
)

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

def now_string() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")

def run_mock_mode(args):
    started_at = now_string()
    
    health = ClientHeartBeat(
        client=ClientMetaData(
            client_id = CLIENT_ID,
            region = CLIENT_REGION,
        ),
        runtime=ClientRuntimeHealth(started_at = started_at)
    )
    logger.info("start mock mode")
    while True:
        try:
            health.runtime.loop_count += 1
            health.runtime.last_loop_at = now_string()
            health.runtime.uptime_seconds = int(
                datetime.now(JST).timestamp() 
                - datetime.fromisoformat(started_at).timestamp()
            )
            dht_health = health.sensor.dht22
            
            sensor_data = get_dummy_data()
            sensor_read = True
            logger.debug(sensor_data)
            payload = build_payload(sensor_data)
            sensor_data = True
            send_to_server(payload, args.server_addr, args.server_port)

            logger.info("mock sensor data sent")
        except OSError as e:
            heartbeat_error = None
            logger.error("socket send failed: %s", e)
            embed_message = build_server_disconnect_error_embed(
                payload, args.server_addr, args.server_port
            )
            notify_discord(DISCORD_WEBHOOK_URL, embed_message)
            time.sleep(DEFAULT_SEND_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Ctrl + C\nstop mock mode")
            break

        finally:
            now = time.monotonic()
            if now - last_heart_beat >= HEARTBEAT_INTERVAL:
                send_heartbeat(sensor_read, sensor_data, heartbeat_error)
                last_heart_beat = now
            time.sleep
