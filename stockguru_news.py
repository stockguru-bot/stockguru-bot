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

# ── News RSS sources ──────────────────────────────────────────────────────────
GENERAL_RSS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://feeds.marketwatch.com/marketwatch/marketpulse/",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
]
CRYPTO_RSS = [
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
]
FED_RSS = [
    "https://www.federalreserve.gov/feeds/press_all.xml",
]
MY_NEWS_RSS = [
    "https://theedgemarkets.com/rss",
    "https://www.thestar.com.my/rss/business/business-news",
    "https://www.nst.com.my/rss/business",
]

# ── Market data tickers ────────────────────────────────────────────────────────
ETF_POOL = {"SMH":"半导体","XLK":"科技","XLE":"能源","XLF":"金融","ARKK":"创新","GLD":"黄金","IWM":"小盘"}
US_INDICES  = {"^GSPC":"S&P500","^IXIC":"Nasdaq"}
ASIA_INDICES = {"^N225":"日经225","^KS11":"韩国KOSPI","^TWII":"台湾加权","^HSI":"恒生指数"}
MY_TICKERS  = ["^KLSE","1155.KL","1023.KL","5681.KL","6012.KL","5347.KL"]
MY_NAMES    = {"^KLSE":"KLCI","1155.KL":"Maybank","1023.KL":"CIMB","5681.KL":"Tenaga","6012.KL":"Maxis","5347.KL":"PetChem"}
US_POOL     = ["SPCX","ASTS","LUNR","NVDA","INTC","MU","AMD","TSLA","META","GOOGL","AMZN","ROKU","PLTR","COIN","MSTR","HOOD"]

# ── Keyword classifiers ────────────────────────────────────────────────────────
FED_KW    = ["fed","federal reserve","fomc","interest rate","powell","rate cut","rate hike",
             "inflation","monetary policy","jerome","treasury","yield","bond"]
STOCK_KW  = ["nvidia","apple","tesla","microsoft","meta","amazon","intel","google","alphabet",
             "earnings","buyback","acquisition","merger","ipo","short","rally","plunge","surge",
             "beats","misses","upgrade","downgrade","guidance","revenue","profit","loss"]
CRYPTO_KW = ["bitcoin","btc","ethereum","eth","crypto","blockchain","coinbase","binance",
             "defi","nft","stablecoin","altcoin","solana","xrp"]
MACRO_KW  = ["gdp","jobs","unemployment","cpi","pce","recession","growth","tariff","trade",
             "oil","gold","dollar","yuan","yen","euro","debt","deficit","budget"]


# ── Helpers ────────────────────────────────────────────────────────────────────

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
            raise Exception(r.get("description", ""))
    print("✓ Sent:", text[:60])

def fetch_url(url, extra=None):
    h = {"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)","Accept":"*/*"}
    if extra: h.update(extra)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=12) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def fetch_rss_items(url, max_items=8):
    """Parse RSS and return list of {title, link, desc}."""
    try:
        xml = fetch_url(url, {"Accept":"application/rss+xml,application/xml,*/*"})
    except Exception as e:
        print(f"RSS fetch fail {url}: {e}")
        return []
    items = []
    for m in re.finditer(r'<item[^>]*>(.*?)</item>', xml, re.DOTALL):
        raw = m.group(1)
        tm  = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', raw, re.DOTALL)
        lm  = re.search(r'<link>(?:<!\[CDATA\[)?(https?://[^\s<"]+?)(?:\]\]>)?</link>', raw, re.DOTALL)
        if not lm:
            lm = re.search(r'<guid[^>]*>(?:<!\[CDATA\[)?(https?://[^\s<"]+?)(?:\]\]>)?</guid>', raw, re.DOTALL)
        dm  = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', raw, re.DOTALL)
        if tm and lm:
            title = html.unescape(re.sub(r'<[^>]+>','', tm.group(1))).strip()
            link  = re.sub(r'<.*','', lm.group(1)).strip()
            desc  = html.unescape(re.sub(r'<[^>]+>','', dm.group(1) if dm else '')).strip()[:200]
            if title and len(title) > 10:
                items.append({"title": title, "link": link, "desc": desc})
        if len(items) >= max_items:
            break
    return items

