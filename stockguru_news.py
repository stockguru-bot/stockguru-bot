"""
StockGuru 财经快讯 — @not.a.stockguru
Pipeline:
  1. Collect 50-80 articles from 6 sources (Yahoo Finance, Reuters, CNBC, MarketWatch, Finviz)
  2. Score by: trending ticker match + screener match + source quality + freshness
  3. Deduplicate (content similarity)
  4. Show top 4 articles per broadcast
"""

import urllib.request, json, datetime, re, html
from email.utils import parsedate_to_datetime

try:
    import yfinance as yf
    YF_OK = True
except ImportError:
    YF_OK = False

BOT_TOKEN = "8238743813:AAEQqdLdDKz6OM2txjSE5FbI73cFdQc1P0w"
CHAT_ID   = "1237620041"
BASE_URL  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

NEWS_MAX_AGE_HOURS = 24

US_IDX   = {"^GSPC":"S&P500","^IXIC":"Nasdaq"}
ASIA_IDX = {"^N225":"日经225","^KS11":"韩国KOSPI","^TWII":"台湾加权","^HSI":"恒生指数"}
ETF_POOL = {"SMH":"半导体","XLK":"科技","XLE":"能源","XLF":"金融","ARKK":"创新","GLD":"黄金","IWM":"小盘"}
MY_SYMS  = ["^KLSE","1155.KL","1023.KL","5681.KL","6012.KL","5347.KL"]
MY_NAME  = {"^KLSE":"KLCI","1155.KL":"Maybank","1023.KL":"CIMB",
            "5681.KL":"Tenaga","6012.KL":"Maxis","5347.KL":"PetChem"}
SECTOR   = {
    "NVDA":"半导体/AI","AMD":"半导体","INTC":"半导体","MU":"存储芯片",
    "AVGO":"半导体","QCOM":"半导体","TSLA":"电动车","META":"社交/AI",
    "GOOGL":"科技/AI","GOOG":"科技/AI","MSFT":"科技/AI","AAPL":"科技/消费",
    "AMZN":"电商/云","PLTR":"大数据/AI","COIN":"加密金融","HOOD":"金融科技",
    "GS":"投行","JPM":"银行","BAC":"银行","WFC":"银行","MSTR":"比特币",
    "ASTS":"太空通讯","RKLB":"航天","MRVL":"半导体","ORCL":"云计算",
    "SNDK":"存储/AI","QURE":"生物科技","LUV":"航空","DAL":"航空","UAL":"航空",
    "XOM":"能源","CVX":"能源","V":"支付","MA":"支付","PYPL":"金融科技",
    "NFLX":"流媒体","DIS":"媒体","SPOT":"音乐流媒体","UBER":"出行",
    "ARM":"半导体/AI","SMCI":"AI服务器","TSM":"半导体",
}
CRYPTO_RSS = ["https://cointelegraph.com/rss"]
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
        "Accept":"application/rss+xml,application/xml,text/html,*/*",
        "Accept-Language":"en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

# ── RSS parser ────────────────────────────────────────────────────────────────
def _parse_dt(raw):
    m = re.search(r'<pubDate>(.*?)</pubDate>', raw, re.DOTALL)
    if not m: return None
    try:
        dt = parsedate_to_datetime(m.group(1).strip())
        return datetime.datetime(*dt.utctimetuple()[:6])
    except Exception: return None

def parse_rss(xml, max_items=30, label="", bonus=0):
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
        desc  = html.unescape(re.sub(r'<[^>]+>','',(dm.group(1) if dm else '')))[:250].strip()
        if title and len(title) > 10:
            items.append({"title":title,"link":link,"desc":desc,
                          "age_hours":age,"source":label,"score_bonus":bonus})
        if len(items) >= max_items: break
    return items

def fetch_rss(url, max_items=30, label="", bonus=0):
    try:
        return parse_rss(fetch(url), max_items, label, bonus)
    except Exception as e:
        print(f"RSS fail [{label}]: {e}"); return []

