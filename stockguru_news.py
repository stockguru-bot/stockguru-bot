import urllib.request
import json
import datetime
import re
import html

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

BOT_TOKEN = "8238743813:AAEQqdLdDKz6OM2txjSE5FbI73cFdQc1P0w"
CHAT_ID = "1237620041"
BASE_URL = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"

# US tickers: index + hot stocks
US_TICKERS  = ["^GSPC", "^IXIC", "NVDA", "TSLA", "AAPL", "MSFT", "META", "AMZN"]
US_NAMES    = {"^GSPC": "S&P500", "^IXIC": "Nasdaq", "NVDA": "Nvidia",
               "TSLA": "Tesla", "AAPL": "Apple", "MSFT": "Microsoft",
               "META": "Meta", "AMZN": "Amazon"}

# Malaysian blue chips
MY_TICKERS  = ["^KLSE", "1155.KL", "1023.KL", "5681.KL", "6012.KL", "5347.KL"]
MY_NAMES    = {"^KLSE": "KLCI", "1155.KL": "Maybank", "1023.KL": "CIMB",
               "5681.KL": "Tenaga", "6012.KL": "Maxis", "5347.KL": "PetChem"}


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


def fetch_url(url, headers=None):
    h = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
         "Accept": "application/json, */*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="ignore")


# ── Crypto ──────────────────────────────────────────────────────────────────

def fetch_crypto_data():
    """Get BTC & ETH price + 24h change from CoinGecko (free, no auth)."""
    url = ("https://api.coingecko.com/api/v3/simple/price"
           "?ids=bitcoin,ethereum&vs_currencies=usd"
           "&include_24hr_change=true&include_market_cap=true")
    raw = fetch_url(url)
    return json.loads(raw)


def fetch_crypto_headline():
    """Get latest headline from CoinTelegraph RSS."""
    url = "https://cointelegraph.com/rss"
    xml = fetch_url(url, {"Accept": "application/rss+xml, application/xml, */*"})
    item_match = re.search(r'<item[^>]*>(.*?)</item>', xml, re.DOTALL)
    if not item_match:
        return None, None
    item = item_match.group(1)
    tm = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
    lm = re.search(r'<link>(?:<!\[CDATA\[)?(https?://[^\s<"]+?)(?:\]\]>)?</link>', item, re.DOTALL)
    if not lm:
        lm = re.search(r'<guid[^>]*>(?:<!\[CDATA\[)?(https?://[^\s<"]+?)(?:\]\]>)?</guid>', item, re.DOTALL)
    if tm and lm:
        title = html.unescape(tm.group(1).strip())
        link = re.sub(r'<.*', '', lm.group(1).strip())
        return title, link
    return None, None


def build_crypto_msg():
    prices = fetch_crypto_data()
    btc = prices.get("bitcoin", {})
    eth = prices.get("ethereum", {})
    title, link = fetch_crypto_headline()

    btc_price = "${:,.0f}".format(btc.get("usd", 0))
    btc_pct   = btc.get("usd_24h_change", 0)
    eth_price = "${:,.0f}".format(eth.get("usd", 0))
    eth_pct   = eth.get("usd_24h_change", 0)

    def arrow(v): return "🟢▲" if v >= 0 else "🔴▼"
    def pct(v): return ("+" if v >= 0 else "") + "{:.2f}%".format(v)

    price_line = (
        "BTC " + arrow(btc_pct) + " " + btc_price + " (" + pct(btc_pct) + ")  "
        "ETH " + arrow(eth_pct) + " " + eth_price + " (" + pct(eth_pct) + ")"
    )

    headline = title[:55] if title else "市场最新动态"
    link_str = link if link else "https://cointelegraph.com"

    if btc_pct <= -2:
        tone = "⚠️ 加密市场今日大幅承压！\n\n" + price_line + "\n\n"
        analysis = (headline + "\n\n"
                    "链上数据持续走弱，恐慌指数处于极度恐慌区间。"
                    "多头若无法快速收复关键阻力位，短期面临进一步下探风险。"
                    "机构资金观望情绪浓厚，切忌盲目抄底，严格做好仓位管理。📉")
        threads_txt = price_line + "\n" + headline[:45] + "\n链上指标偏空，关键阻力未突破前建议轻仓观望。📉"
    elif btc_pct >= 2:
        tone = "🚀 加密市场今日强势反弹！\n\n" + price_line + "\n\n"
        analysis = (headline + "\n\n"
                    "链上资金回流迹象积极，市场情绪从恐慌区逐步回暖。"
                    "ETF持续净流入叠加长线持有者增持，短期支撑逐步筑牢。"
                    "但牛市信号需配合成交量放大才算确认，切勿追高。📊")
        threads_txt = price_line + "\n" + headline[:45] + "\n资金回流迹象积极，成交量是确认信号关键。🚀"
    else:
        tone = "⚡ 加密市场今日震荡整理\n\n" + price_line + "\n\n"
        analysis = (headline + "\n\n"
                    "多空力量胶着，市场等待更明确催化剂。"
                    "短期方向取决于宏观数据及美联储政策表态，"
                    "建议持续关注关键价位，避免重仓操作。")
        threads_txt = price_line + "\n" + headline[:45] + "\n市场方向未明，等待宏观数据指引。⚡"

    ig = tone + analysis + "\n\n#Bitcoin #加密货币 #BTC #ETH #链上数据 #加密市场"

    msg = (
        "⚡ *快讯 #1* 🪙 加密\n"
        "🔗 [" + headline + "](" + link_str + ")\n\n"
        "📸 *Instagram*\n" + ig + "\n\n"
        "🧵 *Threads*\n" + threads_txt
    )
    return msg


