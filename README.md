# LINE-STOCK-BOT

這是一個用 Python Flask + LINE Messaging API 實作的股票機器人，可查詢台股與美股即時報價。

## 功能

- 輸入台股（如 2330）或美股（如 AAPL）代碼，回傳即時價格與漲跌幅。

## 使用說明

1. 部署到 Render（需設定環境變數 LINE_CHANNEL_SECRET / ACCESS_TOKEN）
2. 將 `/callback` 設為 LINE Webhook URL