# ── Finviz (server-rendered HTML, aggregates 50+ sources) ─────────────────────
def fetch_finviz():
    try:
        content = fetch("https://finviz.com/news.ashx")
        items = []; now = datetime.datetime.utcnow()
        for m in re.finditer(
            r'<td[^>]*news_date[^>]*>(.*?)</td>\s*<td[^>]*><a[^>]+href="(https?://[^"]+)"[^>]*>([^<]+)</a>',
            content, re.DOTALL):
            raw_time = m.group(1).strip()
            link  = m.group(2).strip()
            title = html.unescape(m.group(3)).strip()
            if not title or len(title) < 10: continue
            age = None
            tm = re.match(r'(\d+):(\d+)(AM|PM)', raw_time.upper().replace(" ",""))
            if tm:
                h,mi,ap = int(tm.group(1)),int(tm.group(2)),tm.group(3)
                if ap=="PM" and h!=12: h+=12
                if ap=="AM" and h==12: h=0
                art_dt = now.replace(hour=h, minute=mi, second=0, microsecond=0)
                if art_dt > now: art_dt -= datetime.timedelta(days=1)
                age = (now - art_dt).total_seconds()/3600
                if age > NEWS_MAX_AGE_HOURS: continue
            items.append({"title":title,"link":link,"desc":"",
                          "age_hours":age,"source":"Finviz","score_bonus":2})
            if len(items) >= 25: break
        print(f"Finviz: {len(items)} articles")
        return items
    except Exception as e:
        print("Finviz fail:", e); return []

# ── Yahoo Finance Trending Tickers ────────────────────────────────────────────
def get_trending():
    try:
        url  = ("https://query1.finance.yahoo.com/v1/finance/trending/US"
                "?lang=en-US&region=US&count=15&corsDomain=finance.yahoo.com")
        data = json.loads(fetch(url))
        qs   = data.get("finance",{}).get("result",[{}])[0].get("quotes",[])
        syms = [q.get("symbol","") for q in qs if q.get("symbol")]
        print("Trending:", syms[:8]); return syms
    except Exception as e:
        print("Trending API:", e); return []

# ── Screener ──────────────────────────────────────────────────────────────────
def screener(sid, n=5):
    try:
        s = yf.Screener(); s.set_predefined_body(sid); s.set_count(n)
        return [{"sym":str(q.get("symbol","")),"pct":float(q.get("regularMarketChangePercent",0)),
                 "price":float(q.get("regularMarketPrice",0)),"vol":float(q.get("regularMarketVolume",0))}
                for q in s.response.get("quotes",[])[:n]]
    except Exception as e: print(f"Screener {sid}:", e); return []

# ── Quote helper ──────────────────────────────────────────────────────────────
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
    except Exception as e: print("yf.download:", e)
    return out

def fmt_pct(v): return ("+" if v>=0 else "")+f"{v:.2f}%"
def arrow(v):   return "🟢" if v>=0 else "🔴"
def darrow(v):  return "▲" if v>=0 else "▼"
def fmt_vol(v):
    if v>=1e9: return f"{v/1e9:.1f}B"
    if v>=1e6: return f"{v/1e6:.1f}M"
    return f"{v/1e3:.0f}K"

# ── Generic article detector ──────────────────────────────────────────────────
GENERIC_PATTERNS = [
    r"^\d+ stocks? to watch", r"^top \d+ stocks?", r"^stocks? (rising|falling|trending)",
    r"^(what|which) stocks?", r"^morning brief", r"^market wrap", r"^pre-?market",
    r"^week ahead", r"^today'?s (top|market)", r"^biggest movers",
]
def is_generic(title):
    t = title.lower()
    return any(re.search(p, t) for p in GENERIC_PATTERNS)

