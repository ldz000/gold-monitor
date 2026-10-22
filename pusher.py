# -*- coding: utf-8 -*-
"""
多渠道微信推送 + 定时调度
支持渠道（按优先级）：
  1. 企业微信群机器人（WECHAT_WEBHOOK_URL）
  2. Server酱（SERVERCHAN_SENDKEY）— 推到个人微信
  3. PushPlus（PUSHPLUS_TOKEN）— 推到个人微信
每30分钟推送：实时金价 + 核心指标 + 走势分析
"""
import json
import datetime
import requests
import config
import data_fetcher
import analyzer


def build_push_content():
    """构造推送内容（同时返回 markdown 版和纯文本版）
    包含：实时金价 + 5大类黄金信息（宏观/供需/持仓/国内/核心指标） + 完整走势分析
    """
    prices = data_fetcher.get_realtime_prices()
    info = data_fetcher.collect_gold_info()
    ana = analyzer.analyze(prices, info)

    intl = prices["international"]
    dom = prices["domestic"]
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    cats = info["categories"]
    cat_icons = {
        "宏观基本面": "📊",
        "供需基本面": "⚖️",
        "资金持仓数据": "💰",
        "国内专属信息": "🇨🇳",
        "核心跟踪指标": "🎯",
    }

    direction_color = "green" if ana["direction"] in ["看涨", "偏多震荡"] else ("red" if ana["direction"] in ["看跌", "偏空震荡"] else "info")

    # ---- 纯文本版（Server酱 / PushPlus 个人微信用）----
    txt_lines = [
        f"🥇 黄金实时监控 · {now}",
        "",
        f"🌍 国际金价：{intl['price']} {intl['unit']}（{intl['source']}）",
        f"🇨🇳 国内金价：{dom['price']} {dom['unit']}（{dom['source']}）",
        f"💱 美元兑人民币：{prices['usd_cny']}",
        "",
    ]
    for cat, items in cats.items():
        icon = cat_icons.get(cat, "•")
        txt_lines.append(f"━━━ {icon} {cat} ━━━")
        for it in items:
            txt_lines.append(f"• {it['name']}：{it['value']}")
            txt_lines.append(f"   解读：{it['interpret']}")
        txt_lines.append("")
    txt_lines.append("━━━ 🧭 明日走势分析 ━━━")
    txt_lines.append(f"方向：{ana['direction']} | 综合评分：{ana['score']:+d}")
    txt_lines.append(f"操作建议：{ana['action']}")
    txt_lines.append("")
    txt_lines.append("核心原因：")
    txt_lines.append(ana["reasons"])
    txt_lines.append("")
    txt_lines.append(f"—— 黄金监控台自动推送 · {ana['method']}")
    txt = "\n".join(txt_lines)

    # ---- markdown 版（企业微信用）----
    md_lines = [
        f"### 🥇 黄金实时监控 · {now}",
        "",
        f"**国际金价**：<font color=\"gold\">{intl['price']}</font> {intl['unit']}",
        f"**国内金价**：<font color=\"gold\">{dom['price']}</font> {dom['unit']}",
        f"**美元兑人民币**：{prices['usd_cny']}",
        "",
    ]
    for cat, items in cats.items():
        icon = cat_icons.get(cat, "•")
        md_lines.append(f"**{icon} {cat}**")
        for it in items:
            md_lines.append(f"> {it['name']}：{it['value']}")
        md_lines.append("")
    md_lines.append("**🧭 明日走势分析**")
    md_lines.append(f"方向：<font color=\"{direction_color}\">{ana['direction']}</font> | 综合评分：{ana['score']:+d}")
    md_lines.append(f"操作建议：{ana['action']}")
    md_lines.append("")
    md_lines.append("**核心原因：**")
    md_lines.append(ana["reasons"])
    md_lines.append("")
    md_lines.append(f"<small>黄金监控台自动推送 · {ana['method']}</small>")
    md = "\n".join(md_lines)

    return {"md": md, "txt": txt, "prices": prices, "analysis": ana}


# ============ 各渠道推送实现 ============

def _push_wecom(md):
    """企业微信群机器人"""
    payload = {"msgtype": "markdown", "markdown": {"content": md}}
    r = requests.post(config.WECHAT_WEBHOOK_URL, json=payload, timeout=15)
    if r.status_code == 200 and r.json().get("errcode") == 0:
        return {"ok": True, "channel": "企业微信群"}
    return {"ok": False, "msg": f"企业微信返回: {r.text}"}


