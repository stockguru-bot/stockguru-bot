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
CHAT_ID   = "1237620041"
BASE_URL  = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"

# ── Watchlists ───────────────────────────────────────────────────────────────

# Broad US pool — top movers will be auto-selected
US_POOL = [
    "SPCX","ASTS","LUNR","RDW","RKLB",          # Space
    "NVDA","INTC","MU","AMD","QCOM","AVGO",       # Semis
    "TSLA","META","GOOGL","AMZN","AAPL","MSFT",  # Mega-cap
    "ROKU","PLTR","COIN","MSTR","HOOD",            # High-beta
    "GS","JPM","BAC",                              # Financials
]

# Sector ETFs
ETF_POOL = {
    "SMH":  "半导体",
    "XLK":  "科技",
    "XLE":  "能源",
    "XLF":  "金融",
    "ARKK": "创新",
    "GLD":  "黄金",
    "IWM":  "小盘",
    "QQQ":  "Nasdaq100",
}

# Asian indices
ASIA_INDICES = {
    "^N225":  "日经225",
    "^KS11":  "韩国KOSPI",
    "^TWII":  "台湾加权",
    "^HSI":   "恒生指数",
}

# US broad market
US_INDICES = {"^GSPC": "S&P500", "^IXIC": "Nasdaq"}

# Malaysian blue chips
MY_TICKERS = ["^KLSE","1155.KL","1023.KL","5681.KL","6012.KL","5347.KL"]
MY_NAMES   = {"^KLSE":"KLCI","1155.KL":"Maybank","1023.KL":"CIMB",
               "5681.KL":"Tenaga","6012.KL":"Maxis","5347.KL":"PetChem"}


# ── Helpers ──────────────────────────────────────────────────────────────────