# ── NEWS PIPELINE ─────────────────────────────────────────────────────────────
def collect_all_news(trending_syms, screener_syms):
    """Collect 50-80 articles from 6 sources. No keyword topic filter."""
    all_items = []; seen_titles = set()

    def add(batch):
        for item in batch:
            key = item["title"][:50].lower()
            if key in seen_titles or len(item.get("title","")) < 12: continue
            seen_titles.add(key)
            all_items.append(item)

    # 1. Yahoo Finance top stories — most curated popular news
    add(fetch_rss("https://finance.yahoo.com/rss/topstories",
                  max_items=30, label="Yahoo Finance", bonus=2))

    # 2. Reuters Business — high quality wire service
    add(fetch_rss("https://feeds.reuters.com/reuters/businessNews",
                  max_items=20, label="Reuters", bonus=3))

    # 3. CNBC Markets + Tech
    add(fetch_rss("https://www.cnbc.com/id/100003114/device/rss/rss.html",
                  max_items=15, label="CNBC", bonus=3))
    add(fetch_rss("https://www.cnbc.com/id/19854910/device/rss/rss.html",
                  max_items=12, label="CNBC Tech", bonus=3))

    # 4. Finviz — aggregates 50+ news sources, server-rendered
    add(fetch_finviz())

    # 5. MarketWatch
    add(fetch_rss("https://feeds.marketwatch.com/marketwatch/topstories/",
                  max_items=15, label="MarketWatch", bonus=2))

    # 6. Per-ticker RSS — only for well-known stocks in SECTOR dict
    known_trending = [s for s in trending_syms if s in SECTOR][:6]
    for sym in known_trending:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
        batch = fetch_rss(url, max_items=4, label=f"YF:{sym}", bonus=4)
        for b in batch: b["sym"] = sym
        add(batch)

    print(f"Collected {len(all_items)} unique articles")
    return all_items

def score_article(item, trending_syms, screener_syms):
    """Score purely on market signals — no topic keywords. Lower = shown first."""
    title = item["title"].lower()
    age   = item.get("age_hours") or 12
    score = 10 - item.get("score_bonus", 0)   # base offset by source quality

    # Boost: matches a currently trending ticker
    if any(s.lower() in title for s in trending_syms if s):
        score -= 3

    # Boost: matches a screener hot mover
    if any(s.lower() in title for s in screener_syms if s):
        score -= 2

    # Boost: mentions a major known stock (SECTOR dict)
    if any(name.lower().split("/")[0] in title or sym.lower() in title
           for sym, name in SECTOR.items()):
        score -= 1

    # Freshness bonus
    score += min(age / 8, 2.5)

    # Penalise generic roundup articles
    if is_generic(item["title"]): score += 3

    return score

def deduplicate(items):
    """Remove near-duplicate articles (same story, different outlet)."""
    unique = []; seen_words = []
    for item in items:
        words = set(w for w in item["title"].lower().split() if len(w) > 3)
        is_dup = False
        for sw in seen_words:
            if words and sw:
                overlap = len(words & sw) / min(len(words), len(sw))
                if overlap >= 0.6: is_dup = True; break
        if not is_dup:
            seen_words.append(words)
            unique.append(item)
    return unique

# ── Sentiment / topic (for copy template only) ────────────────────────────────
def sentiment(title):
    t = title.lower()
    neg = sum(1 for w in ["fall","drop","crash","slump","miss","plunge","slips","decline",
                           "warn","loss","concern","risk","lower","disappoint","bearish",
                           "fine","lawsuit","probe","ban","halt"] if w in t)
    pos = sum(1 for w in ["rise","rally","surge","soars","beat","upgrade","record",
                           "profit","deal","gain","high","strong","lifted","boost",
                           "jump","exceed","partnership","bullish","win","approval"] if w in t)
    return "bull" if pos > neg else "bear" if neg > pos else "neutral"

def topic(title, sym=""):
    t = title.lower()
    if any(k in t for k in ["bitcoin","btc","ethereum","eth","crypto","blockchain","defi"]):
        return "crypto"
    if any(k in t for k in ["federal reserve","fomc","rate cut","rate hike","monetary policy",
                              "interest rate","powell","warsh","fed chair","basis points"]):
        return "fed"
    if any(k in t for k in ["war","military","sanction","conflict","attack","invasion",
                              "missile","ceasefire","iran","airstrike","nuclear","troops","pentagon"]):
        return "geo"
    if sym or any(k in t for k in ["earnings","buyback","acquisition","ipo","merger",
                                    "target raised","upgrade","downgrade","revenue","profit",
                                    "partnership","price target","beats","misses"]):
        return "stock"
    if any(k in t for k in ["gdp","jobs","unemployment","cpi","pce","recession","tariff",
                              "oil price","gold","inflation","trade","deficit","yields"]):
        return "macro"
    return "general"

