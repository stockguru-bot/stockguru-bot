"""
StockGuru 财经快讯 — @not.a.stockguru
Stock news is ALWAYS available because:
  - ALWAYS_WATCH list is fetched regardless of market hours
  - Trending + Screener supplement the always-watch pool
  - Per-ticker RSS + yfinance news API as double-source
"""

import urllib.request, json, datetime, re, html, traceback
from email.utils import parsedate_to_datetime

try:
    import yfinance as yf
    YF_OK = True
except ImportError:
    YF_OK = False

BOT_TOKEN = "8238743813:AAEQqdLdDKz6OM2txjSE5FbI73cFdQc1P0w"
CHAT_ID   = "1237620041"
BASE_URL  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

NEWS_MAX_AGE_HOURS = 48  # wider window so pre/post-market hours always get results

US_IDX   = {"^GSPC":"S&P500","^IXIC":"Nasdaq"}
ASIA_IDX = {"^N225":"日经225","^KS11":"韩国KOSPI","^TWII":"台湾加权","^HSI":"恒生指数"}
ETF_POOL = {"SMH":"半导体","XLK":"科技","XLE":"能源","XLF":"金融","ARKK":"创新","GLD":"黄金","IWM":"小盘"}
MY_SYMS  = ["^KLSE","1155.KL","1023.KL","5681.KL","6012.KL","5347.KL"]
MY_NAME  = {"^KLSE":"KLCI","1155.KL":"Maybank","1023.KL":"CIMB",
            "5681.KL":"Tenaga","6012.KL":"Maxis","5347.KL":"PetChem"}

SECTOR = {
    "NVDA":"半导体/AI","AMD":"半导体","INTC":"半导体","MU":"存储芯片",
    "AVGO":"半导体","QCOM":"半导体","TSLA":"电动车","META":"社交/AI",
    "GOOGL":"科技/AI","GOOG":"科技/AI","MSFT":"科技/AI","AAPL":"科技/消费",
    "AMZN":"电商/云","PLTR":"大数据/AI","COIN":"加密金融","HOOD":"金融科技",
    "GS":"投行","JPM":"银行","BAC":"银行","MSTR":"比特币","WDC":"存储",
    "ASTS":"太空通讯","RKLB":"航天","MRVL":"半导体","ORCL":"云计算",
    "SNDK":"存储/AI","QURE":"生物科技","LUV":"航空","DAL":"航空","UAL":"航空",
    "XOM":"能源","CVX":"能源","MA":"支付","PYPL":"金融科技","NFLX":"流媒体",
    "DIS":"媒体","UBER":"出行","ARM":"半导体/AI","SMCI":"AI服务器","TSM":"半导体",
    "LRCX":"半导体设备","AMAT":"半导体设备","CRM":"企业软件","NOW":"企业软件",
    "PANW":"网络安全","CRWD":"网络安全","DDOG":"云监控","NET":"云安全",
    "SNOW":"云数据","MDB":"云数据库","GTLB":"开发工具","RIVN":"电动车",
    "NIO":"电动车","BABA":"中概/电商","JD":"中概/电商","PDD":"中概/电商",
}

# Always fetch news for these regardless of market hours / screener results
ALWAYS_WATCH = [
    "NVDA","AAPL","MSFT","TSLA","META","AMZN","GOOGL","AMD",
    "INTC","MU","COIN","PLTR","MSTR","ARM","SNDK","AVGO","QCOM",
    "SMCI","RKLB","ASTS","NFLX","JPM","GS","XOM",
]

CRYPTO_RSS = ["https://cointelegraph.com/rss","https://decrypt.co/feed"]
MY_RSS     = ["https://theedgemarkets.com/rss",
              "https://www.thestar.com.my/rss/business/business-news"]

