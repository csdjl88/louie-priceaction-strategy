#!/usr/bin/env python3
"""
backtest_multi_shared.py - 多品种共享仓位组合回测
================================================

模拟真实交易场景：
- 单一账户：初始资金 100,000
- 所有品种共享 3 个仓位（按夏普比优先级排序）
- 保证金上限 70%
- 全市场扫描，信号按夏普比优先级竞争仓位

使用方法:
    uv run python scripts/backtest_multi_shared.py --days 365 --mode swing
"""

import argparse
import sys
import os
from datetime import datetime
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_fetcher import fetch_multi_futures_data, get_all_futures_symbols
from china_futures_strategy import ChinaFuturesStrategy


# ──────────────────────────────────────────────────────────────────────────
# 夏普比白名单 + 优先级（数值越大优先级越高）
# ──────────────────────────────────────────────────────────────────────────
SHARPE_PRIORITY = {
    # 第一梯队
    'jm': 12.04,   # 焦煤 日内
    'p':  7.69,    # 棕榈油 日内
    'cs': 6.63,    # 玉米淀粉 日内
    'bu': 5.68,    # 沥青 日内
    'v':  5.33,    # PVC 日内
    # 第二梯队
    'ta': 3.92,
    'i':  3.62,
    'a':  2.91,
    'al': 2.50,
    'zn': 2.30,
    # 第三梯队
    'pp': 1.80,
    'sc': 1.50,
    'ru': 1.30,
    'm':  1.20,
    'cf': 1.10,
    'rb': 1.00,
    'sr': 0.90,
    'ma': 0.80,
}

MAX_POSITIONS = 3
MAX_MARGIN_RATIO = 0.70
INITIAL_CAPITAL = 100000
MARGIN_RATE = 0.12
COMMISSION_RATE = 0.0003


# ──────────────────────────────────────────────────────────────────────────
# 简化 Portfolio
# ──────────────────────────────────────────────────────────────────────────
class Portfolio:
    def __init__(self):
        self.initial_capital = INITIAL_CAPITAL
        self.cash = INITIAL_CAPITAL
        self.positions: Dict[str, dict] = {}
        self.closed_trades: List[dict] = []
        self.trades_by_symbol: Dict[str, list] = {}

    def _margin(self) -> float:
        return sum(p['entry_price'] * p['volume'] * MARGIN_RATE for p in self.positions.values())

    def _equity(self, prices: Dict[str, float]) -> float:
        pos_pnl = 0
        for sym, pos in self.positions.items():
            cur = prices.get(sym, pos['entry_price'])
            if pos['direction'] == 'long':
                pos_pnl += (cur - pos['entry_price']) * pos['volume']
            else:
                pos_pnl += (pos['entry_price'] - cur) * pos['volume']
        return self.cash + self._margin() + pos_pnl

    def can_open(self, price: float, stop_loss: float = 0) -> tuple:
        """返回 (能否开仓, 手数)"""
        if len(self.positions) >= MAX_POSITIONS:
            return False, 0
        # 按风险计算手数（每笔 2% 本金）
        risk_amount = self.initial_capital * 0.02
        risk_per_contract = abs(price - stop_loss) if stop_loss and stop_loss > 0 else price * 0.02
        volume = max(1, int(risk_amount / risk_per_contract))
        volume = min(volume, 5)  # 最多5手
        margin = price * volume * MARGIN_RATE
        if (self._margin() + margin) / self.initial_capital > MAX_MARGIN_RATIO:
            return False, 0
        return True, volume

    def open(self, sym: str, direction: str, price: float,
             volume: int, stop_loss: float, target: float, atr: float):
        if sym in self.positions:
            return False
        self.cash -= price * volume * COMMISSION_RATE
        self.positions[sym] = {
            'direction': direction, 'entry_price': price,
            'volume': volume, 'stop_loss': stop_loss, 'target': target,
            'atr': atr, 'entry_commission': price * volume * COMMISSION_RATE,
        }
        return True

    def check_trigger(self, sym: str, price: float) -> Optional[str]:
        pos = self.positions.get(sym)
        if not pos:
            return None
        d, sl, tp = pos['direction'], pos['stop_loss'], pos['target']
        if d == 'long':
            if price <= sl: return 'stop_loss'
            if tp > 0 and price >= tp: return 'target'
        else:
            if price >= sl: return 'stop_loss'
            if tp > 0 and price <= tp: return 'target'
        return None

    def close(self, sym: str, price: float, reason: str) -> Optional[dict]:
        pos = self.positions.pop(sym, None)
        if not pos:
            return None
        vol, entry = pos['volume'], pos['entry_price']
        self.cash -= price * vol * COMMISSION_RATE
        pnl = (price - entry) * vol if pos['direction'] == 'long' else (entry - price) * vol
        net = pnl - pos['entry_commission'] - price * vol * COMMISSION_RATE
        self.cash += entry * vol * MARGIN_RATE + net
        trade = {
            'symbol': sym, 'direction': pos['direction'],
            'entry_price': entry, 'exit_price': price,
            'volume': vol, 'pnl': round(net, 2),
            'exit_reason': reason,
        }
        self.closed_trades.append(trade)
        self.trades_by_symbol.setdefault(sym, []).append(trade)
        return trade


