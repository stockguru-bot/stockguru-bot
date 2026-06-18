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

# ── Tickers ────────────────────────────────────────────────────────────────────
ETF_POOL     = {"SMH":"半导体","XLK":"科技","XLE":"能源","XLF":"金融","ARKK":"创新","GLD":"黄金","IWM":"小盘"}
US_INDICES   = {"^GSPC":"S&P500","^IXIC":"Nasdaq"}
ASIA_INDICES = {"^N225":"日经225","^KS11":"韩国KOSPI","^TWII":"台湾加权","^HSI":"恒生指数"}
MY_TICKERS   = ["^KLSE","1155.KL","1023.KL","5681.KL","6012.KL","5347.KL"]
MY_NAMES     = {"^KLSE":"KLCI","1155.KL":"Maybank","1023.KL":"CIMB","5681.KL":"Tenaga","6012.KL":"Maxis","5347.KL":"PetChem"}

# Tickers used as news anchors (broad market + crypto + themes)
NEWS_ANCHORS = ["SPY","QQQ","^GSPC","BTC-USD","ETH-USD","INTC","NVDA","MU","META","TSLA","AAPL","AMZN","HOOD","PLTR"]
MY_NEWS_ANCHORS = ["^KLSE","1155.KL","1023.KL","MAYBANK","CIMB"]

# Fallback RSS for Fed/macro
FALLBACK_RSS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://www.federalreserve.gov/feeds/press_all.xml",
]
CRYPTO_RSS = ["https://cointelegraph.com/rss"]
MY_NEWS_RSS = [
    "https://theedgemarkets.com/rss",
    "https://www.thestar.com.my/rss/business/business-news",
    "https://www.nst.com.my/rss/business",
]

# ── Classifiers ────────────────────────────────────────────────────────────────
FED_KW    = ["fed","federal reserve","fomc","interest rate","powell","warsh","rate cut","rate hike",
             "inflation","monetary policy","treasury","yield","bond","chair","central bank"]
STOCK_KW  = ["nvidia","apple","tesla","microsoft","meta","amazon","intel","micron","sandisk",
             "spacex","google","alphabet","hynix","oracle","marvell","earnings","buyback",
             "acquisition","ipo","rally","plunge","surge","soars","slips","target","upgrade",
             "downgrade","revenue","profit","partnership","deal","beats","misses"]
CRYPTO_KW = ["bitcoin","btc","ethereum","eth","crypto","blockchain","coinbase","binance",
             "defi","nft","stablecoin","solana","xrp","altcoin"]
MACRO_KW  = ["gdp","jobs","unemployment","cpi","pce","recession","growth","tariff","trade",
             "oil","gold","dollar","yuan","yen","iran","china","europe","debt","deficit"]

def classify(title):
    t = title.lower()
    if any(k in t for k in CRYPTO_KW): return "crypto"
    if any(k in t for k in FED_KW):    return "fed"
    if any(k in t for k in STOCK_KW):  return "stock"
    if any(k in t for k in MACRO_KW):  return "macro"
    return "general"

# ── Utilities ──────────────────────────────────────────────────────────────────
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
    print("✓ Sent:", text[:60])

def fetch_url(url, extra=None):
    h = {"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
         "Accept":"*/*"}
    if extra: h.update(extra)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=12) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def fetch_rss_items(url, max_items=6):
    try:
        xml = fetch_url(url, {"Accept":"application/rss+xml,application/xml,*/*"})
    except Exception as e:
        print(f"RSS fail {url}: {e}")
        return []
    items = []
    for m in re.finditer(r'<item[^>]*>(.*?)</item>', xml, re.DOTALL):
        raw = m.group(1)
        tm = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', raw, re.DOTALL)
        lm = re.search(r'<link>(?:<!\[CDATA\[)?(https?://[^\s<"]+?)(?:\]\]>)?</link>', raw, re.DOTALL)
        if not lm:
            lm = re.search(r'<guid[^>]*>(?:<!\[CDATA\[)?(https?://[^\s<"]+?)(?:\]\]>)?</guid>', raw, re.DOTALL)
        dm = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', raw, re.DOTALL)
        if tm and lm:
            title = html.unescape(re.sub(r'<[^>]+>','', tm.group(1))).strip()
            link  = re.sub(r'<.*','', lm.group(1)).strip()
            desc  = html.unescape(re.sub(r'<[^>]+>','', dm.group(1) if dm else '')).strip()[:200]
            if title and len(title) > 10:
                items.append({"title": title, "link": link, "desc": desc})
        if len(items) >= max_items: break
    return items