def classify(title):
    t = title.lower()
    if any(k in t for k in CRYPTO_KW): return "crypto"
    if any(k in t for k in FED_KW):    return "fed"
    if any(k in t for k in STOCK_KW):  return "stock"
    if any(k in t for k in MACRO_KW):  return "macro"
    return "general"

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
        return [{"sym": q.get("symbol",""), "name": q.get("shortName", q.get("symbol",""))[:14],
                 "price": q.get("regularMarketPrice",0), "pct": q.get("regularMarketChangePercent",0),
                 "vol": q.get("regularMarketVolume",0)} for q in s.response.get("quotes",[])[:count]]
    except Exception as e:
        print(f"screener {scr_id} err:", e)
        return []

def get_time_label():
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    h = now.hour
    if h < 14:   return "🕛","午间快讯"
    elif h < 17: return "🕒","下午快讯"
    elif h < 20: return "🕕","晚间快讯"
    else:        return "🌙","夜盘快讯"


# ── Copy generators ────────────────────────────────────────────────────────────

def gen_crypto_copy(title, btc_pct):
    t = title.lower()
    bearish = any(k in t for k in ["fall","drop","crash","bear","down","low","bottom","outflow","sell","slump"])
    bullish = any(k in t for k in ["rise","rally","bull","surge","high","gain","etf","inflow","record","break"])

    if btc_pct <= -2 or bearish:
        ig = ("⚠️ 加密市场今日承压！\n\n"
              + title[:50] + "\n\n"
              "链上数据走弱，恐慌指数仍处极度恐慌区间。多头若无法快速收复关键阻力位，"
              "短期面临进一步下探风险。机构资金观望情绪浓厚，切忌盲目抄底，严格管理仓位。📉\n\n"
              "#Bitcoin #加密货币 #BTC行情 #熊市信号 #链上数据 #风险管理")
        th = title[:50] + "\n链上指标偏空，关键阻力未突破前建议轻仓观望。📉"
    elif btc_pct >= 2 or bullish:
        ig = ("🚀 加密市场出现积极信号！\n\n"
              + title[:50] + "\n\n"
              "链上资金持续回流，市场情绪从恐慌区逐步回暖。ETF净流入叠加长线持有者增持，"
              "短期支撑逐步筑牢。但牛市信号需配合成交量放大才算确认，切勿追高。📊\n\n"
              "#Bitcoin #加密货币 #BTC #牛市信号 #ETF资金 #链上数据")
        th = title[:50] + "\n资金回流积极，成交量放大是确认信号。🚀"
    else:
        ig = ("⚡ 加密快讯：\n\n"
              + title[:55] + "\n\n"
              "多空力量胶着，市场等待更明确催化剂。短期方向取决于宏观数据及美联储政策走向，"
              "建议持续关注关键价位变化，做好风险管理，避免重仓操作。\n\n"
              "#Bitcoin #加密货币 #BTC #ETH #市场动态 #实时快讯")
        th = title[:50] + "\n市场方向未明，等待宏观数据指引。⚡"
    return ig, th

def gen_fed_copy(title, desc):
    ig = ("🏛️ 美联储重磅消息！\n\n"
          + title[:60] + "\n\n"
          + (desc[:120] + "…" if desc else "") + "\n\n"
          "利率政策走向直接影响全球资产定价。加息预期升温将压制股市估值，降息预期则提振风险资产。"
          "建议密切关注后续声明措辞变化，尤其是对通胀和就业市场的评估。📊\n\n"
          "#美联储 #FOMC #利率 #货币政策 #通胀 #宏观经济")
    th = "🏛️ " + title[:55] + "\n利率政策走向是当前市场最核心变量，持续关注。"
    return ig, th

def gen_stock_copy(title, desc):
    t = title.lower()
    bearish = any(k in t for k in ["fall","drop","slump","miss","downgrade","loss","plunge","lawsuit","fine"])
    bullish = any(k in t for k in ["rise","surge","beat","upgrade","buyback","acquisition","record","profit","gain"])

    if bullish:
        ig = ("📈 个股利好消息！\n\n"
              + title[:60] + "\n\n"
              + (desc[:120] + "…" if desc else "") + "\n\n"
              "基本面改善或催化剂驱动，短期股价动能偏强。关注成交量是否配合，"
              "确认突破有效性后再考虑追入，同时留意大盘整体走势风险。\n\n"
              "#美股 #个股行情 #WallStreet #投资机会 #热门股 #财经快讯")
        th = "📈 " + title[:55] + "\n基本面利好驱动，关注成交量确认突破有效性。"
    elif bearish:
        ig = ("📉 个股利空消息！\n\n"
              + title[:60] + "\n\n"
              + (desc[:120] + "…" if desc else "") + "\n\n"
              "负面催化剂拖累股价，短期动能偏弱。持仓者建议评估止损位，"
              "观望者等待下方支撑企稳后再考虑布局，切勿盲目抄底。\n\n"
              "#美股 #个股行情 #WallStreet #风险管理 #热门股 #财经快讯")
        th = "📉 " + title[:55] + "\n利空压制，建议等待支撑企稳再布局。"
    else:
        ig = ("⚡ 个股快讯！\n\n"
              + title[:60] + "\n\n"
              + (desc[:120] + "…" if desc else "") + "\n\n"
              "市场持续关注个股动态，相关板块情绪值得追踪。"
              "建议结合大盘走势综合判断，做好仓位风险管理。\n\n"
              "#美股 #个股行情 #WallStreet #热门股 #财经 #实时快讯")
        th = "⚡ " + title[:55] + "\n持续关注个股动态及板块情绪变化。"
    return ig, th

