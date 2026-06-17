import urllib.request
import json
import datetime
import re
import html

BOT_TOKEN = "8238743813:AAEQqdLdDKz6OM2txjSE5FbI73cFdQc1P0w"
CHAT_ID = "1237620041"
BASE_URL = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"

# RSS Sources — more market-focused feeds
RSS_SOURCES = {
    "crypto": [
        "https://cointelegraph.com/rss",
        "https://decrypt.co/feed",
    ],
    "us": [
        "https://feeds.marketwatch.com/marketwatch/marketpulse/",   # market pulse, not personal finance
        "https://feeds.marketwatch.com/marketwatch/realtimeheadlines/",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",    # CNBC markets
    ],
    "my": [
        "https://theedgemarkets.com/rss",
        "https://www.theedgemarkets.com/rss",
        "https://www.thestar.com.my/rss/business/business-news",
        "https://www.thestar.com.my/rss/business",
        "https://www.nst.com.my/rss/business",
    ],
}

LABELS = {
    "crypto": ("🪙", "加密"),
    "us":     ("📈", "美股"),
    "my":     ("🇲🇾", "马股"),
}

# Keywords to skip (non-market content)
SKIP_KEYWORDS = [
    "million saved", "retirement", "should i quit", "personal finance",
    "credit card", "mortgage", "divorce", "salary", "i'm a realist",
    "inflation holds steady in", "uk's inflation", "uk inflation",
]


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


def parse_rss_items(xml, max_items=5):
    """Extract multiple articles from RSS XML."""
    items = []
    for item_match in re.finditer(r'<item[^>]*>(.*?)</item>', xml, re.DOTALL):
        item = item_match.group(1)
        title_match = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
        link_match = re.search(r'<link>(?:<!\[CDATA\[)?(https?://[^\s<"]+?)(?:\]\]>)?</link>', item, re.DOTALL)
        if not link_match:
            link_match = re.search(r'<guid[^>]*>(?:<!\[CDATA\[)?(https?://[^\s<"]+?)(?:\]\]>)?</guid>', item, re.DOTALL)
        if title_match and link_match:
            title = html.unescape(title_match.group(1).strip())
            link = re.sub(r'<.*', '', link_match.group(1).strip())
            items.append((title, link))
        if len(items) >= max_items:
            break
    return items


def is_relevant(title, market):
    """Filter out non-market articles."""
    t = title.lower()
    for kw in SKIP_KEYWORDS:
        if kw in t:
            return False
    if market == "my":
        # Must contain Malaysia-related keywords
        my_keywords = ["klci", "bursa", "malaysia", "ringgit", "klse", "petronas",
                       "maybank", "cimb", "tenaga", "axiata", "maxis", "rm"]
        if not any(k in t for k in my_keywords):
            return False
    return True


