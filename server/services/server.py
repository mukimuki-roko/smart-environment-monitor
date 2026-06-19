import csv
import json
import logging
import socket
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

CSV_PATH = Path("data/sensor_data.csv")
CSV_LOCK = threading.Lock()

CSV_FIELDS = [
    "client_id",
    "region",
    "datetime",
    "temperature",
    "humidity",
    "pressure",
    "co2",
]

def save_received_data_to_csv(payload):
    # payloadからセンサーデータ部分を取り出す
    sensor_data = payload["sensor_data"]

    # CSVに書き込む1行分のデータを整形する
    # メタデータ（client_id, region, datetime）＋センサー値を1つにまとめる
    row = {
        "client_id": payload["client_id"],
        "region": payload["region"],
        "datetime": payload["datetime"],
        "temperature": sensor_data["temperature"],
        "humidity": sensor_data["humidity"],
        "pressure": sensor_data["pressure"],
        "co2": sensor_data["co2"],
    }
    # 排他制御
    # 複数スレッドから同時に書き込みが発生すると
    # CSVが壊れる可能性があるためロックをかける
    with CSV_LOCK:

        # CSVファイルが既に存在しているか確認
        file_exists = CSV_PATH.exists()

        # ファイルを追記モードで開く
        with CSV_PATH.open("a", newline="", encoding="utf-8") as f:

            # CSVライターを作成（列名はCSV_FIELDSで固定）
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)

            # 初回のみヘッダーを書き込む
            if not file_exists:
                writer.writeheader()

            # 1行分のデータを書き込む
            writer.writerow(row)


def handle_client(conn):
    try:
        # これは分割されて届いたデータを一時的に入れておくリスト
        # これで通信によりデータが分断された場合でも安全に管理することができる。
        chunks = []
        while True:
            data = conn.recv(1024)
            if not data:
                break
            chunks.append(data)
            logger.info("received data: %s", data)
            # そのままだと読めんからデコード
            payload = json.loads(data.decode("utf-8"))
            # 保存処理
            save_received_data_to_csv(payload)
    except json.JSONDecodeError as e:
        logger.error("invalid json: %s",e)
    finally:
        conn.close()


def start_server(server_addr, server_port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((server_addr, server_port))
        server.listen()
        logger.info("server listening on %s:%s", server_addr, server_port)
        while True:
            conn, addr = server.accept()
            logger.info("connected: %s", addr)
            t = threading.Thread(
                target=handle_client,
                args=(conn,),
                daemon=True,
            )
            t.start()
    except socket.error as e:
        logger.error("socket error: %s", e)
        server.close()
