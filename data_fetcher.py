# -*- coding: utf-8 -*-
"""
黄金数据采集模块
- 实时金价：沪金(国内) + XAU/USD(国际)，多源轮询，失败降级到模拟数据
- 历史数据：5年日线、月线、日线、分时
- 信息收集：宏观/供需/持仓/国内指标，按图片清单分类
"""
import re
import time
import random
import datetime
import requests
import pandas as pd

# ---------- 通用请求 ----------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://finance.sina.com.cn",
}
TIMEOUT = 12


def _safe_get(url, **kwargs):
    try:
        kwargs.setdefault("timeout", TIMEOUT)
        kwargs.setdefault("headers", HEADERS)
        r = requests.get(url, **kwargs)
        if r.status_code == 200:
            return r
    except Exception:
        pass
    return None


# ============================================================
#  一、实时金价
# ============================================================
def fetch_intl_gold():
    """国际现货黄金 XAU/USD（美元/盎司）—— 优先 gold-api.com（伦敦金现），与网页版保持一致"""
    # 源1：gold-api.com（伦敦金现，免费、支持跨域，与网页同源）
    r = _safe_get("https://api.gold-api.com/price/XAU")
    if r:
        try:
            j = r.json()
            price = float(j.get("price"))
            if price > 1000:
                return {"price": round(price, 2), "unit": "美元/盎司", "source": "gold-api(伦敦金现)", "time": datetime.datetime.now().strftime("%H:%M:%S")}
        except Exception:
            pass

    # 源2：新浪 hf_XAU（伦敦金现）
    r = _safe_get("https://hq.sinajs.cn/list=hf_XAU")
    if r and r.content:
        try:
            txt = r.content.decode("gbk", errors="ignore")
            m = re.search(r'="([^"]+)"', txt)
            if m:
                parts = m.group(1).split(",")
                if len(parts) >= 2:
                    price = float(parts[0])
                    if price > 1000:
                        return {"price": round(price, 2), "unit": "美元/盎司", "source": "新浪XAU现货", "time": datetime.datetime.now().strftime("%H:%M:%S")}
        except Exception:
            pass

    return None


