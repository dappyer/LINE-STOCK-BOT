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

# 確保 static 資料夾存在
if not os.path.exists('static'):
    os.makedirs('static')

LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
USER_ID = os.getenv('LINE_USER_ID', 'YOUR_USER_ID')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

app = Flask(__name__)
scheduler = BackgroundScheduler()

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@app.route("/admin")
def admin():
    return render_template_string("""
        <html><head><title>Line Bot 管理後台</title></head>
        <body>
        <h1>管理後台</h1>
        <p>這是簡易版的後台頁面。</p>
        <ul>
            <li><a href='/static/kchart.png' target='_blank'>最新 K 線圖</a></li>
            <li><a href='/static/indicator.png' target='_blank'>最新技術指標圖</a></li>
        </ul>
        </body></html>
    """)

def get_fundamentals(stock_id):
    try:
        url = f"https://www.cmoney.tw/finance/{stock_id}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        data = soup.select(".stock-financial tbody tr")
        eps, pe, bps, yield_ = "N/A", "N/A", "N/A", "N/A"
        for row in data:
            cols = row.find_all("td")
            if len(cols) >= 4:
                if "每股盈餘(EPS)" in row.text:
                    eps = cols[1].text.strip()
                elif "本益比(PER)" in row.text:
                    pe = cols[1].text.strip()
                elif "每股淨值(BPS)" in row.text:
                    bps = cols[1].text.strip()
                elif "殖利率" in row.text:
                    yield_ = cols[1].text.strip()
        return f"{stock_id} 基本資料：\nEPS: {eps}\nP/E: {pe}\nBPS: {bps}\n殖利率: {yield_}"
    except:
        return f"查無 {stock_id} 基本面資料"

def get_strategy(stock_id):
    stock = yf.Ticker(stock_id if '.' in stock_id else f"{stock_id}.TW")
    data = stock.history(period="1mo")
    if data.empty:
        return f"查無 {stock_id} 的策略建議資料"
    try:
        ma5 = data['Close'].rolling(window=5).mean().iloc[-1]
        ma20 = data['Close'].rolling(window=20).mean().iloc[-1]
        close = data['Close'].iloc[-1]
        trend = "偏多" if ma5 > ma20 and close > ma5 else "觀望/偏空"
        return f"{stock_id} 策略建議：\n目前收盤: {close:.2f}\nMA5: {ma5:.2f}\nMA20: {ma20:.2f}\n趨勢建議: {trend}"
    except:
        return f"{stock_id} 策略分析失敗"

def get_earnings_info(stock_id):
    try:
        url = f"https://mops.twse.com.tw/mops/web/ajax_t100sb15?encodeURIComponent=1&step=1&firstin=true&TYPEK=sii&co_id={stock_id}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        if "查無資料" in res.text:
            return f"{stock_id} 無法查詢財報資訊"
        return f"{stock_id} 財報日程請參見公開資訊觀測站"
    except:
        return f"查無 {stock_id} 財報資訊"

def get_news(stock_id):
    try:
        url = f"https://www.cnyes.com/twstock/{stock_id}/news"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, "html.parser")
        articles = soup.select("a._1Zdp")
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
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, "html.parser")
        comment = soup.select_one(".forum-card__content")
        if comment:
            return f"{stock_id} 熱門留言：\n{comment.text.strip()}"
        return "無熱門留言"
    except:
        return "留言讀取失敗"

def get_price(stock_id):
    try:
        if stock_id.isdigit():
            rt = twstock.realtime.get(stock_id)
            if rt['success']:
                info = rt['info']
                rtdata = rt['realtime']
                name = info['name']
                price = rtdata['latest_trade_price']
                change = float(rtdata.get('change', 0))
                percent = float(rtdata.get('change_percent', 0))
                vol = rtdata['accumulate_trade_volume']
                return f"{name}({stock_id})\n現價: {price} 元\n漲跌: {change} ({percent}%)\n成交量: {vol} 張"
            else:
                return f"查無 {stock_id} 即時資訊"
        else:
            stock = yf.Ticker(stock_id)
            data = stock.history(period="1d")
            close = data['Close'].iloc[-1]
            change = close - data['Open'].iloc[-1]
            percent = (change / data['Open'].iloc[-1]) * 100
            return f"{stock_id}\n現價: {close:.2f}\n漲跌: {change:.2f} ({percent:.2f}%)"
    except:
        return "股價查詢失敗"

def get_kchart(stock_id):
    try:
        stock = yf.Ticker(stock_id if '.' in stock_id else f"{stock_id}.TW")
        df = stock.history(period="3mo")
        if df.empty:
            return False
        mpf.plot(df, type='candle', style='charles', mav=(5, 20), volume=True, savefig='static/kchart.png')
        return True
    except:
        return False

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip().upper()

    if msg == "HELP":
        reply = "請輸入以下指令：\nF+股票代號 查基本面\nS+股票代號 策略建議\nE+股票代號 財報日程\nN+股票代號 最新新聞\nB+股票代號 熱門留言\nP+股票代號 即時股價\nK+股票代號 K線圖"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if not any(msg.startswith(prefix) for prefix in ["F", "S", "E", "N", "B", "P", "K"]):
        return

    stock_id = msg[1:]
    cmd = msg[0]

    if cmd == "F" and stock_id.isdigit():
        reply = get_fundamentals(stock_id)
    elif cmd == "S":
        reply = get_strategy(stock_id)
    elif cmd == "E" and stock_id.isdigit():
        reply = get_earnings_info(stock_id)
    elif cmd == "N":
        reply = get_news(stock_id)
    elif cmd == "B":
        reply = get_comments(stock_id)
    elif cmd == "P":
        reply = get_price(stock_id)
    elif cmd == "K":
        success = get_kchart(stock_id)
        if success:
            image_url = f"https://line-stock-bot-0966.onrender.com/static/kchart.png"
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=image_url, preview_image_url=image_url))
            return
        else:
            reply = "K 線圖產生失敗"
    else:
        reply = "無效的股票代號格式"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

scheduler.add_job(lambda: line_bot_api.push_message(USER_ID, TextSendMessage(text="[推播] 可自訂 AI 新聞內容")), 'cron', hour=8, minute=30)
scheduler.start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)

