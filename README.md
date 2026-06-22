# Smart Environment Monitor

Raspberry Pi 上の温湿度・気圧・CO2 センサーを監視し、TCP で収集サーバーへ保存したデータを Web ダッシュボードで確認するシステムです。

## 構成

```text
client (Raspberry Pi + sensors)
  ├─ BME280 / DHT22 / MH-Z19C を読み取り
  ├─ TCP JSON Lines で server へ送信
  ├─ ヘルス情報を Web へ HTTP POST
  └─ 必要に応じて Discord へ通知

server
  └─ 受信データを data/sensor_data.csv へ保存

web
  ├─ CSV の一覧・グラフ・ヘルス状態を表示
  └─ JSON API と API ドキュメントを提供
```

| ディレクトリ | 役割 |
| --- | --- |
| `client/` | センサー読み取り、TCP 送信、ヘルスレポート、Discord 通知 |
| `server/` | TCP JSON Lines の受信、重複排除、CSV 保存 |
| `web/` | Flask ダッシュボード、ヘルス受信、JSON API |
| `data/` | `sensor_data.csv` と `health_history.csv` の保存先 |

TCP の送信形式とヘルスレポートの詳細は [client/docs/data-transmission.md](client/docs/data-transmission.md) を参照してください。

## 前提条件

- Python 3.13 以上
- Raspberry Pi でクライアントを動かす場合: BME280、DHT22、MH-Z19C と必要な I2C / GPIO / UART 設定
- クライアント、サーバー、Web が互いに通信できるネットワーク

依存パッケージをインストールします。

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## 設定

クライアントとサーバーはそれぞれのディレクトリにある `.env` を読み込みます。`.env` は Git 管理対象外です。

`server/.env`:

```dotenv
SERVER_ADDR=0.0.0.0
SERVER_PORT=9000
```

`client/.env`:

```dotenv
SERVER_ADDR=192.168.1.10
SERVER_PORT=9000
CLIENT_ID=123456
CLIENT_REGION=tokyo
WEB_HEALTH_URL=http://192.168.1.20:5000/api/health

# 任意。未設定時は Discord 通知を送信しません。
DISCORD_WEBHOOK_URL=
```

センサー関連の既定値は `client/config/settings.py` にあります。

- DHT22 GPIO: `26`
- BME280 I2C アドレス: `0x76`
- MH-Z19C: `/dev/serial0`, 9600 baud

## 起動

次の順で起動します。

1. 収集サーバー

   ```bash
   cd server
   python main.py --mode main
   ```

2. Web ダッシュボード

   ```bash
   cd web
   python app.py
   ```

   `http://<Webサーバー>:5000/` を開きます。API ドキュメントは `http://<Webサーバー>:5000/api/docs` です。

3. センサークライアント

   ```bash
   cd client
   python main.py --mode main
   ```

開発時は実機センサーなしでダミー値を送信できます。

```bash
cd client
python main.py --mode mock --iterations 10 --no-notify
```

`--server-addr`、`--server-port` で送信先を一時的に上書きできます。`--debug` を付けると詳細ログを出力します。

## データ保存

サーバーは `data/sensor_data.csv` を作成し、次の順で保存します。

```text
client_id, region, datetime, session_id, sequence,
temperature, humidity, pressure, co2
```

同じ `client_id`、`session_id`、`sequence` の組合せは重複として保存しません。Web はセンサーデータを日時の新しい順で表示・API 返却します。

ヘルスレポートは Web が `data/health_history.csv` に保存し、端末ごとの最新状態を表示します。最終受信から 30 秒を超える端末はオフラインになります。

## Web API

API のリクエスト例、実行フォーム、実際のレスポンス確認は Web の `http://<Webサーバー>:5000/api/docs` にあります。

| メソッド | エンドポイント | 内容 |
| --- | --- | --- |
| `GET` | `/api/sensor-data` | 全センサーデータ |
| `GET` | `/api/sensor-data/search` | 端末ID、地域、日時、各測定値で検索 |
| `GET` | `/api/health` | 最新ヘルス状態。`client_id` と `region` の部分一致検索に対応 |
| `POST` | `/api/health` | クライアントからヘルスレポートを受信 |
| `GET` | `/api/health/stream` | ヘルス更新の Server-Sent Events |

例:

```bash
curl 'http://localhost:5000/api/sensor-data/search?client_id=TK&temperature_min=25'
curl 'http://localhost:5000/api/health?region=tokyo'
```

## テスト

Web API テスト:

```bash
cd web
python -m unittest discover -s tests -v
```

TCP のクライアント・サーバー結合テスト:

```bash
cd server
python main.py --mode test --target roundtrip --count 10
```

実機センサー個別テスト:

```bash
cd client
python main.py --mode test --target bme280
python main.py --mode test --target dht22
python main.py --mode test --target mhz19c
python main.py --mode test --target notification
```

## 運用上の注意

- 現在の TCP 受信と Web API に認証はありません。信頼できる LAN 内で使い、外部公開する場合はリバースプロキシ、認証、TLS、ファイアウォールを追加してください。
- CSV は継続的に増加します。必要に応じてバックアップ、ローテーション、保管期間を設定してください。
- センサーの読み取りに失敗した場合はデータ送信を行わず、ヘルス状態と通知で確認できます。