def _push_serverchan(txt):
    """Server酱 → 个人微信"""
    title = "🥇 黄金监控 · " + datetime.datetime.now().strftime("%m-%d %H:%M")
    url = f"https://sctapi.ftqq.com/{config.SERVERCHAN_SENDKEY}.send"
    r = requests.post(url, data={"title": title, "desp": txt}, timeout=15)
    if r.status_code == 200 and r.json().get("code") == 0:
        return {"ok": True, "channel": "Server酱(个人微信)"}
    return {"ok": False, "msg": f"Server酱返回: {r.text[:120]}"}


def _push_pushplus(txt):
    """PushPlus → 个人微信 / 群组（填了 PUSHPLUS_TOPIC 则推给群内所有人）"""
    title = "🥇 黄金监控 · " + datetime.datetime.now().strftime("%m-%d %H:%M")
    url = "http://www.pushplus.plus/send"
    payload = {
        "token": config.PUSHPLUS_TOKEN,
        "title": title,
        "content": txt,
        "template": "txt",
    }
    topic = getattr(config, "PUSHPLUS_TOPIC", "")
    if topic:
        payload["topic"] = topic
    r = requests.post(url, json=payload, timeout=15)
    if r.status_code == 200 and r.json().get("code") == 200:
        name = "PushPlus(群组)" if topic else "PushPlus(个人微信)"
        return {"ok": True, "channel": name}
    return {"ok": False, "msg": f"PushPlus返回: {r.text[:120]}"}


def push_to_wechat():
    """统一推送入口：依次尝试已配置的渠道"""
    content = build_push_content()
    md, txt = content["md"], content["txt"]

    results = []
    # 1. 企业微信群
    if config.WECHAT_WEBHOOK_URL:
        try:
            results.append(_push_wecom(md))
        except Exception as e:
            results.append({"ok": False, "msg": f"企业微信异常: {e}"})
    # 2. Server酱
    if config.SERVERCHAN_SENDKEY:
        try:
            results.append(_push_serverchan(txt))
        except Exception as e:
            results.append({"ok": False, "msg": f"Server酱异常: {e}"})
    # 3. PushPlus
    if config.PUSHPLUS_TOKEN:
        try:
            results.append(_push_pushplus(txt))
        except Exception as e:
            results.append({"ok": False, "msg": f"PushPlus异常: {e}"})

    if not results:
        return {"ok": False, "msg": "未配置任何推送渠道，请在 config.py 填写 Server酱 或 PushPlus 的 token"}

    ok_count = sum(1 for r in results if r.get("ok"))
    if ok_count > 0:
        channels = "、".join(r["channel"] for r in results if r.get("ok"))
        return {"ok": True, "msg": f"已推送到 {channels}", "time": datetime.datetime.now().isoformat(), "details": results}
    else:
        return {"ok": False, "msg": "所有渠道推送失败", "time": datetime.datetime.now().isoformat(), "details": results}


def push_once():
    """供手动调用的一次推送"""
    return push_to_wechat()


def push_status():
    """返回已配置的推送渠道状态"""
    channels = []
    if config.WECHAT_WEBHOOK_URL:
        channels.append({"name": "企业微信群机器人", "enabled": True})
    if config.SERVERCHAN_SENDKEY:
        channels.append({"name": "Server酱(个人微信)", "enabled": True})
    if config.PUSHPLUS_TOKEN:
        channels.append({"name": "PushPlus(个人微信)", "enabled": True})
    return {
        "channels": channels,
        "any_enabled": len(channels) > 0,
        "interval_minutes": config.PUSH_INTERVAL_MINUTES,
    }


# —— 定时调度 ——
_scheduler = None


def start_scheduler():
    """启动定时推送调度器（后台线程）"""
    global _scheduler
    if _scheduler is not None:
        return
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    _scheduler.add_job(
        push_to_wechat,
        IntervalTrigger(minutes=config.PUSH_INTERVAL_MINUTES),
        id="gold_push",
        replace_existing=True,
        next_run_time=datetime.datetime.now() + datetime.timedelta(seconds=10),
    )
    _scheduler.start()


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