# ── Stocks (via yfinance) ─────────────────────────────────────────────────

def get_quotes_yf(tickers):
    """Returns {symbol: {price, pct, change}} using yfinance."""
    result = {}
    data = yf.download(tickers, period="2d", interval="1d",
                       group_by="ticker", auto_adjust=True, progress=False)
    for sym in (tickers if isinstance(tickers, list) else [tickers]):
        try:
            if len(tickers) == 1:
                closes = data["Close"]
            else:
                closes = data[sym]["Close"]
            closes = closes.dropna()
            if len(closes) >= 2:
                prev, curr = float(closes.iloc[-2]), float(closes.iloc[-1])
                pct = (curr - prev) / prev * 100
                result[sym] = {"price": curr, "pct": pct, "change": curr - prev}
            elif len(closes) == 1:
                curr = float(closes.iloc[-1])
                result[sym] = {"price": curr, "pct": 0.0, "change": 0.0}
        except Exception as e:
            print("yf error for", sym, e)
    return result


def fmt_pct(v): return ("+" if v >= 0 else "") + "{:.2f}%".format(v)
def arrow_emoji(v): return "🟢" if v >= 0 else "🔴"


def build_us_msg(quotes):
    indices = {s: quotes[s] for s in ["^GSPC", "^IXIC"] if s in quotes}
    stocks  = {s: quotes[s] for s in US_TICKERS if s in quotes and s not in ["^GSPC", "^IXIC"]}

    # Sort stocks by absolute % move
    top3 = sorted(stocks.items(), key=lambda x: abs(x[1]["pct"]), reverse=True)[:3]

    # Index summary
    idx_parts = []
    sp_pct = 0
    for sym, name in [("^GSPC", "S&P500"), ("^IXIC", "Nasdaq")]:
        if sym in indices:
            p = indices[sym]["pct"]
            if sym == "^GSPC":
                sp_pct = p
            idx_parts.append(name + " " + ("▲" if p >= 0 else "▼") + fmt_pct(p))
    idx_line = "  |  ".join(idx_parts)

    # Stock lines
    stock_lines, ig_short = [], []
    for sym, q in top3:
        name = US_NAMES.get(sym, sym)
        price = "${:,.2f}".format(q["price"])
        pct   = q["pct"]
        stock_lines.append(arrow_emoji(pct) + " " + name + " " + price + " (" + fmt_pct(pct) + ")")
        ig_short.append(name + " " + fmt_pct(pct))

    if sp_pct >= 0.5:
        sentiment = "美股今日整体走强，风险偏好回升。科技板块领涨，关注是否能持续放量突破阻力位。建议适量持有，逢高注意止盈。"
    elif sp_pct <= -0.5:
        sentiment = "美股今日承压，避险情绪升温。建议减少曝险，关注美联储政策及通胀数据，等待回调企稳后再逐步布局。"
    else:
        sentiment = "美股今日震荡，多空力量均衡。市场等待更明确方向指引，建议保持中性仓位，关注重要经济数据窗口。"

    ig = (
        "📊 美股今日盘面：" + idx_line + "\n\n"
        "🔥 热门股动态：\n" + "\n".join(stock_lines) + "\n\n"
        + sentiment + "\n\n"
        "#美股 #WallStreet #热门股 #Nasdaq #标普500 #投资策略"
    )
    threads = (
        "美股 | " + idx_line + " 📈\n"
        "热门：" + "  |  ".join(ig_short) + "\n"
        + sentiment[:55] + "…"
    )
    return "⚡ *快讯 #2* 📈 美股\n\n📸 *Instagram*\n" + ig + "\n\n🧵 *Threads*\n" + threads