def send_message(text):
    data = json.dumps({
        "chat_id": CHAT_ID, "text": text,
        "parse_mode": "Markdown", "disable_web_page_preview": True
    }).encode("utf-8")
    req = urllib.request.Request(BASE_URL, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        r = json.loads(resp.read().decode())
        if not r.get("ok"):
            raise Exception(r.get("description",""))
    print("Sent:", text[:60])

def fetch_url(url, extra_headers=None):
    h = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
         "Accept": "application/json, */*"}
    if extra_headers:
        h.update(extra_headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def fmt_pct(v):
    return ("+" if v >= 0 else "") + "{:.2f}%".format(v)

def arrow(v):
    return "🟢" if v >= 0 else "🔴"

def dir_arrow(v):
    return "▲" if v >= 0 else "▼"

def get_quotes_yf(tickers):
    """Returns {sym: {price, pct}} for a list of tickers."""
    result = {}
    if not tickers:
        return result
    try:
        raw = yf.download(tickers, period="5d", interval="1d",
                          group_by="ticker", auto_adjust=True,
                          progress=False, threads=True)
        for sym in (tickers if isinstance(tickers, list) else [tickers]):
            try:
                if len(tickers) == 1:
                    closes = raw["Close"].dropna()
                else:
                    closes = raw[sym]["Close"].dropna()
                if len(closes) >= 2:
                    prev, curr = float(closes.iloc[-2]), float(closes.iloc[-1])
                    pct = (curr - prev) / prev * 100
                    result[sym] = {"price": curr, "pct": pct}
                elif len(closes) == 1:
                    result[sym] = {"price": float(closes.iloc[-1]), "pct": 0.0}
            except Exception as e:
                print(f"  yf parse err {sym}: {e}")
    except Exception as e:
        print("yf download error:", e)
    return result

def get_time_label():
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    h = now.hour
    if h < 14:   return "🕛", "午间快讯"
    elif h < 17: return "🕒", "下午快讯"
    elif h < 20: return "🕕", "晚间快讯"
    else:        return "🌙", "夜盘快讯"


# ── Crypto ───────────────────────────────────────────────────────────────────

def fetch_crypto_data():
    url = ("https://api.coingecko.com/api/v3/simple/price"
           "?ids=bitcoin,ethereum&vs_currencies=usd"
           "&include_24hr_change=true&include_market_cap=true")
    return json.loads(fetch_url(url))

def fetch_crypto_headline():
    xml = fetch_url("https://cointelegraph.com/rss",
                    {"Accept": "application/rss+xml, application/xml, */*"})
    m = re.search(r'<item[^>]*>(.*?)</item>', xml, re.DOTALL)
    if not m: return None, None
    item = m.group(1)
    tm = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
    lm = re.search(r'<link>(?:<!\[CDATA\[)?(https?://[^\s<"]+?)(?:\]\]>)?</link>', item, re.DOTALL)
    if not lm:
        lm = re.search(r'<guid[^>]*>(?:<!\[CDATA\[)?(https?://[^\s<"]+?)(?:\]\]>)?</guid>', item, re.DOTALL)
    if tm and lm:
        title = html.unescape(tm.group(1).strip())
        link  = re.sub(r'<.*','', lm.group(1).strip())
        return title, link
    return None, None

def build_crypto_msg():
    prices = fetch_crypto_data()
    btc = prices.get("bitcoin", {})
    eth = prices.get("ethereum", {})
    title, link = fetch_crypto_headline()

    btc_p   = "${:,.0f}".format(btc.get("usd", 0))
    btc_pct = btc.get("usd_24h_change", 0)
    eth_p   = "${:,.0f}".format(eth.get("usd", 0))
    eth_pct = eth.get("usd_24h_change", 0)

    price_line = (
        "BTC " + arrow(btc_pct) + " " + btc_p + " (" + fmt_pct(btc_pct) + ")  "
        "ETH " + arrow(eth_pct) + " " + eth_p + " (" + fmt_pct(eth_pct) + ")"
    )
    headline = (title or "加密市场最新动态")[:55]
    link_str = link or "https://cointelegraph.com"

    if btc_pct <= -2:
        ig = ("⚠️ 加密市场今日大幅承压！\n\n" + price_line + "\n\n" + headline + "\n\n"
              "链上数据持续走弱，恐慌指数处于极度恐慌区间。多头若无法快速收复关键阻力位，"
              "短期面临进一步下探风险。机构资金观望情绪浓厚，切忌盲目抄底，严格做好仓位管理。📉\n\n"
              "#Bitcoin #加密货币 #BTC行情 #熊市信号 #链上数据 #风险管理")
        threads = price_line + "\n" + headline[:45] + "\n链上指标偏空，关键阻力未突破前建议轻仓观望。📉"
    elif btc_pct >= 2:
        ig = ("🚀 加密市场今日强势反弹！\n\n" + price_line + "\n\n" + headline + "\n\n"
              "链上资金回流迹象积极，市场情绪逐步回暖。ETF净流入叠加长线持有者增持，"
              "短期支撑逐步筑牢。但牛市信号需配合成交量放大才算确认，切勿追高。📊\n\n"
              "#Bitcoin #加密货币 #BTC #牛市信号 #ETF资金 #链上数据")
        threads = price_line + "\n" + headline[:45] + "\n资金回流积极，成交量放大是确认信号。🚀"
    else:
        ig = ("⚡ 加密市场今日震荡整理\n\n" + price_line + "\n\n" + headline + "\n\n"
              "多空力量胶着，市场等待更明确催化剂。短期方向取决于宏观数据及美联储政策表态，"
              "建议持续关注关键价位，避免重仓操作。\n\n"
              "#Bitcoin #加密货币 #BTC #ETH #市场动态 #实时快讯")
        threads = price_line + "\n" + headline[:45] + "\n市场方向未明，等待宏观数据指引。⚡"

    return ("⚡ *快讯 #1* 🪙 加密\n🔗 [" + headline + "](" + link_str + ")\n\n"
            "📸 *Instagram*\n" + ig + "\n\n🧵 *Threads*\n" + threads)


# ── US Stocks + ETFs ─────────────────────────────────────────────────────────

def build_us_msg():
    # Fetch everything in one call
    all_syms = list(US_INDICES.keys()) + US_POOL + list(ETF_POOL.keys())
    quotes   = get_quotes_yf(all_syms)

    # Indices
    idx_parts, sp_pct = [], 0
    for sym, name in US_INDICES.items():
        if sym in quotes:
            p = quotes[sym]["pct"]
            if sym == "^GSPC": sp_pct = p
            idx_parts.append(name + " " + dir_arrow(p) + fmt_pct(p))
    idx_line = "  |  ".join(idx_parts)

    # Top 3 movers from pool (by absolute % change, exclude 0%)
    pool_q = [(s, quotes[s]) for s in US_POOL if s in quotes and abs(quotes[s]["pct"]) > 0.1]
    top3   = sorted(pool_q, key=lambda x: abs(x[1]["pct"]), reverse=True)[:3]

    stock_lines, stock_short = [], []
    for sym, q in top3:
        price = "${:,.2f}".format(q["price"])
        pct   = q["pct"]
        stock_lines.append(arrow(pct) + " " + sym + " " + price + " (" + fmt_pct(pct) + ")")
        stock_short.append(sym + " " + fmt_pct(pct))

    # Top 3 ETFs
    etf_q    = [(s, quotes[s], ETF_POOL[s]) for s in ETF_POOL if s in quotes and abs(quotes[s]["pct"]) > 0.05]
    top_etfs = sorted(etf_q, key=lambda x: x[1]["pct"], reverse=True)[:4]
    etf_lines = []
    for sym, q, name in top_etfs:
        etf_lines.append(arrow(q["pct"]) + " " + name + "(" + sym + ") " + fmt_pct(q["pct"]))

    # Sentiment
    if sp_pct >= 0.5:
        sentiment = "美股今日整体走强，风险偏好回升。科技及半导体板块领涨，关注是否能持续放量突破阻力位。逢高注意止盈。"
    elif sp_pct <= -0.5:
        sentiment = "美股今日承压，避险情绪升温。建议减少曝险，等待回调企稳后再逐步布局。关注美联储政策及通胀数据走向。"
    else:
        sentiment = "美股今日震荡整理，多空力量均衡。市场等待明确催化剂，建议保持中性仓位，关注重要数据发布窗口。"

    ig = ("📊 美股今日盘面：" + idx_line + "\n\n"
          "🔥 市场热门股：\n" + "\n".join(stock_lines) + "\n\n"
          "📂 板块ETF表现：\n" + "\n".join(etf_lines) + "\n\n"
          + sentiment + "\n\n"
          "#美股 #WallStreet #热门股 #板块ETF #Nasdaq #标普500 #投资策略")

    threads = ("美股 | " + idx_line + " 📈\n"
               "热门：" + "  |  ".join(stock_short) + "\n"
               + sentiment[:60] + "…")

    return "⚡ *快讯 #2* 📈 美股\n\n📸 *Instagram*\n" + ig + "\n\n🧵 *Threads*\n" + threads


# ── Asia Indices ──────────────────────────────────────────────────────────────

def build_asia_msg():
    quotes = get_quotes_yf(list(ASIA_INDICES.keys()))

    lines, short = [], []
    for sym, name in ASIA_INDICES.items():
        if sym in quotes:
            q   = quotes[sym]
            p   = q["pct"]
            px  = "{:,.2f}".format(q["price"])
            lines.append(arrow(p) + " " + name + " " + px + " (" + fmt_pct(p) + ")")
            short.append(name + " " + fmt_pct(p))

    # Overall sentiment
    avg = sum(quotes[s]["pct"] for s in ASIA_INDICES if s in quotes) / max(len(quotes), 1)
    if avg >= 0.5:
        sentiment = "亚太市场今日整体偏强，外资风险偏好改善。日韩台股受科技产业链提振，建议关注半导体相关个股机会。"
    elif avg <= -0.5:
        sentiment = "亚太市场今日普遍承压，地缘风险及美股夜盘影响持续发酵。建议短期降低曝险，等待市场情绪稳定再布局。"
    else:
        sentiment = "亚太市场今日表现分化，各地区独立走势明显。建议关注个别市场催化剂，避免盲目跟风操作。"

    ig = ("🌏 亚太市场今日盘面：\n\n"
          + "\n".join(lines) + "\n\n"
          + sentiment + "\n\n"
          "#日经 #KOSPI #台湾加权 #恒生 #亚太股市 #全球市场 #投资策略")

    threads = ("亚太市场 🌏\n" + "\n".join(short) + "\n" + sentiment[:55] + "…")

    return "⚡ *快讯 #3* 🌏 亚太指数\n\n📸 *Instagram*\n" + ig + "\n\n🧵 *Threads*\n" + threads


# ── Malaysia ──────────────────────────────────────────────────────────────────

def build_my_msg(msg_num=4):
    quotes = get_quotes_yf(MY_TICKERS)
    klci_q = quotes.get("^KLSE", {})
    stocks = {s: quotes[s] for s in MY_TICKERS if s in quotes and s != "^KLSE"}

    klci_pct   = klci_q.get("pct", 0)
    klci_price = "{:,.2f}".format(klci_q.get("price", 0))
    klci_line  = "KLCI " + dir_arrow(klci_pct) + klci_price + " (" + fmt_pct(klci_pct) + ")"

    top3 = sorted(stocks.items(), key=lambda x: abs(x[1]["pct"]), reverse=True)[:3]
    stock_lines, short = [], []
    for sym, q in top3:
        name  = MY_NAMES.get(sym, sym)
        price = "RM{:.2f}".format(q["price"])
        pct   = q["pct"]
        stock_lines.append(arrow(pct) + " " + name + " " + price + " (" + fmt_pct(pct) + ")")
        short.append(name + " " + fmt_pct(pct))

    if klci_pct >= 0.3:
        sentiment = "KLCI今日走强，外资回流迹象积极。能源及金融板块表现亮眼，市场信心逐步恢复。可关注蓝筹股逢低布局机会。"
    elif klci_pct <= -0.3:
        sentiment = "KLCI今日承压，外资净卖出拖累大市。令吉汇率波动加剧不确定性，建议短期减少曝险，等待止卖信号再入场。"
    else:
        sentiment = "KLCI今日窄幅震荡，市场方向感不强。外资观望为主，建议追踪外资流向及令吉走势作为判断依据。"

    ig = ("🇲🇾 马股今日盘面：" + klci_line + "\n\n"
          "🔥 蓝筹动态：\n" + "\n".join(stock_lines) + "\n\n"
          + sentiment + "\n\n"
          "#马股 #KLCI #Bursa #蓝筹股 #外资动向 #马来西亚投资")

    threads = ("马股 | " + klci_line + " 🇲🇾\n"
               "蓝筹：" + "  |  ".join(short) + "\n"
               + sentiment[:55] + "…")

    return ("⚡ *快讯 #" + str(msg_num) + "* 🇲🇾 马股\n\n"
            "📸 *Instagram*\n" + ig + "\n\n🧵 *Threads*\n" + threads)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    emoji, label = get_time_label()
    now_cst  = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    date_str = now_cst.strftime("%Y年%m月%d日")

    send_message(emoji + " *" + label + " | @not.a.stockguru* 📅 " + date_str
                 + "\n━━━━━━━━━━━━━━━━━━━━")

    # 1. Crypto
    try:
        send_message(build_crypto_msg())
    except Exception as e:
        print("Crypto err:", e)
        send_message("⚠️ *加密快讯获取失败*：" + str(e)[:80])

    if not YF_AVAILABLE:
        send_message("⚠️ yfinance 未安装，跳过股票行情。")
        send_message("📲 关注 @not.a.stockguru 获取更多实时财经")
        return

    # 2. US Stocks + ETFs
    try:
        send_message(build_us_msg())
    except Exception as e:
        print("US err:", e)
        send_message("⚠️ *美股快讯获取失败*：" + str(e)[:80])

    # 3. Asia Indices
    try:
        send_message(build_asia_msg())
    except Exception as e:
        print("Asia err:", e)
        send_message("⚠️ *亚太指数获取失败*：" + str(e)[:80])

    # 4. Malaysia
    try:
        send_message(build_my_msg(msg_num=4))
    except Exception as e:
        print("MY err:", e)
        send_message("⚠️ *马股快讯获取失败*：" + str(e)[:80])

    send_message("📲 关注 @not.a.stockguru 获取更多实时财经")
    print("Done.")


if __name__ == "__main__":
    main()
