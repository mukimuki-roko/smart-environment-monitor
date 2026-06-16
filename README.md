# smart-environment-monitor

## Client

実センサーを使って送信する場合:

```bash
python3 client/main.py
```

センサー未接続、またはセンサー故障の可能性がある状態で開発する場合は、テストデータを送信する:

```bash
python3 client/main.py --test
```

`--test` では DHT22、MH-Z19C、BME280 の初期化を行わず、固定のダミー値を送信する。

通信エラーをDiscordへ通知する場合は、`client/.env` にDiscord Webhook URLを設定する:

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```