# ──────────────────────────────────────────────────────────────────────────
# 回测
# ──────────────────────────────────────────────────────────────────────────
def run_backtest(symbols: List[str], days: int = 365,
                 mode: str = 'swing', atr_target: float = 8.0) -> Dict:
    """
    多品种组合回测：单一账户，共享仓位
    """
    whitelist = [s for s in symbols if s.lower() in SHARPE_PRIORITY]
    print(f"白名单: {len(symbols)} -> {len(whitelist)} 个品种")

    # 加载所有品种数据
    print("加载数据...")
    all_data = fetch_multi_futures_data(whitelist, days=days)
    if not all_data:
        print("数据加载失败")
        return {}

    # 找最长数据长度
    max_len = max(len(all_data[s]['closes']) for s in whitelist if s in all_data)
    start_idx = 5  # 从第5根K线开始（需要足够历史数据）

    portfolio = Portfolio()
    equity_curve = []
    signals_log = []  # 记录每日信号

    # 逐日扫描
    for i in range(start_idx, max_len):
        # 收集所有品种的信号
        candidates = []

        for sym in whitelist:
            if sym not in all_data:
                continue
            d = all_data[sym]
            if i >= len(d['closes']):
                continue

            closes = d['closes']
            opens = d['opens']
            highs = d['highs']
            lows = d['lows']
            dates = d['dates']
            current_price = closes[i]

            # 检查持仓触发
            trigger = portfolio.check_trigger(sym, current_price)
            if trigger:
                trade = portfolio.close(sym, current_price, trigger)
                if trade:
                    signals_log.append({
                        'date': dates[i], 'symbol': sym,
                        'action': f'平仓({trigger})', 'price': current_price,
                        'pnl': trade['pnl'], 'positions': len(portfolio.positions)
                    })

            # 策略信号
            strat = ChinaFuturesStrategy(sym, trading_mode=mode, atr_target=atr_target, require_trend=True)
            result = strat.analyze(opens, highs, lows, closes, i)
            action = result.get('action', 'none')
            if action in ('long', 'short') and sym not in portfolio.positions:
                if len(portfolio.positions) < MAX_POSITIONS:
                    atr = result.get('atr', 0)
                    sl = result.get('stop_loss', 0)
                    tp = result.get('take_profit', 0)
                    candidates.append({
                        'symbol': sym,
                        'action': action,
                        'price': current_price,
                        'stop_loss': sl,
                        'target': tp,
                        'atr': atr,
                        'priority': SHARPE_PRIORITY.get(sym.lower(), 0),
                        'confidence': result.get('confidence', 0),
                        'reason': result.get('reason', ''),
                    })

        # 按夏普比优先级排序，开仓
        candidates.sort(key=lambda x: -x['priority'])
        for c in candidates:
            if len(portfolio.positions) >= MAX_POSITIONS:
                break
            ok, vol = portfolio.can_open(c['price'], c['stop_loss'])
            if ok:
                portfolio.open(c['symbol'], c['action'], c['price'],
                             vol, c['stop_loss'], c['target'], c['atr'])
                signals_log.append({
                    'date': all_data[c['symbol']]['dates'][i],
                    'symbol': c['symbol'],
                    'action': f"开仓({'做多' if c['action']=='long' else '做空'})",
                    'price': c['price'],
                    'pnl': 0,
                    'positions': len(portfolio.positions),
                    'confidence': c['confidence'],
                })

        # 记录当日权益
        prices = {sym: all_data[sym]['closes'][min(i, len(all_data[sym]['closes'])-1)]
                  for sym in whitelist if sym in all_data}
        equity = portfolio._equity(prices)
        date = all_data[whitelist[0]]['dates'][i] if whitelist and whitelist[0] in all_data else ''
        equity_curve.append({'date': date, 'equity': equity})

    # 最后一天收盘平仓
    for sym in list(portfolio.positions.keys()):
        if sym in all_data and all_data[sym]['closes']:
            final_price = all_data[sym]['closes'][-1]
            portfolio.close(sym, final_price, 'end_of_backtest')

    # 统计数据
    wins = [t for t in portfolio.closed_trades if t['pnl'] > 0]
    losses = [t for t in portfolio.closed_trades if t['pnl'] <= 0]
    total_pnl = sum(t['pnl'] for t in portfolio.closed_trades)
    final_equity = INITIAL_CAPITAL + total_pnl

    # 最大回撤
    peak = INITIAL_CAPITAL
    max_dd = 0
    for eq in equity_curve:
        if eq['equity'] > peak:
            peak = eq['equity']
        dd = (peak - eq['equity']) / peak * 100
        if dd > max_dd:
            max_dd = dd

    win_rate = len(wins) / len(portfolio.closed_trades) * 100 if portfolio.closed_trades else 0
    return_pct = (final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    sharpe = return_pct / max_dd if max_dd > 0 else 0

    return {
        'initial_capital': INITIAL_CAPITAL,
        'final_equity': final_equity,
        'total_pnl': total_pnl,
        'return_pct': return_pct,
        'max_drawdown': max_dd,
        'sharpe_ratio': sharpe,
        'win_rate': win_rate,
        'total_trades': len(portfolio.closed_trades),
        'winning_trades': len(wins),
        'losing_trades': len(losses),
        'profit_sum': sum(t['pnl'] for t in wins),
        'loss_sum': sum(t['pnl'] for t in losses),
        'equity_curve': equity_curve,
        'closed_trades': portfolio.closed_trades,
        'signals_log': signals_log,
    }


def print_report(r: Dict):
    if not r:
        return

    print()
    print("=" * 75)
    print("  Louie PriceAction 多品种组合回测报告")
    print("  单一账户共享仓位（最多3个 | 保证金上限70%）")
    print("=" * 75)
    print()
    print(f"  初始资金:   {r['initial_capital']:,.0f}")
    print(f"  最终权益:   {r['final_equity']:,.2f}")
    print(f"  总盈亏:     {r['total_pnl']:>+12.2f}")
    print(f"  收益率:     {r['return_pct']:>+11.2f}%")
    print(f"  最大回撤:   {r['max_drawdown']:>11.2f}%")
    print(f"  夏普比:     {r['sharpe_ratio']:>11.2f}")
    print(f"  总交易次数: {r['total_trades']:>11d} 笔")
    print(f"  胜率:       {r['win_rate']:>11.1f}%")
    print(f"  盈利总额:   {r['profit_sum']:>+12.2f}")
    print(f"  亏损总额:   {r['loss_sum']:>+12.2f}")
    print()
    print("  " + "-" * 73)

    # 按盈亏排序的已平仓交易
    trades = sorted(r['closed_trades'], key=lambda x: -x['pnl'])
    print(f"  {'品种':<6} {'方向':<5} {'入场价':>10} {'出场价':>10} {'盈亏':>10} {'出场原因':<15}")
    print("  " + "-" * 73)
    for t in trades:
        emoji = '+' if t['pnl'] > 0 else '-'
        d = '多' if t['direction'] == 'long' else '空'
        print(f"  {emoji}{t['symbol']:<5} {d:<5} {t['entry_price']:>10.0f} {t['exit_price']:>10.0f} {t['pnl']:>+10.2f} {t['exit_reason']:<15}")

    print()
    print("=" * 75)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=365)
    parser.add_argument('--mode', default='swing', choices=['swing', 'intraday'])
    parser.add_argument('--atr-target', type=float, default=8.0)
    parser.add_argument('--symbols', nargs='+')
    parser.add_argument('--label', default='')
    args = parser.parse_args()

    symbols = args.symbols or get_all_futures_symbols()
    label = args.label or f"止盈{args.atr_target}×ATR/{args.mode}"
    print(f"\n{'='*60}")
    print(f"  回测: {label}")
    print(f"{'='*60}")
    print(f"品种: {len(symbols)} 个 | {args.days} 天 | 模式: {args.mode} | 止盈: {args.atr_target}×ATR")
    print(f"规则: 夏普比优先 | 最多 {MAX_POSITIONS} 仓位 | 保证金上限 {int(MAX_MARGIN_RATIO*100)}%")
    print()

    r = run_backtest(symbols, days=args.days, mode=args.mode, atr_target=args.atr_target)
    print_report(r)
