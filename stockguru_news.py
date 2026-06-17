import urllib.request
import json
import datetime
import re
import html

BOT_TOKEN = "8238743813:AAEQqdLdDKz6OM2txjSE5FbI73cFdQc1P0w"
CHAT_ID = "1237620041"
BASE_URL = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"

# Malaysian blue chips to track (Yahoo Finance tickers)
MY_TICKERS = [
    ("^KLSE",    "KLCI指数"),
    ("1155.KL",  "Maybank"),
    ("1023.KL",  "CIMB"),
    ("5681.KL",  "Tenaga"),
    ("6012.KL",  "Maxis"),
    ("5347.KL",  "Petronas Chemicals"),
    ("4863.KL",  "Axiata"),
    ("3816.KL",  "MISC"),
]

# US stocks to track (mix of index + hot stocks)
US_TICKERS = [
    ("^GSPC",  "S&P 500"),
    ("^IXIC",  "Nasdaq"),
    ("NVDA",   "Nvidia"),
    ("TSLA",   "Tesla"),
    ("AAPL",   "Apple"),
    ("MSFT",   "Microsoft"),
    ("META",   "Meta"),
    ("AMZN",   "Amazon"),
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
    print("Sent:", text[:60])


def fetch_yahoo_quotes(symbols):
    """Fetch real-time quotes from Yahoo Finance."""
    syms = ",".join(symbols)
    url = (
        "https://query1.finance.yahoo.com/v7/finance/quote"
        "?symbols=" + syms +
        "&fields=symbol,shortName,regularMarketPrice,regularMarketChangePercent"
        ",regularMarketChange,regularMarketVolume,fiftyTwoWeekHigh,fiftyTwoWeekLow"
        "&lang=en-US&region=US"
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    return data["quoteResponse"]["result"]


def fetch_crypto_rss():
    """Fetch latest crypto headline from CoinTelegraph RSS."""
    url = "https://cointelegraph.com/rss"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Accept": "application/rss+xml, application/xml, */*"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        xml = resp.read().decode("utf-8", errors="ignore")

    item_match = re.search(r'<item[^>]*>(.*?)</item>', xml, re.DOTALL)
    if not item_match:
        return None, None
    item = item_match.group(1)

    title_match = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
    link_match = re.search(r'<link>(?:<!\[CDATA\[)?(https?://[^\s<"]+?)(?:\]\]>)?</link>', item, re.DOTALL)
    if not link_match:
        link_match = re.search(r'<guid[^>]*>(?:<!\[CDATA\[)?(https?://[^\s<"]+?)(?:\]\]>)?</guid>', item, re.DOTALL)

    if title_match and link_match:
        title = html.unescape(title_match.group(1).strip())
        link = re.sub(r'<.*', '', link_match.group(1).strip())
        return title, link
    return None, None


def fmt_pct(val):
    sign = "+" if val >= 0 else ""
    return sign + "{:.2f}%".format(val)


def fmt_price(val, currency=""):
    if val >= 1000:
        return currency + "{:,.2f}".format(val)
    elif val >= 1:
        return currency + "{:.2f}".format(val)
    else:
        return currency + "{:.4f}".format(val)


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


def build_crypto_msg(title, link):
    t = title.lower()
    if any(k in t for k in ["fall", "drop", "crash", "bear", "down", "low", "bottom", "sell", "outflow", "slump"]):
        sentiment = "空头"
        ig = (
            "⚠️ 加密市场承压！" + title[:45] + "\n\n"
            "链上数据持续走弱，恐慌指数仍处极度恐慌区间。"
            "多头若无法快速收复关键阻力位，短期将面临进一步下探风险。"
            "机构资金观望情绪浓厚，散户切忌盲目抄底，严格做好仓位管理。📉\n\n"
            "#Bitcoin #加密货币 #BTC行情 #熊市信号 #链上数据 #风险管理"
        )
        threads = title[:50] + " 📉\n链上指标偏空，关键阻力未突破前建议轻仓观望。"
    elif any(k in t for k in ["rise", "rally", "bull", "surge", "high", "gain", "etf", "inflow", "record"]):
        sentiment = "多头"
        ig = (
            "🚀 加密市场出现积极信号！" + title[:45] + "\n\n"
            "链上数据显示资金持续流入，市场情绪从恐慌区逐步回暖。"
            "ETF资金回流叠加长线持有者增持，短期支撑逐步筑牢。"
            "但牛市信号需配合成交量放大才算真正确认，切勿追高。📊\n\n"
            "#Bitcoin #加密货币 #BTC #牛市信号 #ETF资金 #链上数据"
        )
        threads = title[:50] + " 🚀\n资金回流迹象积极，成交量放大才是真正确认信号。"
    else:
        sentiment = "中性"
        ig = (
            "⚡ 加密快讯：" + title[:50] + "\n\n"
            "当前市场多空力量胶着，投资者情绪偏谨慎。"
            "短期方向取决于宏观数据及美联储政策表态，建议持续关注关键价位变化，"
            "做好风险管理，避免重仓操作。\n\n"
            "#Bitcoin #加密货币 #BTC #市场动态 #宏观经济 #实时快讯"
        )
        threads = title[:50] + " ⚡\n市场方向未明，宏观数据是短期关键变量。"

    msg = (
        "⚡ *快讯 #1* 🪙 加密\n"
        "🔗 [" + title[:60] + "](" + link + ")\n\n"
        "📸 *Instagram*\n" + ig + "\n\n"
        "🧵 *Threads*\n" + threads
    )
    return msg


def build_us_msg(quotes):
    # Separate index vs individual stocks
    indices = [q for q in quotes if q["symbol"] in ["^GSPC", "^IXIC"]]
    stocks  = [q for q in quotes if q["symbol"] not in ["^GSPC", "^IXIC"]]

    # Sort stocks by absolute % change (biggest movers first)
    stocks.sort(key=lambda q: abs(q.get("regularMarketChangePercent", 0)), reverse=True)
    top3 = stocks[:3]

    # Build index summary line
    idx_lines = []
    for q in indices:
        name = "S&P500" if q["symbol"] == "^GSPC" else "Nasdaq"
        pct = q.get("regularMarketChangePercent", 0)
        arrow = "▲" if pct >= 0 else "▼"
        idx_lines.append(name + " " + arrow + " " + fmt_pct(pct))
    idx_summary = "  |  ".join(idx_lines)

    # Build stock lines
    stock_lines = []
    ig_stock_lines = []
    for q in top3:
        name = q.get("shortName", q["symbol"])[:15]
        price = fmt_price(q.get("regularMarketPrice", 0), "$")
        pct = q.get("regularMarketChangePercent", 0)
        chg = q.get("regularMarketChange", 0)
        arrow = "🟢" if pct >= 0 else "🔴"
        stock_lines.append(arrow + " " + name + " " + price + " (" + fmt_pct(pct) + ")")
        ig_stock_lines.append(name + " " + fmt_pct(pct))

    # Overall sentiment
    avg_pct = sum(q.get("regularMarketChangePercent", 0) for q in top3) / max(len(top3), 1)
    sp_pct = next((q.get("regularMarketChangePercent", 0) for q in indices if q["symbol"] == "^GSPC"), 0)

    if sp_pct >= 0.5:
        sentiment_line = "美股今日整体走强，风险偏好回升。"
        advice = "科技板块领涨，关注是否能持续放量突破阻力。建议适量持有，逢高注意止盈。"
    elif sp_pct <= -0.5:
        sentiment_line = "美股今日承压，避险情绪升温。"
        advice = "建议减少曝险，关注美联储政策及通胀数据对后市影响，等待回调企稳后再布局。"
    else:
        sentiment_line = "美股今日震荡，多空力量均衡。"
        advice = "市场等待更明确方向指引，建议保持中性仓位，关注重要经济数据发布窗口。"

    stocks_str = "\n".join(stock_lines)
    ig_stocks_str = "  |  ".join(ig_stock_lines)

    ig = (
        "📊 美股今日盘面：" + idx_summary + "\n\n"
        "🔥 热门股动态：\n" + stocks_str + "\n\n"
        + sentiment_line + " " + advice + "\n\n"
        "#美股 #WallStreet #热门股 #Nasdaq #标普500 #投资策略"
    )
    threads = (
        "美股 | " + idx_summary + " 📈\n"
        "热门：" + ig_stocks_str + "\n"
        + sentiment_line
    )

    msg = (
        "⚡ *快讯 #2* 📈 美股\n\n"
        "📸 *Instagram*\n" + ig + "\n\n"
        "🧵 *Threads*\n" + threads
    )
    return msg


def build_my_msg(quotes):
    klci = next((q for q in quotes if q["symbol"] == "^KLSE"), None)
    stocks = [q for q in quotes if q["symbol"] != "^KLSE"]
    stocks.sort(key=lambda q: abs(q.get("regularMarketChangePercent", 0)), reverse=True)
    top3 = stocks[:3]

    # KLCI summary
    if klci:
        klci_price = fmt_price(klci.get("regularMarketPrice", 0))
        klci_pct = klci.get("regularMarketChangePercent", 0)
        klci_arrow = "▲" if klci_pct >= 0 else "▼"
        klci_line = "KLCI " + klci_arrow + " " + klci_price + " (" + fmt_pct(klci_pct) + ")"
    else:
        klci_line = "KLCI 数据获取中"
        klci_pct = 0

    # Stock lines
    stock_lines = []
    ig_stock_lines = []
    for q in top3:
        name = q.get("shortName", q["symbol"])[:15]
        price = fmt_price(q.get("regularMarketPrice", 0), "RM")
        pct = q.get("regularMarketChangePercent", 0)
        arrow = "🟢" if pct >= 0 else "🔴"
        stock_lines.append(arrow + " " + name + " " + price + " (" + fmt_pct(pct) + ")")
        ig_stock_lines.append(name + " " + fmt_pct(pct))

    # Sentiment
    if klci_pct >= 0.3:
        sentiment = "KLCI今日走强，外资回流迹象积极。能源及金融板块表现亮眼，市场信心逐步恢复。建议关注蓝筹股逢低布局机会。"
    elif klci_pct <= -0.3:
        sentiment = "KLCI今日承压，外资持续净卖出拖累大市。令吉汇率波动加剧不确定性，建议短期减少曝险，等待止卖信号再入场。"
    else:
        sentiment = "KLCI今日窄幅震荡，市场方向感不强。外资观望为主，建议持续追踪外资流向及令吉走势作为判断依据。"

    stocks_str = "\n".join(stock_lines)
    ig_stocks_str = "  |  ".join(ig_stock_lines)

    ig = (
        "🇲🇾 马股今日盘面：" + klci_line + "\n\n"
        "🔥 蓝筹动态：\n" + stocks_str + "\n\n"
        + sentiment + "\n\n"
        "#马股 #KLCI #Bursa #蓝筹股 #外资动向 #马来西亚投资"
    )
    threads = (
        "马股 | " + klci_line + " 🇲🇾\n"
        "蓝筹：" + ig_stocks_str + "\n"
        + sentiment[:50] + "…"
    )

    msg = (
        "⚡ *快讯 #3* 🇲🇾 马股\n\n"
        "📸 *Instagram*\n" + ig + "\n\n"
        "🧵 *Threads*\n" + threads
    )
    return msg


def main():
    emoji, label = get_time_label()
    now_cst = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    date_str = now_cst.strftime("%Y年%m月%d日")

    header = (
        emoji + " *" + label + " | @not.a.stockguru* 📅 " + date_str + "\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    send_message(header)

    # --- Crypto ---
    try:
        title, link = fetch_crypto_rss()
        if title and link:
            send_message(build_crypto_msg(title, link))
        else:
            send_message("⚠️ *加密快讯获取失败*，请稍后重试。")
    except Exception as e:
        print("Crypto error:", e)
        send_message("⚠️ *加密快讯获取失败*：" + str(e)[:60])

    # --- US Stocks ---
    try:
        us_syms = [t[0] for t in US_TICKERS]
        us_quotes = fetch_yahoo_quotes(us_syms)
        send_message(build_us_msg(us_quotes))
    except Exception as e:
        print("US error:", e)
        send_message("⚠️ *美股快讯获取失败*：" + str(e)[:60])

    # --- Malaysian Stocks ---
    try:
        my_syms = [t[0] for t in MY_TICKERS]
        my_quotes = fetch_yahoo_quotes(my_syms)
        send_message(build_my_msg(my_quotes))
    except Exception as e:
        print("MY error:", e)
        send_message("⚠️ *马股快讯获取失败*：" + str(e)[:60])

    send_message("📲 关注 @not.a.stockguru 获取更多实时财经")
    print("Done.")


if __name__ == "__main__":
    main()
