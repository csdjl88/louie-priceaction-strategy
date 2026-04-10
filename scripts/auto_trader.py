#!/usr/bin/env python3
"""
auto_trader.py - 自动交易 + 实时监听系统
=========================================

功能:
1. 实时监控市场行情（新浪盘中 API）
2. PriceAction 策略自动检测信号
3. 发现信号自动开仓
4. 追踪持仓、计算盈亏、自动止损/止盈
5. 完整日志记录

使用:
    python auto_trader.py                          # 默认 10 万本金
    python auto_trader.py --capital 50000           # 5 万本金
    python auto_trader.py --interval 5            # 5 秒刷新
    python auto_trader.py --symbols ru rb al cf   # 只监控指定品种
    python auto_trader.py --dry-run                # 模拟模式（只记录信号，不下单）
"""

import argparse
import sys
import os
import time
import json
from datetime import datetime
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from data_fetcher import fetch_multi_realtime_quotes, fetch_futures_data
    from china_futures_strategy import ChinaFuturesStrategy
    from scripts.portfolio import Portfolio
except ImportError as e:
    print(f"错误: 导入模块失败 - {e}")
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────────────────────────────────
NAME_MAP = {
    'ru': '橡胶', 'rb': '螺纹钢', 'hc': '热轧卷板', 'i': '铁矿石',
    'j': '焦炭', 'jm': '焦煤', 'cu': '铜', 'al': '铝', 'zn': '锌',
    'ni': '镍', 'sn': '锡', 'bu': '沥青', 'ma': '甲醇', 'ta': 'PTA',
    'pp': '聚丙烯', 'l': '塑料', 'v': 'PVC', 'm': '豆粕', 'y': '豆油',
    'p': '棕榈油', 'cs': '玉米淀粉', 'c': '玉米', 'a': '黄大豆A',
    'b': '黄大豆B', 'oi': '菜籽油', 'rm': '菜粕', 'cf': '棉花',
    'sr': '白糖', 'au': '黄金', 'ag': '白银', 'sc': '原油',
}

ALL_SYMBOLS = list(NAME_MAP.keys())

# ──────────────────────────────────────────────────────────────────────────
# 品种筛选规则：夏普比优先
# ──────────────────────────────────────────────────────────────────────────
# 夏普比排序的白名单（从高到低），只交易这些品种
# 空头/做空用波段回测，做多/做多用日内回测
SHARPE_WHITELIST = [
    # 第一梯队：夏普比 > 5.0
    'jm',   # 焦煤 日内 Sharpe=12.04
    'p',    # 棕榈油 日内 Sharpe=7.69
    'cs',   # 玉米淀粉 日内 Sharpe=6.63
    'bu',   # 沥青 日内 Sharpe=5.68
    'v',    # PVC 日内 Sharpe=5.33
    # 第二梯队：夏普比 2.0~5.0
    'ta',   # PTA 波段 Sharpe=3.92
    'i',    # 铁矿石 波段 Sharpe=3.62
    'a',    # 黄大豆A
    'al',   # 铝
    'zn',   # 锌
    # 第三梯队：夏普比 1.0~2.0
    'pp',   # 聚丙烯
    'sc',   # 原油
    'ru',   # 橡胶
    'm',    # 豆粕
    'cf',   # 棉花
    'rb',   # 螺纹钢
    'sr',   # 白糖
    'ma',   # 甲醇
]

# 交易规则
MAX_POSITIONS = 3          # 最多持仓数
MAX_MARGIN_RATIO = 0.70   # 保证金上限（占本金比例）

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
    try:
        data = fetch_futures_data(symbol, days=60)
        if not data or len(data.get('closes', [])) < 30:
            return None

        closes  = data['closes']
        opens   = data['opens']
        highs   = data['highs']
        lows    = data['lows']

        if realtime_price and realtime_price > 0:
            closes[-1] = realtime_price
            highs[-1] = max(highs[-1], realtime_price)
            lows[-1]  = min(lows[-1], realtime_price)

        strategy = ChinaFuturesStrategy(symbol, require_trend=True)
        result = strategy.analyze(opens, highs, lows, closes, len(closes) - 1)

        action = result.get('action', 'none')
        if action == 'none':
            return None

        atr = result.get('atr', 0)
        price = closes[-1]

        return {
            'symbol': symbol.upper(),
            'name': NAME_MAP.get(symbol, symbol.upper()),
            'action': action,
            'price': price,
            'atr': atr,
            'confidence': result.get('confidence', 0),
            'trend': result.get('trend', 'unknown'),
            'reason': result.get('reason', ''),
            'suggested_stop': round(price - 2*atr) if action == 'long' else round(price + 2*atr),
            'suggested_target': round(price + 6*atr) if action == 'long' else round(price - 6*atr),
            'date': data['dates'][-1],
        }
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────
# 风险等级
# ──────────────────────────────────────────────────────────────────────────
def get_risk_level(dist_stop: float, pnl_pct: float) -> tuple:
    if dist_stop < 1.0 or pnl_pct < -8:
        return '🔴 极度危险', RED
    elif dist_stop < 2.0 or pnl_pct < -5:
        return '⚠️  高风险', YELLOW
    elif dist_stop < 3.0 or pnl_pct < -2:
        return '⚡ 中风险', BLUE
    return '✅ 正常', GREEN


