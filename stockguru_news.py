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

# ── Market tickers ─────────────────────────────────────────────────────────────
ETF_POOL     = {"SMH":"半导体","XLK":"科技","XLE":"能源","XLF":"金融","ARKK":"创新","GLD":"黄金","IWM":"小盘"}
US_INDICES   = {"^GSPC":"S&P500","^IXIC":"Nasdaq"}
ASIA_INDICES = {"^N225":"日经225","^KS11":"韩国KOSPI","^TWII":"台湾加权","^HSI":"恒生指数"}
MY_TICKERS   = ["^KLSE","1155.KL","1023.KL","5681.KL","6012.KL","5347.KL"]
MY_NAMES     = {"^KLSE":"KLCI","1155.KL":"Maybank","1023.KL":"CIMB",
                "5681.KL":"Tenaga","6012.KL":"Maxis","5347.KL":"PetChem"}

# ── News sources ───────────────────────────────────────────────────────────────
# Yahoo Finance RSS — same content as the Popular/Top Stories section
YF_MARKET_RSS = [
    "https://finance.yahoo.com/rss/topstories",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY&region=US&lang=en-US",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=QQQ&region=US&lang=en-US",
]
YF_TICKER_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
FALLBACK_RSS  = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://www.federalreserve.gov/feeds/press_all.xml",
]
CRYPTO_RSS    = ["https://cointelegraph.com/rss"]
MY_NEWS_RSS   = [
    "https://theedgemarkets.com/rss",
    "https://www.thestar.com.my/rss/business/business-news",
]

# ── Sentiment keywords ─────────────────────────────────────────────────────────
FED_KW  = ["fed","federal reserve","fomc","interest rate","powell","warsh","rate cut",
           "rate hike","inflation","monetary policy","treasury","yield","bond","chair","central bank"]
STOCK_KW= ["nvidia","apple","tesla","microsoft","meta","amazon","intel","micron","sandisk",
           "spacex","hynix","oracle","marvell","uniqure","google","alphabet","robinhood",
           "earnings","buyback","acquisition","ipo","rally","plunge","surge","soars","slips",
           "target raised","target lifted","upgrade","downgrade","revenue","profit","partnership","deal",
           "beats","misses","guidance","short","overweight","underweight"]
CRYPTO_KW=["bitcoin","btc","ethereum","eth","crypto","blockchain","coinbase","binance",
           "defi","nft","stablecoin","solana","xrp","altcoin"]
MACRO_KW =["gdp","jobs","unemployment","cpi","pce","recession","growth","tariff","trade",
           "oil","gold","dollar","yuan","yen","iran","china","europe","debt","deficit","war","deal"]

def classify(title):
    t = title.lower()
    if any(k in t for k in CRYPTO_KW): return "crypto"
    if any(k in t for k in FED_KW):    return "fed"
    if any(k in t for k in STOCK_KW):  return "stock"
    if any(k in t for k in MACRO_KW):  return "macro"
    return "general"

def sentiment(title):
    t = title.lower()
    if any(k in t for k in ["fall","drop","crash","slump","miss","loss","plunge","slips",
                             "decline","weak","concern","fine","lawsuit","fear","risk"]):
        return "bear"
    if any(k in t for k in ["rise","rally","surge","soars","beat","upgrade","record","profit",
                             "partnership","deal","gain","high","strong","lifted","boost","jump"]):
        return "bull"
    return "neutral"