def gen_macro_copy(title, desc):
    t = title.lower()
    bearish = any(k in t for k in ["recession","slowdown","weak","decline","risk","concern","fear","fall"])
    bullish = any(k in t for k in ["strong","growth","beat","recover","improve","rise","gain"])

    if bullish:
        ig = ("🌐 宏观利好！\n\n"
              + title[:60] + "\n\n"
              + (desc[:120] + "…" if desc else "") + "\n\n"
              "经济数据超预期，市场风险偏好有望提升。关注美股科技及周期板块的联动反应，"
              "以及美元指数和国债收益率的短期走势变化。\n\n"
              "#宏观经济 #美股 #全球市场 #经济数据 #风险偏好 #投资策略")
        th = "🌐 " + title[:55] + "\n经济数据超预期，关注风险资产联动反应。"
    elif bearish:
        ig = ("⚠️ 宏观利空信号！\n\n"
              + title[:60] + "\n\n"
              + (desc[:120] + "…" if desc else "") + "\n\n"
              "经济前景不确定性上升，市场避险情绪可能升温。"
              "建议适当降低风险敞口，关注黄金、美债等避险资产的表现。\n\n"
              "#宏观经济 #避险 #全球市场 #经济衰退风险 #美股 #投资策略")
        th = "⚠️ " + title[:55] + "\n宏观风险升温，关注避险资产表现。"
    else:
        ig = ("📊 宏观要闻：\n\n"
              + title[:60] + "\n\n"
              + (desc[:120] + "…" if desc else "") + "\n\n"
              "宏观数据是影响市场方向的核心变量。建议持续追踪美联储政策路径及主要经济指标，"
              "结合技术面信号做出投资决策。\n\n"
              "#宏观经济 #美股 #全球市场 #经济数据 #美联储 #投资策略")
        th = "📊 " + title[:55] + "\n宏观数据持续影响市场方向，保持关注。"
    return ig, th

def gen_my_news_copy(title, desc):
    ig = ("🇲🇾 马股要闻：\n\n"
          + title[:60] + "\n\n"
          + (desc[:120] + "…" if desc else "") + "\n\n"
          "关注此消息对KLCI及相关板块的影响。外资动向及令吉汇率仍是判断马股走势的关键指标，"
          "建议结合基本面综合评估布局时机。\n\n"
          "#马股 #KLCI #Bursa #马来西亚 #财经快讯 #投资")
    th = "🇲🇾 " + title[:55] + "\n关注对KLCI及相关板块的影响。"
    return ig, th


# ── Message builders ────────────────────────────────────────────────────────────

