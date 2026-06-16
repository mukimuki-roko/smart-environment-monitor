import json
import urllib.error
import urllib.request
import logging

logger = logging.getLogger(__name__)


def notify_discord(webhook_url, message):
    logger.debug("webhook_url is set: %s", bool(webhook_url))
    logger.debug("message length: %d", len(message) if message else 0)
    #念のためトークンの存在チェック
    if not webhook_url:
        logger.warning("Discord notification skipped: DISCORD_WEBHOOK_URL is not set")
        return
    #ウェブフックのURLが間違っている場合
    if not webhook_url.startswith(("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")):
        logger.warning("Discord notification skipped: invalid webhook URL")
        return
    payload = json.dumps({"content": message}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "smart-environment-monitor/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5):
            pass
        logger.info('discord notification is success')
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error("Discord notification failed: HTTP %s: %s", e.code, body)
    except (urllib.error.URLError, TimeoutError) as e:
        logger.error("Discord notification failed: %s", e)
