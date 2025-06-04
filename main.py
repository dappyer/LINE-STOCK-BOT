from flask import Flask, request, abort
import yfinance as yf
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# 環境變數請於 Render 設定
import os
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip().upper()
    stock_code = None

    if text.isdigit():
        stock_code = f"{text}.TW"
    elif text.isalpha():
        stock_code = text

    if stock_code:
        try:
            stock = yf.Ticker(stock_code)
            info = stock.info
            price = info['regularMarketPrice']
            change = info['regularMarketChangePercent']
            reply = f"{stock_code} 價格: {price} 元\n漲跌: {round(change*100, 2)}%"
        except:
            reply = "找不到該股票資訊，請確認代碼是否正確"
    else:
        reply = "請輸入正確的股票代碼，例如：2330 或 AAPL"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run()
