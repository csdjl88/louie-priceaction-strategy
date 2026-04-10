#!/usr/bin/env python3
"""
realtime_monitor.py - 持仓 + 策略信号实时监听
================================================

使用新浪盘中实时行情，持续监控：
1. 持仓浮动盈亏与风险
2. 策略信号检测（PriceAction 趋势跟踪）

使用:
    python realtime_monitor.py                    # 默认10秒刷新
    python realtime_monitor.py --interval 5       # 5秒刷新
    python realtime_monitor.py --signals-only     # 只看信号，不管持仓
    python realtime_monitor.py --no-signals        # 只看持仓，不管信号
"""

import argparse
import sys
import time
import os
from datetime import datetime
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from data_fetcher import fetch_multi_realtime_quotes, fetch_futures_data
    from china_futures_strategy import ChinaFuturesStrategy
except ImportError as e:
    print(f"错误: 导入模块失败 - {e}")
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────
# 持仓数据（需要手动维护，或接入外部持仓系统）
# ──────────────────────────────────────────────────────────────────────────
POSITIONS = [
    {'symbol': 'RU0', 'direction': 'long',  'entry_price': 16225.00, 'atr': 414.64,  'entry_date': '2026-03-24', 'stop_loss': 15395.71, 'target': 18712.86},
    {'symbol': 'M0',  'direction': 'long',  'entry_price': 2961.00,  'atr': 81.57,   'entry_date': '2026-03-24', 'stop_loss': 2797.86,  'target': 3450.43},
    {'symbol': 'A0',  'direction': 'long',  'entry_price': 4655.00,  'atr': 103.29,  'entry_date': '2026-03-24', 'stop_loss': 4448.43,  'target': 5274.71},
    {'symbol': 'CF0', 'direction': 'long',  'entry_price': 15215.00, 'atr': 246.79,  'entry_date': '2026-03-24', 'stop_loss': 14721.43, 'target': 16695.71},
    {'symbol': 'AL0', 'direction': 'long',  'entry_price': 23860.00, 'atr': 618.93,  'entry_date': '2026-03-25', 'stop_loss': 22622.14, 'target': 27573.57},
    {'symbol': 'P0',  'direction': 'long',  'entry_price': 9510.00,  'atr': 304.43,  'entry_date': '2026-03-25', 'stop_loss': 8901.14,  'target': 11336.57},
    {'symbol': 'B0',  'direction': 'long',  'entry_price': 3708.00,  'atr': 94.14,   'entry_date': '2026-03-25', 'stop_loss': 3519.71,  'target': 4272.86},
    {'symbol': 'C0',  'direction': 'long',  'entry_price': 2369.00,  'atr': 19.07,   'entry_date': '2026-03-27', 'stop_loss': 2330.86,  'target': 2483.43},
    {'symbol': 'V0',  'direction': 'long',  'entry_price': 5551.00,  'atr': 323.64,  'entry_date': '2026-03-30', 'stop_loss': 4903.71,  'target': 7492.86},
    {'symbol': 'RB0', 'direction': 'long',  'entry_price': 3121.00,  'atr': 26.57,   'entry_date': '2026-03-31', 'stop_loss': 3067.86,  'target': 3280.43},
    {'symbol': 'L0',  'direction': 'long',  'entry_price': 8380.00,  'atr': 469.79,  'entry_date': '2026-04-01', 'stop_loss': 7440.43,  'target': 11198.71},
    {'symbol': 'OI0', 'direction': 'long',  'entry_price': 9720.00,  'atr': 176.64,  'entry_date': '2026-04-01', 'stop_loss': 9366.71,  'target': 10779.86},
    {'symbol': 'SR0', 'direction': 'long',  'entry_price': 5380.00,  'atr': 68.50,   'entry_date': '2026-04-01', 'stop_loss': 5243.00,  'target': 5791.00},
    {'symbol': 'HC0', 'direction': 'long',  'entry_price': 3285.00,  'atr': 26.64,   'entry_date': '2026-04-03', 'stop_loss': 3231.71,  'target': 3444.86},
    {'symbol': 'NI0', 'direction': 'short', 'entry_price': 136130.00,'atr': 3791.43,  'entry_date': '2026-03-25', 'stop_loss': 143712.86,'target': 113381.43},
    {'symbol': 'SN0', 'direction': 'short', 'entry_price': 370720.00,'atr': 19625.00, 'entry_date': '2026-03-30', 'stop_loss': 409970.00,'target': 252970.00},
    {'symbol': 'ZN0', 'direction': 'short', 'entry_price': 23600.00, 'atr': 391.79,  'entry_date': '2026-04-02', 'stop_loss': 24383.57, 'target': 21249.29},
]