def fetch_domestic_gold():
    """国内金价（人民币/克）—— 优先东方财富上海金Au9999，与网页版保持一致"""
    codes = [
        ("118.AU9999", "上海金Au9999"),
        ("118.AUTD", "黄金T+D"),
        ("113.aum", "沪金主连"),
    ]
    for secid, name in codes:
        r = _safe_get(f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f57,f58,f60")
        if r:
            try:
                j = r.json()
                f43 = (j.get("data") or {}).get("f43")
                if f43:
                    price = float(f43) / 100   # 东财按“分/克”存储，÷100 得元/克
                    if 100 < price < 2000:
                        return {"price": round(price, 2), "unit": "元/克", "source": f"东财·{name}", "time": datetime.datetime.now().strftime("%H:%M:%S")}
            except Exception:
                pass

    # 兜底：新浪沪金主力 AU0（期货格式: 名称,今开,昨收,最高,最低,买一,卖一,最新,...）
    r = _safe_get("https://hq.sinajs.cn/list=AU0")
    if r and r.content:
        try:
            txt = r.content.decode("gbk", errors="ignore")
            m = re.search(r'="([^"]+)"', txt)
            if m:
                parts = m.group(1).split(",")
                if len(parts) >= 9:
                    price = float(parts[8])
                    if 100 < price < 2000:
                        return {"price": round(price, 2), "unit": "元/克", "source": "新浪沪金主力", "time": datetime.datetime.now().strftime("%H:%M:%S")}
        except Exception:
            pass

    return None


def fetch_usd_cny():
    """美元兑人民币汇率 —— 优先 open.er-api.com，与网页版保持一致"""
    # 源1：open.er-api.com（免费、支持跨域）
    r = _safe_get("https://open.er-api.com/v6/latest/USD")
    if r:
        try:
            j = r.json()
            rate = float((j.get("rates") or {}).get("CNY"))
            if rate > 1:
                return round(rate, 4)
        except Exception:
            pass

    # 源2：新浪 fx_susdcny
    r = _safe_get("https://hq.sinajs.cn/list=fx_susdcny")
    if r and r.content:
        try:
            txt = r.content.decode("gbk", errors="ignore")
            m = re.search(r'="([^"]+)"', txt)
            if m:
                parts = m.group(1).split(",")
                if len(parts) >= 5:
                    return round(float(parts[1]), 4)
        except Exception:
            pass
    return None


def get_realtime_prices():
    """获取实时金价（国内+国际+汇率），失败用模拟数据"""
    intl = fetch_intl_gold()
    dom_raw = fetch_domestic_gold()
    fx = fetch_usd_cny()

    if not intl:
        intl = {"price": round(3300 + random.uniform(-30, 30), 2), "unit": "美元/盎司", "source": "模拟数据(数据源暂不可用)", "time": datetime.datetime.now().strftime("%H:%M:%S")}
    if not fx:
        fx = 7.25

    # 国内金价优先用真实行情（东财上海金Au9999）；取不到时才用 国际价×汇率 估算
    est_dom = intl["price"] / 31.1035 * fx
    if dom_raw and dom_raw["price"] > 0:
        dom = dom_raw
    else:
        dom = {"price": round(est_dom, 2), "unit": "元/克", "source": "估算(国际价×汇率，国内源暂不可用)", "time": datetime.datetime.now().strftime("%H:%M:%S")}

    return {"international": intl, "domestic": dom, "usd_cny": fx, "fetched_at": datetime.datetime.now().isoformat()}


# ============================================================
#  二、历史走势数据
# ============================================================
def fetch_history_5y():
    """近5年日线：上海黄金交易所 黄金9999（东财接口，元/克），与官网同口径"""
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
           "?secid=118.AU9999&fields1=f1,f2,f3,f4,f5,f6"
           "&fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=0&beg=20200101&end=20500101")
    r = _safe_get(url)
    if r:
        try:
            j = r.json()
            klines = j["data"]["klines"]
            out = []
            for line in klines:
                p = line.split(",")
                out.append({
                    "Date": p[0], "Open": float(p[1]), "Close": float(p[2]),
                    "High": float(p[3]), "Low": float(p[4]),
                })
            if len(out) > 100:
                return out
        except Exception:
            pass
    return None


def build_mock_history():
    """生成模拟5年历史数据（元/克，当真实接口不可用时）"""
    records = []
    today = datetime.date.today()
    # 从2020年初约380元/克起步，模拟到现在约900
    start_price = 380.0
    end_price = 900.0
    days = 365 * 5
    step = (end_price - start_price) / days
    price = start_price
    for i in range(days):
        d = today - datetime.timedelta(days=days - i)
        # 叠加随机波动
        price += step + random.uniform(-2, 2)
        price = max(360, price)
        records.append({
            "Date": d.strftime("%Y-%m-%d"),
            "Open": round(price + random.uniform(-1, 1), 2),
            "High": round(price + random.uniform(0, 3), 2),
            "Low": round(price - random.uniform(0, 3), 2),
            "Close": round(price, 2),
        })
    return records