# ── Chinese copy generator ────────────────────────────────────────────────────
def make_copy(item, price_ctx=None):
    title = item["title"]; desc = item.get("desc","")
    sym   = item.get("sym",""); t = title.lower()
    sent  = sentiment(title); cat = topic(title, sym)
    sect  = SECTOR.get(sym,"")
    sect_s= f"（{sect}板块）" if sect else ""
    desc_s= (desc[:160]+"…") if desc else ""
    src   = item.get("source","")
    src_s = f"  |  来源：{src}" if src else ""
    age   = item.get("age_hours")
    age_s = ("  🕐 刚刚" if age and age<1 else
             f"  🕐 {age:.0f}小时前" if age and age<6 else
             "  🕐 今日" if age and age<24 else "")
    px_s  = ""
    if price_ctx:
        p,pct,ps = price_ctx.get("price",0),price_ctx.get("pct",0),price_ctx.get("sym",sym)
        px_s = f"\n💹 ${ps} 今日 {'▲' if pct>=0 else '▼'} ${p:.2f}（{fmt_pct(pct)}）"

    if cat == "geo":
        if sent == "bear":
            ig=(f"🚨 地缘政治风险警报！{age_s}{src_s}\n\n📌 {title}\n{desc_s}{px_s}\n\n"
                "【市场影响】\n地缘冲突直接冲击全球风险情绪，能源供应链受威胁时"
                "油价急升，传导至通胀预期，压制降息空间。\n\n"
                "📊 市场联动：\n🛢️ 能源/油价↑  🥇 黄金避险需求↑  📉 科技成长承压\n"
                "⚠️ 减持高风险资产，关注能源(XLE)、黄金(GLD)对冲机会。\n\n"
                "#地缘政治 #风险 #避险 #美股 #财经快讯")
            th=(f"🚨 {title[:65]}\n\n地缘风险升温！油价↑黄金↑科技承压。减持激进仓位，能源黄金对冲。")
        else:
            ig=(f"🌐 地缘局势最新进展{age_s}{src_s}\n\n📌 {title}\n{desc_s}{px_s}\n\n"
                "【市场影响】\n局势缓和提振风险偏好，周期股及新兴市场受益，"
                "能源供应担忧减少有助通胀预期回落。\n\n"
                "📊 受益方向：科技/周期板块 ✅  新兴市场资金回流 ✅\n\n"
                "#地缘政治 #全球市场 #风险偏好 #美股 #财经快讯")
            th=(f"🌐 {title[:65]}\n\n地缘缓和！风险偏好回升，科技周期受益，新兴市场资金回流机会。")
    elif cat == "fed":
        if any(k in t for k in ["hike","raise","hawkish","higher for longer"]):
            ig=(f"🏛️ 美联储鹰派信号！{age_s}{src_s}\n\n📌 {title}\n{desc_s}{px_s}\n\n"
                "【政策解读】\n联储偏鹰，科技/成长股估值承压，美债收益率上行，"
                "新兴市场面临资金外流压力。\n\n"
                "📊 应对策略：减持高估值仓位  |  关注金融(XLF)防御配置\n\n"
                "#美联储 #加息 #FOMC #利率 #美股 #财经快讯")
            th=(f"🏛️ 美联储鹰派！{title[:55]}\n\n降息预期降温，科技承压，金融防御相对占优。")
        elif any(k in t for k in ["cut","ease","pause","dovish","pivot"]):
            ig=(f"🏛️ 美联储鸽派！降息预期重燃！{age_s}{src_s}\n\n📌 {title}\n{desc_s}{px_s}\n\n"
                "【政策解读】\n利率下行预期推升风险偏好，科技成长股估值修复，"
                "小盘股(IWM)及新兴市场迎阶段性机会。\n\n"
                "📊 关注方向：科技 | 生物科技 | 小盘成长\n"
                "⚠️ 关键验证：CPI/PCE需持续回落，单次表态不等于政策转向。\n\n"
                "#美联储 #降息 #FOMC #利率 #美股 #风险偏好 #财经快讯")
            th=(f"🏛️ 美联储鸽派！{title[:55]}\n\n降息预期升温，科技小盘迎机会。追踪通胀数据验证。🚀")
        else:
            ig=(f"🏛️ 美联储动态{age_s}{src_s}\n\n📌 {title}\n{desc_s}{px_s}\n\n"
                "【政策解读】\n联储措辞变化是全球资产定价核心变量。"
                "重点追踪：通胀路径、非农数据、官员措辞变化。\n\n"
                "策略：中性仓位，等待更明确信号。\n\n"
                "#美联储 #FOMC #货币政策 #利率 #美股 #宏观 #财经快讯")
            th=(f"🏛️ {title[:60]}\n\n联储政策牵动全市场。追踪通胀+就业数据，中性仓位等信号。📊")
    elif cat == "stock":
        sym_tag = f"${sym} " if sym else ""
        if sent == "bull":
            ig=(f"📈 {sym_tag}重磅利好{sect_s}！{age_s}{src_s}\n\n📌 {title}\n{desc_s}{px_s}\n\n"
                "【交易解读】\n"
                +("分析师上调目标价/评级，机构信心提升，短期强势支撑。"
                  if any(k in t for k in ["target","raised","upgraded","lift"]) else
                  "重大合作/业绩催化剂落地，市场对成长前景信心回升。")
                +"\n\n📊 交易策略：\n"
                "✅ 成交量放大（>20日均量）→ 突破信号可信度高\n"
                "✅ 消息当日冲高 → 次日易回吐，分批布局优于追高\n"
                "⚠️ 设好止损，避免满仓追单\n\n#美股 #热门股 #WallStreet #财经快讯")
            th=(f"📈 {sym_tag}{title[:65]}\n\n利好催化！成交量是突破有效性的确认关键。分批布局，避免追高。")
        elif sent == "bear":
            ig=(f"📉 {sym_tag}重磅利空{sect_s}！{age_s}{src_s}\n\n📌 {title}\n{desc_s}{px_s}\n\n"
                "【风险解读】\n"
                +("评级下调或目标价下修，机构分歧扩大，短期股价承压。"
                  if any(k in t for k in ["downgrade","cut","lower","reduce","probe","fine"]) else
                  "负面催化剂打击市场信心，买盘力量减弱。")
                +"\n\n📊 风险管理：\n"
                "⚠️ 持仓者：检查止损位，避免情绪化持有\n"
                "👀 观望者：等待关键支撑（200日线/前低）企稳缩量后再布局\n\n"
                "#美股 #热门股 #WallStreet #财经快讯")
            th=(f"📉 {sym_tag}{title[:65]}\n\n利空压制！等关键支撑企稳再考虑布局，切忌情绪化抄底。")
        else:
            ig=(f"⚡ {sym_tag}个股要闻{sect_s}{age_s}{src_s}\n\n📌 {title}\n{desc_s}{px_s}\n\n"
                "【市场解读】\n消息往往是板块情绪先行指标，"
                "结合成交量变化和机构资金流向综合判断实际影响力。\n\n"
                "📊 关注要点：同板块相对强弱 | 期权隐含波动率异动 | 大单净流向\n\n"
                "#美股 #热门股 #WallStreet #财经快讯")
            th=(f"⚡ {sym_tag}{title[:65]}\n\n关注板块情绪联动，结合成交量和机构资金流向综合判断方向。")
    elif cat == "crypto":
        if sent == "bear":
            ig=(f"🔴 加密市场警报！{age_s}{src_s}\n\n📌 {title}\n{desc_s}{px_s}\n\n"
                "【行情解读】\n链上资金外流，恐慌情绪升温。\n\n"
                "📊 风险管理：\n⚠️ BTC跌破关键支撑 → 下行空间打开\n"
                "✅ 恐慌指数<20 往往是中长线布局参考信号\n\n"
                "#Bitcoin #BTC #ETH #加密 #熊市 #风险管理 #财经快讯")
            th=(f"🔴 {title[:65]}\n\n链上资金外流，恐慌升温。守住关键支撑，山寨仓位严格管理。")
        else:
            ig=(f"🚀 加密市场积极信号！{age_s}{src_s}\n\n📌 {title}\n{desc_s}{px_s}\n\n"
                "【行情解读】\n链上数据回暖，机构资金回流信号出现。\n\n"
                "📊 多头确认条件：\n✅ 成交量持续放大\n✅ 链上活跃地址数回升\n"
                "✅ 稳定币净流入交易所\n\n"
                "⚠️ 牛市同样需要风险管理，分批入场，设定止盈止损区间。\n\n"
                "#Bitcoin #BTC #ETH #加密 #牛市 #链上数据 #财经快讯")
            th=(f"🚀 {title[:65]}\n\n链上资金回流！成交量确认是关键。分批入场，设好止盈止损。")
    else:
        if sent == "bear":
            ig=(f"⚠️ 宏观风险预警！{age_s}{src_s}\n\n📌 {title}\n{desc_s}{px_s}\n\n"
                "【宏观解读】\n经济数据走弱或风险事件冲击市场情绪，避险资产短期受益。\n\n"
                "📊 避险配置：🥇 黄金(GLD) | 📉 美债(TLT) | 💵 美元\n"
                "建议降低高风险资产仓位，增加防御性配置。\n\n"
                "#宏观 #全球市场 #避险 #黄金 #美股 #财经快讯")
            th=(f"⚠️ {title[:65]}\n\n宏观风险升温！关注黄金美债避险，降低激进仓位。")
        elif sent == "bull":
            ig=(f"🌐 宏观利好！{age_s}{src_s}\n\n📌 {title}\n{desc_s}{px_s}\n\n"
                "【宏观解读】\n数据超预期/风险缓解，市场风险偏好回升。"
                "周期股、新兴市场、大宗商品短期受益。\n\n"
                "📊 关注方向：科技/半导体 | 能源/材料 | 新兴市场（含马股）\n\n"
                "#宏观 #全球市场 #风险偏好 #美股 #新兴市场 #财经快讯")
            th=(f"🌐 {title[:65]}\n\n宏观利好！科技能源新兴市场关注联动机会。")
        else:
            ig=(f"📊 财经要闻精析{age_s}{src_s}\n\n📌 {title}\n{desc_s}{px_s}\n\n"
                "【解读】\n宏观事件是影响市场中长期方向的根本变量。"
                "持续追踪联储政策路径、企业盈利预期方向、全球资金流向。\n\n"
                "保持冷静，数据说话，避免情绪化追涨杀跌。\n\n"
                "#宏观 #全球市场 #美股 #财经快讯 #投资策略")
            th=(f"📊 {title[:65]}\n\n追踪联储政策路径及企业盈利预期。数据说话，避免情绪化操作。")

    return ig, th