def fetch_with_fallback(market):
    """Try each RSS URL, return first relevant article."""
    urls = RSS_SOURCES[market]
    for url in urls:
        try:
            print("Trying:", url)
            xml = fetch_rss(url)
            items = parse_rss_items(xml, max_items=10)
            for title, link in items:
                if is_relevant(title, market):
                    print("OK:", title[:60])
                    return title, link
            print("No relevant items in:", url)
        except Exception as e:
            print("Failed:", url, "-", str(e))
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
        if any(k in t for k in ["fall", "drop", "crash", "bear", "down", "low", "bottom", "sell", "outflow", "slump"]):
            ig = (
                "⚠️ 加密市场再度承压！" + title[:40] + "\n\n"
                "链上数据持续走弱，恐慌指数仍处极度恐慌区间。"
                "多头若无法快速收复关键阻力位，短期将面临进一步下探风险。"
                "机构资金观望情绪浓厚，散户切忌盲目抄底，严格做好仓位管理。📉\n\n"
                "#Bitcoin #加密货币 #BTC行情 #熊市信号 #链上数据 #风险管理"
            )
            threads = (
                title[:45] + " 📉\n"
                "链上指标偏空，关键阻力未突破前建议轻仓观望。"
            )
        elif any(k in t for k in ["rise", "rally", "bull", "surge", "high", "gain", "etf", "inflow", "record"]):
            ig = (
                "🚀 加密市场出现积极信号！" + title[:40] + "\n\n"
                "链上数据显示资金持续流入，市场情绪从恐慌区逐步回暖。"
                "ETF资金回流叠加长线持有者增持，短期支撑逐步筑牢。"
                "但切记：牛市信号需配合成交量放大才算真正确认，勿追高。📊\n\n"
                "#Bitcoin #加密货币 #BTC #牛市信号 #ETF资金 #加密市场"
            )
            threads = (
                title[:45] + " 🚀\n"
                "资金回流迹象积极，但需成交量配合才算确认突破。"
            )
        else:
            ig = (
                "⚡ 加密快讯：" + title[:45] + "\n\n"
                "当前市场多空力量胶着，投资者情绪偏谨慎。"
                "短期方向取决于宏观数据及美联储政策表态，建议持续关注关键价位变化，"
                "做好风险管理，避免重仓操作。📊\n\n"
                "#Bitcoin #加密货币 #BTC #市场动态 #宏观经济 #实时快讯"
            )
            threads = (
                title[:45] + " ⚡\n"
                "市场方向未明，宏观数据是短期关键变量。"
            )

    elif market == "us":
        if any(k in t for k in ["fall", "drop", "sell", "bear", "down", "recession", "fear", "loss", "slump", "tumble"]):
            ig = (
                "📉 美股承压！" + title[:40] + "\n\n"
                "宏观不确定性持续困扰市场，投资者避险情绪升温。"
                "S&P 500关键支撑位受考验，科技股领跌。"
                "美联储政策方向及通胀数据将是左右短期走势的核心变量，"
                "建议关注债券市场动向，谨慎应对波动。\n\n"
                "#美股 #WallStreet #标普500 #宏观经济 #避险情绪 #投资策略"
            )
            threads = (
                title[:45] + " 📉\n"
                "避险情绪升温，关注美联储表态及通胀数据走向。"
            )
        elif any(k in t for k in ["rise", "rally", "gain", "record", "up", "high", "bull", "surge", "rebound"]):
            ig = (
                "📈 美股反弹！" + title[:40] + "\n\n"
                "风险偏好回升提振市场情绪，科技及消费板块领涨。"
                "但需注意本轮反弹能否持续，仍取决于美联储政策路径及企业盈利表现。"
                "建议在关键阻力位附近逢高减仓，保持灵活仓位。\n\n"
                "#美股 #WallStreet #标普500 #科技股 #牛市 #投资策略"
            )
            threads = (
                title[:45] + " 📈\n"
                "风险偏好回升，但需观察反弹能否在阻力位持续放量。"
            )
        else:
            ig = (
                "🇺🇸 美股快讯：" + title[:45] + "\n\n"
                "华尔街最新动态持续影响全球资产配置。"
                "当前市场情绪中性，投资者等待更多经济数据指引方向。"
                "建议关注本周重要数据发布窗口，做好仓位对冲准备。\n\n"
                "#美股 #WallStreet #标普500 #财经快讯 #宏观数据 #实时资讯"
            )
            threads = (
                title[:45] + " 🇺🇸\n"
                "市场等待数据指引，短期方向仍存不确定性。"
            )

    else:  # my
        if any(k in t for k in ["fall", "drop", "loss", "down", "weak", "decline", "slip", "net sell"]):
            ig = (
                "📉 马股承压！" + title[:40] + "\n\n"
                "KLCI走势偏弱，外资持续净卖出拖累大市。"
                "令吉汇率波动及大宗商品价格走低是当前主要压力来源。"
                "能源、种植及金融板块普遍回调，建议短期减少曝险，"
                "等待外资止卖信号再逐步布局。\n\n"
                "#马股 #KLCI #Bursa #外资动向 #令吉 #马来西亚投资"
            )
            threads = (
                title[:45] + " 📉\n"
                "外资净卖出压制大市，等待止卖信号再布局。"
            )
        elif any(k in t for k in ["rise", "gain", "up", "high", "net buy", "foreign buy", "surge", "record", "rebound"]):
            ig = (
                "📈 马股回暖！" + title[:40] + "\n\n"
                "KLCI出现积极信号，外资净买入带动市场情绪改善。"
                "能源及金融板块领涨，令吉走强进一步吸引资金回流。"
                "中长线来看Bursa估值仍具吸引力，可考虑逢低分批建仓优质蓝筹。\n\n"
                "#马股 #KLCI #Bursa #外资买入 #马来西亚 #蓝筹股"
            )
            threads = (
                title[:45] + " 📈\n"
                "外资回流提振KLCI，能源金融板块领涨值得关注。"
            )
        else:
            ig = (
                "🇲🇾 马股快讯：" + title[:45] + "\n\n"
                "Bursa Malaysia最新动态出炉。"
                "当前KLCI走势中性，市场等待更多催化剂提振情绪。"
                "建议持续追踪外资流向及令吉汇率变化，"
                "这两项指标将是判断马股短期方向的重要参考。\n\n"
                "#马股 #KLCI #Bursa #马来西亚股市 #外资 #财经快讯"
            )
            threads = (
                title[:45] + " 🇲🇾\n"
                "关注外资流向及令吉走势，是判断马股方向的关键指标。"
            )

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
            send_message("⚠️ *" + market_name + "快讯获取失败*，请稍后重试。")

        index += 1

    send_message("📲 关注 @not.a.stockguru 获取更多实时财经")
    print("Done.")


if __name__ == "__main__":
    main()
