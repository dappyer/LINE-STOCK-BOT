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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip().upper()

    if msg.startswith('P') and msg[1:].isdigit():
        stock_id = msg[1:]
        realtime = twstock.realtime.get(stock_id)
        if realtime['success']:
            name = realtime['info'].get('name', '未知名稱')
            price = realtime['realtime'].get('latest_trade_price', 'N/A')
            try:
                change = float(realtime['realtime'].get('change', 0))
                percent = float(realtime['realtime'].get('change_percent', 0))
            except (ValueError, TypeError):
                change = percent = 0
            volume = int(realtime['realtime'].get('accumulate_trade_volume', 0))
            reply = f"{name} ({stock_id})\n價格: {price}\n漲跌: {change:+.2f} ({percent:+.2f}%)\n成交量: {volume:,}"
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

    elif msg.startswith("H") and msg[1:].isdigit():
        stock_id = msg[1:]
        try:
            url = f"https://www.cnyes.com/twstock/{stock_id}/institutional-investors"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                chart = soup.select_one('img[src*="InstitutionalInvestors"]')
                if chart:
                    img_url = chart['src']
                    reply = f"{stock_id} 法人持股趨勢圖：\n{img_url}"
                else:
                    reply = f"查無 {stock_id} 的法人持股趨勢圖"
            else:
                reply = f"無法取得 {stock_id} 的資料"
        except Exception:
            reply = f"取得法人持股趨勢失敗"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    elif msg.startswith("N") and msg[1:].isdigit():
        stock_id = msg[1:]
        try:
            news_url = f"https://www.cnyes.com/twstock/{stock_id}/news"
            res = requests.get(news_url, headers={'User-Agent': 'Mozilla/5.0'})
            soup = BeautifulSoup(res.text, 'html.parser')
            articles = soup.select("section a[href^='/news/story/']")
            if articles:
                latest = articles[0]
                title = latest.text.strip()
                href = latest['href']
                reply = f"{stock_id} 最新新聞：\n{title}\nhttps://www.cnyes.com{href}"
            else:
                reply = f"查無 {stock_id} 的最新新聞"
        except Exception:
            reply = f"新聞擷取失敗"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    elif msg.startswith("B") and msg[1:].isdigit():
        stock_id = msg[1:]
        try:
            url = f"https://www.cmoney.tw/forum/stock/{stock_id}"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            soup = BeautifulSoup(res.text, 'html.parser')
            comment = soup.select_one("div.comment-item")
            if comment:
                text = comment.text.strip().replace('\n', '')
                reply = f"{stock_id} 熱門留言（CMoney）：\n{text[:150]}..."
            else:
                reply = f"查無 {stock_id} 的熱門留言"
        except Exception:
            reply = f"留言擷取失敗"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

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
        except Exception:
            reply = "法人買超排行擷取失敗"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

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
        except Exception:
            reply = "殖利率排行擷取失敗"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    elif msg == "HELP":
        instructions = (
            "\n指令教學：\n"
            "P2330 → 即時股價 (台股 twstock)\n"
            "K2330 → 日K線圖\n"
            "T2330 → 三大法人資料\n"
            "H2330 → 法人持股趨勢圖\n"
            "PTSLA → 美股即時股價\n"
            "KTSLA → 美股K線圖\n"
            "IND2330 或 INDTSLA → 技術指標圖(MA5/20)\n"
            "B2330 → CMoney熱門留言\n"
            "N2330 → 鉅亨網最新新聞\n"
            "TOP法人買超 → 法人買超排行\n"
            "TOP殖利率 → 殖利率排行"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=instructions))
    else:
        return

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
            line_bot_api.push_message('YOUR_USER_ID', TextSendMessage(text=msg))
    except Exception as e:
        print(f"推播失敗: {e}")

scheduler.add_job(push_ai_news, 'cron', hour=8, minute=30)
scheduler.start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