# ──────────────────────────────────────────────────────────────────────────
# 全局变量
# ──────────────────────────────────────────────────────────────────────────
INTERVAL = 10
DRY_RUN = False
portfolio = None
_last_signals: Dict = {}
_log_dir = ''
_trade_log_file = ''
_closed_trades_file = ''
_capital = 100000


# ──────────────────────────────────────────────────────────────────────────
# 日志初始化
# ──────────────────────────────────────────────────────────────────────────
def init_logging(log_dir: str):
    global _log_dir, _trade_log_file, _closed_trades_file
    _log_dir = log_dir
    os.makedirs(log_dir, exist_ok=True)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    _trade_log_file = os.path.join(log_dir, f'trade_log_{ts}.csv')
    _closed_trades_file = os.path.join(log_dir, f'closed_trades_{ts}.csv')

    portfolio.set_log_file(_trade_log_file)
    portfolio.set_trade_csv(_closed_trades_file)

    # 记录启动状态
    status_file = os.path.join(log_dir, f'status_{ts}.json')
    with open(status_file, 'w') as f:
        json.dump({
            'event': 'START',
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'initial_capital': portfolio.initial_capital,
            'dry_run': DRY_RUN,
            'log_dir': log_dir,
        }, f, ensure_ascii=False, indent=2)


def log_message(msg: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"  {CYAN}[{ts}]{RESET} {msg}")
    if _log_dir:
        log_file = os.path.join(_log_dir, f'auto_trader_{datetime.now().strftime("%Y%m%d")}.log')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{ts}] {msg}\n")


# ──────────────────────────────────────────────────────────────────────────
# 交易执行
# ──────────────────────────────────────────────────────────────────────────
def execute_signal(signal: Dict, current_price: float):
    global portfolio, DRY_RUN

    sym = signal['symbol']
    action = signal['action']

    # ── 规则1：夏普比白名单过滤 ──
    if sym.lower() not in SHARPE_WHITELIST:
        return

    if sym in portfolio.positions:
        return

    if action not in ('long', 'short'):
        if sym in portfolio.positions:
            trade = portfolio.close_position(sym, current_price, reason='signal')
            if trade:
                log_message(f"📤 平仓 {sym} @ {current_price} | 盈亏 {trade.pnl:+.2f} ({trade.pnl_pct:+.2f}%) | 原因: {signal.get('reason','')}")
        return

    direction = action
    stop = signal['suggested_stop']
    target = signal['suggested_target']
    atr = signal['atr']
    price = current_price

    # ── 规则2：最多3个仓位 ──
    if len(portfolio.positions) >= MAX_POSITIONS:
        return

        # ── 规则3：按风险计算仓位（每笔风险 2%）先算手数，再算保证金 ──
    risk_percent = 0.02  # 每笔交易风险 2% 本金
    risk_amount = portfolio.initial_capital * risk_percent
    risk_per_contract = abs(price - stop) if stop and stop > 0 else price * 0.02
    volume = max(1, int(risk_amount / risk_per_contract))
    volume = min(volume, 5)  # 最多5手

    # 保证金检查（用计算后的手数）
    margin_needed = price * volume * portfolio.margin_rate
    current_margin = portfolio._get_margin_used()
    if (current_margin + margin_needed) / portfolio.initial_capital > MAX_MARGIN_RATIO:
        return

    if DRY_RUN:
        d = '买入' if direction == 'long' else '卖出'
        log_message(f"📋 [模拟] {d} {sym} @ {price} x{volume} | 止损 {stop} | 目标 {target} | ATR {atr:.2f} | 风险 {risk_percent*100:.0f}% | 信号: {signal.get('reason','')}")
        return

    success = portfolio.open_position(
        symbol=sym, direction=direction, entry_price=price,
        volume=volume, stop_loss=stop, target=target, atr=atr
    )

    if success:
        emoji = '🟢' if direction == 'long' else '🔴'
        d = '做多' if direction == 'long' else '做空'
        log_message(f"✅ {emoji} 开仓 {sym} {d} x{volume} @ {price} | 止损 {stop} | 目标 {target} | ATR {atr:.2f}")


