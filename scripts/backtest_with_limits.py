#!/usr/bin/env python3
"""
backtest_with_limits.py - 带仓位限制的回测
==========================================

基于最新策略规则回测：
- 夏普比白名单品种筛选
- 最多 3 个仓位
- 保证金上限 70%
- 初始资金 100,000

使用方法:
    uv run python scripts/backtest_with_limits.py --days 365
"""

import argparse
import sys
import os
from datetime import datetime
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_fetcher import fetch_multi_futures_data
from china_futures_strategy import ChinaFuturesStrategy


# ──────────────────────────────────────────────────────────────────────────
# 夏普比白名单（与 auto_trader.py 保持一致）
# ──────────────────────────────────────────────────────────────────────────
SHARPE_WHITELIST = [
    'jm', 'p', 'cs', 'bu', 'v',     # 第一梯队
    'ni', 'ta', 'i', 'ag', 'a', 'al', 'zn',  # 第二梯队
    'pp', 'sc', 'ru', 'm', 'cf', 'rb', 'sr', 'ma',  # 第三梯队
]

MAX_POSITIONS = 3
MAX_MARGIN_RATIO = 0.70
INITIAL_CAPITAL = 100000
MARGIN_RATE = 0.12
COMMISSION_RATE = 0.0003


# ──────────────────────────────────────────────────────────────────────────
# 简化 Portfolio（用于回测）
# ──────────────────────────────────────────────────────────────────────────
class BacktestPortfolio:
    def __init__(self, initial_capital: float = INITIAL_CAPITAL):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, dict] = {}  # symbol -> {direction, entry_price, volume, stop, target}
        self.closed_trades: List[dict] = []
        self.margin_rate = MARGIN_RATE
        self.commission_rate = COMMISSION_RATE

    def _get_margin_used(self) -> float:
        return sum(
            p['entry_price'] * p['volume'] * self.margin_rate
            for p in self.positions.values()
        )

    def can_open(self, price: float) -> bool:
        if len(self.positions) >= MAX_POSITIONS:
            return False
        margin = price * self.margin_rate
        return (self._get_margin_used() + margin) / self.initial_capital <= MAX_MARGIN_RATIO

    def open_position(self, symbol: str, direction: str, entry_price: float,
                    volume: int, stop_loss: float, target: float):
        if symbol in self.positions:
            return False
        commission = entry_price * volume * self.commission_rate
        self.cash -= commission
        self.positions[symbol] = {
            'direction': direction,
            'entry_price': entry_price,
            'volume': volume,
            'stop_loss': stop_loss,
            'target': target,
            'entry_commission': commission,
        }
        return True

    def check_triggers(self, symbol: str, current_price: float) -> Optional[str]:
        pos = self.positions.get(symbol)
        if not pos:
            return None
        d = pos['direction']
        sl = pos['stop_loss']
        tp = pos['target']
        if d == 'long':
            if current_price <= sl:
                return 'stop_loss'
            if tp > 0 and current_price >= tp:
                return 'target'
        else:
            if current_price >= sl:
                return 'stop_loss'
            if tp > 0 and current_price <= tp:
                return 'target'
        return None

    def close_position(self, symbol: str, exit_price: float, reason: str) -> dict:
        pos = self.positions.pop(symbol, None)
        if not pos:
            return None
        vol = pos['volume']
        entry = pos['entry_price']
        exit_comm = exit_price * vol * self.commission_rate
        self.cash -= exit_comm

        if pos['direction'] == 'long':
            pnl = (exit_price - entry) * vol
        else:
            pnl = (entry - exit_price) * vol

        net_pnl = pnl - pos['entry_commission'] - exit_comm
        margin = entry * vol * self.margin_rate
        self.cash += margin + net_pnl

        return {
            'symbol': symbol, 'direction': pos['direction'],
            'entry_price': entry, 'exit_price': exit_price,
            'volume': vol, 'pnl': net_pnl, 'exit_reason': reason,
        }

    def get_capital(self, prices: Dict[str, float]) -> float:
        margin = self._get_margin_used()
        pos_pnl = 0
        for sym, pos in self.positions.items():
            cur = prices.get(sym, pos['entry_price'])
            if pos['direction'] == 'long':
                pos_pnl += (cur - pos['entry_price']) * pos['volume']
            else:
                pos_pnl += (pos['entry_price'] - cur) * pos['volume']
        return self.cash + margin + pos_pnl