# ── Telegram ──────────────────────────────────────────────────────────────────
def send_msg(text):
    data = json.dumps({"chat_id":CHAT_ID,"text":text,
                       "parse_mode":"Markdown","disable_web_page_preview":True}).encode()
    req  = urllib.request.Request(BASE_URL, data=data,
                                  headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        resp = json.loads(r.read().decode())
    if not resp.get("ok"):
        raise Exception(resp.get("description",""))
    print("✓ Sent:", text[:60])

# ── HTTP ──────────────────────────────────────────────────────────────────────
def fetch(url, timeout=12):
    req = urllib.request.Request(url, headers={
        "User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept":"application/rss+xml,application/xml,text/html,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

# ── RSS ───────────────────────────────────────────────────────────────────────
def _parse_dt(raw):
    m = re.search(r'<pubDate>(.*?)</pubDate>', raw, re.DOTALL)
    if not m: return None
    try:
        dt = parsedate_to_datetime(m.group(1).strip())
        return datetime.datetime(*dt.utctimetuple()[:6])
    except Exception: return None

def parse_rss(xml, max_items=20, label="", bonus=0):
    items = []; now = datetime.datetime.utcnow()
    for m in re.finditer(r'<item[^>]*>(.*?)</item>', xml, re.DOTALL):
        raw = m.group(1)
        pub = _parse_dt(raw)
        age = (now - pub).total_seconds()/3600 if pub else None
        if age and age > NEWS_MAX_AGE_HOURS: continue
        tm = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', raw, re.DOTALL)
        lm = re.search(r'<link>(?:<!\[CDATA\[)?(https?://\S+?)(?:\]\]>)?</link>', raw, re.DOTALL)
        if not lm:
            lm = re.search(r'<guid[^>]*>(?:<!\[CDATA\[)?(https?://\S+?)(?:\]\]>)?</guid>', raw, re.DOTALL)
        dm = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', raw, re.DOTALL)
        if not (tm and lm): continue
        title = html.unescape(re.sub(r'<[^>]+>','',tm.group(1))).strip()
        link  = lm.group(1).strip()
        desc  = html.unescape(re.sub(r'<[^>]+>','',(dm.group(1) if dm else '')))[:300].strip()
        if title and len(title) > 10:
            items.append({"title":title,"link":link,"desc":desc,
                          "age_hours":age,"source":label,"bonus":bonus,"sym":""})
        if len(items) >= max_items: break
    return items

def fetch_rss(url, max_items=20, label="", bonus=0):
    try:
        return parse_rss(fetch(url), max_items, label, bonus)
    except Exception as e:
        print(f"RSS [{label}]: {e}"); return []

def ticker_rss(sym, n=5):
    """Yahoo Finance per-ticker RSS — always about that specific stock."""
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
    items = fetch_rss(url, max_items=n, label=f"YF:{sym}", bonus=5)
    for i in items: i["sym"] = sym
    return items

# ── Market data ───────────────────────────────────────────────────────────────
def get_trending():
    try:
        url  = ("https://query1.finance.yahoo.com/v1/finance/trending/US"
                "?lang=en-US&region=US&count=15&corsDomain=finance.yahoo.com")
        data = json.loads(fetch(url))
        qs   = data.get("finance",{}).get("result",[{}])[0].get("quotes",[])
        syms = [q.get("symbol","") for q in qs if q.get("symbol")]
        print(f"Trending ({len(syms)}):", syms[:8]); return syms
    except Exception as e:
        print("Trending:", e); return []

def screener(sid, n=8):
    try:
        s = yf.Screener(); s.set_predefined_body(sid); s.set_count(n)
        return [{"sym":str(q.get("symbol","")),"pct":float(q.get("regularMarketChangePercent",0)),
                 "price":float(q.get("regularMarketPrice",0)),"vol":float(q.get("regularMarketVolume",0))}
                for q in s.response.get("quotes",[])[:n]]
    except Exception as e: print(f"Screener {sid}:", e); return []

def quotes(syms):
    out = {}
    if not syms or not YF_OK: return out
    try:
        raw = yf.download(syms, period="5d", interval="1d",
                          group_by="ticker", auto_adjust=True, progress=False, threads=True)
        for s in (syms if isinstance(syms, list) else [syms]):
            try:
                cl = raw[s]["Close"].dropna() if len(syms)>1 else raw["Close"].dropna()
                if len(cl)>=2: p,c=float(cl.iloc[-2]),float(cl.iloc[-1]); out[s]={"price":c,"pct":(c-p)/p*100}
                elif len(cl)==1: out[s]={"price":float(cl.iloc[-1]),"pct":0.0}
            except Exception: pass
    except Exception as e: print("quotes:", e)
    return out

def fmt_pct(v): return ("+" if v>=0 else "")+f"{v:.2f}%"
def arrow(v):   return "🟢" if v>=0 else "🔴"
def darrow(v):  return "▲" if v>=0 else "▼"
def fmt_vol(v):
    if v>=1e9: return f"{v/1e9:.1f}B"
    if v>=1e6: return f"{v/1e6:.1f}M"
    return f"{v/1e3:.0f}K"

def find_ticker(title):
    """Word-boundary ticker detection. Skip single-char tickers to avoid false positives."""
    t = title.upper()
    for sym in sorted(SECTOR.keys(), key=len, reverse=True):
        if len(sym) < 2: continue
        if re.search(rf'\b{re.escape(sym)}\b', t):
            return sym
    return ""

# ── Sentiment / topic ─────────────────────────────────────────────────────────
def sentiment(title):
    t = title.lower()
    neg = sum(1 for w in ["fall","drop","crash","slump","miss","plunge","slips","decline",
                           "warn","loss","concern","risk","lower","disappoint","bearish",
                           "fine","lawsuit","probe","ban","recall","halt","cut rating"] if w in t)
    pos = sum(1 for w in ["rise","rally","surge","soars","beat","upgrade","record","high",
                           "profit","deal","gain","strong","lifted","boost","jump","exceed",
                           "partnership","bullish","win","approval","all-time","historic"] if w in t)
    return "bull" if pos > neg else "bear" if neg > pos else "neutral"

def topic(title, sym=""):
    t = title.lower()
    if any(k in t for k in ["bitcoin","btc","ethereum","eth","crypto","blockchain","defi","solana","xrp"]):
        return "crypto"
    if any(k in t for k in ["federal reserve","fomc","rate cut","rate hike","monetary policy",
                              "interest rate","powell","warsh","fed chair","basis points"]):
        return "fed"
    if any(k in t for k in ["war","military","sanction","conflict","attack","invasion",
                              "missile","ceasefire","iran","airstrike","nuclear","troops","pentagon"]):
        return "geo"
    if sym or any(k in t for k in ["earnings","buyback","acquisition","ipo","merger",
                                    "target raised","upgrade","downgrade","revenue","profit",
                                    "partnership","price target","beats","misses","all-time high",
                                    "record high","government contract","chip act","fda",
                                    "stake","shares","quarterly","annual report"]):
        return "stock"
    if any(k in t for k in ["gdp","jobs","unemployment","cpi","pce","recession","tariff",
                              "oil price","inflation","trade","deficit","yields","treasury"]):
        return "macro"
    return "general"

# ── Stock news collection ─────────────────────────────────────────────────────
def collect_stock_news(trending, active, gainers, losers):
    """
    Build hot pool = trending + screener + ALWAYS_WATCH (fallback).
    Per-ticker RSS is fetched for EVERY stock in the pool.
    Always returns results regardless of market hours.
    """
    # Combine trending + all screener stocks (no pct filter)
    scr_syms = [i["sym"] for i in active+gainers+losers if i.get("sym")]
    pool     = list(dict.fromkeys(trending + scr_syms))

    # Always add ALWAYS_WATCH to ensure we always have major stocks
    for sym in ALWAYS_WATCH:
        if sym not in pool:
            pool.append(sym)

    # Limit pool: prioritise trending & screener, then always-watch
    pool = pool[:30]
    print(f"Stock pool ({len(pool)}): {pool[:12]}")

    rank_map   = {sym: i for i, sym in enumerate(pool)}
    stock_news = []
    seen       = set()

    # PRIMARY: per-ticker RSS for every stock in pool
    for sym in pool:
        for item in ticker_rss(sym, 5):
            key = item["title"][:55].lower()
            if key in seen or len(item["title"]) < 12: continue
            seen.add(key)
            item["sym"]   = sym
            item["_rank"] = rank_map.get(sym, 999)
            stock_news.append(item)

    print(f"After ticker RSS: {len(stock_news)} articles")

    # SECONDARY: yfinance Ticker.news API (catches news not in RSS)
    now = datetime.datetime.utcnow()
    if YF_OK:
        for sym in pool[:15]:
            try:
                raw = yf.Ticker(sym).news
                if callable(raw): raw = raw()
                for n in (raw or [])[:4]:
                    if not isinstance(n, dict): continue
                    pts = n.get("providerPublishTime", 0)
                    age = (now - datetime.datetime.utcfromtimestamp(pts)).total_seconds()/3600 if pts else None
                    if age and age > NEWS_MAX_AGE_HOURS: continue
                    c     = n.get("content") or {}
                    title = (c.get("title") or n.get("title","")).strip()
                    link  = ((c.get("canonicalUrl") or {}).get("url","") or n.get("link","")).strip()
                    desc  = (c.get("summary") or n.get("summary",""))[:300].strip()
                    key   = title[:55].lower()
                    if title and link and key not in seen and len(title)>12:
                        seen.add(key)
                        stock_news.append({"title":title,"link":link,"desc":desc,
                                           "age_hours":age,"source":"Yahoo Finance","bonus":4,
                                           "sym":sym,"_rank":rank_map.get(sym,999)})
            except Exception as e:
                print(f"yf.news ({sym}):", e)

    # TERTIARY: general RSS — only include if a known hot stock is mentioned
    for url, label, bonus in [
        ("https://feeds.reuters.com/reuters/businessNews", "Reuters", 3),
        ("https://www.cnbc.com/id/100003114/device/rss/rss.html", "CNBC", 3),
        ("https://www.cnbc.com/id/19854910/device/rss/rss.html",  "CNBC Tech", 3),
        ("https://finance.yahoo.com/rss/topstories",               "Yahoo Finance", 2),
    ]:
        for item in fetch_rss(url, max_items=25, label=label, bonus=bonus):
            key = item["title"][:55].lower()
            if key in seen: continue
            det = find_ticker(item["title"])
            if det and det in rank_map:
                seen.add(key)
                item["sym"]   = det
                item["_rank"] = rank_map.get(det, 800)
                stock_news.append(item)

    print(f"Total stock news: {len(stock_news)} articles")
    return stock_news, pool

def score_news(item, scr_syms):
    rank  = item.get("_rank", 999)
    age   = item.get("age_hours") or 18
    score = rank * 0.35 + min(age/8, 3) - item.get("bonus", 0) * 0.5
    if item.get("sym","") in scr_syms: score -= 1
    t = item["title"].lower()
    if any(k in t for k in ["all-time","record high","historic","surges","soars","jumps",
                              "government contract","chip act","fda approval","acquisition",
                              "merger","earnings beat","upgrade","record"]): score -= 1.5
    return score

def deduplicate(items, threshold=0.62):
    unique = []; seen_words = []
    for item in items:
        words = set(w for w in item["title"].lower().split() if len(w) > 3)
        is_dup = any(
            words and sw and len(words & sw) / min(len(words), len(sw)) >= threshold
            for sw in seen_words
        )
        if not is_dup:
            seen_words.append(words)
            unique.append(item)
    return unique

# ── Copy ──────────────────────────────────────────────────────────────────────
def make_full_copy(item, price_ctx=None):
    title = item["title"]; desc = item.get("desc","")
    sym   = item.get("sym","") or find_ticker(title)
    t     = title.lower()
    sent  = sentiment(title); cat = topic(title, sym)
    sect  = SECTOR.get(sym,""); sect_s = f"（{sect}板块）" if sect else ""
    desc_s= (desc[:200]+"…") if desc else ""
    src   = item.get("source",""); src_s = f"  |  来源：{src}" if src else ""
    age   = item.get("age_hours")
    age_s = ("  🕐 刚刚" if age and age<1 else
             f"  🕐 {age:.0f}小时前" if age and age<8 else "  🕐 今日" if age else "")
    px_s  = ""
    if price_ctx:
        p,pct,ps = price_ctx.get("price",0),price_ctx.get("pct",0),price_ctx.get("sym",sym)
        px_s = f"\n💹 ${ps} 今日 {'▲' if pct>=0 else '▼'} ${p:.2f}（{fmt_pct(pct)}）"
    sym_tag = f"${sym} " if sym else ""

    if cat == "geo":
        em = "🚨" if sent=="bear" else "🌐"
        an = ("地缘冲突冲击风险情绪，能源供应受威胁时油价急升，压制降息空间。\n"
              "📊 🛢️ 能源↑  🥇 黄金避险↑  📉 科技成长承压\n"
              "⚠️ 减持高风险资产，关注能源(XLE)、黄金(GLD)对冲。" if sent=="bear" else
              "局势缓和提振风险偏好，周期股及新兴市场受益。\n"
              "📊 ✅ 科技/周期  ✅ 新兴市场资金回流")
        tags = "#地缘政治 #风险 #美股 #财经快讯"
    elif cat == "fed":
        em = "🏛️"
        an = ("联储偏鹰，科技/成长估值承压，美债收益率上行。\n"
              "📊 减持高估值  |  关注金融(XLF)防御" if any(k in t for k in ["hike","hawkish"]) else
              "降息预期重燃，科技成长迎修复机会。\n"
              "📊 ✅ 科技 ✅ 小盘成长(IWM) ✅ 新兴市场" if any(k in t for k in ["cut","dovish","pivot"]) else
              "联储措辞是全球资产定价核心变量。追踪通胀路径+非农数据。\n"
              "策略：中性仓位，等待更明确信号。")
        tags = "#美联储 #FOMC #利率 #美股 #财经快讯"
    elif cat == "crypto":
        em = "🔴" if sent=="bear" else "🚀"
        an = ("链上资金外流，恐慌情绪升温。\n"
              "📊 ⚠️ BTC跌破支撑 → 下行空间打开  ✅ 恐慌指数<20 往往是中长线布局参考" if sent=="bear" else
              "链上资金回流，机构入场信号出现。\n"
              "📊 ✅ 成交量放大  ✅ 稳定币净流入交易所")
        tags = "#Bitcoin #BTC #ETH #加密 #财经快讯"
    elif cat == "macro":
        em = "⚠️" if sent=="bear" else "🌐"
        an = ("经济数据走弱，避险资产受益。\n"
              "📊 🥇 黄金(GLD)  📉 美债(TLT)  💵 美元" if sent=="bear" else
              "数据超预期，风险偏好回升，周期与新兴市场受益。\n"
              "📊 ✅ 科技/半导体  ✅ 能源/材料  ✅ 马股")
        tags = "#宏观 #全球市场 #美股 #财经快讯"
    else:  # stock
        if sent == "bull":
            em = "📈"
            gov_note = ("⚠️ 政府合同/法规支持 → 利好确定性高，但落地执行需持续跟踪。" if
                        any(k in t for k in ["government","act","contract","law","subsidy","grant"]) else
                        "⚠️ 消息冲高当日易回吐，建议分批布局，切忌满仓追单。")
            an = (f"重大催化剂落地，市场对公司前景信心回升。\n"
                  f"📊 ✅ 成交量放大（>20日均量）→ 突破信号可信度高\n{gov_note}")
        elif sent == "bear":
            em = "📉"
            an  = ("负面催化剂打击市场信心。\n"
                   "📊 ⚠️ 持仓者：检查止损位，避免情绪化持有\n"
                   "👀 观望者：等待关键支撑（200日线）企稳缩量后布局")
        else:
            em = "⚡"
            an  = ("重要个股动态，板块情绪先行指标。\n"
                   "📊 关注：同板块相对强弱 | 期权隐含波动率 | 大单净流向")
        tags = "#美股 #热门股 #WallStreet #财经快讯"

    ig = (f"{em} {sym_tag}重磅要闻{sect_s}！{age_s}{src_s}\n\n"
          f"📌 {title}\n{desc_s}{px_s}\n\n"
          f"【解读】\n{an}\n\n{tags}")
    th = f"{em} {sym_tag}{title[:75]}\n\n{an.split(chr(10))[0]}"
    return ig, th

def make_compact_copy(item, price_ctx=None):
    title = item["title"]
    sym   = item.get("sym","") or find_ticker(title)
    sent  = sentiment(title); cat = topic(title, sym)
    sect  = SECTOR.get(sym,"")
    age   = item.get("age_hours"); src = item.get("source","")
    em    = ("📈" if sent=="bull" else "📉" if sent=="bear" else "⚡")
    age_s = (f"{age:.0f}h前" if age and age<24 else "今日" if age else "")
    px_s  = ""
    if price_ctx:
        p,pct,ps = price_ctx.get("price",0),price_ctx.get("pct",0),price_ctx.get("sym",sym)
        px_s = f"\n💹 ${ps} {'▲' if pct>=0 else '▼'} ${p:.2f}（{fmt_pct(pct)}）"
    note = {"stock":{"bull":"利好催化，成交量放大是突破关键确认。分批布局，避免追高。",
                      "bear":"利空压制，等候关键支撑企稳再行布局。",
                      "neutral":"关注板块情绪联动和机构资金流向。"},
            "geo":  {"bear":"地缘风险升温，关注能源/黄金避险配置。","bull":"地缘缓和，风险偏好回升。","neutral":"地缘局势影响全球风险情绪，持续追踪。"},
            "fed":  {"bull":"降息预期增强，科技成长迎机会。","bear":"联储偏鹰，高估值承压。","neutral":"联储表态影响降息路径，追踪通胀数据。"},
            "crypto":{"bear":"链上资金外流，守住关键支撑。","bull":"链上资金回流，成交量确认信号。","neutral":"加密情绪跟随宏观流动性。"},
            }.get(cat,{}).get(sent,"宏观事件影响市场风险偏好，结合联储政策综合判断。")
    header = f"{em} {'$'+sym+'  ' if sym else ''}{sect+'  ' if sect else ''}{src}  {age_s}"
    ig = f"{header}\n📌 {title}{px_s}\n{note}\n#美股 #热门股 #财经快讯"
    th = f"{em} {title[:75]}\n{note}"
    return ig, th

# ── Market overview ───────────────────────────────────────────────────────────
def build_crypto(seq):
    data = json.loads(fetch(
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"))
    btc=data.get("bitcoin",{}); eth=data.get("ethereum",{})
    btc_p=btc.get("usd",0); btc_c=float(btc.get("usd_24h_change",0))
    eth_p=eth.get("usd",0); eth_c=float(eth.get("usd_24h_change",0))
    pl=(f"BTC {arrow(btc_c)} ${btc_p:,.0f} ({fmt_pct(btc_c)})  "
        f"ETH {arrow(eth_c)} ${eth_p:,.0f} ({fmt_pct(eth_c)})")
    # Crypto news: CoinTelegraph first (pure crypto), then Decrypt
    news = []
    for src in CRYPTO_RSS:
        batch = fetch_rss(src, max_items=5, label=src.split("/")[2], bonus=3)
        # Filter to actual crypto news
        news = [n for n in batch if any(k in n["title"].lower()
                for k in ["bitcoin","btc","eth","ethereum","crypto","defi","solana","xrp","blockchain"])]
        if news: break
    # Fallback: BTC-USD ticker RSS filtered
    if not news:
        for item in ticker_rss("BTC-USD", 5):
            if any(k in item["title"].lower() for k in ["bitcoin","btc","eth","crypto","coin"]):
                news.append(item); break
    item = news[0] if news else {"title":"BTC今日行情动态","link":"https://cointelegraph.com",
                                  "desc":"","age_hours":None,"source":"CoinTelegraph","sym":"BTC"}
    ig,th = make_full_copy(item, {"sym":"BTC","price":btc_p,"pct":btc_c})
    return (f"⚡ *快讯 #{seq}* 🪙 加密\n"
            f"🔗 [{item['title'][:70]}]({item['link']})\n\n"
            f"📸 *Instagram：*\n🪙 *行情：* {pl}\n\n{ig}\n\n"
            f"🧵 *Threads：*\n{pl}\n\n{th}")

def build_market(seq):
    lines=[]; sp_pct=0.0
    if YF_OK:
        iq=quotes(list(US_IDX.keys()))
        parts=[]
        for s,n in US_IDX.items():
            if s in iq:
                p=iq[s]["pct"]
                if s=="^GSPC": sp_pct=p
                parts.append(f"{n} {darrow(p)} {fmt_pct(p)}")
        if parts: lines.append("📊 *美股大盘：* "+"  |  ".join(parts))

    active  = screener("most_actives",6) if YF_OK else []
    gainers = screener("day_gainers", 6) if YF_OK else []
    losers  = screener("day_losers",  6) if YF_OK else []

    def row(i, show_vol=False):
        v=f"  vol:{fmt_vol(i['vol'])}" if show_vol and i['vol']>0 else ""
        return f"{arrow(i['pct'])} ${i['sym']}  ${i['price']:.2f}  ({fmt_pct(i['pct'])}){v}"

    if active:  lines.append("\n🔥 *成交量五大：*\n"+"\n".join(row(i,True) for i in active[:5]))
    if gainers: lines.append("\n🚀 *涨幅五大：*\n"  +"\n".join(row(i)      for i in gainers[:5]))
    if losers:  lines.append("\n💥 *跌幅五大：*\n"  +"\n".join(row(i)      for i in losers[:5]))

    if YF_OK:
        eq=quotes(list(ETF_POOL.keys()))
        etfs=sorted([(s,eq[s],ETF_POOL[s]) for s in ETF_POOL if s in eq],
                     key=lambda x:x[1]["pct"],reverse=True)[:5]
        if etfs:
            lines.append("\n📂 *板块ETF：*\n"+"\n".join(
                f"{arrow(q['pct'])} {name}({sym}) {fmt_pct(q['pct'])}" for sym,q,name in etfs))

    if YF_OK:
        aq=quotes(list(ASIA_IDX.keys()))
        al=[f"{arrow(aq[s]['pct'])} {n}  {fmt_pct(aq[s]['pct'])}"
            for s,n in ASIA_IDX.items() if s in aq]
        if al: lines.append("\n🌏 *亚太指数：*\n"+"\n".join(al))

    if YF_OK:
        mq=quotes(MY_SYMS)
        kl=mq.get("^KLSE",{}); kl_p=kl.get("pct",0); kl_px=kl.get("price",0)
        my=sorted([(s,mq[s]) for s in MY_SYMS if s in mq and s!="^KLSE"],
                   key=lambda x:abs(x[1]["pct"]),reverse=True)[:3]
        ml=[f"{arrow(kl_p)} KLCI {kl_px:,.2f} ({fmt_pct(kl_p)})"]
        ml+=[f"{arrow(q['pct'])} {MY_NAME.get(s,s)} RM{q['price']:.2f} ({fmt_pct(q['pct'])})"
             for s,q in my]
        lines.append("\n🇲🇾 *马股：*\n"+"\n".join(ml))

    body="\n".join(lines)
    tail=("整体风险偏好回升，热门股值得追踪。合理控制仓位。" if sp_pct>=0.5 else
          "市场整体承压，关注黄金美债防御。" if sp_pct<=-0.5 else
          "多空胶着，关注热门个股结构性机会。")
    ig=body.replace("*","")+"\n\n"+tail+"\n\n#美股 #涨幅榜 #跌幅榜 #成交量 #亚太指数 #马股 #板块ETF #财经快讯"
    th="\n".join(l.replace("*","").strip() for l in lines[:4] if l.strip())+"\n\n"+tail[:60]+"…"
    return (f"⚡ *快讯 #{seq}* 📊 市场速览\n\n"
            f"📸 *Instagram：*\n{ig}\n\n"
            f"🧵 *Threads：*\n{th}"), active, gainers, losers

def build_stock_news_msgs(seq_start, active, gainers, losers):
    """
    Returns list of (seq, message_text).
    Sends 10 stock news items across 3 messages.
    ALWAYS returns results because ALWAYS_WATCH is used as fallback.
    """
    trending  = get_trending()
    scr_syms  = [i["sym"] for i in active+gainers+losers if i.get("sym")]

    all_news, pool = collect_stock_news(trending, active, gainers, losers)

    if not all_news:
        return [(seq_start, "⚠️ 热门个股要闻：未找到最新新闻，请稍后再试")]

    # Score + sort + deduplicate
    for item in all_news:
        item["_score"] = score_news(item, scr_syms)
    all_news.sort(key=lambda x: x["_score"])
    deduped = deduplicate(all_news, threshold=0.60)
    top10   = deduped[:10]
    print(f"Top {len(top10)} news items selected")

    # Price quotes
    need_q = list(set(i.get("sym","") for i in top10 if i.get("sym")))
    pq     = quotes(need_q) if YF_OK and need_q else {}

    def ctx(sym): return {"sym":sym,**pq[sym]} if sym and sym in pq else None

    CAT_LABEL = {"geo":"🚨 地缘","fed":"🏛️ 美联储","stock":"📊 个股",
                 "macro":"🌐 宏观","crypto":"🪙 加密","general":"📰 财经"}

    def block(item, use_full=True):
        sym = item.get("sym","") or find_ticker(item["title"])
        cat = topic(item["title"], sym)
        lbl = CAT_LABEL.get(cat,"📰 财经")
        src = item.get("source","")
        ig,th = make_full_copy(item, ctx(sym)) if use_full else make_compact_copy(item, ctx(sym))
        return (f"━━ {lbl}  {'$'+sym if sym else ''}  {src} ━━\n"
                f"🔗 [{item['title'][:72]}]({item['link']})\n\n"
                f"📸 *Instagram：*\n{ig}\n\n"
                f"🧵 *Threads：*\n{th}")

    msgs = []; seq = seq_start

    # Message A: items 1-4, full copy
    if top10[:4]:
        body = "\n\n".join(block(i, True) for i in top10[:4])
        msgs.append((seq, f"⚡ *快讯 #{seq}* 🔥 热门个股要闻（1-4）\n\n{body}"))
        seq += 1

    # Message B: items 5-7, full copy
    if top10[4:7]:
        body = "\n\n".join(block(i, True) for i in top10[4:7])
        msgs.append((seq, f"⚡ *快讯 #{seq}* 🔥 热门个股要闻（5-7）\n\n{body}"))
        seq += 1

    # Message C: items 8-10, compact copy
    if top10[7:]:
        body = "\n\n".join(block(i, False) for i in top10[7:])
        msgs.append((seq, f"⚡ *快讯 #{seq}* 📰 更多市场要闻（8-{len(top10)}）\n\n{body}"))
        seq += 1

    return msgs

def build_my_news(seq):
    news=[]
    for sym in ["^KLSE","1155.KL","1023.KL"]:
        news.extend(ticker_rss(sym, 3))
    if not news:
        for src in MY_RSS:
            batch=fetch_rss(src,max_items=8,label="EdgeMarkets")
            rel=[n for n in batch if any(k in n["title"].lower()
                 for k in ["klci","bursa","malaysia","ringgit","maybank","cimb","tenaga"])]
            if rel: news=rel; break
    if not news: return None
    item=news[0]
    kq=quotes(["^KLSE"]).get("^KLSE") if YF_OK else None
    ctx={"sym":"KLCI","price":kq["price"],"pct":kq["pct"]} if kq else None
    ig,th=make_full_copy(item,ctx); ig="🇲🇾 "+ig
    return (f"⚡ *快讯 #{seq}* 🇲🇾 马股要闻\n"
            f"🔗 [{item['title'][:70]}]({item['link']})\n\n"
            f"📸 *Instagram：*\n{ig}\n\n"
            f"🧵 *Threads：*\n{th}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    now_cst = datetime.datetime.utcnow()+datetime.timedelta(hours=8)
    h = now_cst.hour
    emoji,label = (("🕛","午间快讯") if h<14 else ("🕒","下午快讯")
                   if h<17 else ("🕕","晚间快讯") if h<20 else ("🌙","夜盘快讯"))
    send_msg(f"{emoji} *{label} | @not.a.stockguru*\n"
             f"📅 {now_cst.strftime('%Y年%m月%d日 %H:%M')} (CST)\n━━━━━━━━━━━━━━━━━━━━")
    seq=1

    try: send_msg(build_crypto(seq)); seq+=1
    except Exception as e:
        print("Crypto:",e); send_msg(f"⚠️ 加密快讯失败：{str(e)[:80]}")

    active_=gainers_=losers_=[]
    if YF_OK:
        try:
            mkt,active_,gainers_,losers_=build_market(seq)
            send_msg(mkt); seq+=1
        except Exception as e:
            print("Market:",e); send_msg(f"⚠️ 市场数据失败：{str(e)[:80]}")

    try:
        news_msgs = build_stock_news_msgs(seq, active_, gainers_, losers_)
        for s, msg in news_msgs:
            send_msg(msg); seq+=1
    except Exception as e:
        tb = traceback.format_exc()
        print("Stock news error:\n", tb)
        send_msg(f"⚠️ 热门要闻失败：{str(e)[:120]}\n\n`{tb[-200:]}`")

    try:
        msg=build_my_news(seq)
        if msg: send_msg(msg); seq+=1
    except Exception as e: print("MY news:",e)

    send_msg("📲 关注 *@not.a.stockguru* 获取更多实时财经快讯 🔔")
    print(f"Done. Messages sent: {seq-1}")

if __name__=="__main__":
    main()
