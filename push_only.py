# -*- coding: utf-8 -*-
"""
极简推送脚本（不启动网页服务器，只负责定时推送到微信）
适合：只想自动推送、不想挂完整 app.py 的用户

用法：
    1. 在 config.py 里填好 Server酱 或 PushPlus 的 token
    2. python3 push_only.py
    3. 后台常驻：nohup python3 push_only.py > push.log 2>&1 &
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
import datetime
import config
import pusher

INTERVAL = config.PUSH_INTERVAL_MINUTES * 60  # 读取 config.py 里的 PUSH_INTERVAL_MINUTES

def main():
    status = pusher.push_status()
    if not status["any_enabled"]:
        print("❌ 未配置任何推送渠道")
        print("   请在 config.py 填写以下任一 token：")
        print("   - SERVERCHAN_SENDKEY  →  微信扫码 https://sct.ftqq.com 获取")
        print("   - PUSHPLUS_TOKEN      →  微信扫码 https://www.pushplus.plus 获取")
        return

    print("✅ 已启用推送渠道：", "、".join(c["name"] for c in status["channels"]))
    print(f"⏰ 推送间隔：{INTERVAL//60} 分钟")
    print("=" * 50)

    while True:
        try:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{now}] 开始推送...")
            result = pusher.push_to_wechat()
            if result["ok"]:
                print(f"  ✓ {result['msg']}")
            else:
                print(f"  ✗ {result['msg']}")
                for d in result.get("details", []):
                    if not d.get("ok"):
                        print(f"    - {d.get('msg', '')}")
        except Exception as e:
            print(f"  ✗ 推送异常：{e}")

        next_time = datetime.datetime.now() + datetime.timedelta(seconds=INTERVAL)
        print(f"  下次推送：{next_time.strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
