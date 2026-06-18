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

# Sector mapping for US stocks
SECTOR_MAP = {
    "NVDA":"半导体/AI", "AMD":"半导体", "INTC":"半导体", "MU":"存储芯片",
    "AVGO":"半导体", "QCOM":"半导体", "SMH":"半导体ETF",
    "TSLA":"新能源/电动车", "RIVN":"电动车", "NIO":"电动车",
    "META":"社交媒体/AI", "GOOGL":"科技/AI", "MSFT":"科技/AI", "AAPL":"科技/消费",
    "AMZN":"电商/云计算", "NFLX":"流媒体", "ROKU":"流媒体",
    "PLTR":"大数据/AI", "COIN":"加密/金融科技", "HOOD":"金融科技",
    "GS":"投资银行", "JPM":"银行", "BAC":"银行",
    "MSTR":"比特币概念", "MARA":"比特币矿业",
    "ASTS":"太空通讯", "RKLB":"航天", "LUNR":"航天",
    "QURE":"生物科技", "MRNA":"医疗/疫苗",
}

FALLBACK_RSS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://www.federalreserve.gov/feeds/press_all.xml",
]
CRYPTO_RSS = ["https://cointelegraph.com/rss"]
MY_NEWS_RSS = [
    "https://theedgemarkets.com/rss",
    "https://www.thestar.com.my/rss/business/business-news",
]

# Keywords for classification
FED_KW   = ["fed","federal reserve","fomc","interest rate","powell","warsh","rate cut","rate hike",
            "inflation","monetary policy","treasury","yield","bond","chair","central bank","fed chair"]
STOCK_KW = ["nvidia","apple","tesla","microsoft","meta","amazon","intel","micron","sandisk","hynix",
            "spacex","oracle","marvell","uniqure","google","alphabet","robinhood","coinbase","palantir",
            "earnings","buyback","acquisition","ipo","rally","plunge","surge","soars","slips",
            "price target","target raised","target lifted","upgrade","downgrade","revenue","profit",
            "partnership","deal","beats","misses","guidance","overweight","underweight","short"]
CRYPTO_KW= ["bitcoin","btc","ethereum","eth","crypto","blockchain","coinbase","binance",
            "defi","nft","stablecoin","solana","xrp","altcoin"]
MACRO_KW = ["gdp","jobs","unemployment","cpi","pce","recession","growth","tariff","trade",
            "oil","gold","dollar","yuan","yen","iran","china","europe","debt","deficit"]

def classify(title):
    t = title.lower()
    if any(k in t for k in CRYPTO_KW): return "crypto"
    if any(k in t for k in FED_KW):    return "fed"
    if any(k in t for k in STOCK_KW):  return "stock"
    if any(k in t for k in MACRO_KW):  return "macro"
    return "general"

def get_sentiment(title):
    t = title.lower()
    bears = ["fall","drop","crash","slump","miss","loss","plunge","slips","decline","weak",
             "concern","fine","lawsuit","fear","risk","down","lower","cut","warn","disappoint"]
    bulls = ["rise","rally","surge","soars","beat","upgrade","record","profit","partnership",
             "deal","gain","high","strong","lifted","boost","jump","top","exceed","buy","outperform"]
    b_score = sum(1 for k in bears if k in t)
    u_score = sum(1 for k in bulls if k in t)
    if b_score > u_score: return "bear"
    if u_score > b_score: return "bull"
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
            raise Exception(resp.get("description", ""))
    print("✓ Sent:", text[:60])