def build_crypto_msg(idx):
    prices = json.loads(fetch_url(
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"))
    btc    = prices.get("bitcoin", {})
    eth    = prices.get("ethereum", {})
    btc_p  = "${:,.0f}".format(btc.get("usd",0))
    btc_pct= btc.get("usd_24h_change",0)
    eth_p  = "${:,.0f}".format(eth.get("usd",0))
    eth_pct= eth.get("usd_24h_change",0)

    price_line = ("BTC " + arrow(btc_pct) + " " + btc_p + " (" + fmt_pct(btc_pct) + ")  "
                  "ETH " + arrow(eth_pct) + " " + eth_p + " (" + fmt_pct(eth_pct) + ")")

    # Find best headline
    items = []
    for src in CRYPTO_RSS:
        items += fetch_rss_items(src, 4)
        if items: break

    title   = items[0]["title"] if items else "加密市场最新动态"
    link    = items[0]["link"]  if items else "https://cointelegraph.com"
    ig, th  = gen_crypto_copy(title, btc_pct)

    full_ig = ("🪙 加密行情：\n" + price_line + "\n\n" + ig)
    return ("⚡ *快讯 #" + str(idx) + "* 🪙 加密\n"
            "🔗 [" + title[:60] + "](" + link + ")\n\n"
            "📸 *Instagram*\n" + full_ig + "\n\n🧵 *Threads*\n" + price_line + "\n" + th)


def build_news_msg(idx):
    """Fetch latest financial news headlines and generate copy for top 2."""
    # Gather headlines
    all_items = []
    for src in GENERAL_RSS + FED_RSS:
        batch = fetch_rss_items(src, 6)
        for item in batch:
            item["cat"] = classify(item["title"])
            item["src"] = src
        all_items += batch
        if len(all_items) >= 15:
            break

    # Prioritize: fed > stock > macro > general
    def priority(item):
        return {"fed":0,"stock":1,"macro":2,"general":3,"crypto":4}.get(item["cat"],3)

    sorted_items = sorted(all_items, key=priority)

    # Deduplicate by similarity
    seen, final = [], []
    for item in sorted_items:
        title_words = set(item["title"].lower().split())
        if not any(len(title_words & set(s.lower().split())) > 4 for s in seen):
            seen.append(item["title"])
            final.append(item)
        if len(final) >= 2:
            break

    if not final:
        return None

    parts = []
    for i, item in enumerate(final, 1):
        cat   = item["cat"]
        title = item["title"]
        link  = item["link"]
        desc  = item["desc"]

        if cat == "fed":
            ig, th = gen_fed_copy(title, desc)
            label  = "🏛️ 美联储"
        elif cat == "stock":
            ig, th = gen_stock_copy(title, desc)
            label  = "📊 个股"
        elif cat == "macro":
            ig, th = gen_macro_copy(title, desc)
            label  = "🌐 宏观"
        else:
            ig, th = gen_macro_copy(title, desc)
            label  = "📰 财经"

        parts.append(
            "─────────────────────\n"
            "*" + label + "*\n"
            "🔗 [" + title[:60] + "](" + link + ")\n\n"
            "📸 *Instagram*\n" + ig + "\n\n"
            "🧵 *Threads*\n" + th
        )

    return "⚡ *快讯 #" + str(idx) + "* 📰 财经要闻\n\n" + "\n\n".join(parts)


def build_market_msg(idx):
    """US indices + screener + ETFs + Asia + Malaysia in one message."""
    lines = []

    # US indices
    if YF_AVAILABLE:
        idx_q = get_quotes_yf(list(US_INDICES.keys()))
        sp_pct = 0
        idx_parts = []
        for sym, name in US_INDICES.items():
            if sym in idx_q:
                p = idx_q[sym]["pct"]
                if sym == "^GSPC": sp_pct = p
                idx_parts.append(name + " " + darrow(p) + fmt_pct(p))
        if idx_parts:
            lines.append("📊 *美股大盘：* " + "  |  ".join(idx_parts))

    # Screener
    active  = get_screener(  "most_actives", 5)
    gainers = get_screener(  "day_gainers",  5)
    losers  = get_screener(  "day_losers",   5)

    def sline(item, show_vol=False):
        vol = "  vol:" + fmt_vol(item["vol"]) if show_vol and item["vol"] > 0 else ""
        return (arrow(item["pct"]) + " " + item["sym"]
                + " ${:.2f}".format(item["price"]) + " (" + fmt_pct(item["pct"]) + ")" + vol)

    if active:
        lines.append("\n📊 *成交量五大：*\n" + "\n".join(sline(i, True) for i in active))
    if gainers:
        lines.append("\n🚀 *涨幅五大：*\n" + "\n".join(sline(i) for i in gainers))
    if losers:
        lines.append("\n💥 *跌幅五大：*\n" + "\n".join(sline(i) for i in losers))

    # ETFs
    if YF_AVAILABLE:
        etf_q = get_quotes_yf(list(ETF_POOL.keys()))
        etf_sorted = sorted([(s, etf_q[s], ETF_POOL[s]) for s in ETF_POOL if s in etf_q],
                            key=lambda x: x[1]["pct"], reverse=True)[:4]
        if etf_sorted:
            lines.append("\n📂 *板块ETF：*\n" + "\n".join(
                arrow(q["pct"]) + " " + name + "(" + sym + ") " + fmt_pct(q["pct"])
                for sym, q, name in etf_sorted))

    # Asia
    if YF_AVAILABLE:
        asia_q = get_quotes_yf(list(ASIA_INDICES.keys()))
        asia_lines = [arrow(asia_q[s]["pct"]) + " " + name + " " + fmt_pct(asia_q[s]["pct"])
                      for s, name in ASIA_INDICES.items() if s in asia_q]
        if asia_lines:
            lines.append("\n🌏 *亚太指数：*\n" + "\n".join(asia_lines))

    # Malaysia
    if YF_AVAILABLE:
        my_q   = get_quotes_yf(MY_TICKERS)
        klci_q = my_q.get("^KLSE", {})
        klci_p = klci_q.get("pct", 0)
        klci_px= "{:,.2f}".format(klci_q.get("price", 0))
        my_stocks = [(s, my_q[s]) for s in MY_TICKERS if s in my_q and s != "^KLSE"]
        my_top = sorted(my_stocks, key=lambda x: abs(x[1]["pct"]), reverse=True)[:3]
        my_lines = [arrow(klci_p) + " KLCI " + klci_px + " (" + fmt_pct(klci_p) + ")"]
        my_lines += [arrow(q["pct"]) + " " + MY_NAMES.get(s,s) + " RM{:.2f} ({})".format(q["price"], fmt_pct(q["pct"]))
                     for s, q in my_top]
        lines.append("\n🇲🇾 *马股：*\n" + "\n".join(my_lines))

    body = "\n".join(lines)

    # Sentiment
    sp_pct = 0
    if YF_AVAILABLE and "^GSPC" in get_quotes_yf(["^GSPC"]):
        sp_pct = get_quotes_yf(["^GSPC"])["^GSPC"]["pct"]

    if sp_pct >= 0.5:
        sentiment = "美股今日整体走强，风险偏好回升。关注成交量持续放大以确认突破有效性。"
    elif sp_pct <= -0.5:
        sentiment = "美股今日承压，避险情绪升温。关注美联储政策表态及通胀数据走向。"
    else:
        sentiment = "美股今日震荡整理，市场等待明确催化剂，保持中性仓位。"

    ig = (body.replace("*","") + "\n\n" + sentiment + "\n\n"
          "#美股 #WallStreet #涨幅榜 #跌幅榜 #成交量 #亚太指数 #马股 #板块ETF")
    th = ("市场速览 📊\n" + "\n".join(l.replace("*","").strip() for l in lines[:3] if l.strip()) + "\n" + sentiment[:50] + "…")

    return ("⚡ *快讯 #" + str(idx) + "* 📊 市场速览\n\n"
            "📸 *Instagram*\n" + ig + "\n\n🧵 *Threads*\n" + th)


def build_my_news_msg(idx):
    """Malaysian stock news."""
    for src in MY_NEWS_RSS:
        items = fetch_rss_items(src, 8)
        relevant = [i for i in items if any(k in i["title"].lower()
                    for k in ["klci","bursa","malaysia","ringgit","klse","maybank","cimb","tenaga"])]
        if relevant:
            item  = relevant[0]
            ig, th = gen_my_news_copy(item["title"], item["desc"])
            return ("⚡ *快讯 #" + str(idx) + "* 🇲🇾 马股要闻\n"
                    "🔗 [" + item["title"][:60] + "](" + item["link"] + ")\n\n"
                    "📸 *Instagram*\n" + ig + "\n\n🧵 *Threads*\n" + th)
    return None


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    emoji, label = get_time_label()
    now_cst  = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    date_str = now_cst.strftime("%Y年%m月%d日")

    send_message(emoji + " *" + label + " | @not.a.stockguru* 📅 " + date_str
                 + "\n━━━━━━━━━━━━━━━━━━━━")

    idx = 1

    # 1. Crypto
    try:
        send_message(build_crypto_msg(idx)); idx += 1
    except Exception as e:
        print("Crypto err:", e)
        send_message("⚠️ *加密快讯获取失败*：" + str(e)[:80])

    # 2. Financial news (Fed + stock + macro)
    try:
        msg = build_news_msg(idx)
        if msg:
            send_message(msg); idx += 1
    except Exception as e:
        print("News err:", e)
        send_message("⚠️ *财经要闻获取失败*：" + str(e)[:80])

    # 3. Market data (US + Asia + MY prices)
    if YF_AVAILABLE:
        try:
            send_message(build_market_msg(idx)); idx += 1
        except Exception as e:
            print("Market err:", e)
            send_message("⚠️ *市场数据获取失败*：" + str(e)[:80])

    # 4. Malaysian news
    try:
        msg = build_my_news_msg(idx)
        if msg:
            send_message(msg); idx += 1
    except Exception as e:
        print("MY news err:", e)

    send_message("📲 关注 @not.a.stockguru 获取更多实时财经")
    print("Done. Sent", idx - 1, "messages.")


if __name__ == "__main__":
    main()
