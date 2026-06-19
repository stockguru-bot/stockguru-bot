"""
StockGuru 财经快讯 — @not.a.stockguru
News selection is MARKET-DRIVEN, not keyword-driven:
  1. Yahoo Finance Trending Tickers  (real-time popularity signal)
  2. Screener: most-active / top-gainers / top-losers
  3. Per-ticker RSS for every hot symbol  ← the actual news
  4. Yahoo Finance editor-curated top stories
No hardcoded topic keywords are used to decide what's newsworthy.
"""

import urllib.request, json, datetime, re, html
from email.utils import parsedate_to_datetime

try:
    import yfinance as yf
    YF_OK = True
except ImportError:
    YF_OK = False

# ── Credentials ───────────────────────────────────────────────────────────────
BOT_TOKEN = "8238743813:AAEQqdLdDKz6OM2txjSE5FbI73cFdQc1P0w"
CHAT_ID   = "1237620041"
BASE_URL  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

NEWS_MAX_AGE_HOURS = 24   # only last 24 hours

# ── Static market configs ─────────────────────────────────────────────────────
US_IDX   = {"^GSPC":"S&P500","^IXIC":"Nasdaq"}
ASIA_IDX = {"^N225":"日经225","^KS11":"韩国KOSPI","^TWII":"台湾加权","^HSI":"恒生指数"}
ETF_POOL = {"SMH":"半导体","XLK":"科技","XLE":"能源","XLF":"金融","ARKK":"创新","GLD":"黄金","IWM":"小盘"}
MY_SYMS  = ["^KLSE","1155.KL","1023.KL","5681.KL","6012.KL","5347.KL"]
MY_NAME  = {"^KLSE":"KLCI","1155.KL":"Maybank","1023.KL":"CIMB",
            "5681.KL":"Tenaga","6012.KL":"Maxis","5347.KL":"PetChem"}
