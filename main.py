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
        articles = soup.select("a[href^='/news/id/']")
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
        comment = soup.select_one(".forum-card__content")
        if comment:
            return f"{stock_id} 熱門留言：\n{comment.text.strip()}"
        return "無熱門留言"
    except:
        return "留言讀取失敗"

def get_tw_price(stock_id):
    try:
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{stock_id}.tw"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = res.json()['msgArray'][0]
        name = data['n']
        price = data['z']
        y_price = data['y']
        vol = data['v']
        change = float(price) - float(y_price)
        percent = (change / float(y_price)) * 100
        return f"{name} ({stock_id})\n現價: {price}\n漲跌: {change:+.2f} ({percent:+.2f}%)\n成交量: {vol}"
    except:
        return "台股即時報價擷取失敗"

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
        <ul>
            <li><a href='/static/kchart.png' target='_blank'>最新 K 線圖</a></li>
            <li><a href='/static/indicator.png' target='_blank'>最新技術指標圖</a></li>
        </ul>
        </body></html>
    """)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip().upper()
    reply = None

    if msg.startswith("P"):
        stock_id = msg[1:]
        if stock_id.isdigit():
            reply = get_tw_price(stock_id)
        else:
            try:
                stock = yf.Ticker(stock_id)
                price = stock.info['regularMarketPrice']
                name = stock.info['shortName']
                reply = f"{name} ({stock_id})\n現價: {price}"
            except:
                reply = "股價查詢失敗"

    elif msg.startswith("K"):
        stock_id = msg[1:]
        try:
            df = yf.download(stock_id + ".TW" if stock_id.isdigit() else stock_id, period="1mo", interval="1d")
            mpf.plot(df, type='candle', style='charles', savefig='static/kchart.png')
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(
                original_content_url=request.url_root + 'static/kchart.png',
                preview_image_url=request.url_root + 'static/kchart.png'))
            return
        except:
            reply = "K線圖取得失敗"

    elif msg.startswith("T") and msg[1:].isdigit():
        stock_id = msg[1:]
        url = f"https://www.twse.com.tw/fund/TWT38U?response=json&selectType=ALL&stockNo={stock_id}"
        res = requests.get(url)
        try:
            data = res.json()['data'][0]
            reply = f"三大法人買賣資訊（{stock_id}）\n日期: {data[0]}\n外資: {data[1]}\n投信: {data[4]}\n自營商: {data[7]}"
        except:
            reply = f"查無 {stock_id} 的三大法人資料"

    elif msg.startswith("H") and msg[1:].isdigit():
        stock_id = msg[1:]
        try:
            url = f"https://www.cnyes.com/twstock/{stock_id}/institutional-investors"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            soup = BeautifulSoup(res.text, 'html.parser')
            chart = soup.select_one('img[src*="InstitutionalInvestors"]')
            if chart:
                img_url = chart['src']
                reply = f"{stock_id} 法人持股趨勢圖：\n{img_url}"
            else:
                reply = f"查無 {stock_id} 的法人持股趨勢圖"
        except:
            reply = f"取得法人持股趨勢失敗"

    elif msg.startswith("N"):
        stock_id = msg[1:]
        reply = get_news(stock_id)

    elif msg.startswith("B"):
        stock_id = msg[1:]
        reply = get_comments(stock_id)

    elif msg == "HELP":
        reply = (
            "可用指令：\n"
            "P2330：即時股價\n"
            "K2330：K線圖\n"
            "T2330：法人資料\n"
            "H2330：法人持股趨勢\n"
            "N2330：最新新聞\n"
            "B2330：熱門留言\n"
            "IND2330：技術指標圖\n"
            "TOP法人買超：法人買超排行\n"
            "TOP殖利率：高殖利率排行"
        )

    elif msg.startswith("IND"):
        stock_id = msg[3:]
        try:
            df = yf.download(stock_id + ".TW" if stock_id.isdigit() else stock_id, period="3mo", interval="1d")
            df['MA5'] = df['Close'].rolling(window=5).mean()
            df['MA20'] = df['Close'].rolling(window=20).mean()
            mpf.plot(df, type='candle', style='charles', mav=(5, 20), volume=True, savefig='static/indicator.png')
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(
                original_content_url=request.url_root + 'static/indicator.png',
                preview_image_url=request.url_root + 'static/indicator.png'))
            return
        except:
            reply = "技術指標圖生成失敗"

    elif msg == "TOP法人買超":
        try:
            url = "https://www.cnyes.com/twstock/agent-trading"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            soup = BeautifulSoup(res.text, 'html.parser')
            top_items = soup.select('table tr')[1:6]
            results = []
            for item in top_items:
                tds = item.select('td')
                if len(tds) >= 4:
                    results.append(f"{tds[1].text.strip()} ({tds[0].text.strip()}): {tds[3].text.strip()} 張")
            reply = "法人買超排行前五名：\n" + '\n'.join(results)
        except:
            reply = "法人買超排行擷取失敗"

    elif msg == "TOP殖利率":
        try:
            url = "https://histock.tw/stock/yield.aspx"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select("#CPHB1_gv tbody tr")[:5]
            results = []
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 6:
                    results.append(f"{cols[1].text.strip()} ({cols[0].text.strip()}): 殖利率 {cols[5].text.strip()}")
            reply = "高殖利率排行前五名：\n" + '\n'.join(results)
        except:
            reply = "殖利率排行擷取失敗"

    if reply:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

def push_ai_news():
    url = "https://news.cnyes.com/news/cat/tw_stock_ai"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        news = soup.select_one("._1Zdp")
        if news:
            title = news.text.strip()
            link = 'https://news.cnyes.com' + news.get('href')
            msg = f"每日AI新聞：\n{title}\n{link}"
            line_bot_api.push_message(USER_ID, TextSendMessage(text=msg))
    except Exception as e:
        print(f"推播失敗: {e}")

scheduler.add_job(push_ai_news, 'cron', hour=8, minute=30)
scheduler.start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
