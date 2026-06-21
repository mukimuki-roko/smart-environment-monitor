import json
import logging
import urllib.error
import urllib.request
from dataclasses import asdict

from config.settings import WEB_HEALTH_INTERVAL
from utils.data_class import ClientHeartBeat

logger = logging.getLogger(__name__)


def send_heartbeat(
    health: ClientHeartBeat,
    web_health_url=None,
    timeout=5,
):
    url = web_health_url or WEB_HEALTH_INTERVAL
    if not url:
        logger.warning("heartbeat url is not set")
        return False

    payload = asdict(health)

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = response.getcode()
            if 200 <= status_code < 300:
                logger.debug("heartbeat sent: status=%s", status_code)
                return True

            logger.warning("heartbeat failed: status=%s", status_code)
            return False

    except urllib.error.HTTPError as e:
        logger.warning("heartbeat failed: status=%s", e.code)
        return False
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        logger.warning("heartbeat request failed: %s", e)
        return False
