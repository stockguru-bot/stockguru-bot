import urllib.request
import json
import datetime
import re
import html

BOT_TOKEN = "8238743813:AAEQqdLdDKz6OM2txjSE5FbI73cFdQc1P0w"
CHAT_ID = "1237620041"
BASE_URL = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"

# RSS Sources
RSS_SOURCES = {
    "crypto": "https://cointelegraph.com/rss",
    "us":     "https://feeds.marketwatch.com/marketwatch/topstories/",
    "my":     "https://theedgemarkets.com/rss",
}

LABELS = {
    "crypto": ("🪙", "加密"),
    "us":     ("📈", "美股"),
    "my":     ("🇲🇾", "马股"),
}


def send_message(text):
    data = json.dumps({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL, data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode())
        if not result.get("ok"):
            raise Exception(result.get("description", "Unknown error"))
    print("Sent:", text[:50])


def fetch_rss(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)",
        "Accept": "application/rss+xml, application/xml, text/xml"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_rss(xml):
    """Extract first article (title + link) from RSS XML."""
    # Extract first <item>
    item_match = re.search(r'<item>(.*?)</item>', xml, re.DOTALL)
    if not item_match:
        return None, None
    item = item_match.group(1)

    title_match = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
    link_match = re.search(r'<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>', item, re.DOTALL)

    if not title_match or not link_match:
        return None, None

    title = html.unescape(title_match.group(1).strip())
    link = link_match.group(1).strip()
    return title, link


def get_time_label():
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    hour = now.hour
    if hour < 14:
        return "🕛", "午间快讯"
    elif hour < 17:
        return "🕒", "下午快讯"
    elif hour < 20:
        return "🕕", "晚间快讯"
    else:
        return "🌙", "夜盘快讯"


def generate_copy(market, title, url):
    """Generate IG and Threads copy based on market type and title keywords."""
    t = title.lower()

    if market == "crypto":
        if any(k in t for k in ["fall", "drop", "crash", "bear", "down", "low", "bottom"]):
            ig = (
                "加密市场承压！" + title[:35] + " 📉 "
                "链上数据显示市场仍处于观望阶段，关键支撑位能否守住是短期方向关键。谨慎操作。\n"
                "#Bitcoin #加密货币 #BTC行情 #熊市 #加密市场"
            )
            threads = title[:40] + " 📉 加密市场短期偏空，风险自控。"
        elif any(k in t for k in ["rise", "rally", "bull", "up", "high", "gain", "etf"]):
            ig = (
                "加密好消息！" + title[:35] + " 🚀 "
                "市场情绪出现改善迹象，资金持续流入。把握机会，但仍需注意回调风险。\n"
                "#Bitcoin #加密货币 #BTC #牛市信号 #加密市场"
            )
            threads = title[:40] + " 🚀 加密市场出现积极信号，持续关注。"
        else:
            ig = (
                "加密快讯：" + title[:40] + " ⚡ "
                "市场动态持续更新，投资者保持关注。\n"
                "#Bitcoin #加密货币 #BTC #市场动态 #实时快讯"
            )
            threads = "⚡ " + title[:50] + " 持续关注加密市场走势。"

    elif market == "us":
        if any(k in t for k in ["fall", "drop", "sell", "bear", "down", "recession", "fear"]):
            ig = (
                "美股承压！" + title[:35] + " 📉 "
                "宏观不确定性持续影响市场情绪，投资者避险情绪升温。S&P 500关键支撑位受考验。\n"
                "#美股 #WallStreet #股市 #宏观经济 #投资"
            )
            threads = title[:40] + " 📉 美股短期承压，关注宏观数据变化。"
        elif any(k in t for k in ["rise", "rally", "gain", "record", "up", "high", "bull"]):
            ig = (
                "美股上涨！" + title[:35] + " 📈 "
                "市场风险偏好回升，科技股领涨。关注美联储政策走向对后市影响。\n"
                "#美股 #WallStreet #股市 #科技股 #投资"
            )
            threads = title[:40] + " 📈 美股反弹，风险情绪改善。"
        else:
            ig = (
                "美股快讯：" + title[:40] + " 🇺🇸 "
                "华尔街最新动态，持续关注市场走向。\n"
                "#美股 #WallStreet #股市 #财经 #实时快讯"
            )
            threads = "🇺🇸 " + title[:50] + " 关注美股最新动态。"

    else:  # my
        if any(k in t for k in ["fall", "drop", "loss", "down", "weak", "decline"]):
            ig = (
                "马股承压！" + title[:35] + " 📉 "
                "KLCI走势偏弱，外资持续净卖出。关注令吉汇率及大宗商品价格走势对马股影响。\n"
                "#马股 #KLCI #Bursa #马来西亚股市 #投资"
            )
            threads = title[:40] + " 📉 马股短期偏弱，外资动向值得关注。"
        elif any(k in t for k in ["rise", "gain", "up", "high", "buy", "foreign"]):
            ig = (
                "马股好消息！" + title[:35] + " 📈 "
                "KLCI出现积极信号，外资净流入提振市场信心。关注能源及金融板块表现。\n"
                "#马股 #KLCI #Bursa #马来西亚股市 #投资机会"
            )
            threads = title[:40] + " 📈 马股回暖，外资流入值得关注。"
        else:
            ig = (
                "马股快讯：" + title[:40] + " 🇲🇾 "
                "Bursa Malaysia最新动态，持续关注市场走向。\n"
                "#马股 #KLCI #Bursa #马来西亚 #财经快讯"
            )
            threads = "🇲🇾 " + title[:50] + " 关注马股最新动态。"

    return ig, threads


def main():
    emoji, label = get_time_label()
    now_cst = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    date_str = now_cst.strftime("%Y年%m月%d日")

    # Send header
    header = (
        emoji + " *" + label + " | @not.a.stockguru* 📅 " + date_str + "\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    send_message(header)

    index = 1
    for market, rss_url in RSS_SOURCES.items():
        market_emoji, market_name = LABELS[market]
        try:
            xml = fetch_rss(rss_url)
            title, link = parse_rss(xml)
            if not title or not link:
                raise Exception("Could not parse RSS")

            ig, threads = generate_copy(market, title, link)
            msg = (
                "⚡ *快讯 #" + str(index) + "* " + market_emoji + " " + market_name + "\n"
                "🔗 [" + title[:60] + "](" + link + ")\n\n"
                "📸 *Instagram*\n" + ig + "\n\n"
                "🧵 *Threads*\n" + threads
            )
            send_message(msg)
            print(market_name + " sent OK")

        except Exception as e:
            print("Error fetching " + market_name + ": " + str(e))

        index += 1

    send_message("📲 关注 @not.a.stockguru 获取更多实时财经")
    print("Done.")


if __name__ == "__main__":
    main()