SECTOR   = {
    "NVDA":"半导体/AI","AMD":"半导体","INTC":"半导体","MU":"存储芯片",
    "AVGO":"半导体","QCOM":"半导体","TSLA":"电动车","META":"社交/AI",
    "GOOGL":"科技/AI","MSFT":"科技/AI","AAPL":"科技/消费","AMZN":"电商/云",
    "PLTR":"大数据/AI","COIN":"加密金融","HOOD":"金融科技","GS":"投行",
    "JPM":"银行","MSTR":"比特币","ASTS":"太空通讯","RKLB":"航天",
    "MRVL":"半导体","ORCL":"云计算","SNDK":"存储/AI","QURE":"生物科技",
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


# ── HTTP / RSS helpers ────────────────────────────────────────────────────────
def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept":"application/rss+xml,application/xml,text/html,*/*"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return r.read().decode("utf-8", errors="ignore")

def _parse_dt(raw):
    m = re.search(r'<pubDate>(.*?)</pubDate>', raw, re.DOTALL)
    if not m: return None
    try:
        dt = parsedate_to_datetime(m.group(1).strip())
        return datetime.datetime(*dt.utctimetuple()[:6])
    except Exception: return None

def parse_rss(xml, max_items=12):
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
            items.append({"title":title,"link":link,"desc":desc,"age_hours":age})
        if len(items) >= max_items: break
    items.sort(key=lambda x: x.get("age_hours") or 999)
    return items

def rss(url, n=10):
    try:   return parse_rss(fetch(url), n)
    except Exception as e: print(f"RSS fail {url}: {e}"); return []


# ── Market data helpers ───────────────────────────────────────────────────────
def quotes(syms):
    out = {}
    if not syms or not YF_OK: return out
    try:
        raw = yf.download(syms, period="5d", interval="1d",
                          group_by="ticker", auto_adjust=True,
                          progress=False, threads=True)
        for s in (syms if isinstance(syms,list) else [syms]):
            try:
                cl = raw[s]["Close"].dropna() if len(syms)>1 else raw["Close"].dropna()
                if len(cl)>=2: p,c=float(cl.iloc[-2]),float(cl.iloc[-1]); out[s]={"price":c,"pct":(c-p)/p*100}
                elif len(cl)==1: out[s]={"price":float(cl.iloc[-1]),"pct":0.0}
            except Exception: pass
    except Exception as e: print("yf.download:", e)
    return out

def screener(sid, n=5):
    try:
        s = yf.Screener(); s.set_predefined_body(sid); s.set_count(n)
        return [{"sym":str(q.get("symbol","")),"price":float(q.get("regularMarketPrice",0)),
                 "pct":float(q.get("regularMarketChangePercent",0)),
                 "vol":float(q.get("regularMarketVolume",0))}
                for q in s.response.get("quotes",[])[:n]]
    except Exception as e: print(f"screener {sid}:", e); return []

def fmt_pct(v): return ("+" if v>=0 else "")+f"{v:.2f}%"
def arrow(v):   return "🟢" if v>=0 else "🔴"
def darrow(v):  return "▲" if v>=0 else "▼"
def fmt_vol(v):
    if v>=1e9: return f"{v/1e9:.1f}B"
    if v>=1e6: return f"{v/1e6:.1f}M"
    return f"{v/1e3:.0f}K"


# ── Market-driven news gathering ──────────────────────────────────────────────
def get_trending_tickers():
    """
    Yahoo Finance Trending Tickers API — real-time market popularity signal.
    Returns list of ticker symbols, most-trending first.
    """
    try:
        url  = ("https://query1.finance.yahoo.com/v1/finance/trending/US"
                "?lang=en-US&region=US&count=15&corsDomain=finance.yahoo.com")
        data = json.loads(fetch(url))
        qs   = data.get("finance",{}).get("result",[{}])[0].get("quotes",[])
        syms = [q.get("symbol","") for q in qs if q.get("symbol")]
        print(f"Trending tickers ({len(syms)}):", syms[:8])
        return syms
    except Exception as e:
        print("Trending API err:", e); return []

def ticker_rss(sym, n=4):
    url   = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
    items = rss(url, n)
    for i in items: i["sym"] = sym
    return items

def gather_market_news():
    """
    Market-driven news pipeline (no keyword topic filter):
      1. Yahoo Finance trending tickers  → per-ticker RSS
      2. Screener hot movers (vol/gain/loss) → per-ticker RSS
      3. Yahoo Finance editor top-stories RSS
      4. yfinance Ticker.news API (fallback)
    Returns (news_list, hot_syms).
    """
    # ── Step 1: Trending now ────────────────────────────────────────────────
    trending = get_trending_tickers()

    # ── Step 2: Hot movers ──────────────────────────────────────────────────
    active  = screener("most_actives", 6)
    gainers = screener("day_gainers",  5)
    losers  = screener("day_losers",   5)
    mover_syms = [i["sym"] for i in active+gainers+losers if i.get("sym")]

    # Combined priority list: trending first, then movers
    priority = list(dict.fromkeys(trending + mover_syms))[:20]
    print("Hot pool:", priority[:10])

    all_news = []; seen = set()

    def add(items, market_rank=999):
        for item in items:
            key = item["title"][:45].lower()
            if key in seen or len(item.get("title","")) < 12: continue
            seen.add(key)
            item.setdefault("tickers", []); item.setdefault("sym","")
            item["market_rank"] = market_rank   # rank among trending pool
            all_news.append(item)

    # Per-ticker RSS for each hot symbol (most targeted source)
    for i, sym in enumerate(priority[:12]):
        add(ticker_rss(sym, 3), market_rank=i)

    # ── Step 3: Yahoo Finance editor curated top stories ───────────────────
    top = rss("https://finance.yahoo.com/rss/topstories", 12)
    for t in top: t.setdefault("sym","")
    add(top, market_rank=500)

    # ── Step 4: yfinance Ticker.news API fallback ──────────────────────────
    if len(all_news) < 5 and YF_OK:
        for sym in (trending or priority)[:5]:
            try:
                raw = yf.Ticker(sym).news
                if callable(raw): raw = raw()
                now = datetime.datetime.utcnow()
                for n in (raw or [])[:3]:
                    if not isinstance(n, dict): continue
                    pts = n.get("providerPublishTime",0)
                    age = (now - datetime.datetime.utcfromtimestamp(pts)).total_seconds()/3600 if pts else None
                    if age and age > NEWS_MAX_AGE_HOURS: continue
                    c = n.get("content") or {}
                    title = (c.get("title") or n.get("title","")).strip()
                    link  = ((c.get("canonicalUrl") or {}).get("url","") or n.get("link","")).strip()
                    desc  = (c.get("summary") or n.get("summary",""))[:250].strip()
                    if title and link:
                        add([{"title":title,"link":link,"desc":desc,
                              "sym":sym,"tickers":[sym],"age_hours":age}],
                            market_rank=priority.index(sym) if sym in priority else 999)
            except Exception as e: print(f"yf.news ({sym}):", e)

    # ── Sort: market_rank (what's trending) + freshness ───────────────────
    all_news.sort(key=lambda x: x.get("market_rank",999)*0.6
                                + min((x.get("age_hours") or 12),24)*0.4)
    return all_news, priority, active, gainers, losers


# ── Sentiment detection (lightweight, for copy tone only) ─────────────────────
def sentiment(title):
    t = title.lower()
    neg = sum(1 for w in ["fall","drop","crash","slump","miss","plunge","slips",
                           "decline","concern","risk","warn","down","lower","loss",
                           "disappoint","fine","lawsuit","bearish"] if w in t)
    pos = sum(1 for w in ["rise","rally","surge","soars","beat","upgrade","record",
                           "profit","deal","gain","high","strong","lifted","boost",
                           "jump","exceed","buy","outperform","partnership","bullish"] if w in t)
    return "bull" if pos>neg else "bear" if neg>pos else "neutral"

def topic(sym, title=""):
    """Light classification for copy template selection only — not for filtering."""
    t = title.lower()
    if any(k in t for k in ["bitcoin","btc","ethereum","eth","crypto","blockchain"]): return "crypto"
    if any(k in t for k in ["federal reserve","fomc","rate cut","rate hike","monetary policy",
                              "interest rate","powell","warsh","fed chair"]): return "fed"
    if sym or any(k in t for k in ["earnings","buyback","acquisition","target raised",
                                    "upgrade","downgrade","revenue","profit","ipo",
                                    "partnership","deal","price target"]): return "stock"
    if any(k in t for k in ["war","military","sanction","conflict","attack","invasion",
                              "missile","ceasefire","geopolit","iran","russia","china military",
                              "taiwan strait","north korea"]): return "geo"
    if any(k in t for k in ["gdp","jobs","unemployment","cpi","pce","recession","tariff",
                              "oil","gold","inflation","trade","deficit","yields","treasury"]): return "macro"
    return "general"


# ── Chinese copy generator ─────────────────────────────────────────────────────
def make_copy(item, price_ctx=None):
    title = item["title"]
    desc  = item.get("desc","")
    sym   = item.get("sym","")
    t     = title.lower()
    sent  = sentiment(title)
    cat   = topic(sym, title)
    sect  = SECTOR.get(sym,"")
    sect_s= f"（{sect}板块）" if sect else ""
    desc_s= (desc[:160]+"…") if desc else ""
    px_s  = ""
    if price_ctx:
        p,pct = price_ctx.get("price",0), price_ctx.get("pct",0)
        ps    = price_ctx.get("sym",sym)
        px_s  = f"\n💹 ${ps} 今日 {'▲' if pct>=0 else '▼'} ${p:.2f}（{fmt_pct(pct)}）"
    age   = item.get("age_hours")
    age_s = ("  🕐 刚刚" if age and age<1 else
             f"  🕐 {age:.0f}小时前" if age and age<6 else
             "  🕐 今日" if age and age<24 else "")

    # ── Geopolitical ──────────────────────────────────────────────────────
    if cat == "geo":
        if sent == "bear":
            ig = (f"🚨 地缘政治风险警报！{age_s}\n\n"
                  f"📌 {title}\n{desc_s}{px_s}\n\n"
                  "【市场影响】\n地缘冲突直接冲击全球风险情绪，能源供应链受威胁时"
                  "油价急升，传导至通胀预期，压制降息空间。\n\n"
                  "📊 市场联动：\n"
                  "🛢️ 能源/油价↑  🥇 黄金避险需求↑  📉 科技成长承压\n"
                  "⚠️ 减持高风险资产，关注能源(XLE)、黄金(GLD)对冲机会。\n\n"
                  "#地缘政治 #风险 #避险 #美股 #财经快讯")
            th  = f"🚨 {title[:65]}\n\n地缘风险升温！油价↑黄金↑科技承压。减持激进仓位，能源黄金对冲。"
        else:
            ig = (f"🌐 地缘局势最新进展{age_s}\n\n"
                  f"📌 {title}\n{desc_s}{px_s}\n\n"
                  "【市场影响】\n局势缓和提振风险偏好，周期股及新兴市场受益，"
                  "能源供应担忧减少有助通胀预期回落。\n\n"
                  "📊 受益方向：科技/周期板块 ✅  新兴市场资金回流 ✅\n\n"
                  "#地缘政治 #全球市场 #风险偏好 #美股 #财经快讯")
            th  = f"🌐 {title[:65]}\n\n地缘缓和！风险偏好回升，科技周期受益，新兴市场关注资金回流机会。"

    # ── Fed ───────────────────────────────────────────────────────────────
    elif cat == "fed":
        if any(k in t for k in ["hike","raise","hawkish","higher for longer"]):
            ig = (f"🏛️ 美联储鹰派信号！{age_s}\n\n"
                  f"📌 {title}\n{desc_s}{px_s}\n\n"
                  "【政策解读】\n联储偏鹰，科技/成长股估值承压，美债收益率上行"
                  "，美元走强，新兴市场面临资金外流压力。\n\n"
                  "📊 应对策略：\n减持高估值仓位  |  关注金融(XLF)防御配置\n\n"
                  "#美联储 #加息 #FOMC #利率 #美股 #财经快讯")
            th  = f"🏛️ 美联储鹰派！{title[:55]}\n\n降息预期降温，科技承压，金融防御相对占优。"
        elif any(k in t for k in ["cut","ease","pause","dovish","pivot"]):
            ig = (f"🏛️ 美联储鸽派！降息预期重燃！{age_s}\n\n"
                  f"📌 {title}\n{desc_s}{px_s}\n\n"
                  "【政策解读】\n利率下行预期推升风险偏好，科技成长股估值修复，"
                  "小盘股(IWM)及新兴市场迎来阶段性机会。\n\n"
                  "📊 关注方向：科技 | 生物科技 | 小盘成长\n"
                  "⚠️ 关键验证：CPI/PCE需持续回落，单次表态不等于政策转向。\n\n"
                  "#美联储 #降息 #FOMC #利率 #美股 #风险偏好 #财经快讯")
            th  = f"🏛️ 美联储鸽派！{title[:55]}\n\n降息预期升温，科技小盘迎机会。持续关注通胀数据验证。🚀"
        else:
            ig = (f"🏛️ 美联储动态{age_s}\n\n"
                  f"📌 {title}\n{desc_s}{px_s}\n\n"
                  "【政策解读】\n联储措辞变化是全球资产定价核心变量。"
                  "重点追踪：通胀路径、非农数据、官员措辞中\"data dependent\"程度。\n\n"
                  "策略：中性仓位，等待更明确信号。\n\n"
                  "#美联储 #FOMC #货币政策 #利率 #美股 #宏观 #财经快讯")
            th  = f"🏛️ {title[:60]}\n\n联储政策牵动全市场。追踪通胀+就业数据，中性仓位等信号。📊"

    # ── Individual Stock ──────────────────────────────────────────────────
    elif cat == "stock":
        sym_tag  = f"${sym} " if sym else ""
        sect_tag = sect_s
        if sent == "bull":
            ig = (f"📈 {sym_tag}重磅利好{sect_tag}！{age_s}\n\n"
                  f"📌 {title}\n{desc_s}{px_s}\n\n"
                  "【交易解读】\n"
                  +("分析师上调目标价/评级，机构信心提升，短期强势支撑。"
                    if any(k in t for k in ["target","raised","upgraded","lift"]) else
                    "重大合作/业绩催化剂落地，市场对成长前景信心回升。")
                  +"\n\n📊 交易策略：\n"
                  "✅ 成交量放大（>20日均量）→ 突破信号可信度高\n"
                  "✅ 消息当日冲高 → 次日易回吐，分批布局优于追高\n"
                  "⚠️ 设好止损，避免满仓追单\n\n"
                  f"#美股 #热门股 #WallStreet #财经快讯")
            th = (f"📈 {sym_tag}{title[:65]}\n\n"
                  "利好催化！成交量是突破有效性的确认关键。分批布局，避免追高。")
        elif sent == "bear":
            ig = (f"📉 {sym_tag}重磅利空{sect_tag}！{age_s}\n\n"
                  f"📌 {title}\n{desc_s}{px_s}\n\n"
                  "【风险解读】\n"
                  +("评级下调或目标价下修，机构分歧扩大，短期股价承压。"
                    if any(k in t for k in ["downgrade","cut","lower","reduce"]) else
                    "负面催化剂打击市场信心，买盘力量减弱。")
                  +"\n\n📊 风险管理：\n"
                  "⚠️ 持仓者：检查止损位，避免情绪化持有\n"
                  "👀 观望者：等待关键支撑（200日线/前低）企稳缩量后再布局\n"
                  "❌ 下行趋势中忌盲目抄底\n\n"
                  f"#美股 #热门股 #WallStreet #财经快讯")
            th = (f"📉 {sym_tag}{title[:65]}\n\n"
                  "利空压制！等关键支撑企稳再考虑布局，切忌情绪化抄底。")
        else:
            ig = (f"⚡ {sym_tag}个股要闻{sect_tag}{age_s}\n\n"
                  f"📌 {title}\n{desc_s}{px_s}\n\n"
                  "【市场解读】\n消息往往是板块情绪先行指标，"
                  "结合成交量变化和机构资金流向综合判断实际影响力。\n\n"
                  "📊 关注要点：同板块相对强弱 | 期权隐含波动率异动 | 大单净流向\n\n"
                  f"#美股 #热门股 #WallStreet #财经快讯")
            th = (f"⚡ {sym_tag}{title[:65]}\n\n"
                  "关注板块情绪联动，结合成交量和机构资金流向综合判断方向。")

    # ── Crypto ────────────────────────────────────────────────────────────
    elif cat == "crypto":
        if sent == "bear":
            ig = (f"🔴 加密市场警报！{age_s}\n\n"
                  f"📌 {title}\n{desc_s}{px_s}\n\n"
                  "【行情解读】\n链上资金外流，恐慌情绪升温。"
                  "加密与宏观流动性高度相关，联储收紧将进一步压制风险资产。\n\n"
                  "📊 风险管理：\n⚠️ BTC跌破关键支撑 → 下行空间打开\n"
                  "⚠️ 山寨币在BTC走弱时跌幅通常更大\n"
                  "✅ 恐慌指数<20 往往是中长线布局参考信号\n\n"
                  "#Bitcoin #BTC #ETH #加密 #熊市 #风险管理 #财经快讯")
            th = (f"🔴 {title[:65]}\n\n链上资金外流，恐慌升温。守住关键支撑，山寨仓位严格管理。")
        else:
            ig = (f"🚀 加密市场积极信号！{age_s}\n\n"
                  f"📌 {title}\n{desc_s}{px_s}\n\n"
                  "【行情解读】\n链上数据回暖，机构资金回流信号出现。"
                  "市场情绪从恐慌向贪婪区过渡。\n\n"
                  "📊 多头确认条件：\n✅ 成交量持续放大\n"
                  "✅ 链上活跃地址数回升\n✅ 稳定币净流入交易所\n\n"
                  "⚠️ 牛市同样需要风险管理，分批入场，设定止盈止损区间。\n\n"
                  "#Bitcoin #BTC #ETH #加密 #牛市 #链上数据 #财经快讯")
            th = (f"🚀 {title[:65]}\n\n链上资金回流！成交量确认是关键。分批入场，设好止盈止损。")

    # ── Macro / General ───────────────────────────────────────────────────
    else:
        if sent == "bear":
            ig = (f"⚠️ 宏观风险预警！{age_s}\n\n"
                  f"📌 {title}\n{desc_s}{px_s}\n\n"
                  "【宏观解读】\n经济数据走弱或风险事件冲击市场情绪，"
                  "避险资产短期受益。\n\n"
                  "📊 避险配置：🥇 黄金(GLD) | 📉 美债(TLT) | 💵 美元\n"
                  "建议降低高风险资产仓位，增加防御性配置。\n\n"
                  "#宏观 #全球市场 #避险 #黄金 #美股 #财经快讯")
            th = (f"⚠️ {title[:65]}\n\n宏观风险升温！关注黄金美债避险，降低激进仓位。")
        elif sent == "bull":
            ig = (f"🌐 宏观利好！{age_s}\n\n"
                  f"📌 {title}\n{desc_s}{px_s}\n\n"
                  "【宏观解读】\n数据超预期/风险缓解，市场风险偏好回升。"
                  "周期股、新兴市场、大宗商品短期受益。\n\n"
                  "📊 关注方向：科技/半导体 | 能源/材料 | 新兴市场（含马股）\n"
                  "⚠️ 单一事件影响有限，需配合联储政策判断持续性。\n\n"
                  "#宏观 #全球市场 #风险偏好 #美股 #新兴市场 #财经快讯")
            th = (f"🌐 {title[:65]}\n\n宏观利好！科技能源新兴市场关注联动机会。")
        else:
            ig = (f"📊 财经要闻精析{age_s}\n\n"
                  f"📌 {title}\n{desc_s}{px_s}\n\n"
                  "【解读】\n宏观事件是影响市场中长期方向的根本变量。"
                  "持续追踪联储政策路径、企业盈利预期方向、全球资金流向。\n\n"
                  "保持冷静，数据说话，避免情绪化追涨杀跌。\n\n"
                  "#宏观 #全球市场 #美股 #财经快讯 #投资策略")
            th = (f"📊 {title[:65]}\n\n追踪联储政策路径及企业盈利预期。数据说话，避免情绪化操作。")

    return ig, th


# ── Message builders ──────────────────────────────────────────────────────────
def build_crypto(seq):
    data = json.loads(fetch(
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"))
    btc = data.get("bitcoin",{}); eth = data.get("ethereum",{})
    btc_p = btc.get("usd",0); btc_pct = float(btc.get("usd_24h_change",0))
    eth_p = eth.get("usd",0); eth_pct = float(eth.get("usd_24h_change",0))
    pl = (f"BTC {arrow(btc_pct)} ${btc_p:,.0f} ({fmt_pct(btc_pct)})  "
          f"ETH {arrow(eth_pct)} ${eth_p:,.0f} ({fmt_pct(eth_pct)})")
    # Get crypto news from ticker RSS first (market-driven)
    news = ticker_rss("BTC-USD",3) + ticker_rss("ETH-USD",2)
    if not news:
        for src in CRYPTO_RSS:
            news = rss(src,5)
            if news: break
    item = news[0] if news else {"title":"加密市场最新动态",
                                  "link":"https://cointelegraph.com","desc":"","age_hours":None}
    ig,th = make_copy(item, {"sym":"BTC","price":btc_p,"pct":btc_pct})
    return (f"⚡ *快讯 #{seq}* 🪙 加密\n"
            f"🔗 [{item['title'][:70]}]({item['link']})\n\n"
            f"📸 *Instagram：*\n🪙 *行情：* {pl}\n\n{ig}\n\n"
            f"🧵 *Threads：*\n{pl}\n\n{th}")

def build_market(seq):
    lines = []
    if YF_OK:
        iq = quotes(list(US_IDX.keys()))
        parts = []
        for s,n in US_IDX.items():
            if s in iq: parts.append(f"{n} {darrow(iq[s]['pct'])} {fmt_pct(iq[s]['pct'])}")
        if parts: lines.append("📊 *美股大盘：* " + "  |  ".join(parts))

    active  = screener("most_actives",5)
    gainers = screener("day_gainers", 5)
    losers  = screener("day_losers",  5)

    def row(i, show_vol=False):
        v = f"  vol:{fmt_vol(i['vol'])}" if show_vol and i['vol']>0 else ""
        return f"{arrow(i['pct'])} ${i['sym']}  ${i['price']:.2f}  ({fmt_pct(i['pct'])}){v}"

    if active:  lines.append("\n🔥 *成交量五大：*\n"+"\n".join(row(i,True) for i in active))
    if gainers: lines.append("\n🚀 *涨幅五大：*\n"  +"\n".join(row(i)      for i in gainers))
    if losers:  lines.append("\n💥 *跌幅五大：*\n"  +"\n".join(row(i)      for i in losers))

    if YF_OK:
        eq = quotes(list(ETF_POOL.keys()))
        etfs= sorted([(s,eq[s],ETF_POOL[s]) for s in ETF_POOL if s in eq],
                      key=lambda x:x[1]["pct"], reverse=True)[:5]
        if etfs:
            lines.append("\n📂 *板块ETF：*\n"+"\n".join(
                f"{arrow(q['pct'])} {name}({sym}) {fmt_pct(q['pct'])}"
                for sym,q,name in etfs))

    if YF_OK:
        aq = quotes(list(ASIA_IDX.keys()))
        al = [f"{arrow(aq[s]['pct'])} {n}  {fmt_pct(aq[s]['pct'])}"
              for s,n in ASIA_IDX.items() if s in aq]
        if al: lines.append("\n🌏 *亚太指数：*\n"+"\n".join(al))

    if YF_OK:
        mq = quotes(MY_SYMS)
        kl = mq.get("^KLSE",{}); kl_p=kl.get("pct",0); kl_px=kl.get("price",0)
        my = sorted([(s,mq[s]) for s in MY_SYMS if s in mq and s!="^KLSE"],
                     key=lambda x:abs(x[1]["pct"]),reverse=True)[:3]
        ml = [f"{arrow(kl_p)} KLCI {kl_px:,.2f} ({fmt_pct(kl_p)})"]
        ml+= [f"{arrow(q['pct'])} {MY_NAME.get(s,s)} RM{q['price']:.2f} ({fmt_pct(q['pct'])})"
              for s,q in my]
        lines.append("\n🇲🇾 *马股：*\n"+"\n".join(ml))

    body = "\n".join(lines)
    sp_pct = quotes(["^GSPC"]).get("^GSPC",{}).get("pct",0) if YF_OK else 0
    tail = ("整体风险偏好回升，成交量扩张中热门股值得追踪。合理控制仓位，做好风险管理。" if sp_pct>=0.5 else
            "市场整体承压，避险情绪升温。关注黄金、美债防御资产，谨慎对待反弹。" if sp_pct<=-0.5 else
            "多空胶着，等待新的方向性催化剂。以中性仓位为主，关注热门个股结构性机会。")
    ig = body.replace("*","") + "\n\n" + tail + "\n\n#美股 #涨幅榜 #跌幅榜 #成交量 #亚太指数 #马股 #板块ETF #财经快讯"
    th = "\n".join(l.replace("*","").strip() for l in lines[:4] if l.strip()) + "\n\n" + tail[:60] + "…"
    return (f"⚡ *快讯 #{seq}* 📊 市场速览\n\n"
            f"📸 *Instagram：*\n{ig}\n\n"
            f"🧵 *Threads：*\n{th}"), active, gainers, losers

def build_hot_news(seq, active, gainers, losers):
    """
    Market-driven hot news:
    - Yahoo Finance Trending Tickers → per-ticker RSS
    - Screener hot movers → per-ticker RSS
    - Yahoo Finance top stories
    No topic keywords used for selection or ranking.
    """
    all_news, priority, *_ = gather_market_news()
    if not all_news: return None

    # Get price context for known hot symbols
    pq = quotes(priority[:8]) if YF_OK else {}

    # De-duplicate by content similarity and pick top 3
    final = []; seen_words = []
    for item in all_news:
        words = set(item["title"].lower().split())
        if any(len(words & sw) > 5 for sw in seen_words): continue
        seen_words.append(words); final.append(item)
        if len(final) >= 3: break
    if not final: return None

    cat_label = {"geo":"🚨 地缘","fed":"🏛️ 美联储","stock":"📊 个股",
                 "macro":"🌐 宏观","crypto":"🪙 加密","general":"📰 财经"}
    parts = []
    for item in final:
        sym  = item.get("sym","")
        cat  = topic(sym, item["title"])
        lbl  = cat_label.get(cat,"📰 财经")
        ctx  = {"sym":sym, **pq[sym]} if sym and sym in pq else None
        ig,th = make_copy(item, ctx)
        rank_note = f"  |  📈 Trending #{priority.index(sym)+1}" if sym and sym in priority else ""
        parts.append(f"━━━━ {lbl}{rank_note} ━━━━\n"
                     f"🔗 [{item['title'][:70]}]({item['link']})\n\n"
                     f"📸 *Instagram：*\n{ig}\n\n"
                     f"🧵 *Threads：*\n{th}")

    return f"⚡ *快讯 #{seq}* 📰 市场热门要闻\n\n" + "\n\n".join(parts)

def build_my_news(seq):
    news = []
    for sym in ["^KLSE","1155.KL","1023.KL"]:
        news.extend(ticker_rss(sym,3))
    if not news:
        for src in MY_RSS:
            batch = rss(src,8)
            rel   = [n for n in batch if any(
                k in n["title"].lower() for k in
                ["klci","bursa","malaysia","ringgit","maybank","cimb","tenaga","petronas"])]
            if rel: news = rel; break
    if not news: return None
    item = news[0]; item.setdefault("tickers",[]); item.setdefault("sym","")
    kq = quotes(["^KLSE"]).get("^KLSE") if YF_OK else None
    ctx = {"sym":"KLCI","price":kq["price"],"pct":kq["pct"]} if kq else None
    ig,th = make_copy(item,ctx); ig = "🇲🇾 "+ig
    return (f"⚡ *快讯 #{seq}* 🇲🇾 马股要闻\n"
            f"🔗 [{item['title'][:70]}]({item['link']})\n\n"
            f"📸 *Instagram：*\n{ig}\n\n"
            f"🧵 *Threads：*\n{th}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    emoji, label = (lambda h:
        ("🕛","午间快讯") if h<14 else
        ("🕒","下午快讯") if h<17 else
        ("🕕","晚间快讯") if h<20 else
        ("🌙","夜盘快讯"))((datetime.datetime.utcnow()+datetime.timedelta(hours=8)).hour)

    now_cst = datetime.datetime.utcnow()+datetime.timedelta(hours=8)
    send_msg(f"{emoji} *{label} | @not.a.stockguru*\n"
             f"📅 {now_cst.strftime('%Y年%m月%d日 %H:%M')} (CST)\n━━━━━━━━━━━━━━━━━━━━")
    seq = 1

    try: send_msg(build_crypto(seq)); seq+=1
    except Exception as e: print("Crypto:", e); send_msg(f"⚠️ 加密快讯失败：{str(e)[:80]}")

    active_=gainers_=losers_=[]
    if YF_OK:
        try:
            mkt,active_,gainers_,losers_ = build_market(seq)
            send_msg(mkt); seq+=1
        except Exception as e: print("Market:", e); send_msg(f"⚠️ 市场数据失败：{str(e)[:80]}")

    try:
        msg = build_hot_news(seq, active_, gainers_, losers_)
        if msg: send_msg(msg); seq+=1
    except Exception as e: print("Hot news:", e); send_msg(f"⚠️ 热门要闻失败：{str(e)[:80]}")

    try:
        msg = build_my_news(seq)
        if msg: send_msg(msg); seq+=1
    except Exception as e: print("MY news:", e)

    send_msg("📲 关注 *@not.a.stockguru* 获取更多实时财经快讯 🔔")
    print("Done, messages sent:", seq-1)

if __name__ == "__main__":
    main()