def check_and_close_positions(prices: Dict[str, float]):
    global portfolio
    portfolio.update_all_positions(prices)

    for sym in list(portfolio.positions.keys()):
        current = prices.get(sym)
        if not current:
            continue
        trigger = portfolio.check_stop_triggered(sym, current)
        if trigger:
            reason = '止损' if trigger == 'stop_loss' else '止盈'
            trade = portfolio.close_position(sym, current, reason=trigger)
            if trade:
                emoji = '🔴' if trade.pnl < 0 else '🟢'
                log_message(f"{emoji} {reason} {sym} @ {current} | 盈亏 {trade.pnl:+.2f} ({trade.pnl_pct:+.2f}%) | 持仓 {trade.holding_days}天")


# ──────────────────────────────────────────────────────────────────────────
# 界面打印
# ──────────────────────────────────────────────────────────────────────────
def Clear_screen():
    os.system('clear' if os.name != 'nt' else 'cls')


def print_header():
    print()
    mode = "[模拟模式]" if DRY_RUN else ""
    print(c(f" ╔════════════════════════════════════════════════════════════════════════════════╗", BOLD + GREEN))
    print(c(f" ║         自动交易 + 实时监听  —  Louie PriceAction  {mode:9}║", BOLD + GREEN))
    print(c(f" ╚════════════════════════════════════════════════════════════════════════════════╝", BOLD + GREEN))
    print()


def print_signals(signals: List[Dict]):
    print(f"  {BOLD}【策略信号】{RESET}  (扫描 {len(ALL_SYMBOLS)} 个品种)")
    print(f"  {'─' * 80}")
    print(f"  {'品种':<10} {'信号':<14} {'价格':>10} {'ATR':>8} {'止损':>10} {'目标':>10} {'依据'}")
    print(f"  {'─' * 80}")
    if not signals:
        print(f"  {YELLOW}  暂无新信号{RESET}")
    else:
        for s in signals[:10]:
            action_col = GREEN if 'long' in s['action'] else RED
            print(f"  {s['name']:<10} {c(s['action'].upper(), action_col):<14} {s['price']:>10.0f} {s['atr']:>8.2f} {s['suggested_stop']:>10.0f} {s['suggested_target']:>10.0f} {s.get('reason','')[:12]}")
    print()


def print_positions(positions: List[Dict], status):
    if not positions:
        print(f"  {BOLD}【当前持仓】{RESET}  无持仓")
        print()
        return

    longs  = [p for p in positions if p['direction'] == 'long']
    shorts = [p for p in positions if p['direction'] == 'short']

    print(f"  {BOLD}【当前持仓】{RESET}  {status.position_count} 个仓位")
    print(f"  {'─' * 80}")

    for label, items in [('做多', longs), ('做空', shorts)]:
        if not items:
            continue
        print(f"  {BOLD}{label}{RESET}")
        print(f"  {'品种':<8} {'现价':>10} {'浮盈':>10} {'距止损':>8} {'距目标':>8} {'持仓':>6} {'风险'}")
        print(f"  {'─' * 68}")
        for p in items:
            risk, col = get_risk_level(p['distance_to_stop'], p['unrealized_pnl_pct'])
            pnl_str = f"{p['unrealized_pnl_pct']:+.2f}%"
            pnl_col = GREEN if p['unrealized_pnl_pct'] > 0 else RED
            print(f"  {p['symbol']:<8} {p['current_price']:>10.0f} {c(pnl_str, pnl_col):>10} {p['distance_to_stop']:>7.2f}% {p['distance_to_target']:>7.2f}% {p['days_held']:>5}天 {c(risk, col)}")
    print()


def print_account(status):
    margin_used = portfolio._get_margin_used()
    margin_ratio = margin_used / _capital * 100
    margin_col = RED if margin_ratio > 70 else YELLOW if margin_ratio > 50 else GREEN
    print(f"  {BOLD}【账户】{RESET}")
    print(f"  {'─' * 80}")
    total_col = GREEN if status.total_pnl >= 0 else RED
    print(f"  初始资金: {_capital:,.0f}  |  当前权益: {c(f'{status.capital:,.2f}', total_col)}")
    pnl_col = GREEN if status.total_pnl >= 0 else RED
    print(f"  持仓盈亏: {c(f'{status.position_pnl:+.2f}', GREEN if status.position_pnl >= 0 else RED)}  |  已实现: {c(f'{status.realized_pnl:+.2f}', GREEN if status.realized_pnl >= 0 else RED)}  |  总盈亏: {c(f'{status.total_pnl:+.2f}', pnl_col)} ({status.total_pnl/_capital*100:+.2f}%)")
    print(f"  胜率: {status.win_rate:.1f}%  ({status.winning_trades}胜 {status.losing_trades}负)  |  持仓: {status.position_count}/{MAX_POSITIONS}个  |  保证金: {c(f'{margin_ratio:.1f}%', margin_col)}  |  可用: {status.available:,.2f}")
    print()