def fmt_pct(v):  return ("+" if v >= 0 else "") + "{:.2f}%".format(v)
def arrow(v):    return "🟢" if v >= 0 else "🔴"
def darrow(v):   return "▲" if v >= 0 else "▼"
def fmt_vol(v):
    if v >= 1e9: return "{:.1f}B".format(v/1e9)
    if v >= 1e6: return "{:.1f}M".format(v/1e6)
    if v >= 1e3: return "{:.0f}K".format(v/1e3)
    return str(v)

def get_quotes_yf(tickers):
    result = {}
    if not tickers or not YF_AVAILABLE: return result
    try:
        raw = yf.download(tickers, period="5d", interval="1d",
                          group_by="ticker", auto_adjust=True, progress=False, threads=True)
        for sym in (tickers if isinstance(tickers, list) else [tickers]):
            try:
                closes = raw[sym]["Close"].dropna() if len(tickers) > 1 else raw["Close"].dropna()
                if len(closes) >= 2:
                    p, c = float(closes.iloc[-2]), float(closes.iloc[-1])
                    result[sym] = {"price": c, "pct": (c-p)/p*100}
                elif len(closes) == 1:
                    result[sym] = {"price": float(closes.iloc[-1]), "pct": 0.0}
            except: pass
    except Exception as e:
        print("yf err:", e)
    return result

def get_screener(scr_id, count=5):
    try:
        s = yf.Screener()
        s.set_predefined_body(scr_id)
        s.set_count(count)
        return [{"sym": q.get("symbol",""), "name": q.get("shortName", q.get("symbol",""))[:16],
                 "price": q.get("regularMarketPrice",0), "pct": q.get("regularMarketChangePercent",0),
                 "vol": q.get("regularMarketVolume",0)} for q in s.response.get("quotes",[])[:count]]
    except Exception as e:
        print(f"screener {scr_id} err:", e)
        return []

def get_yf_news(symbols, max_total=8):
    """Fetch news via yfinance Ticker.news — same source as Yahoo Finance 'popular'."""
    items = []
    seen_titles = set()
    for sym in symbols:
        if len(items) >= max_total: break
        try:
            ticker = yf.Ticker(sym)
            news_raw = ticker.news  # list of dicts
            for n in news_raw[:4]:
                title = (n.get("title") or "").strip()
                link  = (n.get("link") or n.get("url") or "").strip()
                desc  = (n.get("summary") or "").strip()[:200]
                pub   = (n.get("publisher") or "").strip()
                if not title or not link: continue
                key = title[:40].lower()
                if key in seen_titles: continue
                seen_titles.add(key)
                items.append({"title": title, "link": link, "desc": desc, "pub": pub,
                              "tickers": n.get("relatedTickers", [])})
        except Exception as e:
            print(f"yf.news {sym}: {e}")
    return items

def get_time_label():
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    h = now.hour
    if h < 14:   return "🕛","午间快讯"
    elif h < 17: return "🕒","下午快讯"
    elif h < 20: return "🕕","晚间快讯"
    else:        return "🌙","夜盘快讯"


# ── Copy generators ────────────────────────────────────────────────────────────