# ── Utilities ──────────────────────────────────────────────────────────────────
def send_message(text):
    data = json.dumps({"chat_id": CHAT_ID, "text": text,
                       "parse_mode": "Markdown", "disable_web_page_preview": True}).encode()
    req  = urllib.request.Request(BASE_URL, data=data,
                                  headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        resp = json.loads(r.read().decode())
        if not resp.get("ok"):
            raise Exception(resp.get("description",""))
    print("✓ Sent:", text[:60])

def fetch_url(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept":     "application/rss+xml,application/xml,text/xml,*/*"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return r.read().decode("utf-8", errors="ignore")

def parse_rss(xml, max_items=8):
    """Parse RSS XML → list of {title, link, desc}."""
    items = []
    for m in re.finditer(r'<item[^>]*>(.*?)</item>', xml, re.DOTALL):
        raw = m.group(1)
        tm  = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', raw, re.DOTALL)
        lm  = re.search(r'<link>(?:<!\[CDATA\[)?(https?://[^\s<"]+)(?:\]\]>)?</link>', raw, re.DOTALL)
        if not lm:
            lm = re.search(r'<guid[^>]*>(?:<!\[CDATA\[)?(https?://[^\s<"]+)(?:\]\]>)?</guid>', raw, re.DOTALL)
        dm  = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', raw, re.DOTALL)
        if tm and lm:
            title = html.unescape(re.sub(r'<[^>]+>','', tm.group(1))).strip()
            link  = lm.group(1).strip()
            desc  = html.unescape(re.sub(r'<[^>]+>','', dm.group(1) if dm else '')).strip()[:200]
            if title and len(title) > 10:
                items.append({"title": title, "link": link, "desc": desc})
        if len(items) >= max_items:
            break
    return items

def fetch_rss(url, max_items=8):
    try:
        return parse_rss(fetch_url(url), max_items)
    except Exception as e:
        print(f"RSS fail {url}: {e}")
        return []

def fmt_pct(v): return ("+" if v >= 0 else "") + "{:.2f}%".format(v)
def arrow(v):   return "🟢" if v >= 0 else "🔴"
def darrow(v):  return "▲" if v >= 0 else "▼"
def fmt_vol(v):
    if v >= 1e9: return "{:.1f}B".format(v/1e9)
    if v >= 1e6: return "{:.1f}M".format(v/1e6)
    return "{:.0f}K".format(v/1e3)

def get_quotes_yf(tickers):
    result = {}
    if not tickers or not YF_AVAILABLE: return result
    try:
        raw = yf.download(tickers, period="5d", interval="1d",
                          group_by="ticker", auto_adjust=True, progress=False, threads=True)
        for sym in (tickers if isinstance(tickers, list) else [tickers]):
            try:
                if len(tickers) > 1:
                    closes = raw[sym]["Close"].dropna()
                else:
                    closes = raw["Close"].dropna()
                if len(closes) >= 2:
                    p, c = float(closes.iloc[-2]), float(closes.iloc[-1])
                    result[sym] = {"price": c, "pct": (c - p) / p * 100}
                elif len(closes) == 1:
                    result[sym] = {"price": float(closes.iloc[-1]), "pct": 0.0}
            except Exception:
                pass
    except Exception as e:
        print("yf.download err:", e)
    return result

def get_screener(scr_id, count=5):
    try:
        s = yf.Screener()
        s.set_predefined_body(scr_id)
        s.set_count(count)
        return [{"sym":   str(q.get("symbol", "")),
                 "name":  str(q.get("shortName", q.get("symbol", "")))[:16],
                 "price": float(q.get("regularMarketPrice", 0)),
                 "pct":   float(q.get("regularMarketChangePercent", 0)),
                 "vol":   float(q.get("regularMarketVolume", 0))}
                for q in s.response.get("quotes", [])[:count]]
    except Exception as e:
        print(f"screener {scr_id}: {e}")
        return []

def get_yf_news_for_ticker(sym, max_items=4):
    """Fetch news via yfinance — handles both old and new API formats."""
    results = []
    try:
        ticker   = yf.Ticker(sym)
        news_raw = ticker.news
        # Safety: news might be callable in some versions
        if callable(news_raw):
            news_raw = news_raw()
        if not isinstance(news_raw, list):
            return results
        for n in news_raw[:max_items]:
            try:
                if not isinstance(n, dict):
                    continue
                # ── New yfinance format (content nested) ──
                if "content" in n:
                    c = n["content"]
                    if not isinstance(c, dict):
                        continue
                    title = str(c.get("title") or "").strip()
                    url_d = c.get("canonicalUrl") or c.get("clickThroughUrl") or {}
                    link  = str(url_d.get("url", "") if isinstance(url_d, dict) else "").strip()
                    desc  = str(c.get("summary") or "")[:200].strip()
                    prov  = c.get("provider") or {}
                    pub   = str(prov.get("displayName", "") if isinstance(prov, dict) else "").strip()
                    fin   = c.get("finance") or {}
                    traw  = fin.get("stockTickers", []) if isinstance(fin, dict) else []
                    tickers = [str(t.get("symbol", "")) for t in traw if isinstance(t, dict)]
                # ── Old yfinance format (flat dict) ──
                else:
                    title   = str(n.get("title") or "").strip()
                    link    = str(n.get("link") or n.get("url") or "").strip()
                    desc    = str(n.get("summary") or "")[:200].strip()
                    pub     = str(n.get("publisher") or "").strip()
                    traw    = n.get("relatedTickers") or []
                    tickers = [str(t) if isinstance(t, str) else str(t.get("symbol", ""))
                               for t in traw if t]

                if not title or not link:
                    continue
                results.append({"title": title, "link": link, "desc": desc,
                                "pub": pub, "tickers": tickers})
            except Exception as ie:
                print(f"  news item parse ({sym}): {ie}")
    except Exception as e:
        print(f"yf.Ticker.news ({sym}): {e}")
    return results

def get_all_news(hot_syms):
    """Aggregate news: Yahoo Finance RSS first, then yfinance per-ticker, then fallbacks."""
    items = []
    seen  = set()

    def add(batch):
        for item in batch:
            key = item["title"][:40].lower()
            if key not in seen and len(item["title"]) > 15:
                seen.add(key)
                items.append(item)

    # 1. Yahoo Finance Top Stories RSS (same as Popular section)
    for url in YF_MARKET_RSS:
        batch = fetch_rss(url, 8)
        for b in batch:
            b.setdefault("tickers", [])
            b.setdefault("pub", "Yahoo Finance")
        add(batch)
        if len(items) >= 10:
            break

    # 2. Yahoo Finance per-ticker RSS for hot stocks
    for sym in (hot_syms or [])[:4]:
        url   = YF_TICKER_RSS.format(sym=sym)
        batch = fetch_rss(url, 4)
        for b in batch:
            b.setdefault("tickers", [sym])
            b.setdefault("pub", "Yahoo Finance")
        add(batch)

    # 3. yfinance Ticker.news (handles both API formats)
    if YF_AVAILABLE and len(items) < 6:
        for sym in (hot_syms or [])[:4] + ["SPY", "QQQ"]:
            batch = get_yf_news_for_ticker(sym, 3)
            add(batch)
            if len(items) >= 12:
                break

    # 4. Fallback RSS (Reuters, CNBC, Fed)
    if len(items) < 4:
        for url in FALLBACK_RSS:
            batch = fetch_rss(url, 6)
            for b in batch:
                b.setdefault("tickers", [])
                b.setdefault("pub", "")
            add(batch)
            if len(items) >= 8:
                break

    return items

def get_time_label():
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    h   = now.hour
    if h < 14:   return "🕛", "午间快讯"
    elif h < 17: return "🕒", "下午快讯"
    elif h < 20: return "🕕", "晚间快讯"
    else:        return "🌙", "夜盘快讯"


# ── Copy generation ────────────────────────────────────────────────────────────

def make_copy(cat, sent, title, desc, tickers):
    """Return (instagram_text, threads_text)."""
    related = " ".join("$" + str(s) for s in tickers[:2] if s) if tickers else ""
    desc_snippet = (desc[:110] + "…") if desc else ""

    if cat == "fed":
        if sent == "bear":
            ig = ("🏛️ 美联储鹰派信号！\n\n"
                  "📌 " + title[:75] + "\n\n"
                  + (desc_snippet + "\n\n" if desc_snippet else "")
                  + "多位联储官员倾向年内加息，利率政策明显偏鹰。"
                  "加息预期升温将压制科技成长股估值，美债收益率短期上行压力增大。"
                  "注意科技、高估值板块回调风险，可关注金融、能源等受益板块。📉\n\n"
                  "#美联储 #加息 #FOMC #利率 #货币政策 #美股 #通胀 #财经快讯")
            th  = ("🏛️ 美联储鹰派！" + title[:50] + "\n\n"
                   "加息预期升温，科技成长股承压，关注金融能源板块机会。📉")
        elif sent == "bull":
            ig = ("🏛️ 美联储鸽派信号！\n\n"
                  "📌 " + title[:75] + "\n\n"
                  + (desc_snippet + "\n\n" if desc_snippet else "")
                  + "降息或暂停加息预期提振市场风险偏好！"
                  "利率下行有利于科技、成长及房地产板块表现，"
                  "美债收益率承压。关注后续通胀数据验证降息路径。🚀\n\n"
                  "#美联储 #降息 #FOMC #利率 #货币政策 #美股 #风险偏好 #财经快讯")
            th  = ("🏛️ 美联储鸽派！" + title[:50] + "\n\n"
                   "降息预期提振风险资产，科技成长板块迎布局机会。🚀")
        else:
            ig = ("🏛️ 美联储最新动态！\n\n"
                  "📌 " + title[:75] + "\n\n"
                  + (desc_snippet + "\n\n" if desc_snippet else "")
                  + "利率政策走向是当前市场最核心变量。"
                  "关注声明措辞，尤其是对通胀与就业的评估，将直接影响全球资产定价。📊\n\n"
                  "#美联储 #FOMC #利率 #货币政策 #美股 #宏观经济 #财经快讯")
            th  = ("🏛️ 美联储要闻：" + title[:50] + "\n\n"
                   "利率政策牵动市场神经，持续关注政策表态变化。📊")

    elif cat == "stock":
        tag = (" " + related) if related else ""
        if sent == "bull":
            ig = ("📈" + ((" " + related) if related else "") + " 个股利好！\n\n"
                  "📌 " + title[:75] + "\n\n"
                  + (desc_snippet + "\n\n" if desc_snippet else "")
                  + "催化剂驱动短期动能强劲！关注成交量是否持续放大以确认突破有效性，"
                  "顺势布局时同时留意大盘整体配合情况。\n\n"
                  "#美股 #个股行情 #WallStreet #热门股 #财经快讯" + tag)
            th  = ("📈" + ((" " + related) if related else "") + " " + title[:60] + "\n\n"
                   "催化剂利好驱动，成交量放大是确认信号。")
        elif sent == "bear":
            ig = ("📉" + ((" " + related) if related else "") + " 个股利空！\n\n"
                  "📌 " + title[:75] + "\n\n"
                  + (desc_snippet + "\n\n" if desc_snippet else "")
                  + "负面消息拖累股价，短期动能偏弱。持仓者注意评估止损位，"
                  "等待下方支撑企稳及基本面改善信号后再考虑布局。\n\n"
                  "#美股 #个股行情 #WallStreet #热门股 #财经快讯" + tag)
            th  = ("📉" + ((" " + related) if related else "") + " " + title[:60] + "\n\n"
                   "利空压制，等待下方企稳信号再行布局。")
        else:
            ig = ("⚡" + ((" " + related) if related else "") + " 个股快讯！\n\n"
                  "📌 " + title[:75] + "\n\n"
                  + (desc_snippet + "\n\n" if desc_snippet else "")
                  + "市场高度关注，相关板块情绪值得持续追踪。"
                  "结合大盘走势及成交量综合判断，做好仓位风险管理。\n\n"
                  "#美股 #个股行情 #WallStreet #热门股 #财经快讯" + tag)
            th  = ("⚡" + ((" " + related) if related else "") + " " + title[:60] + "\n\n"
                   "市场热议，结合大盘走势综合判断布局时机。")

    elif cat == "crypto":
        if sent == "bear":
            ig = ("🔴 加密市场承压！\n\n"
                  "📌 " + title[:75] + "\n\n"
                  + (desc_snippet + "\n\n" if desc_snippet else "")
                  + "链上资金外流，市场恐慌情绪升温。多头需收复关键阻力位才能扭转局面，"
                  "短期严控仓位，等待企稳信号确认再行布局。\n\n"
                  "#Bitcoin #加密货币 #BTC #ETH #熊市 #链上数据 #风险管理")
            th  = ("🔴 " + title[:60] + "\n\n链上资金外流，等待企稳信号再行布局。")
        else:
            ig = ("🚀 加密市场信号！\n\n"
                  "📌 " + title[:75] + "\n\n"
                  + (desc_snippet + "\n\n" if desc_snippet else "")
                  + "链上数据回暖，资金回流信号出现！ETF净流入配合长线持有者增持，"
                  "市场情绪改善。成交量配合才算有效确认，谨慎追高。\n\n"
                  "#Bitcoin #加密货币 #BTC #ETH #牛市 #链上数据 #ETF")
            th  = ("🚀 " + title[:60] + "\n\n链上资金回流，成交量配合是确认信号。")

    else:  # macro / general
        if sent == "bear":
            ig = ("⚠️ 宏观风险信号！\n\n"
                  "📌 " + title[:75] + "\n\n"
                  + (desc_snippet + "\n\n" if desc_snippet else "")
                  + "全球风险情绪承压，黄金、美债等避险资产短期受益。"
                  "建议适当降低权益仓位，关注宏观数据对市场预期的修正影响。\n\n"
                  "#宏观经济 #全球市场 #避险 #黄金 #美股 #财经快讯 #投资策略")
            th  = ("⚠️ " + title[:60] + "\n\n宏观风险升温，关注黄金等避险资产。")
        elif sent == "bull":
            ig = ("🌐 宏观利好！\n\n"
                  "📌 " + title[:75] + "\n\n"
                  + (desc_snippet + "\n\n" if desc_snippet else "")
                  + "宏观数据改善或地缘风险缓解，市场风险偏好回升！"
                  "科技、周期板块有望联动走强，关注美元指数对新兴市场的影响。\n\n"
                  "#宏观经济 #全球市场 #风险偏好 #美股 #财经快讯 #投资策略")
            th  = ("🌐 " + title[:60] + "\n\n宏观利好带动风险偏好，关注科技周期板块。")
        else:
            ig = ("📊 宏观财经要闻：\n\n"
                  "📌 " + title[:75] + "\n\n"
                  + (desc_snippet + "\n\n" if desc_snippet else "")
                  + "宏观事件持续影响市场节奏。密切追踪美联储政策及经济数据走向，"
                  "结合技术面信号制定操作策略，避免情绪化决策。\n\n"
                  "#宏观经济 #全球市场 #美股 #财经快讯 #投资策略")
            th  = ("📊 " + title[:60] + "\n\n宏观要闻影响市场节奏，持续追踪政策信号。")

    return ig, th


# ── Message builders ───────────────────────────────────────────────────────────

def build_crypto_msg(seq):
    prices  = json.loads(fetch_url(
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"))
    btc     = prices.get("bitcoin", {})
    eth     = prices.get("ethereum", {})
    btc_p   = "${:,.0f}".format(btc.get("usd", 0))
    btc_pct = float(btc.get("usd_24h_change", 0))
    eth_p   = "${:,.0f}".format(eth.get("usd", 0))
    eth_pct = float(eth.get("usd_24h_change", 0))
    price_line = ("BTC " + arrow(btc_pct) + " " + btc_p + " (" + fmt_pct(btc_pct) + ")  "
                  "ETH " + arrow(eth_pct) + " " + eth_p + " (" + fmt_pct(eth_pct) + ")")

    # News: yfinance first, then RSS
    news = get_yf_news_for_ticker("BTC-USD", 3) + get_yf_news_for_ticker("ETH-USD", 2)
    if not news:
        for src in CRYPTO_RSS:
            news = fetch_rss(src, 4)
            for n in news:
                n.setdefault("tickers", [])
            if news: break

    if news:
        n     = news[0]
        title = n["title"]
        link  = n["link"]
        desc  = n.get("desc", "")
        ticks = n.get("tickers", [])
    else:
        title, link, desc, ticks = "加密市场最新动态", "https://cointelegraph.com", "", []

    sent    = sentiment(title)
    ig, th  = make_copy("crypto", sent, title, desc, ticks)
    ig_full = "🪙 行情：" + price_line + "\n\n" + ig

    return ("⚡ *快讯 #" + str(seq) + "* 🪙 加密\n"
            "🔗 [" + title[:70] + "](" + link + ")\n\n"
            "📸 *Instagram：*\n" + ig_full + "\n\n"
            "🧵 *Threads：*\n" + price_line + "\n" + th)


def build_market_msg(seq):
    lines   = []
    sp_pct  = 0.0

    # US indices
    if YF_AVAILABLE:
        idx_q = get_quotes_yf(list(US_INDICES.keys()))
        parts = []
        for sym, name in US_INDICES.items():
            if sym in idx_q:
                p = idx_q[sym]["pct"]
                if sym == "^GSPC": sp_pct = p
                parts.append(name + " " + darrow(p) + " " + fmt_pct(p))
        if parts:
            lines.append("📊 *美股大盘：* " + "  |  ".join(parts))

    # Screeners
    active  = get_screener("most_actives", 5)
    gainers = get_screener("day_gainers",  5)
    losers  = get_screener("day_losers",   5)

    def sl(item, vol=False):
        v = "  vol:" + fmt_vol(item["vol"]) if vol and item["vol"] > 0 else ""
        return (arrow(item["pct"]) + " $" + item["sym"]
                + "  ${:.2f}".format(item["price"])
                + "  (" + fmt_pct(item["pct"]) + ")" + v)

    if active:  lines.append("\n🔥 *成交量五大：*\n" + "\n".join(sl(i, True)  for i in active))
    if gainers: lines.append("\n🚀 *涨幅五大：*\n"   + "\n".join(sl(i)        for i in gainers))
    if losers:  lines.append("\n💥 *跌幅五大：*\n"   + "\n".join(sl(i)        for i in losers))

    # ETFs
    if YF_AVAILABLE:
        etf_q = get_quotes_yf(list(ETF_POOL.keys()))
        etf_s = sorted([(s, etf_q[s], ETF_POOL[s]) for s in ETF_POOL if s in etf_q],
                        key=lambda x: x[1]["pct"], reverse=True)[:5]
        if etf_s:
            lines.append("\n📂 *板块ETF：*\n" + "\n".join(
                arrow(q["pct"]) + " " + name + "(" + sym + ")  " + fmt_pct(q["pct"])
                for sym, q, name in etf_s))

    # Asian indices
    if YF_AVAILABLE:
        asia_q = get_quotes_yf(list(ASIA_INDICES.keys()))
        alines = [arrow(asia_q[s]["pct"]) + " " + name + "  " + fmt_pct(asia_q[s]["pct"])
                  for s, name in ASIA_INDICES.items() if s in asia_q]
        if alines:
            lines.append("\n🌏 *亚太指数：*\n" + "\n".join(alines))

    # Malaysia
    if YF_AVAILABLE:
        my_q = get_quotes_yf(MY_TICKERS)
        klci = my_q.get("^KLSE", {})
        klci_p, klci_px = klci.get("pct", 0), "{:,.2f}".format(klci.get("price", 0))
        my_s = [(s, my_q[s]) for s in MY_TICKERS if s in my_q and s != "^KLSE"]
        my_t = sorted(my_s, key=lambda x: abs(x[1]["pct"]), reverse=True)[:3]
        mylines = [arrow(klci_p) + " KLCI " + klci_px + " (" + fmt_pct(klci_p) + ")"]
        mylines += [arrow(q["pct"]) + " " + MY_NAMES.get(s, s)
                    + "  RM{:.2f} ({})".format(q["price"], fmt_pct(q["pct"])) for s, q in my_t]
        lines.append("\n🇲🇾 *马股：*\n" + "\n".join(mylines))

    body = "\n".join(lines)
    if sp_pct >= 0.5:
        tail = "整体风险偏好回升，关注热门个股动向及成交量配合，合理配置板块敞口。"
    elif sp_pct <= -0.5:
        tail = "市场整体承压，避险情绪升温。关注黄金、债券等防御资产，谨慎对待反弹。"
    else:
        tail = "市场震荡等待方向，保持中性仓位，关注美联储政策信号及宏观数据催化剂。"

    ig_text = (body.replace("*", "") + "\n\n" + tail + "\n\n"
               "#美股 #WallStreet #涨幅榜 #跌幅榜 #成交量 #热门股 #亚太指数 #马股 #板块ETF")
    th_text = "\n".join(l.replace("*", "").strip() for l in lines[:4] if l.strip()) + "\n" + tail[:55] + "…"

    msg = ("⚡ *快讯 #" + str(seq) + "* 📊 市场速览\n\n"
           "📸 *Instagram：*\n" + ig_text + "\n\n"
           "🧵 *Threads：*\n" + th_text)
    return msg, active   # return active list for news anchoring


def build_hot_news_msg(seq, active_items):
    hot_syms = [str(i.get("sym", "")) for i in (active_items or []) if i.get("sym")][:5]
    all_news = get_all_news(hot_syms)

    if not all_news:
        return None

    # Classify and rank
    ranked = sorted(all_news,
                    key=lambda x: {"fed":0,"stock":1,"macro":2,"general":3,"crypto":4}.get(
                        classify(x["title"]), 3))

    # Pick top 3 deduplicated
    final = []
    seen  = set()
    for item in ranked:
        words = frozenset(item["title"].lower().split())
        overlap = any(len(words & frozenset(s.lower().split())) > 5 for s in seen)
        if not overlap:
            seen.add(item["title"])
            final.append(item)
        if len(final) >= 3:
            break

    if not final:
        return None

    parts = []
    label_map = {"fed":"🏛️ 美联储","stock":"📊 个股","macro":"🌐 宏观",
                 "crypto":"🪙 加密","general":"📰 财经"}
    for item in final:
        cat   = classify(item["title"])
        sent  = sentiment(item["title"])
        title = item["title"]
        link  = item.get("link", "#")
        desc  = item.get("desc", "")
        ticks = item.get("tickers", [])
        pub   = item.get("pub", "")
        label = label_map.get(cat, "📰 财经")
        ig, th = make_copy(cat, sent, title, desc, ticks)
        pub_str = "  |  " + pub if pub else ""
        parts.append(
            "━━━━ " + label + pub_str + " ━━━━\n"
            "🔗 [" + title[:70] + "](" + link + ")\n\n"
            "📸 *Instagram：*\n" + ig + "\n\n"
            "🧵 *Threads：*\n" + th
        )

    return "⚡ *快讯 #" + str(seq) + "* 📰 财经热门要闻\n\n" + "\n\n".join(parts)


def build_my_news_msg(seq):
    # Try yfinance first
    news = get_yf_news_for_ticker("^KLSE", 3) + get_yf_news_for_ticker("1155.KL", 2)
    if not news:
        for src in MY_NEWS_RSS:
            batch = fetch_rss(src, 8)
            relevant = [n for n in batch if any(
                k in n["title"].lower()
                for k in ["klci","bursa","malaysia","ringgit","maybank","cimb","tenaga"])]
            if relevant:
                for r in relevant:
                    r.setdefault("tickers", [])
                    r.setdefault("pub", "")
                news = relevant
                break

    if not news:
        return None

    item  = news[0]
    title = item["title"]
    link  = item.get("link", "#")
    desc  = item.get("desc", "")
    pub   = item.get("pub", "")
    sent  = sentiment(title)

    ig = ("🇲🇾 马股要闻：\n\n"
          "📌 " + title[:75] + "\n\n"
          + ((desc[:120] + "…\n\n") if desc else "")
          + "关注此消息对KLCI及相关蓝筹股的影响。"
          "外资动向及令吉汇率仍是判断马股走势的关键指标，"
          "建议结合基本面综合评估，避免单一消息驱动决策。\n\n"
          "#马股 #KLCI #Bursa #马来西亚 #财经快讯 #投资 #蓝筹股")
    th  = "🇲🇾 " + title[:60] + "\n\n关注KLCI及蓝筹股影响，追踪外资动向及令吉汇率。"

    pub_str = "  |  " + pub if pub else ""
    return ("⚡ *快讯 #" + str(seq) + "* 🇲🇾 马股要闻" + pub_str + "\n"
            "🔗 [" + title[:70] + "](" + link + ")\n\n"
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
        send_message(build_crypto_msg(seq))
        seq += 1
    except Exception as e:
        print("Crypto err:", e)
        send_message("⚠️ 加密快讯获取失败：" + str(e)[:80])

    # 2. Market data + screener (returns active list)
    active_list = []
    if YF_AVAILABLE:
        try:
            market_msg, active_list = build_market_msg(seq)
            send_message(market_msg)
            seq += 1
        except Exception as e:
            print("Market err:", e)
            send_message("⚠️ 市场数据获取失败：" + str(e)[:80])

    # 3. Hot news anchored by today's trending stocks
    try:
        msg = build_hot_news_msg(seq, active_list)
        if msg:
            send_message(msg)
            seq += 1
    except Exception as e:
        print("Hot news err:", e)
        send_message("⚠️ 热门要闻获取失败：" + str(e)[:80])

    # 4. Malaysian news
    try:
        msg = build_my_news_msg(seq)
        if msg:
            send_message(msg)
            seq += 1
    except Exception as e:
        print("MY news err:", e)

    send_message("📲 关注 *@not.a.stockguru* 获取更多实时财经快讯 🔔")
    print("Done. Messages sent:", seq - 1)


if __name__ == "__main__":
    main()