# ──────────────────────────────────────────────────────────────────────────
# 主循环
# ──────────────────────────────────────────────────────────────────────────
def run_trader(capital: float = 100000,
              interval: int = 10,
              dry_run: bool = False,
              symbols: List[str] = None,
              scan_symbols: List[str] = None):
    global INTERVAL, DRY_RUN, portfolio, ALL_SYMBOLS, _capital

    INTERVAL = interval
    DRY_RUN = dry_run
    _capital = capital
    portfolio = Portfolio(initial_capital=capital)
    ALL_SYMBOLS = scan_symbols or ALL_SYMBOLS

    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs', datetime.now().strftime('%Y%m%d'))
    init_logging(log_dir)

    print_header()
    print(f"  {'='*80}")
    mode_str = "[模拟模式]" if dry_run else ""
    print(f"  {BOLD}自动交易启动{mode_str}{RESET}")
    print(f"  {'='*80}")
    print(f"  初始资金: {capital:,.0f}  |  刷新间隔: {interval}s  |  扫描品种: {len(ALL_SYMBOLS)}个")
    print(f"  规则: 夏普比优先 | 最多 {MAX_POSITIONS} 个仓位 | 保证金上限 {int(MAX_MARGIN_RATIO*100)}%")
    print(f"  日志目录: {log_dir}")
    if dry_run:
        print(f"  {YELLOW}⚠️  模拟模式：只产生信号，不执行交易{RESET}")
    print(f"  按 Ctrl+C 停止\n")

    try:
        while True:
            ts_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            Clear_screen()
            print_header()

            # 1. 获取所有品种实时行情
            quotes = fetch_multi_realtime_quotes(ALL_SYMBOLS)
            prices = {sym: q['last_price'] for sym, q in quotes.items() if q}

            # 2. 检查持仓（止损/止盈）
            check_and_close_positions(prices)

            # 3. 策略信号检测
            signals = []
            for sym in ALL_SYMBOLS:
                rt_price = prices.get(sym)
                sig = analyze_signal(sym, rt_price)
                if sig:
                    key = f"{sig['symbol']}_{sig['action']}"
                    if _last_signals.get(key) != sig['date']:
                        signals.append(sig)
                        _last_signals[key] = sig['date']
                        execute_signal(sig, rt_price or sig['price'])

            # 4. 打印状态
            status = portfolio.get_status()
            positions = portfolio.get_positions_with_prices(prices)

            print_signals(signals)
            print_positions(positions, status)
            print_account(status)

            print(f"  {ts_str}  |  {interval}s  |  Ctrl+C 退出")

            time.sleep(interval)

    except KeyboardInterrupt:
        final_status = portfolio.get_status()
        log_file = os.path.join(log_dir, f'final_status_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        with open(log_file, 'w') as f:
            json.dump({
                'event': 'STOP',
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'initial_capital': capital,
                'final_capital': final_status.capital,
                'total_pnl': final_status.total_pnl,
                'total_pnl_pct': round(final_status.total_pnl / capital * 100, 2),
                'winning_trades': final_status.winning_trades,
                'losing_trades': final_status.losing_trades,
                'win_rate': final_status.win_rate,
                'closed_trades': len(portfolio.closed_trades),
            }, f, ensure_ascii=False, indent=2)
        print(f"\n\n  {GREEN}自动交易已停止{RESET}")
        print(f"  最终权益: {final_status.capital:,.2f}  |  总盈亏: {final_status.total_pnl:,.2f} ({final_status.total_pnl/capital*100:+.2f}%)")
        print(f"  交易记录: {log_dir}")
        print()
        sys.exit(0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='自动交易 + 实时监听')
    parser.add_argument('--capital', type=float, default=100000, help='初始资金 (默认 100000)')
    parser.add_argument('--interval', '-i', type=int, default=10, help='刷新间隔秒数 (默认 10)')
    parser.add_argument('--dry-run', action='store_true', help='模拟模式（只产生信号，不下单）')
    parser.add_argument('--symbols', '-s', nargs='+', help='指定持仓品种 (如 ru rb)')
    parser.add_argument('--scan', nargs='+', help='指定扫描品种 (如 ru rb al cf)')
    args = parser.parse_args()

    run_trader(
        capital=args.capital,
        interval=args.interval,
        dry_run=args.dry_run,
        symbols=args.symbols,
        scan_symbols=args.scan
    )
