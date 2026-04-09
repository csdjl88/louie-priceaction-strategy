#!/bin/bash
# 期货信号检测脚本 - 供cron调用
cd /home/node/.openclaw/workspace/projects/louie-priceaction-strategy
UV_CACHE_DIR=/home/node/.openclaw/workspace/.uv-cache /home/node/.local/bin/uv run python -c "
from data_fetcher import fetch_multi_futures_data
from indicators import ema, atr
import warnings
warnings.filterwarnings('ignore')
from datetime import datetime

names = {
    'rb': '螺纹钢', 'hc': '热轧卷板', 'i': '铁矿石', 'j': '焦炭', 'jm': '焦煤',
    'cu': '铜', 'al': '铝', 'zn': '锌', 'ni': '镍', 'sn': '锡',
    'ru': '橡胶', 'bu': '沥青', 'ma': '甲醇', 'ta': 'PTA', 'ta0': 'PTA',
    'pp': '聚丙烯', 'l': '塑料', 'v': 'PVC', 'm': '豆粕', 'y': '豆油',
    'p': '棕榈油', 'cs': '玉米淀粉', 'c': '玉米', 'a': '黄大豆', 'b': '黄大豆',
    'oi': '菜籽油', 'rm': '菜籽粕', 'cf': '棉花', 'sr': '白糖',
    'au': '黄金', 'ag': '白银', 'sc': '原油'
}

symbols = list(names.keys())
data = fetch_multi_futures_data(symbols, days=10)

print(f'=== 期货信号检测 {datetime.now().strftime(\"%Y-%m-%d %H:%M:%S\")} ===')
print()

buy_signals = []
sell_signals = []

for sym in symbols:
    if sym not in data:
        continue
    
    d = data[sym]
    closes = d['closes']
    opens = d['opens']
    highs = d['highs']
    lows = d['lows']
    dates = d['dates']
    
    if len(closes) < 50:
        continue
    
    idx = len(closes) - 1
    closes_until_idx = closes[:idx+1]
    
    ema20 = ema(closes_until_idx, 20)
    ema50 = ema(closes_until_idx, 50)
    atr_val = atr(opens[:idx+1], highs[:idx+1], lows[:idx+1], closes[:idx+1], idx, 14)
    
    if ema20 is None or ema50 is None or atr_val is None or atr_val == 0:
        continue
    
    close = closes[idx]
    trend = '上涨' if ema20 > ema50 else '下跌'
    
    signal = None
    if trend == '上涨' and close < ema20 and close > ema20 * 0.98:
        signal = '做多'
    elif trend == '下跌' and close > ema20 and close < ema20 * 1.02:
        signal = '做空'
    
    if signal:
        info = {
            'symbol': sym,
            'name': names[sym],
            'date': dates[idx],
            'close': close,
            'ema20': ema20,
            'atr': atr_val,
            'stop': close - 2 * atr_val if signal == '做多' else close + 2 * atr_val,
            'target': close + 6 * atr_val if signal == '做多' else close - 6 * atr_val,
            'trend': trend,
            'signal': signal
        }
        if signal == '做多':
            buy_signals.append(info)
        else:
            sell_signals.append(info)

if buy_signals:
    print(f'🟢 做多信号 ({len(buy_signals)}个):')
    for s in sorted(buy_signals, key=lambda x: x['date'], reverse=True):
        print(f'  {s[\"date\"]} {s[\"symbol\"]}({s[\"name\"]}): 现价{s[\"close\"]:.2f} 入场{s[\"close\"]:.2f} 止损{s[\"stop\"]:.2f} 目标{s[\"target\"]:.2f}')
else:
    print('🟢 做多信号: 无')

print()

if sell_signals:
    print(f'🔴 做空信号 ({len(sell_signals)}个):')
    for s in sorted(sell_signals, key=lambda x: x['date'], reverse=True):
        print(f'  {s[\"date\"]} {s[\"symbol\"]}({s[\"name\"]}): 现价{s[\"close\"]:.2f} 入场{s[\"close\"]:.2f} 止损{s[\"stop\"]:.2f} 目标{s[\"target\"]:.2f}')
else:
    print('🔴 做空信号: 无')

print()
print('=' * 50)
"