NAME_MAP = {
    'ru': '橡胶', 'm': '豆粕', 'a': '黄大豆A', 'cf': '棉花', 'al': '铝',
    'p': '棕榈油', 'b': '黄大豆B', 'c': '玉米', 'v': 'PVC', 'rb': '螺纹钢',
    'l': '塑料', 'oi': '菜籽油', 'sr': '白糖', 'hc': '热轧卷板',
    'ni': '镍', 'sn': '锡', 'zn': '锌',
}

# 全部可监控品种（策略扫描用）
ALL_SYMBOLS = ['ru', 'rb', 'hc', 'i', 'j', 'jm', 'cu', 'al', 'zn', 'ni', 'sn',
                'bu', 'ma', 'ta', 'pp', 'l', 'v', 'm', 'y', 'p', 'cs', 'c', 'a', 'b',
                'oi', 'rm', 'cf', 'sr', 'au', 'ag', 'sc']


# ──────────────────────────────────────────────────────────────────────────
# 颜色输出
# ──────────────────────────────────────────────────────────────────────────
RED    = '\033[91m'
GREEN  = '\033[92m'
YELLOW = '\033[93m'
BLUE   = '\033[94m'
BOLD   = '\033[1m'
CYAN   = '\033[96m'
RESET  = '\033[0m'

def c(text, color): return f"{color}{text}{RESET}"


# ──────────────────────────────────────────────────────────────────────────
# 策略信号分析
# ──────────────────────────────────────────────────────────────────────────
def analyze_signal(symbol: str, realtime_price: Optional[float] = None) -> Optional[Dict]:
    """
    使用 PriceAction 策略分析信号
    """
    try:
        sym = symbol.lower().replace('0', '')
        data = fetch_futures_data(sym, days=60)
        if not data or len(data.get('closes', [])) < 30:
            return None

        closes  = data['closes']
        opens   = data['opens']
        highs   = data['highs']
        lows    = data['lows']
        volumes = data['volumes']
        dates   = data['dates']

        # 注入实时价格到最新K线
        if realtime_price and realtime_price > 0:
            closes[-1] = realtime_price
            highs[-1] = max(highs[-1], realtime_price)
            lows[-1]  = min(lows[-1], realtime_price)

        strategy = ChinaFuturesStrategy(sym, require_trend=True)
        idx = len(closes) - 1
        result = strategy.analyze(opens, highs, lows, closes, idx)

        action = result.get('action', 'none')
        if action == 'none':
            return None

        trend = result.get('trend', 'unknown')
        confidence = result.get('confidence', 0)
        atr = result.get('atr', 0)
        reason = result.get('reason', result.get('signal_direction', ''))

        signal_emoji = {
            'long': '🟢 做多', 'short': '🔴 做空',
            'close_long': '🔵 平多', 'close_short': '🔵 平空'
        }
        trend_emoji = {
            'bullish': '📈 上涨', 'bearish': '📉 下跌', 'unknown': '⚖️ 震荡'
        }

        return {
            'symbol': sym.upper(),
            'name': NAME_MAP.get(sym, sym.upper()),
            'action': action,
            'action_text': signal_emoji.get(action, action),
            'trend': trend,
            'trend_text': trend_emoji.get(trend, trend),
            'price': closes[-1],
            'atr': atr,
            'confidence': confidence,
            'reason': reason,
            'date': dates[-1],
            'suggested_stop': round(closes[-1] - 2*atr) if action == 'long' else round(closes[-1] + 2*atr),
            'suggested_target': round(closes[-1] + 6*atr) if action == 'long' else round(closes[-1] - 6*atr),
        }
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────
# 持仓状态计算
# ──────────────────────────────────────────────────────────────────────────
def calculate_position_stats(positions: List[Dict], quotes: Dict) -> List[Dict]:
    results = []
    now = datetime.now()
    for pos in positions:
        sym = pos['symbol'].replace('0', '').lower()
        q = quotes.get(sym)
        if not q:
            continue
        current = q['last_price']
        entry = pos['entry_price']
        stop = pos['stop_loss']
        target = pos['target']
        if pos['direction'] == 'long':
            pnl_pct = (current - entry) / entry * 100
            dist_stop = (current - stop) / stop * 100
            dist_target = (target - current) / target * 100
        else:
            pnl_pct = (entry - current) / entry * 100
            dist_stop = (stop - current) / stop * 100
            dist_target = (current - target) / target * 100
        entry_dt = datetime.strptime(pos['entry_date'], '%Y-%m-%d')
        days = (now - entry_dt).days
        results.append({
            'symbol': pos['symbol'],
            'name': NAME_MAP.get(sym, sym.upper()),
            'direction': pos['direction'],
            'entry_price': entry,
            'current_price': current,
            'pnl_pct': round(pnl_pct, 2),
            'distance_to_stop': round(dist_stop, 2),
            'distance_to_target': round(dist_target, 2),
            'days_held': days,
            'change_pct': q['change_pct'],
            'update_time': q['datetime'],
        })
    return sorted(results, key=lambda x: x['pnl_pct'], reverse=True)