# ── Market data builders ──────────────────────────────────────────────────────
def build_crypto(seq):
    data = json.loads(fetch(
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"))
    btc=data.get("bitcoin",{}); eth=data.get("ethereum",{})
    btc_p=btc.get("usd",0); btc_c=float(btc.get("usd_24h_change",0))
    eth_p=eth.get("usd",0); eth_c=float(eth.get("usd_24h_change",0))
    pl=(f"BTC {arrow(btc_c)} ${btc_p:,.0f} ({fmt_pct(btc_c)})  "
        f"ETH {arrow(eth_c)} ${eth_p:,.0f} ({fmt_pct(eth_c)})")
    news = fetch_rss(f"https://feeds.finance.yahoo.com/rss/2.0/headline?s=BTC-USD&region=US&lang=en-US",
                     max_items=3, label="YF:BTC")
    if not news:
        for src in CRYPTO_RSS:
            news = fetch_rss(src, max_items=5, label="CoinTelegraph", bonus=2)
            if news: break
    item = news[0] if news else {"title":"加密市场最新动态","link":"https://cointelegraph.com",
                                  "desc":"","age_hours":None,"source":""}
    ig,th = make_copy(item, {"sym":"BTC","price":btc_p,"pct":btc_c})
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
    gainers = screener("day_gainers", 5) if YF_OK else []
    losers  = screener("day_losers",  5) if YF_OK else []

    def row(i, show_vol=False):
        v=f"  vol:{fmt_vol(i['vol'])}" if show_vol and i['vol']>0 else ""
        return f"{arrow(i['pct'])} ${i['sym']}  ${i['price']:.2f}  ({fmt_pct(i['pct'])}){v}"

    if active:  lines.append("\n🔥 *成交量五大：*\n"+"\n".join(row(i,True) for i in active))
    if gainers: lines.append("\n🚀 *涨幅五大：*\n"  +"\n".join(row(i)      for i in gainers))
    if losers:  lines.append("\n💥 *跌幅五大：*\n"  +"\n".join(row(i)      for i in losers))

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
    tail=("整体风险偏好回升，成交量扩张中的热门股值得追踪。合理控制仓位，做好风险管理。" if sp_pct>=0.5 else
          "市场整体承压，避险情绪升温。关注黄金、美债防御资产，谨慎对待反弹。" if sp_pct<=-0.5 else
          "多空胶着，等待新的方向性催化剂。中性仓位为主，关注热门个股结构性机会。")
    ig=body.replace("*","")+"\n\n"+tail+"\n\n#美股 #涨幅榜 #跌幅榜 #成交量 #亚太指数 #马股 #板块ETF #财经快讯"
    th="\n".join(l.replace("*","").strip() for l in lines[:4] if l.strip())+"\n\n"+tail[:60]+"…"
    return (f"⚡ *快讯 #{seq}* 📊 市场速览\n\n"
            f"📸 *Instagram：*\n{ig}\n\n"
            f"🧵 *Threads：*\n{th}"), active, gainers, losers

def build_hot_news(seq, active, gainers, losers):
    """Collect large pool, score, deduplicate, show top 4."""
    trending = get_trending()
    screener_syms = [i["sym"] for i in active+gainers+losers if i.get("sym")]

    all_news = collect_all_news(trending, screener_syms)
    if not all_news: return None

    # Score each article
    for item in all_news:
        item["_score"] = score_article(item, trending, screener_syms)

    all_news.sort(key=lambda x: x["_score"])
    final_pool = deduplicate(all_news)

    # Pick top 4, max 2 per source for variety
    final = []
    sources_used = {}   # FIX: dict not set — was causing 'set has no .get()' error
    for item in final_pool:
        if len(final) >= 4: break
        src = item.get("source","")
        if sources_used.get(src, 0) >= 2: continue
        sources_used[src] = sources_used.get(src, 0) + 1
        final.append(item)

    if not final: return None

    # Get price context for major tickers mentioned
    mentioned = [s for item in final for s in SECTOR
                 if s.lower() in item["title"].lower()]
    pq = quotes(list(set(mentioned))[:8]) if YF_OK and mentioned else {}

    cat_label = {"geo":"🚨 地缘","fed":"🏛️ 美联储","stock":"📊 个股",
                 "macro":"🌐 宏观","crypto":"🪙 加密","general":"📰 财经"}
    parts = []
    for item in final:
        sym = item.get("sym","")
        if not sym:
            for s in SECTOR:
                if s.lower() in item["title"].lower(): sym=s; break
        cat = topic(item["title"], sym)
        lbl = cat_label.get(cat,"📰 财经")
        ctx = {"sym":sym,**pq[sym]} if sym and sym in pq else None
        ig,th = make_copy(item, ctx)
        src = item.get("source","")
        src_tag = f"  |  {src}" if src else ""
        parts.append(f"━━━━ {lbl}{src_tag} ━━━━\n"
                     f"🔗 [{item['title'][:70]}]({item['link']})\n\n"
                     f"📸 *Instagram：*\n{ig}\n\n"
                     f"🧵 *Threads：*\n{th}")

    return f"⚡ *快讯 #{seq}* 📰 市场热门要闻\n\n"+"".join(p+"\n\n" for p in parts)

def build_my_news(seq):
    news=[]
    for sym in ["^KLSE","1155.KL","1023.KL"]:
        url=f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
        news.extend(fetch_rss(url,max_items=3,label=f"YF:{sym}"))
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
    ig,th=make_copy(item,ctx); ig="🇲🇾 "+ig
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
    except Exception as e: print("Crypto:",e); send_msg(f"⚠️ 加密快讯失败：{str(e)[:80]}")

    active_=gainers_=losers_=[]
    if YF_OK:
        try:
            mkt,active_,gainers_,losers_=build_market(seq)
            send_msg(mkt); seq+=1
        except Exception as e: print("Market:",e); send_msg(f"⚠️ 市场数据失败：{str(e)[:80]}")

    try:
        msg=build_hot_news(seq,active_,gainers_,losers_)
        if msg: send_msg(msg); seq+=1
    except Exception as e: print("Hot news:",e); send_msg(f"⚠️ 热门要闻失败：{str(e)[:80]}")

    try:
        msg=build_my_news(seq)
        if msg: send_msg(msg); seq+=1
    except Exception as e: print("MY news:",e)

    send_msg("📲 关注 *@not.a.stockguru* 获取更多实时财经快讯 🔔")
    print("Done, messages sent:",seq-1)

if __name__=="__main__":
    main()
