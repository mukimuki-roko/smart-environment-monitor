import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=True)

def require_env(name): #.envにデータが設定されているかチェック
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is not set. Please check .env")
    return value

SERVER_ADDR = require_env("SERVER_ADDR")
SERVER_PORT = int(require_env("SERVER_PORT"))

CLIENT_REGION = require_env("CLIENT_REGION")
CLIENT_ID = require_env("CLIENT_ID")

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

DEFAULT_SEND_INTERVAL = 4

#dht22関連設定
DHT22_GPIO = 26

#mh_z19c関連設定
SERIAL_PORT = "/dev/serial0"
SERIAL_BAUDRATE = 9600
SERIAL_TIMEOUT = 1

#bme280関連設定
BME280_ADDR = 0x76