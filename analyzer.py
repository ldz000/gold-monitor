# -*- coding: utf-8 -*-
"""
黄金走势分析模块
- 收盘后基于最新消息 + 核心指标，分析次日走势
- 内置规则打分（不依赖AI也能用）
- 可选：调用大模型生成更详细的分析
"""
import json
import datetime
import requests
import config
import data_fetcher
from events import GOLD_EVENTS


def get_recent_events(days=7):
    """取最近 days 天的事件"""
    today = datetime.date.today().isoformat()
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    return [e for e in GOLD_EVENTS if cutoff <= e["date"] <= today]


def _score_price_trend():
    """
    技术面因子：近期价格趋势。
    取近一月日线，计算近5日涨跌幅与20日均线。
    - 近5日涨 > 1.5% 且 当前价 > 20日均线：+1.5
    - 近5日跌 < -1.5% 且 当前价 < 20日均线：-1.5
    - 其他或数据不足：0 / None
    """
    hist = data_fetcher.get_history("1m")
    data = hist.get("data", [])
    if len(data) < 25:
        return None

    closes = [d["Close"] for d in data]
    current = closes[-1]
    five_days_ago = closes[-6]
    ma20 = sum(closes[-20:]) / 20

    change_pct = (current - five_days_ago) / five_days_ago * 100

    if change_pct > 1.5 and current > ma20:
        score = 1.5
        reason = f"近5日上涨{change_pct:.2f}%且当前价高于20日均线，短期趋势偏强"
    elif change_pct < -1.5 and current < ma20:
        score = -1.5
        reason = f"近5日下跌{change_pct:.2f}%且当前价低于20日均线，短期趋势偏弱"
    else:
        score = 0
        reason = f"近5日涨跌幅{change_pct:.2f}%，趋势信号不明显"

    return {"name": "近期价格趋势", "score": score, "reason": reason}


def score_factors():
    """
    基于核心指标打分，返回各因子分数与方向。
    每因子 -2 ~ +2，正数利多黄金。
    """
    factors = []

    # 1. 美元指数
    dxy = data_fetcher._fetch_dxy()
    if dxy < 102:
        s, reason = 2, f"美元指数{dxy}处于低位，弱势美元利好黄金"
    elif dxy < 105:
        s, reason = 1, f"美元指数{dxy}偏弱，对金价形成一定支撑"
    elif dxy < 107:
        s, reason = 0, f"美元指数{dxy}中性，对金价影响有限"
    else:
        s, reason = -2, f"美元指数{dxy}强势，压制金价"
    factors.append({"name": "美元指数", "score": s, "reason": reason})

    # 2. 实际利率 TIPS
    tips = data_fetcher._fetch_tips()
    if tips < 1.0:
        s, reason = 2, f"TIPS实际利率{tips}%处于低位，持有黄金机会成本低"
    elif tips < 1.8:
        s, reason = 1, f"TIPS实际利率{tips}%偏低，利好黄金"
    elif tips < 2.3:
        s, reason = 0, f"TIPS实际利率{tips}%中性"
    else:
        s, reason = -2, f"TIPS实际利率{tips}%高企，压制金价"
    factors.append({"name": "实际利率(TIPS)", "score": s, "reason": reason})

    # 3. 通胀
    cpi_text = data_fetcher._latest_cpi()
    try:
        cpi = float(cpi_text.split("%")[0])
        if cpi > 3.5:
            s, reason = 1, f"CPI {cpi}%偏高，抗通胀需求支撑金价"
        elif cpi > 2.5:
            s, reason = 0, f"CPI {cpi}%温和"
        else:
            s, reason = -1, f"CPI {cpi}%回落，抗通胀需求减弱"
    except Exception:
        s, reason = 0, "CPI数据待更新"
    factors.append({"name": "美国通胀(CPI)", "score": s, "reason": reason})

    # 4. 美联储政策
    fed = data_fetcher._fed_status()
    if "降息" in fed or "偏鸽" in fed:
        s, reason = 1, f"美联储{fed}，利率路径偏鸽，利好黄金"
    elif "加息" in fed or "偏鹰" in fed:
        s, reason = -1, f"美联储{fed}，政策偏鹰，压制金价"
    else:
        # 按兵不动/维持利率均为中性
        s, reason = 0, f"美联储{fed}，政策立场中性，对金价影响有限"
    factors.append({"name": "美联储政策", "score": s, "reason": reason})

    # 5. 地缘风险
    events = get_recent_events(14)
    geo = [e for e in events if any(k in e["title"] for k in ["冲突", "战争", "地缘", "袭", "俄", "中东"])]
    if geo:
        s, reason = 2, f"近期地缘事件：{geo[-1]['title']}，避险情绪推升金价"
    else:
        s, reason = 0, "近期无重大地缘事件"
    factors.append({"name": "地缘风险", "score": s, "reason": reason})

    # 6. 央行购金
    # 不无条件加分：优先看近30天事件中是否有央行/购金相关消息
    recent_month = get_recent_events(30)
    cb_events = [
        e for e in recent_month
        if any(k in e["title"] for k in ["央行", "购金"])
    ]
    if cb_events:
        # 用最新一条相关事件的 impact，方向以正数为主
        latest = cb_events[-1]
        impact = latest.get("impact", 1)
        s = max(-1, min(2, impact))
        reason = f"近期央行购金动态：{latest['title']}（评分{s:+g}）"
    else:
        # 无近期事件时仅给轻权重，避免多头偏向
        s = 0.5
        reason = "全球央行持续净购金构成中长期结构性支撑，但近期无新事件，权重较轻"
    factors.append({"name": "央行购金", "score": s, "reason": reason})

    # 7. 技术面：近期价格趋势
    trend_factor = _score_price_trend()
    if trend_factor is not None:
        factors.append(trend_factor)

    return factors