def get_risk_level(dist_stop: float, pnl_pct: float) -> tuple:
    if dist_stop < 1.0 or pnl_pct < -8:
        return '🔴 极度危险', RED
    elif dist_stop < 2.0 or pnl_pct < -5:
        return '⚠️  高风险', YELLOW
    elif dist_stop < 3.0 or pnl_pct < -2:
        return '⚡ 中风险', BLUE
    else:
        return '✅ 正常', GREEN


# ──────────────────────────────────────────────────────────────────────────
# 界面打印
# ──────────────────────────────────────────────────────────────────────────
def clear_screen():
    os.system('clear' if os.name != 'nt' else 'cls')


def print_header():
    print()
    print(c(f" ╔══════════════════════════════════════════════════════════════════════════╗", BOLD + GREEN))
    print(c(f" ║         持仓实时监听 + 策略信号检测  —  Louie PriceAction           ║", BOLD + GREEN))
    print(c(f" ╚══════════════════════════════════════════════════════════════════════════╝", BOLD + GREEN))
    print()


def print_signals(signals: List[Dict], update_time: str):
    print(f"  {BOLD}【策略信号】{RESET}  (扫描 {len(ALL_SYMBOLS)} 个品种)     数据: {update_time}")
    print(f"  {'─' * 82}")
    hdr = f"  {'品种':<10} {'信号':<14} {'趋势':<10} {'价格':>10} {'ATR':>8} {'建议止损':>10} {'建议目标':>10}"
    print(hdr)
    print(f"  {'─' * 82}")
    if not signals:
        print(f"  {YELLOW}  暂无信号（等待策略触发）{RESET}")
    else:
        for s in signals:
            action_col = GREEN if '做多' in s['action_text'] else RED if '做空' in s['action_text'] else BLUE
            trend_col = GREEN if '上涨' in s['trend_text'] else RED if '下跌' in s['trend_text'] else YELLOW
            conf = '★' * max(1, int(s['confidence'] * 5)) if s['confidence'] > 0 else '-'
            print(f"  {s['name']:<10} {c(s['action_text'], action_col):<14} {c(s['trend_text'], trend_col):<10} {s['price']:>10.0f} {s['atr']:>8.2f} {s['suggested_stop']:>10.0f} {s['suggested_target']:>10.0f} {conf}")
    print()


def print_positions(results: List[Dict], update_time: str):
    longs  = [r for r in results if r['direction'] == 'long']
    shorts = [r for r in results if r['direction'] == 'short']

    print(f"  数据更新: {update_time}          间隔: {INTERVAL}s          Ctrl+C 退出")
    print(f"  {'─' * 82}")

    print(f"\n  {BOLD}【做多持仓】{RESET}")
    print(f"  {'─' * 82}")
    hdr = f"  {'品种':<8} {'现价':>10} {'浮盈':>10} {'距止损':>8} {'距目标':>8} {'持仓':>6} {'风险'}"
    print(hdr)
    print(f"  {'─' * 82}")
    for r in longs:
        risk, col = get_risk_level(r['distance_to_stop'], r['pnl_pct'])
        pnl_str = f"{r['pnl_pct']:+.2f}%"
        pnl_col = GREEN if r['pnl_pct'] > 0 else RED
        print(f"  {r['name']:<8} {r['current_price']:>10.0f} {c(pnl_str, pnl_col):>10} {r['distance_to_stop']:>7.2f}% {r['distance_to_target']:>7.2f}% {r['days_held']:>5}天 {c(risk, col)}")

    print(f"\n  {BOLD}【做空持仓】{RESET}")
    print(f"  {'─' * 82}")
    print(hdr.replace('做多', '做空'))
    print(f"  {'─' * 82}")
    for r in shorts:
        risk, col = get_risk_level(r['distance_to_stop'], r['pnl_pct'])
        pnl_str = f"{r['pnl_pct']:+.2f}%"
        pnl_col = GREEN if r['pnl_pct'] > 0 else RED
        print(f"  {r['name']:<8} {r['current_price']:>10.0f} {c(pnl_str, pnl_col):>10} {r['distance_to_stop']:>7.2f}% {r['distance_to_target']:>7.2f}% {r['days_held']:>5}天 {c(risk, col)}")

    avg_long  = sum(r['pnl_pct'] for r in longs)  / len(longs)  if longs  else 0
    avg_short = sum(r['pnl_pct'] for r in shorts) / len(shorts) if shorts else 0
    wins   = len([r for r in results if r['pnl_pct'] > 0])
    losses = len([r for r in results if r['pnl_pct'] <= 0])

    print()
    print(f"  {'─' * 82}")
    avg_long_col = GREEN if avg_long > 0 else RED
    avg_short_col = GREEN if avg_short > 0 else RED
    print(f"  {BOLD}汇总:{RESET}  做多平均 {c(f'{avg_long:+.2f}%', avg_long_col)}  |  "
          f"做空平均 {c(f'{avg_short:+.2f}%', avg_short_col)}  |  "
          f"盈利 {wins}个  亏损 {losses}个")

    danger = [r for r in results if r['distance_to_stop'] < 2.0 or r['pnl_pct'] < -5]
    if danger:
        print()
        print(c(f"  ⚠️  风险警示:", RED + BOLD))
        for r in danger:
            print(c(f"    • {r['name']}: 距止损 {r['distance_to_stop']:.2f}% | 浮亏 {r['pnl_pct']:+.2f}%", RED))