def build_my_msg(quotes):
    klci_q  = quotes.get("^KLSE", {})
    stocks  = {s: quotes[s] for s in MY_TICKERS if s in quotes and s != "^KLSE"}

    klci_pct   = klci_q.get("pct", 0)
    klci_price = "{:,.2f}".format(klci_q.get("price", 0))
    klci_line  = "KLCI " + ("▲" if klci_pct >= 0 else "▼") + klci_price + " (" + fmt_pct(klci_pct) + ")"

    top3 = sorted(stocks.items(), key=lambda x: abs(x[1]["pct"]), reverse=True)[:3]
    stock_lines, ig_short = [], []
    for sym, q in top3:
        name  = MY_NAMES.get(sym, sym)
        price = "RM{:.2f}".format(q["price"])
        pct   = q["pct"]
        stock_lines.append(arrow_emoji(pct) + " " + name + " " + price + " (" + fmt_pct(pct) + ")")
        ig_short.append(name + " " + fmt_pct(pct))

    if klci_pct >= 0.3:
        sentiment = "KLCI今日走强，外资回流迹象积极。能源及金融板块表现亮眼，市场信心逐步恢复。可关注蓝筹股逢低布局机会。"
    elif klci_pct <= -0.3:
        sentiment = "KLCI今日承压，外资净卖出拖累大市。令吉汇率波动加剧不确定性，建议短期减少曝险，等待止卖信号再入场。"
    else:
        sentiment = "KLCI今日窄幅震荡，市场方向感不强。外资观望为主，建议持续追踪外资流向及令吉走势作为判断依据。"

    ig = (
        "🇲🇾 马股今日盘面：" + klci_line + "\n\n"
        "🔥 蓝筹动态：\n" + "\n".join(stock_lines) + "\n\n"
        + sentiment + "\n\n"
        "#马股 #KLCI #Bursa #蓝筹股 #外资动向 #马来西亚投资"
    )
    threads = (
        "马股 | " + klci_line + " 🇲🇾\n"
        "蓝筹：" + "  |  ".join(ig_short) + "\n"
        + sentiment[:55] + "…"
    )
    return "⚡ *快讯 #3* 🇲🇾 马股\n\n📸 *Instagram*\n" + ig + "\n\n🧵 *Threads*\n" + threads


# ── Main ─────────────────────────────────────────────────────────────────────

def get_time_label():
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    hour = now.hour
    if hour < 14:   return "🕛", "午间快讯"
    elif hour < 17: return "🕒", "下午快讯"
    elif hour < 20: return "🕕", "晚间快讯"
    else:           return "🌙", "夜盘快讯"


def main():
    emoji, label = get_time_label()
    now_cst  = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    date_str = now_cst.strftime("%Y年%m月%d日")

    send_message(emoji + " *" + label + " | @not.a.stockguru* 📅 " + date_str + "\n━━━━━━━━━━━━━━━━━━━━")

    # Crypto
    try:
        send_message(build_crypto_msg())
    except Exception as e:
        print("Crypto error:", e)
        send_message("⚠️ *加密快讯获取失败*：" + str(e)[:80])

    if not YF_AVAILABLE:
        send_message("⚠️ yfinance 未安装，跳过股票行情。")
    else:
        # US
        try:
            us_q = get_quotes_yf(US_TICKERS)
            send_message(build_us_msg(us_q))
        except Exception as e:
            print("US error:", e)
            send_message("⚠️ *美股快讯获取失败*：" + str(e)[:80])

        # MY
        try:
            my_q = get_quotes_yf(MY_TICKERS)
            send_message(build_my_msg(my_q))
        except Exception as e:
            print("MY error:", e)
            send_message("⚠️ *马股快讯获取失败*：" + str(e)[:80])

    send_message("📲 关注 @not.a.stockguru 获取更多实时财经")
    print("Done.")


if __name__ == "__main__":
    main()