def make_ig_copy(cat, title, desc, tickers_in_news):
    """Generate Instagram copy (~100-140 chars + hashtags) based on news category."""
    t = title.lower()
    ticker_str = " ".join(["$" + s for s in tickers_in_news[:3]]) if tickers_in_news else ""

    # Detect sentiment
    bearish = any(k in t for k in ["fall","drop","crash","slump","miss","loss","plunge","slips","down","concern","fine","lawsuit","weak"])
    bullish = any(k in t for k in ["rise","rally","surge","soars","beat","upgrade","record","profit","partnership","deal","gain","high","strong"])

    if cat == "fed":
        if "hike" in t or "raise" in t:
            body = ("🏛️ 美联储鹰派信号！\n\n"
                    "📌 " + title[:70] + "\n\n"
                    "多位联储官员支持年内加息，利率政策明显偏鹰。加息预期升温将压制科技股估值，"
                    "美债收益率短期上行压力增大。成长股、高估值板块需警惕回调风险，"
                    "关注美元指数及黄金避险走势。\n\n"
                    "#美联储 #加息 #FOMC #利率 #货币政策 #美股 #宏观经济 #财经快讯")
            th   = ("🏛️ " + title[:60] + "\n\n"
                    "加息预期升温，科技成长股承压，关注美债及避险资产走势。")
        elif "cut" in t or "ease" in t or "pause" in t:
            body = ("🏛️ 美联储鸽派信号！\n\n"
                    "📌 " + title[:70] + "\n\n"
                    "降息/暂停加息预期提振市场风险偏好！利率下行有利于科技、成长及房地产板块，"
                    "美债收益率承压。关注后续通胀数据验证降息路径，风险资产迎来阶段性布局机会。\n\n"
                    "#美联储 #降息 #FOMC #利率 #货币政策 #美股 #风险偏好 #财经快讯")
            th   = "🏛️ " + title[:60] + "\n\n降息预期提振风险资产，关注科技成长板块布局机会。"
        else:
            body = ("🏛️ 美联储最新表态！\n\n"
                    "📌 " + title[:70] + "\n\n"
                    (desc[:100] + "…\n\n" if desc else "")
                    + "利率政策走向是当前市场最核心变量。关注声明措辞变化，"
                    "尤其是对通胀与就业的评估，将直接影响全球资产定价节奏。\n\n"
                    "#美联储 #FOMC #利率 #货币政策 #宏观经济 #美股 #财经快讯")
            th   = "🏛️ " + title[:60] + "\n\n联储表态牵动市场神经，持续关注政策走向变化。"

    elif cat == "stock":
        # Extract key ticker info
        related = ", ".join(["$" + s for s in tickers_in_news[:2]]) if tickers_in_news else ""
        if bullish:
            body = ("📈 " + (related + " " if related else "") + "个股利好！\n\n"
                    "📌 " + title[:70] + "\n\n"
                    + (desc[:100] + "…\n\n" if desc else "")
                    + "催化剂驱动股价短期动能强劲！建议关注成交量是否持续放大，"
                    "确认突破有效性后可考虑顺势布局，同时留意大盘整体环境配合情况。\n\n"
                    "#美股 #个股行情 #WallStreet #热门股 #财经快讯" + (" " + ticker_str if ticker_str else ""))
            th   = "📈 " + title[:65] + "\n\n" + (related + " ") + "利好消息驱动，关注成交量确认有效突破。"
        elif bearish:
            body = ("📉 " + (related + " " if related else "") + "个股利空！\n\n"
                    "📌 " + title[:70] + "\n\n"
                    + (desc[:100] + "…\n\n" if desc else "")
                    + "负面消息拖累股价，短期动能偏弱。持仓者注意评估止损位，"
                    "等待下方支撑企稳及基本面改善信号后再考虑重新布局。\n\n"
                    "#美股 #个股行情 #WallStreet #热门股 #财经快讯" + (" " + ticker_str if ticker_str else ""))
            th   = "📉 " + title[:65] + "\n\n" + (related + " ") + "利空压制，等待企稳信号再考虑布局。"
        else:
            body = ("⚡ " + (related + " " if related else "") + "个股快讯！\n\n"
                    "📌 " + title[:70] + "\n\n"
                    + (desc[:100] + "…\n\n" if desc else "")
                    + "市场热议中，相关板块情绪值得持续追踪。"
                    "结合大盘走势及成交量综合判断，做好仓位管理。\n\n"
                    "#美股 #个股行情 #WallStreet #热门股 #财经快讯" + (" " + ticker_str if ticker_str else ""))
            th   = "⚡ " + title[:65] + "\n\n市场高度关注，结合大盘走势综合判断布局时机。"

    elif cat == "crypto":
        if bearish:
            body = ("🔴 加密市场承压！\n\n"
                    "📌 " + title[:70] + "\n\n"
                    + (desc[:100] + "…\n\n" if desc else "")
                    + "链上资金外流，市场恐慌情绪升温。多头需收复关键阻力位才能扭转局面，"
                    "短期内严控仓位，切忌逆势重仓抄底，等待企稳信号确认。\n\n"
                    "#Bitcoin #加密货币 #BTC #ETH #熊市 #链上数据 #风险管理 #财经快讯")
            th   = "🔴 " + title[:65] + "\n\n链上资金外流，等待企稳信号再行布局。"
        else:
            body = ("🚀 加密市场信号！\n\n"
                    "📌 " + title[:70] + "\n\n"
                    + (desc[:100] + "…\n\n" if desc else "")
                    + "链上数据回暖，资金回流信号出现！ETF净流入配合长线持有者增持，"
                    "市场情绪逐步改善。配合成交量放大才算有效确认，谨慎追高。\n\n"
                    "#Bitcoin #加密货币 #BTC #ETH #牛市 #链上数据 #ETF #财经快讯")
            th   = "🚀 " + title[:65] + "\n\n链上资金回流，成交量配合是确认信号，勿追高。"

    else:  # macro / general
        if bearish:
            body = ("⚠️ 宏观风险信号！\n\n"
                    "📌 " + title[:70] + "\n\n"
                    + (desc[:100] + "…\n\n" if desc else "")
                    + "全球风险情绪承压，避险资产（黄金、美债）短期受益。"
                    "建议适当降低权益仓位，关注后续经济数据对市场预期的修正影响。\n\n"
                    "#宏观经济 #全球市场 #避险 #黄金 #美股 #财经快讯 #投资策略")
            th   = "⚠️ " + title[:65] + "\n\n宏观风险升温，关注避险资产及降低权益仓位。"
        elif bullish:
            body = ("🌐 宏观利好消息！\n\n"
                    "📌 " + title[:70] + "\n\n"
                    + (desc[:100] + "…\n\n" if desc else "")
                    + "宏观数据改善或地缘风险缓解，市场风险偏好回升！"
                    "科技、周期板块有望联动走强，关注美元指数走向对新兴市场的影响。\n\n"
                    "#宏观经济 #全球市场 #风险偏好 #美股 #新兴市场 #财经快讯 #投资策略")
            th   = "🌐 " + title[:65] + "\n\n宏观利好带动风险偏好，科技周期板块关注联动机会。"
        else:
            body = ("📊 宏观财经要闻：\n\n"
                    "📌 " + title[:70] + "\n\n"
                    + (desc[:100] + "…\n\n" if desc else "")
                    + "宏观事件持续影响市场方向，建议密切追踪后续政策及经济数据走向，"
                    "结合技术面信号制定操作策略，避免情绪化决策。\n\n"
                    "#宏观经济 #全球市场 #美股 #财经快讯 #投资策略 #市场动态")
            th   = "📊 " + title[:65] + "\n\n宏观要闻影响市场节奏，持续追踪政策信号变化。"

    return body, th