def fetch_url(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept":     "application/rss+xml,application/xml,text/html,*/*"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return r.read().decode("utf-8", errors="ignore")

def parse_rss(xml, max_items=10):
    items = []
    for m in re.finditer(r'<item[^>]*>(.*?)</item>', xml, re.DOTALL):
        raw = m.group(1)
        tm  = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', raw, re.DOTALL)
        lm  = re.search(r'<link>(?:<!\[CDATA\[)?(https?://[^\s<"]+)(?:\]\]>)?</link>', raw, re.DOTALL)
        if not lm:
            lm = re.search(r'<guid[^>]*>(?:<!\[CDATA\[)?(https?://[^\s<"]+)(?:\]\]>)?</guid>', raw, re.DOTALL)
        dm  = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', raw, re.DOTALL)
        if tm and lm:
            title = html.unescape(re.sub(r'<[^>]+>', '', tm.group(1))).strip()
            link  = lm.group(1).strip()
            desc  = html.unescape(re.sub(r'<[^>]+>', '', dm.group(1) if dm else '')).strip()[:250]
            if title and len(title) > 10:
                items.append({"title": title, "link": link, "desc": desc})
        if len(items) >= max_items:
            break
    return items

def fetch_rss(url, max_items=10):
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
                closes = raw[sym]["Close"].dropna() if len(tickers) > 1 else raw["Close"].dropna()
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
                 "name":  str(q.get("shortName", q.get("symbol", "")))[:20],
                 "price": float(q.get("regularMarketPrice", 0)),
                 "pct":   float(q.get("regularMarketChangePercent", 0)),
                 "vol":   float(q.get("regularMarketVolume", 0))}
                for q in s.response.get("quotes", [])[:count]]
    except Exception as e:
        print(f"screener {scr_id}: {e}")
        return []

def fetch_yf_ticker_news(sym, max_items=4):
    """Fetch news for a specific ticker via Yahoo Finance RSS — most reliable method."""
    url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={}&region=US&lang=en-US".format(sym)
    items = fetch_rss(url, max_items)
    for item in items:
        item["sym"] = sym
        item.setdefault("tickers", [sym])
    return items

def fetch_yf_news_api(sym, max_items=4):
    """Fetch news via yfinance Ticker.news — handles both old and new API format."""
    results = []
    try:
        ticker   = yf.Ticker(sym)
        news_raw = ticker.news
        if callable(news_raw):
            news_raw = news_raw()
        if not isinstance(news_raw, list):
            return results
        for n in (news_raw or [])[:max_items]:
            try:
                if not isinstance(n, dict):
                    continue
                # New format: content nested
                if "content" in n:
                    c     = n["content"] or {}
                    title = str(c.get("title") or "").strip()
                    ud    = c.get("canonicalUrl") or c.get("clickThroughUrl") or {}
                    link  = str(ud.get("url", "") if isinstance(ud, dict) else "").strip()
                    desc  = str(c.get("summary") or "")[:250].strip()
                    prov  = c.get("provider") or {}
                    pub   = str(prov.get("displayName", "") if isinstance(prov, dict) else "")
                    fin   = c.get("finance") or {}
                    traw  = fin.get("stockTickers", []) if isinstance(fin, dict) else []
                    tickers = [str(t.get("symbol", "")) for t in traw if isinstance(t, dict) and t.get("symbol")]
                else:
                    # Old format: flat dict
                    title   = str(n.get("title") or "").strip()
                    link    = str(n.get("link") or n.get("url") or "").strip()
                    desc    = str(n.get("summary") or "")[:250].strip()
                    pub     = str(n.get("publisher") or "")
                    traw    = n.get("relatedTickers") or []
                    tickers = [str(t) if isinstance(t, str) else str(t.get("symbol", ""))
                               for t in traw if t]
                if title and link:
                    results.append({"title": title, "link": link, "desc": desc,
                                    "pub": pub, "tickers": tickers, "sym": sym})
            except Exception as ie:
                print(f"  news item ({sym}): {ie}")
    except Exception as e:
        print(f"yf.Ticker.news ({sym}): {e}")
    return results

def gather_stock_news(hot_syms):
    """Gather news for hot stocks — primary method: Yahoo Finance per-ticker RSS."""
    all_items = []
    seen      = set()

    def add(batch):
        for item in batch:
            key = item["title"][:40].lower()
            if key not in seen and len(item["title"]) > 15:
                seen.add(key)
                item.setdefault("tickers", [item.get("sym", "")])
                item.setdefault("pub", "Yahoo Finance")
                all_items.append(item)

    # 1. Per-ticker Yahoo Finance RSS for each hot stock (most targeted)
    for sym in hot_syms[:8]:
        batch = fetch_yf_ticker_news(sym, 3)
        add(batch)

    # 2. Yahoo Finance top stories RSS
    for url in [
        "https://finance.yahoo.com/rss/topstories",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY&region=US&lang=en-US",
    ]:
        batch = fetch_rss(url, 8)
        for b in batch:
            b.setdefault("tickers", [])
            b.setdefault("sym", "")
        add(batch)
        if len(all_items) >= 15:
            break

    # 3. yfinance API fallback
    if len(all_items) < 5 and YF_AVAILABLE:
        for sym in hot_syms[:5] + ["SPY"]:
            add(fetch_yf_news_api(sym, 3))

    # 4. Reuters/CNBC fallback
    if len(all_items) < 4:
        for url in FALLBACK_RSS:
            batch = fetch_rss(url, 6)
            for b in batch:
                b.setdefault("tickers", [])
                b.setdefault("sym", "")
            add(batch)
            if len(all_items) >= 8:
                break

    return all_items

def get_time_label():
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    h   = now.hour
    if h < 14:   return "🕛", "午间快讯"
    elif h < 17: return "🕒", "下午快讯"
    elif h < 20: return "🕕", "晚间快讯"
    else:        return "🌙", "夜盘快讯"


# ── Professional copy generation ───────────────────────────────────────────────

def make_copy(item, price_ctx=None):
    """
    Generate long-form professional Chinese financial copy.
    price_ctx: dict with sym, price, pct for the related stock (if available).
    Returns (instagram_text, threads_text).
    """
    title   = item["title"]
    desc    = item.get("desc", "")
    tickers = item.get("tickers", [])
    cat     = classify(title)
    sent    = get_sentiment(title)
    t       = title.lower()

    # Price context string
    px_str = ""
    if price_ctx and price_ctx.get("sym"):
        sym = price_ctx["sym"]
        px  = price_ctx.get("price", 0)
        pct = price_ctx.get("pct", 0)
        px_str = "\n\n💹 ${sym} 今日 {a} ${px:.2f}（{p}）".format(
            sym=sym, a="▲" if pct >= 0 else "▼", px=px, p=fmt_pct(pct))

    # Sector context
    sym_hint = tickers[0] if tickers else item.get("sym", "")
    sector   = SECTOR_MAP.get(sym_hint, "")
    sector_str = "（" + sector + "板块）" if sector else ""

    desc_clip = (desc[:150] + "…") if desc else ""

    # ── Fed / Interest rates ──────────────────────────────────────────────────
    if cat == "fed":
        if "hike" in t or "raise" in t or "hawkish" in t or "more" in t:
            ig = ("🏛️ 美联储鹰派信号来袭！\n\n"
                  "📌 " + title + "\n"
                  + (desc_clip + "\n" if desc_clip else "")
                  + px_str + "\n\n"
                  "【市场影响解读】\n"
                  "新任联储主席首次表态偏鹰，多位联储官员支持年内继续加息，"
                  "这直接打压了市场此前的降息预期。\n\n"
                  "📊 关键影响链：\n"
                  "利率↑ → 借贷成本↑ → 科技/成长股估值承压\n"
                  "利率↑ → 美债收益率↑ → 美元走强 → 新兴市场资金外流\n"
                  "利率↑ → 银行息差扩大 → 金融板块相对受益\n\n"
                  "⚠️ 投资者需关注：科技、房地产、高杠杆板块短期回调风险上升。"
                  "建议适当降低成长股仓位，关注防御型资产（黄金、金融、能源）配置机会。\n\n"
                  "#美联储 #加息 #FOMC #利率政策 #货币政策 #美股 #通胀 #科技股 #财经快讯")
            th  = ("🏛️ 美联储鹰派！" + title[:55] + "\n\n"
                   "加息预期升温：科技成长承压，金融能源相对受益。"
                   "降低高估值仓位，关注防御型资产配置机会。📉")
        elif "cut" in t or "ease" in t or "pause" in t or "dovish" in t:
            ig = ("🏛️ 美联储鸽派信号！市场迎来重要转折点！\n\n"
                  "📌 " + title + "\n"
                  + (desc_clip + "\n" if desc_clip else "")
                  + px_str + "\n\n"
                  "【市场影响解读】\n"
                  "降息或暂停加息预期重燃，资金开始重新定价风险资产。\n\n"
                  "📊 关键影响链：\n"
                  "利率↓ → 融资成本↓ → 科技/成长股估值提升\n"
                  "利率↓ → 美债收益率↓ → 新兴市场资金回流\n"
                  "利率↓ → 房地产、消费板块受益\n\n"
                  "✅ 关注方向：科技、生物科技、小盘成长股迎来阶段性布局机会。"
                  "关键验证指标：后续通胀（CPI/PCE）数据是否持续回落，"
                  "以支撑降息路径预期。\n\n"
                  "#美联储 #降息 #FOMC #利率政策 #货币政策 #美股 #风险偏好 #科技股 #财经快讯")
            th  = ("🏛️ 美联储鸽派！" + title[:55] + "\n\n"
                   "降息预期重燃，科技成长股迎布局机会。"
                   "关注后续通胀数据验证降息路径。🚀")
        else:
            ig = ("🏛️ 美联储最新表态 | 市场核心变量\n\n"
                  "📌 " + title + "\n"
                  + (desc_clip + "\n" if desc_clip else "")
                  + px_str + "\n\n"
                  "【为什么重要？】\n"
                  "美联储政策是当前全球资产定价的最核心变量。"
                  "每一次官员表态都可能引发债券、美元、股市的连锁反应。\n\n"
                  "📊 重点追踪：\n"
                  "① 措辞变化：'data dependent'（数据依赖）程度\n"
                  "② 通胀预期：PCE/CPI是否继续回落\n"
                  "③ 就业市场：非农数据是否出现明显降温\n\n"
                  "策略建议：维持中性仓位，等待更明确政策信号后再调整方向。\n\n"
                  "#美联储 #FOMC #利率 #货币政策 #美股 #宏观经济 #财经快讯")
            th  = ("🏛️ " + title[:60] + "\n\n"
                   "利率政策走向牵动全球市场。追踪通胀及就业数据变化，维持中性仓位。📊")

    # ── Individual Stock ──────────────────────────────────────────────────────
    elif cat == "stock":
        related  = " ".join("$" + str(s) for s in tickers[:3] if s)
        sect_tag = sector_str

        if sent == "bull":
            ig = ("📈 " + (related + " " if related else "") + "个股重磅利好" + sect_tag + "！\n\n"
                  "📌 " + title + "\n"
                  + (desc_clip + "\n" if desc_clip else "")
                  + px_str + "\n\n"
                  "【利好解读】\n"
                  "这是市场高度关注的催化剂事件。"
                  + ("分析师大幅上调目标价，机构对该股基本面的信心显著提升，"
                     "短期股价获得强力支撑。" if "target" in t or "price" in t else
                     "业绩超预期或重大合作消息落地，提振市场对该公司成长前景的信心。")
                  + "\n\n"
                  "📊 交易策略参考：\n"
                  "✅ 成交量是关键：若突破时成交量显著放大（超过20日均量），"
                  "信号更为可靠，可考虑顺势追入。\n"
                  "⚠️ 风险提示：消息驱动行情往往在公布当日冲高，"
                  "次日可能出现获利回吐，建议分批布局，避免满仓追高。\n\n"
                  "#美股 #个股行情 #WallStreet #热门股 #财经快讯"
                  + (" " + related if related else ""))
            th  = ("📈 " + (related + " " if related else "") + title[:65] + "\n\n"
                   "利好催化驱动，成交量放大是有效突破的关键确认信号。"
                   "分批布局，避免追高。")
        elif sent == "bear":
            ig = ("📉 " + (related + " " if related else "") + "个股重磅利空" + sect_tag + "！\n\n"
                  "📌 " + title + "\n"
                  + (desc_clip + "\n" if desc_clip else "")
                  + px_str + "\n\n"
                  "【利空解读】\n"
                  + ("分析师下调目标价或评级，反映机构对该公司基本面出现分歧，"
                     "短期股价承压风险上升。" if "downgrade" in t or "cut" in t or "lower" in t else
                     "负面催化剂打击市场信心，短期内买盘力量明显减弱。")
                  + "\n\n"
                  "📊 风险管理建议：\n"
                  "⚠️ 持仓者：评估当前止损位是否合理，避免情绪化持有。\n"
                  "👀 观望者：等待股价在关键支撑位（如200日均线/前期低点）"
                  "企稳并出现缩量迹象后，再考虑逢低布局。\n"
                  "❌ 切忌：在下行趋势中盲目抄底，须等待企稳信号确认。\n\n"
                  "#美股 #个股行情 #WallStreet #热门股 #财经快讯"
                  + (" " + related if related else ""))
            th  = ("📉 " + (related + " " if related else "") + title[:65] + "\n\n"
                   "利空压制，等待关键支撑位企稳信号后再考虑布局。切忌盲目抄底。")
        else:
            ig = ("⚡ " + (related + " " if related else "") + "个股要闻" + sect_tag + "\n\n"
                  "📌 " + title + "\n"
                  + (desc_clip + "\n" if desc_clip else "")
                  + px_str + "\n\n"
                  "【市场解读】\n"
                  "此类消息往往是板块情绪变化的先行指标，"
                  "需结合整体大盘方向及成交量变化综合判断其实际影响力。\n\n"
                  "📊 关注要点：\n"
                  "① 该股在同板块中的相对强弱变化\n"
                  "② 机构资金流向（大单净流入/流出）\n"
                  "③ 期权市场隐含波动率是否异动\n\n"
                  "建议持续追踪，结合技术面信号再行决策。\n\n"
                  "#美股 #个股行情 #WallStreet #热门股 #财经快讯"
                  + (" " + related if related else ""))
            th  = ("⚡ " + (related + " " if related else "") + title[:65] + "\n\n"
                   "关注板块情绪变化，结合大盘方向及机构资金流向综合判断。")

    # ── Crypto ────────────────────────────────────────────────────────────────
    elif cat == "crypto":
        if sent == "bear":
            ig = ("🔴 加密市场警报！\n\n"
                  "📌 " + title + "\n"
                  + (desc_clip + "\n" if desc_clip else "")
                  + px_str + "\n\n"
                  "【行情解读】\n"
                  "链上资金出现外流迹象，市场恐慌情绪升温。"
                  "当前加密市场与宏观流动性高度相关，"
                  "美联储政策预期收紧将进一步压制风险资产表现。\n\n"
                  "📊 风险管理参考：\n"
                  "⚠️ BTC需守住关键支撑位，若跌破则下行空间可能进一步打开\n"
                  "⚠️ 山寨币在BTC走弱时跌幅通常更大，仓位管理至关重要\n"
                  "✅ 关注时机：恐慌指数（Fear & Greed）跌入极度恐慌区（<20）"
                  "时，往往是中长线逢低布局的参考信号\n\n"
                  "#Bitcoin #加密货币 #BTC #ETH #熊市 #链上数据 #风险管理 #加密市场")
            th  = ("🔴 " + title[:65] + "\n\n"
                   "链上资金外流，恐慌情绪升温。守住关键支撑位是关键，"
                   "山寨仓位需严格管理。")
        else:
            ig = ("🚀 加密市场积极信号！\n\n"
                  "📌 " + title + "\n"
                  + (desc_clip + "\n" if desc_clip else "")
                  + px_str + "\n\n"
                  "【行情解读】\n"
                  "链上数据回暖，机构资金回流信号出现。"
                  + ("ETF持续净流入叠加长线持有者（HODLer）增持，" if "etf" in t else "")
                  + "市场情绪从恐慌区逐步向贪婪区过渡。\n\n"
                  "📊 多头确认条件：\n"
                  "✅ 成交量持续放大（突破需量配合）\n"
                  "✅ 链上活跃地址数回升\n"
                  "✅ 稳定币净流入交易所（买盘资金储备充足）\n\n"
                  "⚠️ 切记：牛市中同样需要风险管理，建议分批入场，"
                  "设定止盈止损区间，避免情绪化决策。\n\n"
                  "#Bitcoin #加密货币 #BTC #ETH #牛市 #链上数据 #ETF #加密市场")
            th  = ("🚀 " + title[:65] + "\n\n"
                   "链上资金回流信号出现！成交量放大是确认关键。"
                   "分批入场，设好止盈止损区间。")

    # ── Macro / General ───────────────────────────────────────────────────────
    else:
        if sent == "bear":
            ig = ("⚠️ 宏观风险预警！\n\n"
                  "📌 " + title + "\n"
                  + (desc_clip + "\n" if desc_clip else "")
                  + px_str + "\n\n"
                  "【宏观解读】\n"
                  "全球风险情绪面临新的压力测试。"
                  "地缘政治风险、贸易摩擦或经济数据走弱，"
                  "任何一个因素都可能触发市场风险偏好快速下行。\n\n"
                  "📊 避险配置参考：\n"
                  "🥇 黄金（GLD/GDX）：地缘风险及通胀预期双重支撑\n"
                  "📉 美债（TLT）：避险需求推动收益率下行\n"
                  "💵 美元指数：风险厌恶情绪下通常走强\n\n"
                  "建议适当降低高风险资产（科技、小盘）仓位，"
                  "增加防御性配置比例，静待风险释放。\n\n"
                  "#宏观经济 #全球市场 #避险 #黄金 #美股 #财经快讯 #投资策略")
            th  = ("⚠️ " + title[:60] + "\n\n"
                   "宏观风险升温，关注黄金、美债避险配置。"
                   "降低科技小盘仓位，等待风险释放。")
        elif sent == "bull":
            ig = ("🌐 宏观利好！全球风险偏好回升！\n\n"
                  "📌 " + title + "\n"
                  + (desc_clip + "\n" if desc_clip else "")
                  + px_str + "\n\n"
                  "【宏观解读】\n"
                  "地缘局势缓和或经济数据超预期，为市场提供重要正面催化剂。"
                  "风险偏好回升通常利好：周期股、新兴市场、大宗商品相关资产。\n\n"
                  "📊 关注方向：\n"
                  "✅ 科技/半导体：受益于需求改善预期\n"
                  "✅ 能源/材料：大宗商品需求预期回升\n"
                  "✅ 新兴市场（含马股）：资金回流风险资产\n\n"
                  "⚠️ 注意：单一宏观事件的市场影响有限，"
                  "需结合联储政策及整体流动性环境综合判断持续性。\n\n"
                  "#宏观经济 #全球市场 #风险偏好 #美股 #新兴市场 #财经快讯 #投资策略")
            th  = ("🌐 " + title[:60] + "\n\n"
                   "宏观利好提振风险偏好！科技、能源、新兴市场关注联动机会。"
                   "结合流动性环境判断持续性。")
        else:
            ig = ("📊 宏观财经要闻精析\n\n"
                  "📌 " + title + "\n"
                  + (desc_clip + "\n" if desc_clip else "")
                  + px_str + "\n\n"
                  "【背景解读】\n"
                  "宏观事件是影响市场中长期方向的根本性变量。"
                  "短期市场往往过度反应或反应不足，"
                  "真正的机会来自对宏观趋势的正确判断。\n\n"
                  "📊 投资者需追踪：\n"
                  "① 美联储政策路径（利率期货定价变化）\n"
                  "② 美国经济软着陆/硬着陆概率\n"
                  "③ 企业盈利预期修正方向\n"
                  "④ 全球资金流向（美元/新兴市场相对强弱）\n\n"
                  "保持冷静，数据说话，避免情绪化追涨杀跌。\n\n"
                  "#宏观经济 #全球市场 #美股 #财经快讯 #投资策略 #市场分析")
            th  = ("📊 " + title[:60] + "\n\n"
                   "宏观变量是市场方向的根本驱动力。"
                   "追踪联储路径及企业盈利预期，数据说话避免情绪化决策。")

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

    news = (fetch_yf_ticker_news("BTC-USD", 3)
            + fetch_yf_ticker_news("ETH-USD", 2))
    if not news:
        for src in CRYPTO_RSS:
            batch = fetch_rss(src, 4)
            for b in batch:
                b.setdefault("tickers", [])
                b.setdefault("sym", "")
            news = batch
            if news: break

    if not news:
        news = [{"title":"加密市场最新动态","link":"https://cointelegraph.com",
                 "desc":"","tickers":[],"sym":""}]

    item    = news[0]
    ig, th  = make_copy(item, {"sym":"BTC","price":btc.get("usd",0),"pct":btc_pct})
    ig_full = "🪙 *行情速览：*\n" + price_line + "\n\n" + ig

    return ("⚡ *快讯 #" + str(seq) + "* 🪙 加密\n"
            "🔗 [" + item["title"][:70] + "](" + item["link"] + ")\n\n"
            "📸 *Instagram：*\n" + ig_full + "\n\n"
            "🧵 *Threads：*\n" + price_line + "\n\n" + th)


def build_market_msg(seq):
    lines  = []
    sp_pct = 0.0

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

    if YF_AVAILABLE:
        etf_q = get_quotes_yf(list(ETF_POOL.keys()))
        etf_s = sorted([(s, etf_q[s], ETF_POOL[s]) for s in ETF_POOL if s in etf_q],
                        key=lambda x: x[1]["pct"], reverse=True)[:5]
        if etf_s:
            lines.append("\n📂 *板块ETF：*\n" + "\n".join(
                arrow(q["pct"]) + " " + name + "(" + sym + ")  " + fmt_pct(q["pct"])
                for sym, q, name in etf_s))

    if YF_AVAILABLE:
        asia_q = get_quotes_yf(list(ASIA_INDICES.keys()))
        alines = [arrow(asia_q[s]["pct"]) + " " + name + "  " + fmt_pct(asia_q[s]["pct"])
                  for s, name in ASIA_INDICES.items() if s in asia_q]
        if alines:
            lines.append("\n🌏 *亚太指数：*\n" + "\n".join(alines))

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
        tail = "整体风险偏好回升，成交量扩张中的热门股值得重点追踪。合理控制仓位，做好风险管理。"
    elif sp_pct <= -0.5:
        tail = "市场整体承压回落，避险情绪升温。关注黄金、美债等防御资产，谨慎对待反弹行情。"
    else:
        tail = "多空力量胶着，市场等待新的方向性催化剂。中性仓位为主，关注热门个股结构性机会。"

    ig_text = (body.replace("*", "") + "\n\n" + tail + "\n\n"
               "#美股 #WallStreet #涨幅榜 #跌幅榜 #成交量 #热门股 #亚太指数 #马股 #板块ETF #财经快讯")
    th_text = "\n".join(l.replace("*", "").strip() for l in lines[:4] if l.strip()) + "\n\n" + tail[:60] + "…"

    msg = ("⚡ *快讯 #" + str(seq) + "* 📊 市场速览\n\n"
           "📸 *Instagram：*\n" + ig_text + "\n\n"
           "🧵 *Threads：*\n" + th_text)
    return msg, active


def build_hot_news_msg(seq, active_items):
    hot_syms = [str(i.get("sym", "")) for i in (active_items or []) if i.get("sym")][:8]
    # Also add gainers and losers for news anchoring
    gainers  = get_screener("day_gainers", 5)
    losers   = get_screener("day_losers",  5)
    hot_syms += [str(i.get("sym","")) for i in gainers + losers if i.get("sym")]
    hot_syms  = list(dict.fromkeys(hot_syms))[:10]  # deduplicate, keep order

    # Get price context for hot stocks
    price_ctx_map = {}
    if YF_AVAILABLE and hot_syms:
        pq = get_quotes_yf(hot_syms[:8])
        price_ctx_map = {s: {"sym": s, "price": pq[s]["price"], "pct": pq[s]["pct"]}
                         for s in pq}

    all_news = gather_stock_news(hot_syms)

    if not all_news:
        return None

    # Rank: Fed first, then stock (related to hot movers), then macro
    def rank(item):
        cat = classify(item["title"])
        # Boost score if news is about a hot stock
        sym_hit = any(s.lower() in item["title"].lower() or s == item.get("sym","")
                      for s in hot_syms if s)
        boost = -1 if sym_hit else 0
        return {"fed":0,"stock":1,"macro":2,"general":3,"crypto":4}.get(cat, 3) + boost

    all_news.sort(key=rank)

    # Pick top 3 deduplicated
    final, seen = [], set()
    for item in all_news:
        words = frozenset(item["title"].lower().split())
        if not any(len(words & frozenset(s.lower().split())) > 5 for s in seen):
            seen.add(item["title"])
            final.append(item)
        if len(final) >= 3:
            break

    if not final:
        return None

    label_map = {"fed":"🏛️ 美联储","stock":"📊 个股","macro":"🌐 宏观",
                 "crypto":"🪙 加密","general":"📰 财经"}
    parts = []
    for item in final:
        cat   = classify(item["title"])
        label = label_map.get(cat, "📰 财经")
        pub   = item.get("pub", "")
        sym   = item.get("sym", "") or (item.get("tickers", [None])[0] or "")
        px_ctx = price_ctx_map.get(sym)
        ig, th = make_copy(item, px_ctx)
        pub_str = "  |  " + pub if pub else ""
        parts.append(
            "━━━━ " + label + pub_str + " ━━━━\n"
            "🔗 [" + item["title"][:70] + "](" + item["link"] + ")\n\n"
            "📸 *Instagram：*\n" + ig + "\n\n"
            "🧵 *Threads：*\n" + th
        )

    return "⚡ *快讯 #" + str(seq) + "* 📰 财经热门要闻\n\n" + "\n\n".join(parts)


def build_my_news_msg(seq):
    my_syms = ["^KLSE", "1155.KL", "1023.KL"]
    news = []
    for sym in my_syms:
        batch = fetch_yf_ticker_news(sym, 3)
        news.extend(batch)
    if not news:
        for src in MY_NEWS_RSS:
            batch = fetch_rss(src, 8)
            rel   = [n for n in batch if any(
                k in n["title"].lower()
                for k in ["klci","bursa","malaysia","ringgit","maybank","cimb","tenaga"])]
            if rel:
                for r in rel:
                    r.setdefault("tickers", [])
                    r.setdefault("sym", "")
                news = rel
                break
    if not news:
        return None

    item = news[0]
    item.setdefault("tickers", [])
    item.setdefault("sym", "")
    my_q = get_quotes_yf(["^KLSE"]) if YF_AVAILABLE else {}
    klci = my_q.get("^KLSE")
    px_ctx = {"sym": "KLCI", "price": klci["price"], "pct": klci["pct"]} if klci else None

    ig, th  = make_copy(item, px_ctx)
    pub     = item.get("pub", "")
    pub_str = "  |  " + pub if pub else ""
    title   = item["title"]
    link    = item.get("link", "#")

    # Prepend Malaysia context to ig
    ig = "🇲🇾 " + ig

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

    # 2. Market overview + screener
    active_list = []
    if YF_AVAILABLE:
        try:
            market_msg, active_list = build_market_msg(seq)
            send_message(market_msg)
            seq += 1
        except Exception as e:
            print("Market err:", e)
            send_message("⚠️ 市场数据获取失败：" + str(e)[:80])

    # 3. Hot stock news (anchored by today's movers)
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
