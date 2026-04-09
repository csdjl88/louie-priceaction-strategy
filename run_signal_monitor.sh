#!/usr/bin/env python3
"""
信号监听器 - 定时任务运行脚本

使用方法:
    python run_signal_monitor.py --interval 60 --duration 300

参数:
    --interval: 检测间隔(秒)，默认60
    --duration: 运行时间(秒)，默认300(5分钟)
    --symbols: 监控品种，默认 RB0 TA0 BR0 AL0 BU0
"""

import time
import argparse
import sys
import os
from datetime import datetime

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from signal_monitor import SignalMonitor


def main():
    parser = argparse.ArgumentParser(description='交易信号监听器')
    parser.add_argument('--interval', type=int, default=60, help='检测间隔(秒)')
    parser.add_argument('--duration', type=int, default=None, help='运行时间(秒)，不设置则永久运行')
    parser.add_argument('--symbols', nargs='+', 
                       default=['RB0', 'TA0', 'BR0', 'AL0', 'BU0'],
                       help='监控品种')
    
    args = parser.parse_args()
    
    # 信号回调
    def on_signal(symbol, signal_type, direction, price, confidence, reason):
        emoji = '🟢' if signal_type == 'long' else '🔴' if signal_type == 'short' else '⚪'
        print(f'{emoji} {symbol}: {signal_type} @ {price:.0f} 信心:{confidence:.0%} 原因:{reason}')
    
    # 创建监控器
    print(f'启动信号监听器...')
    print(f'  品种: {", ".join(args.symbols)}')
    print(f'  间隔: {args.interval}秒')
    print(f'  运行时长: {args.duration}秒')
    
    monitor = SignalMonitor(
        symbols=args.symbols,
        interval=args.interval
    )
    
    monitor.set_callback(on_signal)
    monitor.start()
    
    print(f'监听器已启动，每 {args.interval} 秒检测一次...')
    
    # 保持运行
    try:
        if args.duration:
            # 定时运行
            loops = args.duration // args.interval
            for i in range(loops):
                time.sleep(args.interval)
                quotes = monitor.get_quotes()
                if quotes:
                    prices = ', '.join([f'{s}:{q.get("close", 0):.0f}' 
                                     for s, q in quotes.items() if q.get('close')])
                    print(f'[{datetime.now().strftime("%H:%M:%S")}] 行情: {prices}')
        else:
            # 永久运行
            while True:
                time.sleep(args.interval)
                quotes = monitor.get_quotes()
                if quotes:
                    prices = ', '.join([f'{s}:{q.get("close", 0):.0f}' 
                                     for s, q in quotes.items() if q.get('close')])
                    print(f'[{datetime.now().strftime("%H:%M:%S")}] 行情: {prices}')
    except KeyboardInterrupt:
        print('\n收到停止信号...')
    
    monitor.stop()
    print('监听已停止')
    print('监听已停止')


if __name__ == '__main__':
    main()