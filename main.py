import os
import requests
import yfinance as yf
import mplfinance as mpf
import matplotlib.pyplot as plt
import twstock
from bs4 import BeautifulSoup
from flask import Flask, request, abort, send_file, render_template_string
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import threading
import pandas as pd

if not os.path.exists('static'):
    os.makedirs('static')

LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
USER_ID = os.getenv('LINE_USER_ID', 'YOUR_USER_ID')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

app = Flask(__name__)
scheduler = BackgroundScheduler()


def get_news(stock_id):
    try:
        url = f"https://www.cnyes.com/twstock/{stock_id}/news"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        articles = soup.select("section a[href^='/news/story/']")
        if not articles:
            return "無最新新聞"
        latest = articles[0].text.strip()
        href = "https://www.cnyes.com" + articles[0]['href']
        return f"{stock_id} 最新新聞：\n{latest}\n{href}"
    except:
        return "新聞讀取失敗"


def get_comments(stock_id):
    try:
        url = f"https://www.cmoney.tw/forum/stock/{stock_id}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        comment = soup.select_one("div.comment-item")
        if comment:
            return f"{stock_id} 熱門留言（CMoney）：\n{comment.text.strip()[:150]}..."
        return "無熱門留言"
    except:
        return "留言讀取失敗"


def get_tw_price(stock_id):
    try:
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{stock_id}.tw|otc_{stock_id}.tw"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        json_data = res.json()
        if not json_data['msgArray']:
            return f"查無 {stock_id} 的報價（可能非上市上櫃）"
        data = json_data['msgArray'][0]
        name = data['n']
        price = data['z']
        y_price = data['y']
        vol = data['v']
        change = float(price) - float(y_price)
        percent = (change / float(y_price)) * 100
        return f"{name} ({stock_id})\n現價: {price}\n漲跌: {change:+.2f} ({percent:+.2f}%)\n成交量: {vol}"
    except Exception as e:
        return f"台股即時報價擷取失敗：{e}"


def draw_k_line(stock_id):
    try:
        stock = twstock.Stock(stock_id)
        df = stock.fetch_from(2024, 1)
        if not df:
            return None
        data = {
            'Open': [d.open for d in df],
            'High': [d.high for d in df],
            'Low': [d.low for d in df],
            'Close': [d.close for d in df],
            'Volume': [d.volume for d in df]
        }
        index = [datetime.datetime(d.date.year, d.date.month, d.date.day) for d in df]
        df_pd = pd.DataFrame(data, index=index)
        filename = f"static/kline_{stock_id}.png"
        mpf.plot(df_pd, type='candle', volume=True, style='charles', savefig=filename)
        return filename
    except:
        return None


def get_institutional_trades(stock_id):
    try:
        url = f"https://www.twse.com.tw/fund/T86?response=json&selectType=ALL&date=&stockNo={stock_id}"
        res = requests.get(url, timeout=5)
        json_data = res.json()
        if not json_data['data']:
            return f"查無 {stock_id} 的三大法人買賣超資料"
        latest = json_data['data'][-1]
        date, foreign, inv_trust, dealer = latest[0], latest[6], latest[7], latest[8]
        return f"{stock_id} 法人買賣超 ({date})\n外資: {foreign}\n投信: {inv_trust}\n自營商: {dealer}"
    except:
        return "法人資料擷取失敗"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip().upper()

    if text.startswith('P'):
        stock_id = text[1:]
        reply = get_tw_price(stock_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    elif text.startswith('K'):
        stock_id = text[1:]
        path = draw_k_line(stock_id)
        if path:
            image_url = f"https://line-stock-bot-0966.onrender.com/{path}"
            image_message = ImageSendMessage(
                original_content_url=image_url,
                preview_image_url=image_url
            )
            line_bot_api.reply_message(event.reply_token, image_message)
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="K 線圖製作失敗"))

    elif text.startswith('T'):
        stock_id = text[1:]
        reply = get_institutional_trades(stock_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    elif text.startswith('N'):
        stock_id = text[1:]
        reply = get_news(stock_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    elif text.startswith('B'):
        stock_id = text[1:]
        reply = get_comments(stock_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))


@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


@app.route('/')
def home():
    return 'LINE Bot is running'


if __name__ == "__main__":
    scheduler.start()
    app.run(host="0.0.0.0", port=10000)