# ──────────────────────────────────────────────────────────────────────────
# 主循环
# ──────────────────────────────────────────────────────────────────────────
INTERVAL = 10
_last_signal_cache = {}  # 防止重复信号


def run_monitor(interval: int = 10, show_positions: bool = True, show_signals: bool = True,
                 scan_symbols: List[str] = None, position_symbols: List[str] = None):
    """运行监听主循环"""
    global INTERVAL
    INTERVAL = interval

    pos_list = POSITIONS
    if position_symbols:
        pos_list = [p for p in POSITIONS if p['symbol'].replace('0', '').lower() in [s.lower() for s in position_symbols]]

    scan_list = scan_symbols or ALL_SYMBOLS

    print_header()
    mode = []
    if show_signals:   mode.append("策略信号")
    if show_positions: mode.append("持仓监控")
    print(f"\n  {YELLOW}正在启动实时监听...{RESET}")
    print(f"  模式: {', '.join(mode)}")
    print(f"  持仓品种: {len(pos_list)}个  |  信号扫描: {len(scan_list)}个")
    print(f"  刷新间隔: {interval}秒")
    print(f"\n  {YELLOW}按 Ctrl+C 停止监听{RESET}\n")

    try:
        while True:
            update_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            clear_screen()
            print_header()

            signals = []
            quotes = {}

            # 1. 获取实时行情（批量）
            all_syms = list(set(
                [p['symbol'].replace('0', '').lower() for p in pos_list] +
                scan_list
            ))
            quotes = fetch_multi_realtime_quotes(all_syms)

            # 2. 策略信号检测
            if show_signals:
                print(f"  {CYAN}正在扫描策略信号...{RESET}")
                for sym in scan_list:
                    rt_price = quotes.get(sym, {}).get('last_price')
                    sig = analyze_signal(sym, rt_price)
                    if sig:
                        # 过滤重复信号
                        key = f"{sig['symbol']}_{sig['action']}"
                        if _last_signal_cache.get(key) != sig['date']:
                            signals.append(sig)
                            _last_signal_cache[key] = sig['date']
                signals.sort(key=lambda x: (
                    0 if '做多' in x['action_text'] else 1 if '做空' in x['action_text'] else 2,
                    -x['confidence']
                ))
                print_signals(signals, update_str)

            # 3. 持仓监控
            if show_positions:
                results = calculate_position_stats(pos_list, quotes)
                print_positions(results, update_str)

                # 风险报警
                for r in results:
                    if r['distance_to_stop'] < 1.0:
                        print(c(f"\n  🚨 紧急! {r['name']} 距止损仅 {r['distance_to_stop']:.2f}%!", RED + BOLD))
                    elif r['distance_to_stop'] < 2.0:
                        print(c(f"\n  ⚠️  警告! {r['name']} 距止损 {r['distance_to_stop']:.2f}%", YELLOW + BOLD))

            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n\n  {GREEN}监听已停止{RESET}\n")
        sys.exit(0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='持仓实时监听 + 策略信号检测')
    parser.add_argument('--interval', '-i', type=int, default=10, help='刷新间隔(秒)')
    parser.add_argument('--signals-only', action='store_true', help='只看策略信号')
    parser.add_argument('--no-signals', action='store_true', help='只看持仓，不管信号')
    parser.add_argument('--symbols', '-s', nargs='+', help='指定持仓品种(如 ru rb)')
    parser.add_argument('--scan', nargs='+', help='指定扫描信号品种(如 ru rb al)')
    args = parser.parse_args()

    run_monitor(
        interval=args.interval,
        show_positions=not args.signals_only,
        show_signals=not args.no_signals,
        scan_symbols=args.scan,
        position_symbols=args.symbols
    )
