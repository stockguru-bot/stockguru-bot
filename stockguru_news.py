import urllib.request
import json
import datetime
import re
import html

BOT_TOKEN = "8238743813:AAEQqdLdDKz6OM2txjSE5FbI73cFdQc1P0w"
CHAT_ID = "1237620041"
BASE_URL = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"

# RSS Sources — MY has multiple fallbacks
RSS_SOURCES = {
    "crypto": [
        "https://cointelegraph.com/rss",
    ],
    "us": [
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    ],
    "my": [
        "https://theedgemarkets.com/rss",
        "https://www.theedgemarkets.com/feed",
        "https://www.thestar.com.my/rss/business",
        "https://www.malaymail.com/rss/money",
        "https://www.freemalaysiatoday.com/category/business/feed/",
    ],
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
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_rss(xml):
    """Extract first article (title + link) from RSS XML."""
    item_match = re.search(r'<item[^>]*>(.*?)</item>', xml, re.DOTALL)
    if not item_match:
        return None, None
    item = item_match.group(1)

    title_match = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
    # Try <link> tag first, then <guid>
    link_match = re.search(r'<link>(?:<!\[CDATA\[)?(https?://[^\s<]+?)(?:\]\]>)?</link>', item, re.DOTALL)
    if not link_match:
        link_match = re.search(r'<guid[^>]*>(?:<!\[CDATA\[)?(https?://[^\s<]+?)(?:\]\]>)?</guid>', item, re.DOTALL)

    if not title_match or not link_match:
        return None, None

    title = html.unescape(title_match.group(1).strip())
    link = link_match.group(1).strip()
    # Remove any trailing XML tags accidentally captured
    link = re.sub(r'<.*', '', link).strip()
    return title, link


def fetch_with_fallback(market):
    """Try each RSS URL in order, return first that works."""
    urls = RSS_SOURCES[market]
    for url in urls:
        try:
            print("Trying:", url)
            xml = fetch_rss(url)
            title, link = parse_rss(xml)
            if title and link:
                print("OK:", title[:50])
                return title, link
            else:
                print("Parsed but no items found")
        except Exception as e:
            print("Failed:", url, str(e))
    return None, None


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
    t = title.lower()

    if market == "crypto":
        if any(k in t for k in ["fall", "drop", "crash", "bear", "down", "low", "bottom", "sell"]):
            ig = (
                "加密市场承压！" + title[:35] + " 📉 "
                "链上数据显示市场仍处于观望阶段，关键支撑位能否守住是短期方向关键。谨慎操作。\n"
                "#Bitcoin #加密货币 #BTC行情 #熊市 #加密市场"
            )
            threads = title[:40] + " 📉 加密市场短期偏空，风险自控。"
        elif any(k in t for k in ["rise", "rally", "bull", "up", "high", "gain", "etf", "inflow"]):
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
        if any(k in t for k in ["fall", "drop", "sell", "bear", "down", "recession", "fear", "loss"]):
            ig = (
                "美股承压！" + title[:35] + " 📉 "
                "宏观不确定性持续影响市场情绪，S&P 500关键支撑位受考验。\n"
                "#美股 #WallStreet #股市 #宏观经济 #投资"
            )
            threads = title[:40] + " 📉 美股短期承压，关注宏观数据变化。"
        elif any(k in t for k in ["rise", "rally", "gain", "record", "up", "high", "bull", "surge"]):
            ig = (
                "美股上涨！" + title[:35] + " 📈 "
                "市场风险偏好回升，关注美联储政策走向对后市影响。\n"
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
        if any(k in t for k in ["fall", "drop", "loss", "down", "weak", "decline", "slip"]):
            ig = (
                "马股承压！" + title[:35] + " 📉 "
                "KLCI走势偏弱，关注外资动向及令吉汇率对大市影响。\n"
                "#马股 #KLCI #Bursa #马来西亚股市 #投资"
            )
            threads = title[:40] + " 📉 马股短期偏弱，外资动向值得关注。"
        elif any(k in t for k in ["rise", "gain", "up", "high", "buy", "foreign", "surge", "record"]):
            ig = (
                "马股好消息！" + title[:35] + " 📈 "
                "KLCI出现积极信号，关注能源及金融板块表现。\n"
                "#马股 #KLCI #Bursa #马来西亚股市 #投资机会"
            )
            threads = title[:40] + " 📈 马股回暖，持续关注外资流向。"
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

    header = (
        emoji + " *" + label + " | @not.a.stockguru* 📅 " + date_str + "\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    send_message(header)

    index = 1
    for market in ["crypto", "us", "my"]:
        market_emoji, market_name = LABELS[market]
        title, link = fetch_with_fallback(market)

        if title and link:
            ig, threads = generate_copy(market, title, link)
            msg = (
                "⚡ *快讯 #" + str(index) + "* " + market_emoji + " " + market_name + "\n"
                "🔗 [" + title[:60] + "](" + link + ")\n\n"
                "📸 *Instagram*\n" + ig + "\n\n"
                "🧵 *Threads*\n" + threads
            )
            send_message(msg)
        else:
            send_message(
                "⚠️ *" + market_name + "快讯获取失败*，请稍后重试。"
            )

        index += 1

    send_message("📲 关注 @not.a.stockguru 获取更多实时财经")
    print("Done.")


if __name__ == "__main__":
    main()
