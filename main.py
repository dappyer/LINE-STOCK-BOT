import os
import requests
import yfinance as yf
import mplfinance as mpf
import matplotlib.pyplot as plt
from flask import Flask, request, abort, send_file
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage

# 確保 static 資料夾存在
if not os.path.exists('static'):
    os.makedirs('static')

LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

app = Flask(__name__)

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
    msg = event.message.text.strip().upper()

    if msg.startswith('P') and msg[1:].isalnum():
        stock_id = msg[1:]
        suffix = "" if stock_id.isalpha() else ".TW"
        stock = yf.Ticker(f"{stock_id}{suffix}")
        data = stock.history(period="2d")
        if not data.empty:
            price = data['Close'].iloc[-1]
            prev_close = data['Close'].iloc[-2] if len(data) > 1 else price
            change = price - prev_close
            pct_change = (change / prev_close) * 100 if prev_close != 0 else 0
            volume = data['Volume'].iloc[-1]
            name = stock.info.get('shortName', stock_id)
            reply = f"{name} ({stock_id})\n價格: {price:.2f}\n漲跌: {change:+.2f} ({pct_change:+.2f}%)\n成交量: {int(volume):,}"
        else:
            reply = f"查無 {stock_id} 的即時資料"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    elif msg.startswith('K') and msg[1:].isalnum():
        stock_id = msg[1:]
        suffix = "" if stock_id.isalpha() else ".TW"
        stock = yf.Ticker(f"{stock_id}{suffix}")
        data = stock.history(period="1mo")
        if not data.empty:
            mpf.plot(data, type='candle', style='charles', volume=True, savefig='static/kchart.png')
            line_bot_api.reply_message(
                event.reply_token,
                ImageSendMessage(
                    original_content_url="https://line-stock-bot-0966.onrender.com/static/kchart.png",
                    preview_image_url="https://line-stock-bot-0966.onrender.com/static/kchart.png"
                )
            )
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"查無 {stock_id} 的K線資料"))

    elif msg.startswith('T') and msg[1:].isdigit():
        stock_id = msg[1:]
        url = f"https://www.twse.com.tw/fund/TWT38U?response=json&selectType=ALL&stockNo={stock_id}"
        res = requests.get(url)
        try:
            data = res.json()['data'][0]
            reply = f"三大法人買賣資訊（{stock_id}）\n日期: {data[0]}\n外資: {data[1]}\n投信: {data[4]}\n自營商: {data[7]}"
        except Exception:
            reply = f"查無 {stock_id} 的三大法人資料"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    elif msg.startswith("IND") and msg[3:].isalnum():
        stock_id = msg[3:]
        suffix = "" if stock_id.isalpha() else ".TW"
        stock = yf.Ticker(f"{stock_id}{suffix}")
        data = stock.history(period="3mo")
        if not data.empty:
            try:
                data['MA5'] = data['Close'].rolling(window=5).mean()
                data['MA20'] = data['Close'].rolling(window=20).mean()
                mpf.plot(data, type='candle', style='charles', mav=(5, 20), volume=True, savefig='static/indicator.png')
                line_bot_api.reply_message(
                    event.reply_token,
                    ImageSendMessage(
                        original_content_url="https://line-stock-bot-0966.onrender.com/static/indicator.png",
                        preview_image_url="https://line-stock-bot-0966.onrender.com/static/indicator.png"
                    )
                )
            except Exception:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{stock_id} 無法產製技術指標圖"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"查無 {stock_id} 的資料"))

    elif msg == "HELP":
        instructions = (
            "\n指令教學：\n"
            "P2330 → 即時股價\n"
            "K2330 → 日K線圖\n"
            "T2330 → 三大法人資料\n"
            "PTSLA → 美股即時股價\n"
            "KTSLA → 美股K線圖\n"
            "IND2330 或 INDTSLA → 技術指標圖(MA5/20)"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=instructions))

    else:
        return

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