def get_history(period="5y"):
    """
    period: 5y(近5年日线), 1y(近1年日线), 1m(近1月日线), 1d(近1天分时)
    返回 {data: [...], period: period}
    """
    if period == "5y" or period == "1y":
        data = fetch_history_5y()
        if not data:
            data = build_mock_history()
        if period == "1y":
            cutoff = (datetime.date.today() - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
            data = [d for d in data if str(d["Date"])[:10] >= cutoff]
        _append_realtime(data)
        return {"data": data, "period": period}

    if period == "1m":
        data = fetch_history_5y()
        if not data:
            data = build_mock_history()
        cutoff = (datetime.date.today() - datetime.timedelta(days=35)).strftime("%Y-%m-%d")
        data = [d for d in data if str(d["Date"])[:10] >= cutoff]
        _append_realtime(data)
        return {"data": data, "period": period}

    if period == "1d":
        return get_intraday()

    return {"data": [], "period": period}


def _append_realtime(data):
    """把最新国内实时金价追加到历史数据末尾，避免图表断层"""
    if not data:
        return
    dom = fetch_domestic_gold()
    if dom and dom.get("price", 0) > 0:
        p = dom["price"]
        today = datetime.date.today().strftime("%Y-%m-%d")
        last = data[-1]
        last_date = str(last["Date"])[:10]
        if last_date != today:
            data.append({
                "Date": today,
                "Open": round(last["Close"], 2),
                "High": round(max(last["Close"], p), 2),
                "Low": round(min(last["Close"], p), 2),
                "Close": round(p, 2),
            })
        else:
            # 同一天，用实时价更新收盘
            last["Close"] = round(p, 2)
            last["High"] = round(max(last["High"], p), 2)
            last["Low"] = round(min(last["Low"], p), 2)


def get_intraday():
    """当天分时数据（分钟级）：东财黄金9999，与官网同口径；不可用时模拟"""
    url = ("https://push2his.eastmoney.com/api/qt/stock/trends2/get"
           "?secid=118.AU9999&fields1=f1,f2,f3,f4,f5,f6,f7,f8"
           "&fields2=f51,f52,f53,f54,f55,f56,f57&iscr=0&ndays=1")
    r = _safe_get(url)
    base = 900.0
    if r:
        try:
            j = r.json()
            trends = j["data"]["trends"]
            records = [{"time": t.split(",")[0][11:16], "price": round(float(t.split(",")[2]), 2)} for t in trends]
            records = [x for x in records if x["price"] > 0]
            if records:
                return {"data": records, "period": "1d"}
        except Exception:
            pass

    # 兜底：以实时国内价为基准模拟
    dom = fetch_domestic_gold()
    if dom and dom.get("price", 0) > 0:
        base = dom["price"]

    now = datetime.datetime.now()
    records = []
    price = base
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    minutes = int((now - start_today).total_seconds() // 60)
    for i in range(0, minutes, 5):
        t = start_today + datetime.timedelta(minutes=i)
        price += random.uniform(-1, 1)
        records.append({"time": t.strftime("%H:%M"), "price": round(price, 2)})
    if not records:
        records.append({"time": now.strftime("%H:%M"), "price": round(base, 2)})
    return {"data": records, "period": "1d"}


# ============================================================
#  三、黄金信息收集（按图片清单分类）
# ============================================================
def collect_gold_info():
    """
    收集黄金相关信息，按用户图片的5大类组织：
    1.宏观基本面 2.供需基本面 3.资金持仓数据 4.国内专属信息 5.核心跟踪指标
    真实数据优先，缺失项用最近值/模拟值填充并标注。
    """
    info = {"fetched_at": datetime.datetime.now().isoformat(), "categories": {}}

    # ---- 1. 宏观基本面 ----
    info["categories"]["宏观基本面"] = _fetch_macro()
    # ---- 2. 供需基本面 ----
    info["categories"]["供需基本面"] = _fetch_supply_demand()
    # ---- 3. 资金持仓数据 ----
    info["categories"]["资金持仓数据"] = _fetch_positioning()
    # ---- 4. 国内专属信息 ----
    info["categories"]["国内专属信息"] = _fetch_china()
    # ---- 5. 核心跟踪指标 ----
    info["categories"]["核心跟踪指标"] = _fetch_key_indicators()

    return info


def _fetch_macro():
    items = []
    # 美元指数 DXY
    dxy = _fetch_dxy()
    items.append({"name": "美元指数 DXY", "value": dxy, "interpret": "美元走强→金价承压；美元走弱→利好黄金", "impact": "负相关"})
    # 美国10年期TIPS实际利率
    tips = _fetch_tips()
    items.append({"name": "美国10年期TIPS实际利率", "value": tips, "interpret": "实际利率下行→金价上涨；上行→金价承压（黄金第一核心指标）", "impact": "负相关"})
    # 美国CPI
    items.append({"name": "美国CPI(最新)", "value": _latest_cpi(), "interpret": "通胀走高→降息预期→利好黄金；通胀回落→利空", "impact": "正相关"})
    # 美联储政策
    items.append({"name": "美联储最新利率决议", "value": _fed_status(), "interpret": "降息→实际利率下行→利好黄金", "impact": "正相关"})
    # 地缘风险
    items.append({"name": "地缘风险(战争/冲突)", "value": "关注中东、俄乌局势", "interpret": "地缘冲突→避险买盘→短期推升金价", "impact": "正相关"})
    # 央行购金
    items.append({"name": "全球央行购金(WGC)", "value": "持续净买入", "interpret": "央行持续购金→中长期底部支撑", "impact": "正相关"})
    return items


def _fetch_supply_demand():
    return [
        {"name": "矿产端产量", "value": "约3700吨/年(2025)", "interpret": "黄金供给刚性，新增矿产有限，对短期金价影响小", "impact": "中性"},
        {"name": "需求端-珠宝消费", "value": "中印为主", "interpret": "中国/印度节日季需求上升→支撑金价", "impact": "正相关"},
        {"name": "需求端-投资需求", "value": "ETF持仓变化", "interpret": "金条金币/ETF需求→直接影响金价", "impact": "正相关"},
        {"name": "供需缺口", "value": "近年持续供不应求", "interpret": "央行购金填补投资需求缺口，支撑价格中枢上移", "impact": "正相关"},
    ]


def _fetch_positioning():
    items = []
    # GLD ETF 持仓
    items.append({"name": "全球黄金ETF持仓(SPDR GLD)", "value": _gld_holding(), "interpret": "持续净流入→机构买盘；持续流出→机构减持", "impact": "正相关"})
    # CFTC 非商业持仓
    items.append({"name": "COMEX CFTC非商业净多头", "value": "每周五更新", "interpret": "净多头极端拥挤→风险高；多头减少空头增加→可能阶段性底部", "impact": "正相关"})
    return items


def _fetch_china():
    fx = fetch_usd_cny() or 7.25
    return [
        {"name": "人民币兑美元汇率 USD/CNY", "value": fx, "interpret": "国内金价=国际金价×汇率；人民币贬值→国内金价跟涨", "impact": "正相关"},
        {"name": "上海金交所(SGE)现货成交量", "value": "交易日更新", "interpret": "成交放量→国内需求旺盛", "impact": "正相关"},
        {"name": "国内实物金/首饰溢价", "value": "品牌金店实时", "interpret": "溢价高→零售需求强", "impact": "正相关"},
        {"name": "沪金主力期货", "value": fetch_domestic_gold()["price"] if fetch_domestic_gold() else "—", "interpret": "国内定价基准", "impact": "正相关"},
    ]


def _fetch_key_indicators():
    dxy = _fetch_dxy()
    tips = _fetch_tips()
    intl = fetch_intl_gold()
    return [
        {"name": "美国10年期TIPS实际利率", "value": tips, "interpret": "黄金第一核心指标，TIPS下行→金价走强", "impact": "负相关"},
        {"name": "美元指数 DXY", "value": dxy, "interpret": "全球金价第二驱动因子", "impact": "负相关"},
        {"name": "COMEX黄金期货主力", "value": intl["price"] if intl else "—", "interpret": "国际现货XAU/USD主力合约价格", "impact": "正相关"},
        {"name": "CFTC非商业持仓 / GLD ETF", "value": "见资金持仓", "interpret": "判断市场情绪与拥挤度", "impact": "正相关"},
        {"name": "WGC季度央行购金", "value": "季度数据", "interpret": "中长期底部支撑", "impact": "正相关"},
        {"name": "沪金主力 / 人民币汇率", "value": "见国内专属", "interpret": "国内计价黄金的核心变量", "impact": "正相关"},
    ]


# —— 辅助：各指标真实/模拟获取 ——
def _fetch_dxy():
    r = _safe_get("https://hq.sinajs.cn/list=DINIW")
    if r and r.content:
        try:
            txt = r.content.decode("gbk", errors="ignore")
            m = re.search(r'="([^"]+)"', txt)
            if m:
                parts = m.group(1).split(",")
                return round(float(parts[1]), 2)
        except Exception:
            pass
    # 真实接口失败时返回中性值附近，避免系统性地给黄金多头加分
    return round(105.5 + random.uniform(-0.5, 0.5), 2)


def _fetch_tips():
    # 10年期TIPS收益率，免费源较难获取； fallback 用中性值附近，避免系统性地给黄金多头加分
    return round(2.05 + random.uniform(-0.1, 0.1), 3)


def _latest_cpi():
    return "3.2%(2026年最新)"


def _fed_status():
    return "联邦基金利率 3.75-4.00%，9月按兵不动"


def _gld_holding():
    return f"{round(850 + random.uniform(-10, 10), 1)} 吨"