# ── Message builders ─────────────────────────────────────────────────────────

def build_crypto_msg(seq):
    # Prices
    prices  = json.loads(fetch_url(
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"))
    btc     = prices.get("bitcoin", {})
    eth     = prices.get("ethereum", {})
    btc_p   = "${:,.0f}".format(btc.get("usd",0))
    btc_pct = btc.get("usd_24h_change", 0)
    eth_p   = "${:,.0f}".format(eth.get("usd",0))
    eth_pct = eth.get("usd_24h_change", 0)

    price_line = ("BTC " + arrow(btc_pct) + " " + btc_p + " (" + fmt_pct(btc_pct) + ")  "
                  "ETH " + arrow(eth_pct) + " " + eth_p + " (" + fmt_pct(eth_pct) + ")")

    # News: yfinance first, then RSS fallback
    news_items = get_yf_news(["BTC-USD","ETH-USD"], max_total=4)
    if not news_items:
        for src in CRYPTO_RSS:
            news_items = fetch_rss_items(src, 4)
            if news_items: break

    if news_items:
        item   = news_items[0]
        title  = item["title"]
        link   = item["link"]
        desc   = item.get("desc","")
        tickers= item.get("tickers",[])
    else:
        title, link, desc, tickers = "加密市场最新动态", "https://cointelegraph.com", "", []

    ig, th = make_ig_copy("crypto", title, desc, tickers)
    ig_full = "🪙 行情：" + price_line + "\n\n" + ig

    return ("⚡ *快讯 #" + str(seq) + "* 🪙 加密\n"
            "🔗 [" + title[:65] + "](" + link + ")\n\n"
            "📸 *Instagram文案：*\n" + ig_full + "\n\n"
            "🧵 *Threads文案：*\n" + price_line + "\n" + th)


def build_hot_news_msg(seq, screener_items):
    """Build 热门个股快讯 driven by Yahoo Finance popular news."""
    # Get hot tickers from screener
    hot_syms = [i["sym"] for i in screener_items if i.get("sym")][:6]

    # Pull yfinance news for hot tickers + broad market anchors
    all_news = get_yf_news(hot_syms + ["SPY","QQQ"], max_total=12)

    # Also pull from fallback RSS
    if len(all_news) < 4:
        for src in FALLBACK_RSS:
            rss_items = fetch_rss_items(src, 6)
            for ri in rss_items:
                ri["tickers"] = []
                all_news.append(ri)
            if len(all_news) >= 8: break

    # Classify & deduplicate
    def priority(item):
        return {"fed":0,"stock":1,"macro":2,"crypto":3,"general":4}.get(
            classify(item["title"]),4)
    all_news.sort(key=priority)

    seen, final = set(), []
    for item in all_news:
        words = set(item["title"].lower().split())
        if not any(len(words & set(s.lower().split())) > 5 for s in seen):
            seen.add(item["title"])
            final.append(item)
        if len(final) >= 3: break

    if not final:
        return None

    parts = []
    for i, item in enumerate(final, 1):
        cat    = classify(item["title"])
        title  = item["title"]
        link   = item.get("link","#")
        desc   = item.get("desc","")
        ticks  = item.get("tickers",[])

        label_map = {"fed":"🏛️ 美联储","stock":"📊 个股","macro":"🌐 宏观",
                     "crypto":"🪙 加密","general":"📰 财经"}
        label  = label_map.get(cat,"📰 财经")
        ig, th = make_ig_copy(cat, title, desc, ticks)

        pub    = item.get("pub","")
        pub_str= " | " + pub if pub else ""

        parts.append(
            "━━━━ " + label + pub_str + " ━━━━\n"
            "🔗 [" + title[:65] + "](" + link + ")\n\n"
            "📸 *Instagram：*\n" + ig + "\n\n"
            "🧵 *Threads：*\n" + th
        )

    return "⚡ *快讯 #" + str(seq) + "* 📰 财经热门要闻\n\n" + "\n\n".join(parts)


def build_market_msg(seq):
    lines = []
    sp_pct = 0

    # US indices
    if YF_AVAILABLE:
        idx_q = get_quotes_yf(list(US_INDICES.keys()))
        idx_parts = []
        for sym, name in US_INDICES.items():
            if sym in idx_q:
                p = idx_q[sym]["pct"]
                if sym == "^GSPC": sp_pct = p
                idx_parts.append(name + " " + darrow(p) + " " + fmt_pct(p))
        if idx_parts:
            lines.append("📊 *美股大盘：* " + "  |  ".join(idx_parts))

    # Screeners
    active  = get_screener("most_actives", 5)
    gainers = get_screener("day_gainers",  5)
    losers  = get_screener("day_losers",   5)

    def sline(item, show_vol=False):
        vol = "  vol:" + fmt_vol(item["vol"]) if show_vol and item["vol"] > 0 else ""
        return (arrow(item["pct"]) + " $" + item["sym"]
                + "  ${:.2f}".format(item["price"])
                + "  (" + fmt_pct(item["pct"]) + ")" + vol)

    if active:
        lines.append("\n🔥 *成交量五大：*\n" + "\n".join(sline(i, True) for i in active))
    if gainers:
        lines.append("\n🚀 *涨幅五大：*\n" + "\n".join(sline(i) for i in gainers))
    if losers:
        lines.append("\n💥 *跌幅五大：*\n" + "\n".join(sline(i) for i in losers))

    # ETFs
    if YF_AVAILABLE:
        etf_q = get_quotes_yf(list(ETF_POOL.keys()))
        etf_sorted = sorted([(s, etf_q[s], ETF_POOL[s]) for s in ETF_POOL if s in etf_q],
                            key=lambda x: x[1]["pct"], reverse=True)[:5]
        if etf_sorted:
            lines.append("\n📂 *板块ETF：*\n" + "\n".join(
                arrow(q["pct"]) + " " + name + "(" + sym + ")  " + fmt_pct(q["pct"])
                for sym, q, name in etf_sorted))

    # Asia
    if YF_AVAILABLE:
        asia_q = get_quotes_yf(list(ASIA_INDICES.keys()))
        asia_lines = [arrow(asia_q[s]["pct"]) + " " + name + "  " + fmt_pct(asia_q[s]["pct"])
                      for s, name in ASIA_INDICES.items() if s in asia_q]
        if asia_lines:
            lines.append("\n🌏 *亚太指数：*\n" + "\n".join(asia_lines))

    # Malaysia
    if YF_AVAILABLE:
        my_q   = get_quotes_yf(MY_TICKERS)
        klci   = my_q.get("^KLSE", {})
        klci_px= "{:,.2f}".format(klci.get("price",0))
        klci_p = klci.get("pct",0)
        my_stocks = [(s, my_q[s]) for s in MY_TICKERS if s in my_q and s != "^KLSE"]
        my_top = sorted(my_stocks, key=lambda x: abs(x[1]["pct"]), reverse=True)[:3]
        my_lines = [arrow(klci_p) + " KLCI " + klci_px + " (" + fmt_pct(klci_p) + ")"]
        my_lines += [arrow(q["pct"]) + " " + MY_NAMES.get(s,s)
                     + "  RM{:.2f} ({})".format(q["price"], fmt_pct(q["pct"])) for s,q in my_top]
        lines.append("\n🇲🇾 *马股：*\n" + "\n".join(my_lines))

    body = "\n".join(lines)
    if sp_pct >= 0.5:
        ig_tail = "整体风险偏好回升，关注成交量配合确认趋势。追踪热门个股动向，合理配置板块敞口。"
    elif sp_pct <= -0.5:
        ig_tail = "市场整体承压，避险情绪升温。建议关注黄金、债券等防御资产，谨慎对待反弹机会。"
    else:
        ig_tail = "市场震荡整理，多空拉锯等待方向。保持中性仓位，关注美联储政策信号及宏观数据催化。"

    ig_full = (body.replace("*","").replace("🔥","").replace("🚀","").replace("💥","")
               + "\n\n" + ig_tail + "\n\n"
               + "#美股 #WallStreet #涨幅榜 #跌幅榜 #成交量 #热门股 #亚太指数 #马股 #板块ETF #财经快讯")
    th_body = "\n".join(l.replace("*","").strip() for l in lines[:4] if l.strip())
    th_full  = th_body + "\n" + ig_tail[:50] + "…"

    # Return screener active list for news anchoring
    return ("⚡ *快讯 #" + str(seq) + "* 📊 市场速览\n\n"
            "📸 *Instagram：*\n" + ig_full + "\n\n"
            "🧵 *Threads：*\n" + th_full), active


def build_my_news_msg(seq):
    # yfinance news for Malaysian tickers
    my_news = get_yf_news(["^KLSE","1155.KL","1023.KL"], max_total=4)
    # RSS fallback
    if not my_news:
        for src in MY_NEWS_RSS:
            items = fetch_rss_items(src, 8)
            relevant = [i for i in items if any(k in i["title"].lower()
                        for k in ["klci","bursa","malaysia","ringgit","klse","maybank","cimb","tenaga"])]
            if relevant:
                i = relevant[0]; i["tickers"] = []; my_news = [i]; break

    if not my_news:
        return None

    item  = my_news[0]
    title = item["title"]
    link  = item.get("link","#")
    desc  = item.get("desc","")
    pub   = item.get("pub","")

    ig = ("🇲🇾 马股要闻：\n\n"
          "📌 " + title[:70] + "\n\n"
          + (desc[:120] + "…\n\n" if desc else "")
          + "关注此消息对KLCI及相关蓝筹股的影响。"
          "外资动向及令吉汇率仍是判断马股走势的关键指标，"
          "建议结合基本面综合评估布局时机，避免单一消息驱动决策。\n\n"
          "#马股 #KLCI #Bursa #马来西亚 #财经快讯 #投资 #蓝筹股")
    th = "🇲🇾 " + title[:60] + "\n\n关注对KLCI及蓝筹股的影响，追踪外资动向及令吉汇率。"

    pub_str = " | " + pub if pub else ""
    return ("⚡ *快讯 #" + str(seq) + "* 🇲🇾 马股要闻" + pub_str + "\n"
            "🔗 [" + title[:65] + "](" + link + ")\n\n"
            "📸 *Instagram：*\n" + ig + "\n\n"
            "🧵 *Threads：*\n" + th)


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    emoji, label = get_time_label()
    now_cst  = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    date_str = now_cst.strftime("%Y年%m月%d日 %H:%M")

    send_message(emoji + " *" + label + " | @not.a.stockguru*\n"
                 "📅 " + date_str + " (CST)\n━━━━━━━━━━━━━━━━━━━━")

    seq = 1

    # 1. Crypto
    try:
        send_message(build_crypto_msg(seq)); seq += 1
    except Exception as e:
        print("Crypto err:", e)
        send_message("⚠️ 加密快讯获取失败：" + str(e)[:80])

    # 2. Market data (returns active list for news anchoring)
    active_list = []
    if YF_AVAILABLE:
        try:
            market_msg, active_list = build_market_msg(seq)
            send_message(market_msg); seq += 1
        except Exception as e:
            print("Market err:", e)
            send_message("⚠️ 市场数据获取失败：" + str(e)[:80])

    # 3. Hot news anchored by today's trending stocks
    try:
        msg = build_hot_news_msg(seq, active_list)
        if msg:
            send_message(msg); seq += 1
    except Exception as e:
        print("Hot news err:", e)
        send_message("⚠️ 热门要闻获取失败：" + str(e)[:80])

    # 4. Malaysia news
    try:
        msg = build_my_news_msg(seq)
        if msg:
            send_message(msg); seq += 1
    except Exception as e:
        print("MY news err:", e)

    send_message("📲 关注 *@not.a.stockguru* 获取更多实时财经快讯 🔔")
    print("Done. Total messages:", seq - 1)


if __name__ == "__main__":
    main()