# ──────────────────────────────────────────────────────────────────────────
# 回测核心
# ──────────────────────────────────────────────────────────────────────────
def run_backtest(symbol: str, days: int = 365, mode: str = 'swing') -> dict:
    """单品种回测"""
    data = fetch_multi_futures_data([symbol], days=days)
    if not data or symbol not in data:
        return None

    d = data[symbol]
    closes = d['closes']
    opens = d['opens']
    highs = d['highs']
    lows = d['lows']
    volumes = d['volumes']
    dates = d['dates']

    if len(closes) < 30:
        return None

    strategy = ChinaFuturesStrategy(symbol, trading_mode=mode, require_trend=True)
    portfolio = BacktestPortfolio(initial_capital=INITIAL_CAPITAL)

    equity_curve = []
    daily_stats = {}

    for i in range(5, len(closes)):
        current_price = closes[i]
        date = dates[i]

        # 更新每日统计
        capital = portfolio.get_capital({symbol: current_price})
        equity_curve.append({'date': date, 'capital': capital})

        # 检查持仓触发
        for sym in list(portfolio.positions.keys()):
            trigger = portfolio.check_triggers(sym, current_price)
            if trigger:
                trade = portfolio.close_position(sym, current_price, trigger)
                if trade:
                    portfolio.closed_trades.append(trade)

        # 策略信号
        result = strategy.analyze(opens, highs, lows, closes, i)
        action = result.get('action', 'none')

        if action in ('long', 'short') and symbol not in portfolio.positions:
            if portfolio.can_open(current_price):
                atr = result.get('atr', 0)
                stop = result.get('stop_loss', current_price - 2*atr if action == 'long' else current_price + 2*atr)
                target = result.get('take_profit', current_price + 6*atr if action == 'long' else current_price - 6*atr)
                portfolio.open_position(symbol, action, current_price, 1, stop, target)

    # 平掉所有剩余持仓（最后一天收盘价）
    final_price = closes[-1]
    for sym in list(portfolio.positions.keys()):
        trade = portfolio.close_position(sym, final_price, 'end_of_backtest')
        if trade:
            portfolio.closed_trades.append(trade)

    # 统计数据
    wins = [t for t in portfolio.closed_trades if t['pnl'] > 0]
    losses = [t for t in portfolio.closed_trades if t['pnl'] <= 0]
    total_pnl = sum(t['pnl'] for t in portfolio.closed_trades)
    final_capital = INITIAL_CAPITAL + total_pnl
    returns = (final_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    # 最大回撤
    peak = INITIAL_CAPITAL
    max_dd = 0
    for eq in equity_curve:
        if eq['capital'] > peak:
            peak = eq['capital']
        dd = (peak - eq['capital']) / peak * 100
        if dd > max_dd:
            max_dd = dd

    win_rate = len(wins) / len(portfolio.closed_trades) * 100 if portfolio.closed_trades else 0

    return {
        'symbol': symbol,
        'total_trades': len(portfolio.closed_trades),
        'winning_trades': len(wins),
        'losing_trades': len(losses),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'total_return': returns,
        'max_drawdown': max_dd,
        'final_capital': final_capital,
        'initial_capital': INITIAL_CAPITAL,
        'trades': portfolio.closed_trades,
        'equity_curve': equity_curve,
    }


def run_multi_backtest(symbols: List[str], days: int = 365, mode: str = 'swing') -> List[dict]:
    """多品种回测"""
    # 过滤白名单
    filtered = [s for s in symbols if s.lower() in SHARPE_WHITELIST]
    print(f"夏普比白名单过滤: {len(symbols)} -> {len(filtered)} 个品种")
    print(f"规则: 最多 {MAX_POSITIONS} 仓位 | 保证金上限 {int(MAX_MARGIN_RATIO*100)}% | 初始资金 {INITIAL_CAPITAL:,.0f}")
    print()

    results = []
    for sym in filtered:
        print(f"  回测 {sym}...", end=" ", flush=True)
        r = run_backtest(sym, days=days, mode=mode)
        if r:
            results.append(r)
            print(f"收益率 {r['total_return']:+.2f}% | {r['total_trades']}笔 | 胜率 {r['win_rate']:.1f}%")
        else:
            print("数据不足")

    return results


def print_report(results: List[dict]):
    if not results:
        print("无回测结果")
        return

    # 按收益率排序
    results.sort(key=lambda x: x['total_return'], reverse=True)

    print()
    print("=" * 80)
    print("  Louie PriceAction 回测报告（带仓位限制规则）")
    print("=" * 80)
    print()
    print(f"  {'品种':<8} {'收益率':>10} {'最大回撤':>10} {'交易次数':>8} {'胜率':>8} {'夏普比(估算)':>12} {'最终资金':>12}")
    print("  " + "-" * 76)

    total_return_sum = 0
    for r in results:
        sharpe = r['total_return'] / r['max_drawdown'] if r['max_drawdown'] > 0 else 0
        total_return_sum += r['total_pnl']
        emoji = "🟢" if r['total_return'] > 0 else "🔴"
        print(f"  {emoji}{r['symbol']:<7} {r['total_return']:>+9.2f}% {r['max_drawdown']:>9.2f}% {r['total_trades']:>8}笔 {r['win_rate']:>7.1f}% {sharpe:>11.2f} {r['final_capital']:>11,.0f}")

    # 汇总
    wins_all = sum(r['winning_trades'] for r in results)
    losses_all = sum(r['losing_trades'] for r in results)
    total_trades_all = sum(r['total_trades'] for r in results)
    avg_return = sum(r['total_return'] for r in results) / len(results)
    avg_dd = sum(r['max_drawdown'] for r in results) / len(results)
    win_rate_all = wins_all / total_trades_all * 100 if total_trades_all else 0

    print("  " + "-" * 76)
    print(f"  {'汇总':<8} {total_return_sum:>+10.2f} {avg_dd:>9.2f}% {total_trades_all:>8}笔 {win_rate_all:>7.1f}%")

    # 盈利/亏损分组
    profitable = [r for r in results if r['total_return'] > 0]
    unprofitable = [r for r in results if r['total_return'] <= 0]

    print()
    print(f"  盈利品种: {len(profitable)}/{len(results)}")
    print(f"  亏损品种: {len(unprofitable)}/{len(results)}")

    # Top 5 / Bottom 5
    print()
    print("  【Top 5 盈利品种】")
    for r in results[:5]:
        print(f"    {r['symbol']}: {r['total_return']:+.2f}%")

    print()
    print("  【Bottom 5 亏损品种】")
    for r in results[-5:]:
        print(f"    {r['symbol']}: {r['total_return']:+.2f}%")

    print()
    print("=" * 80)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='带仓位限制的回测')
    parser.add_argument('--days', type=int, default=365, help='回测天数 (默认 365)')
    parser.add_argument('--mode', default='swing', choices=['swing', 'intraday'], help='交易模式')
    parser.add_argument('--symbols', nargs='+', help='指定品种')
    args = parser.parse_args()

    from data_fetcher import get_all_futures_symbols
    symbols = args.symbols or get_all_futures_symbols()

    print(f"开始回测: {len(symbols)} 个品种 | {args.days} 天 | 模式: {args.mode}")
    print()

    results = run_multi_backtest(symbols, days=args.days, mode=args.mode)
    print_report(results)
