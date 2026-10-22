# -*- coding: utf-8 -*-
"""
黄金监控台 - Flask 主服务
启动：python3 app.py
访问：http://localhost:5000
"""
import os
import datetime
from flask import Flask, jsonify, request, send_from_directory

import config
import data_fetcher
import analyzer
import pusher
from events import GOLD_EVENTS, get_events_in_range

app = Flask(__name__, static_folder="static", static_url_path="")

# 缓存最近一次分析，避免频繁计算
_last_analysis = None
_last_analysis_time = None


@app.route("/")
def index():
    return send_from_directory("static", "dashboard.html")


# ============================================================
#  API：实时金价
# ============================================================
@app.route("/api/realtime")
def api_realtime():
    data = data_fetcher.get_realtime_prices()
    return jsonify(data)


# ============================================================
#  API：历史走势
# ============================================================
@app.route("/api/history")
def api_history():
    period = request.args.get("period", "5y")
    data = data_fetcher.get_history(period)
    return jsonify(data)


# ============================================================
#  API：历史事件（走势图节点原因）
# ============================================================
@app.route("/api/events")
def api_events():
    start = request.args.get("start", "2020-01-01")
    end = request.args.get("end", datetime.date.today().isoformat())
    events = get_events_in_range(start, end)
    return jsonify({"events": events})


# ============================================================
#  API：黄金信息收集
# ============================================================
@app.route("/api/info")
def api_info():
    info = data_fetcher.collect_gold_info()
    return jsonify(info)


# ============================================================
#  API：走势分析
# ============================================================
@app.route("/api/analysis")
def api_analysis():
    global _last_analysis, _last_analysis_time
    # 5分钟缓存
    if _last_analysis and _last_analysis_time and (datetime.datetime.now() - _last_analysis_time).seconds < 300:
        return jsonify(_last_analysis)

    prices = data_fetcher.get_realtime_prices()
    info = data_fetcher.collect_gold_info()
    ana = analyzer.analyze(prices, info)
    _last_analysis = ana
    _last_analysis_time = datetime.datetime.now()
    return jsonify(ana)


# ============================================================
#  API：手动推送测试
# ============================================================
@app.route("/api/push/test", methods=["POST"])
def api_push_test():
    result = pusher.push_once()
    return jsonify(result)


# ============================================================
#  API：推送状态
# ============================================================
@app.route("/api/push/status")
def api_push_status():
    return jsonify(pusher.push_status())


if __name__ == "__main__":
    # 启动定时推送
    pusher.start_scheduler()
    print(f"🥇 黄金监控台启动：http://localhost:{config.PORT}")
    print(f"   微信推送间隔：{config.PUSH_INTERVAL_MINUTES}分钟 | webhook已配置：{bool(config.WECHAT_WEBHOOK_URL)}")
    app.run(host="0.0.0.0", port=config.PORT, debug=False)
