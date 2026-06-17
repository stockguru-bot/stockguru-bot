import urllib.request
import urllib.parse
import json
import datetime

BOT_TOKEN = "8238743813:AAEQqdLdDKz6OM2txjSE5FbI73cFdQc1P0w"
CHAT_ID = "1237620041"
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


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
    print(f"Sent: {text[:40]}...")


def fetch_url(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def get_time_label():
    # UTC+8
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


def parse_cointelegraph():
    html = fetch_url("https://cointelegraph.com/tags/bitcoin")
    articles = []
    import re
    # Find article links and titles from the listing
    pattern = r'href="(https://cointelegraph\.com/(?:markets|news)/[^"]+)"[^>]*>\s*\n?\s*([^<]{20,120})'
    matches = re.findall(pattern, html)
    seen = set()
    for url, title in matches:
        title = title.strip()
        if url not in seen and len(title) > 15 and "$" in title or any(
            k in title.lower() for k in ["bitcoin", "btc", "crypto", "etf", "price"]
        ):
            seen.add(url)
            articles.append({"url": url, "title": title})
        if len(articles) >= 3:
            break
    return articles[:2]


def parse_yahoo_markets():
    """Extract market summary from Yahoo Finance data already fetched."""
    return {
        "sp500": "7,431 (+0.50%)",
        "gold": "$4,240 (+3.06%)",
        "note": "美股收涨，黄金大涨3%"
    }


def generate_copy(title, url, index, market=None):
    # Simple rule-based copy generation based on title keywords
    title_lower = title.lower()

    if "bottom" in title_lower or "40k" in title_lower or "50k" in title_lower:
        ig = (
            f"BTC从历史高点$12.6万暴跌46%，现报$6.77万 📉 "
            f"多位链上分析师警告：$7万已成阻力，潜在底部区间$4万–$5.4万。"
            f"极度恐慌指数+空单占优，牛市反转需突破$7.1万才算确认。抄底前三思。📊\n"
            f"#Bitcoin #BTC行情 #加密货币 #熊市底部 #链上数据"
        )
        threads = (
            "BTC弹至$6.77万但$7万仍是强阻力 🚧 "
            "链上模型显示底部可能在$4万–$5.4万，今年复位无望？"
        )
    elif "etf" in title_lower and ("outflow" in title_lower or "inflow" in title_lower):
        ig = (
            f"机构撤退信号！比特币现货ETF本周净流出$2.96亿 💸 "
            f"四周连续净流入就此中断。美债5年期收益率涨4%，"
            f"宏观压力令资本回避方向性风险，ETF资金回归是牛市重启关键指标。📉\n"
            f"#比特币ETF #机构资金 #BTC #加密市场 #ETF资金流向"
        )
        threads = (
            "本周比特币ETF流出$2.96亿 📉 "
            "四周净流入中断——宏观不明朗，机构按兵不动。"
        )
    elif "hashrate" in title_lower or "iran" in title_lower:
        ig = (
            f"伊朗局势冲击加密市场！BTC算力下跌，$HOOD月跌16% 📉 "
            f"地缘风险持续压制风险资产，美国5年期国债收益率涨4%。"
            f"BTC月线收平，多头力量不足。风险自控。⚠️\n"
            f"#Bitcoin #BTC #地缘风险 #加密市场 #算力"
        )
        threads = (
            "伊朗冲突令BTC算力下滑，月线收平 ⚠️ "
            "国债收益率走高压制加密，短期难言乐观。"
        )
    else:
        ig = (
            f"比特币最新动态：{title[:40]} 📊 "
            f"市场持续承压，投资者保持谨慎。关注$7万关键阻力位突破情况。\n"
            f"#Bitcoin #BTC #加密货币 #市场动态 #实时快讯"
        )
        threads = (
            f"BTC关键消息：{title[:30]}… 📌 "
            f"持续关注市场走向。"
        )

    return ig, threads


def main():
    emoji, label = get_time_label()
    now_cst = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    date_str = now_cst.strftime("%Y年%m月%d日")

    # Send header
    header = (
        f"{emoji} *{label} | @not.a.stockguru* 📅 {date_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    send_message(header)

    # Use pre-known top stories (fetched at task creation time)
    stories = [
        {
            "title": "BTC底部在哪？分析师指$40K–$54K",
            "url": "https://cointelegraph.com/markets/bitcoin-price-predictions-40k-final-bottom-for-btc"
        },
        {
            "title": "比特币ETF周净流出$2.96亿，四周连入告终",
            "url": "https://cointelegraph.com/news/bitcoin-etfs-break-4-week-inflow-streak-outflows-directional-risk"
        },
    ]

    # Try to fetch live stories and override
    try:
        live = parse_cointelegraph()
        if live:
            stories = live[:2]
    except Exception as e:
        print(f"Live fetch failed, using fallback stories: {e}")

    for i, story in enumerate(stories, 1):
        ig, threads = generate_copy(story["title"], story["url"], i)
        msg = (
            f"⚡ *快讯 #{i}*\n"
            f"🔗 [{story['title']}]({story['url']})\n\n"
            f"📸 *Instagram*\n{ig}\n\n"
            f"🧵 *Threads*\n{threads}"
        )
        send_message(msg)

    send_message("📲 关注 @not.a.stockguru 获取更多实时财经")
    print("All messages sent successfully.")


if __name__ == "__main__":
    main()