def rule_based_analysis():
    """基于规则打分给出次日走势判断"""
    factors = score_factors()
    total = sum(f["score"] for f in factors)

    # 7个因子总分范围约 -10 ~ +11，阈值适当提高以避免轻易看涨
    if total >= 5:
        direction = "看涨"
        action = "偏多思路，回调可考虑布局"
    elif total >= 1:
        direction = "偏多震荡"
        action = "区间偏多操作，注意止盈"
    elif total >= -1:
        direction = "震荡"
        action = "观望为主，区间高抛低吸"
    elif total >= -4:
        direction = "偏空震荡"
        action = "区间偏空操作，控制仓位"
    else:
        direction = "看跌"
        action = "偏空思路，反弹可考虑做空"

    reasons = "\n".join([f"• {f['name']}：{f['reason']}（评分{f['score']:+.2g}）" for f in factors])

    return {
        "direction": direction,
        "action": action,
        "score": total,
        "factors": factors,
        "reasons": reasons,
        "generated_at": datetime.datetime.now().isoformat(),
        "method": "规则打分",
    }


def llm_analysis(prices, info):
    """可选：调用大模型生成更详细的分析"""
    if not config.LLM_API_KEY or not config.LLM_API_BASE:
        return None

    prompt = f"""你是黄金分析师。请基于以下数据，分析明天黄金走势并给出原因。

当前金价：
- 国际金价(XAU/USD)：{prices['international']['price']} {prices['international']['unit']}
- 国内金价(沪金)：{prices['domestic']['price']} {prices['domestic']['unit']}
- 美元兑人民币：{prices['usd_cny']}

核心指标：
{json.dumps(info['categories']['核心跟踪指标'], ensure_ascii=False, indent=2)}

宏观信息：
{json.dumps(info['categories']['宏观基本面'], ensure_ascii=False, indent=2)}

请输出：
1. 明日走势判断（看涨/看跌/震荡）
2. 核心原因（3-5条）
3. 关键价位（支撑位、阻力位）
4. 操作建议
"""
    try:
        r = requests.post(
            f"{config.LLM_API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {config.LLM_API_KEY}", "Content-Type": "application/json"},
            json={"model": config.LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.5},
            timeout=60,
        )
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            base = rule_based_analysis()
            base["method"] = "AI分析 + 规则打分"
            base["llm_detail"] = content
            return base
    except Exception as e:
        pass
    return None


def analyze(prices=None, info=None):
    """主分析入口：优先用AI，否则用规则"""
    if prices is None:
        prices = data_fetcher.get_realtime_prices()
    if info is None:
        info = data_fetcher.collect_gold_info()

    ai = llm_analysis(prices, info)
    if ai:
        return ai
    return rule_based_analysis()
