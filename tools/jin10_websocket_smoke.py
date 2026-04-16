#!/usr/bin/env python3
# coding=utf-8
"""
测试金十数据二进制 WebSocket 运行时（带飞书推送）

运行此脚本测试完整的连接、登录、消息接收、统一去重、飞书推送流程。
"""

import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
DEFAULT_FREQUENCY_WORDS_PATH = PROJECT_ROOT / "config" / "frequency_words.txt"

# 添加项目根目录到路径
sys.path.insert(0, str(PROJECT_ROOT))

# 本地手工 smoke test 不依赖当前工作目录
os.environ.setdefault("CONFIG_PATH", str(DEFAULT_CONFIG_PATH))
os.environ.setdefault("FREQUENCY_WORDS_PATH", str(DEFAULT_FREQUENCY_WORDS_PATH))

from trendradar.core.loader import load_config
from trendradar.websocket.testing import build_jin10_test_runtime


def on_news_received(event) -> None:
    print("\n" + "=" * 80)
    print("📰 收到新闻（回调）")
    print("=" * 80)
    print(
        json.dumps(
            {
                "channel": event.channel,
                "event_type": event.event_type,
                "source_message_id": event.source_message_id,
                "dedup_key": event.dedup_key,
                "title": event.title,
                "content": event.content,
                "published_at": event.published_at,
                "detail_url": event.detail_url,
                "meta": event.meta,
                "raw_payload": event.raw_payload,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print("=" * 80 + "\n")


def _print_runtime_stats(runtime) -> None:
    stats = runtime.get_stats()
    print("\n" + "=" * 80)
    print("📊 WebSocket 运行统计")
    print("=" * 80)
    print(f"运行状态: {'运行中' if stats['running'] else '已停止'}")
    print(f"运行时长: {stats['uptime_seconds']:.0f}秒" if stats['uptime_seconds'] else "未运行")
    print(f"队列积压: {stats['queue_size']}")
    print(f"队列丢弃: {stats['queue_dropped']}")
    print(f"接收消息: {stats['pipeline']['total_received']}")
    print(f"重复过滤: {stats['pipeline']['filtered_duplicate']}")
    print(f"发送成功: {stats['pipeline']['sent_success']}")
    print(f"发送失败: {stats['pipeline']['sent_failed']}")
    for name, channel_stats in stats["channels"].items():
        print("-" * 80)
        print(f"渠道: {name}")
        print(f"连接状态: {'已连接' if channel_stats['connected'] else '已断开'}")
        print(f"总消息数: {channel_stats['message_count']}")
        print(f"新闻数: {channel_stats['news_count']}")
        print(f"心跳数: {channel_stats['heartbeat_count']}")
        print(f"错误数: {channel_stats['error_count']}")
        print(f"协议错误: {channel_stats['protocol_error_count']}")
        print(f"连续失败: {channel_stats['consecutive_failures']}")
        print(f"重连次数: {channel_stats['total_reconnects']}")
        print(f"最后错误: {channel_stats['last_error'] or '-'}")
        print(f"扩展信息: {json.dumps(channel_stats.get('extra', {}), ensure_ascii=False)}")
    print("=" * 80)


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║        金十数据 WebSocket 运行时测试（带飞书推送）            ║
╚══════════════════════════════════════════════════════════════╝
    """)

    config = load_config()
    runtime, stats_printer = build_jin10_test_runtime(
        config,
        event_callback=on_news_received,
    )
    jin10_config = config.get("WEBSOCKET", {}).get("CHANNELS", {}).get("jin10", {})

    print(f"📡 连接地址: {jin10_config.get('URL', '(未配置)')}")
    print("🔧 协议版本: 二进制 + XOR加密")
    print(f"⏰ 开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    try:
        started = runtime.start()
        if not started:
            raise RuntimeError("websocket runtime 未启动，请检查 WEBSOCKET 配置")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n⏹️ 用户中断")
        runtime.stop()
    finally:
        runtime.stop()
        stats_printer()
        _print_runtime_stats(runtime)


if __name__ == "__main__":
    print("""
提示：
  - 此工具会启动正式的 websocket runtime，并接入金十渠道
  - 使用完整的二进制协议 + XOR加密
  - 支持自动重连、lastList 历史列表、实时快讯
  - 支持统一去重（避免与热榜/RSS/WebSocket 重复推送）
  - 如果配置了飞书 webhook，会自动推送到飞书
  - 按 Ctrl+C 停止

运行方式：
  python tools/jin10_websocket_smoke.py
""")
    main()
