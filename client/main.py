import argparse
import logging
import datetime
import time
import json
import socket

from sensor.dummy import get_dummy_data
try:
    from config import *
except ValueError as e:
    print(e)
    exit(1)

logger = logging.getLogger(__name__)

def setup_logging(debug: bool):
    #ログレベルの設定
    level = logging.DEBUG if debug else logging.INFO
    #ログのフォーマットの設定
    if debug:
        log_format = "[%(levelname)s] (%(filename)s:%(funcName)s) %(message)s"
    else:
        log_format = "[%(levelname)s] %(message)s"
    logging.basicConfig(
        level=level,
        format=log_format
    )
    return

def parse_args():
    #起動変数の設定
    parser = argparse.ArgumentParser()
    parser.add_argument('-m','--mode',choices=MODE_HANDLERS.keys(),help='動作モードの指定')
    parser.add_argument('-t','--target',choices=TEST_HANDLERS.keys(),help='テスト対象の指定(動作モードがtestの場合のみ実行可能)')
    parser.add_argument('-d','--debug',action='store_true',help='デバッグモードで実行')
    
    return parser.parse_args()

#起動変数のハンドラ関数
def parse_handler(args):
    
    logger.info("mode: %s",args.mode)
    handler = MODE_HANDLERS.get(args.mode)
    if not handler:
        if not args.mode:
            run_send_loop()
        logger.warning("unknown mode: %s",args.mode)
        return
    handler(args)

#テストモードのハンドラ関数
def handle_test_mode(args):
    handler = TEST_HANDLERS.get(args.target)
    if not handler:
        logger.warning("unknown test target: %s", args.target)
        return
    logger.info("start test: %s", args.target)
    handler()
    logger.info("finish test: %s", args.target)

#モックモードのハンドラ関数
def handle_mock_mode(args):
    run_send_loop(args.mode)
    

MODE_HANDLERS = {
    "test":handle_test_mode,
    "mock":handle_mock_mode,
}

#通知のテスト関数
def test_notification():
    from notification.discord import notify_discord
    url = DISCORD_WEBHOOK_URL
    message = 'notification test'
    notify_discord(url,message)
    
TEST_HANDLERS = {
    "notification":test_notification
}

#送信ループ関数
def run_send_loop(mode='default'):
    while True:
        try:
            if mode == 'mock':
                sensor_data = get_dummy_data()
            elif mode == "default":
                #後で実際のセンサー取得に切り替え
                sensor_data = get_dummy_data()
            rawData = {
                "client_id":CLIENT_ID,
                "region":CLIENT_REGION,
                "datetime": datetime.datetime.now().isoformat(),
                "sensor_data":sensor_data
            }
            payload = json.dumps(rawData).encode("utf-8")
            #withを使って勝手にソケットをcloseしてくれる
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((SERVER_ADDR,SERVER_PORT))
                sock.sendall(payload)
            logger.info("sensor data sent")

            time.sleep(DEFAULT_SEND_INTERVAL)

        except OSError as e:
            logger.error("socket send failed: %s", e)
            time.sleep(DEFAULT_SEND_INTERVAL)
        except KeyboardInterrupt as e:
            logger.info("Ctrl + C \nstop system")
    
def main():
    args = parse_args()
    setup_logging(args.debug)
    parse_handler(args)

if __name__ == "__main__":
    main()
