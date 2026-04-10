"""
portfolio.py - 持仓追踪与盈亏计算
===================================

功能:
1. 追踪当前持仓（方向、价格、成本、止损、目标）
2. 计算浮动盈亏和已实现盈亏
3. 生成持仓报告

使用:
    from portfolio import Portfolio
    
    p = Portfolio(initial_capital=100000)
    p.open_position('RU', 'long', entry_price=16225, quantity=1, stop_loss=15395, target=18712)
    p.update_market_price('RU', current_price=17140)
    print(p.get_status())
"""

import json
import csv
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


# ──────────────────────────────────────────────────────────────────────────
# 数据模型
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class Position:
    symbol: str
    direction: str          # 'long' / 'short'
    volume: int             # 持仓手数
    entry_price: float      # 开仓价
    stop_loss: float        # 止损价
    target: float           # 目标价
    atr: float              # ATR
    entry_time: str         # 开仓时间
    commission: float = 0


@dataclass
class ClosedTrade:
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    volume: int
    pnl: float
    pnl_pct: float
    holding_days: int
    exit_reason: str
    entry_time: str
    exit_time: str
    commission: float


@dataclass
class AccountSnapshot:
    timestamp: str
    capital: float
    available: float
    position_pnl: float
    realized_pnl: float
    total_pnl: float
    position_count: int
    winning_trades: int
    losing_trades: int
    win_rate: float


# ──────────────────────────────────────────────────────────────────────────
# Portfolio 核心
# ──────────────────────────────────────────────────────────────────────────
class Portfolio:
    def __init__(self, initial_capital: float = 100000,
                 commission_rate: float = 0.0003,
                 margin_rate: float = 0.12):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.margin_rate = margin_rate
        self.positions: Dict[str, Position] = {}
        self.closed_trades: List[ClosedTrade] = []
        self.cash = initial_capital
        self._position_pnl_cache = 0.0
        self._log_file: Optional[str] = None
        self._csv_file: Optional[str] = None

    def open_position(self, symbol: str, direction: str,
                     entry_price: float, volume: int = 1,
                     stop_loss: float = 0, target: float = 0,
                     atr: float = 0) -> bool:
        if symbol in self.positions:
            print(f"[Portfolio] {symbol} 已在持仓中，跳过开仓")
            return False

        contract_value = entry_price * volume
        margin = contract_value * self.margin_rate
        commission = contract_value * self.commission_rate

        if self.cash < margin + commission:
            print(f"[Portfolio] 资金不足！需要 {margin+commission:.2f}，可用 {self.cash:.2f}")
            return False

        self.cash -= commission
        entry_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        self.positions[symbol] = Position(
            symbol=symbol, direction=direction, volume=volume,
            entry_price=entry_price, stop_loss=stop_loss,
            target=target, atr=atr, entry_time=entry_time,
            commission=commission
        )
        self._log_trade('OPEN', symbol, direction, entry_price, volume, stop_loss, target, entry_time)
        return True

    def close_position(self, symbol: str, exit_price: float,
                      reason: str = 'manual') -> Optional[ClosedTrade]:
        pos = self.positions.pop(symbol, None)
        if not pos:
            return None

        commission = exit_price * pos.volume * self.commission_rate
        self.cash -= commission

        if pos.direction == 'long':
            pnl = (exit_price - pos.entry_price) * pos.volume
        else:
            pnl = (pos.entry_price - exit_price) * pos.volume

        pnl -= pos.commission
        pnl_pct = pnl / (pos.entry_price * pos.volume) * 100
        exit_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        entry_dt = datetime.strptime(pos.entry_time, '%Y-%m-%d %H:%M:%S')
        exit_dt = datetime.strptime(exit_time, '%Y-%m-%d %H:%M:%S')
        holding_days = (exit_dt - entry_dt).days

        margin = pos.entry_price * pos.volume * self.margin_rate
        self.cash += margin + pnl

        trade = ClosedTrade(
            symbol=pos.symbol, direction=pos.direction,
            entry_price=pos.entry_price, exit_price=exit_price,
            volume=pos.volume, pnl=round(pnl, 2), pnl_pct=round(pnl_pct, 2),
            holding_days=holding_days, exit_reason=reason,
            entry_time=pos.entry_time, exit_time=exit_time,
            commission=pos.commission + commission
        )
        self.closed_trades.append(trade)
        self._log_trade('CLOSE', symbol, pos.direction, exit_price, pos.volume,
                        pos.stop_loss, pos.target, exit_time, pnl, pnl_pct, reason)
        self._append_trade_csv(trade)
        return trade

    def update_market_price(self, symbol: str, current_price: float) -> Dict:
        pos = self.positions.get(symbol)
        if not pos:
            return {}

        if pos.direction == 'long':
            unrealized = (current_price - pos.entry_price) * pos.volume
            dist_stop = (current_price - pos.stop_loss) / pos.stop_loss * 100 if pos.stop_loss else 999
            dist_target = (pos.target - current_price) / pos.target * 100 if pos.target else 999
        else:
            unrealized = (pos.entry_price - current_price) * pos.volume
            dist_stop = (pos.stop_loss - current_price) / pos.stop_loss * 100 if pos.stop_loss else 999
            dist_target = (current_price - pos.target) / pos.target * 100 if pos.target else 999

        unrealized_pct = unrealized / (pos.entry_price * pos.volume) * 100 if pos.entry_price * pos.volume else 0

        return {
            'symbol': symbol,
            'current_price': current_price,
            'unrealized_pnl': round(unrealized, 2),
            'unrealized_pnl_pct': round(unrealized_pct, 2),
            'distance_to_stop': round(dist_stop, 2),
            'distance_to_target': round(dist_target, 2),
        }

    def check_stop_triggered(self, symbol: str, current_price: float) -> Optional[str]:
        pos = self.positions.get(symbol)
        if not pos:
            return None
        if pos.direction == 'long':
            if current_price <= pos.stop_loss:
                return 'stop_loss'
            if pos.target > 0 and current_price >= pos.target:
                return 'target'
        else:
            if current_price >= pos.stop_loss:
                return 'stop_loss'
            if pos.target > 0 and current_price <= pos.target:
                return 'target'
        return None

    def get_capital(self) -> float:
        margin_used = self._get_margin_used()
        return self.cash + margin_used + self._position_pnl_cache

    def get_position_pnl(self) -> float:
        return self._position_pnl_cache

    def get_realized_pnl(self) -> float:
        return sum(t.pnl for t in self.closed_trades)

    def get_status(self) -> AccountSnapshot:
        wins = [t for t in self.closed_trades if t.pnl > 0]
        losses = [t for t in self.closed_trades if t.pnl <= 0]
        total_pnl = self.get_capital() - self.initial_capital
        return AccountSnapshot(
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            capital=round(self.get_capital(), 2),
            available=round(self.cash, 2),
            position_pnl=round(self._position_pnl_cache, 2),
            realized_pnl=round(self.get_realized_pnl(), 2),
            total_pnl=round(total_pnl, 2),
            position_count=len(self.positions),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=round(len(wins) / len(self.closed_trades) * 100, 1) if self.closed_trades else 0
        )

    def _get_margin_used(self) -> float:
        return sum(p.entry_price * p.volume * self.margin_rate for p in self.positions.values())

    def update_all_positions(self, prices: Dict[str, float]):
        total = 0.0
        for symbol in list(self.positions.keys()):
            info = self.update_market_price(symbol, prices.get(symbol, 0))
            total += info.get('unrealized_pnl', 0)
        self._position_pnl_cache = total

    def set_log_file(self, path: str):
        self._log_file = path
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['时间', '类型', '品种', '方向', '价格', '手数', '止损', '目标', '盈亏', '盈亏%', '原因'])

    def _log_trade(self, action, symbol, direction, price, volume,
                    stop_loss, target, time, pnl=0, pnl_pct=0, reason=''):
        if not self._log_file:
            return
        with open(self._log_file, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([time, action, symbol, direction, price,
                                  volume, stop_loss, target, pnl, pnl_pct, reason])

    def set_trade_csv(self, path: str):
        self._csv_file = path
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['品种', '方向', '入场价', '出场价', '手数',
                            '盈亏', '盈亏%', '持仓天数', '出场原因', '入场时间', '出场时间', '手续费'])

    def _append_trade_csv(self, trade: ClosedTrade):
        if not self._csv_file:
            return
        with open(self._csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([trade.symbol, trade.direction, trade.entry_price,
                            trade.exit_price, trade.volume, trade.pnl, trade.pnl_pct,
                            trade.holding_days, trade.exit_reason,
                            trade.entry_time, trade.exit_time, trade.commission])

    def get_positions_with_prices(self, prices: Dict[str, float]) -> List[Dict]:
        results = []
        for symbol, pos in self.positions.items():
            current = prices.get(symbol, pos.entry_price)
            if pos.direction == 'long':
                unrealized = (current - pos.entry_price) * pos.volume
                dist_stop = (current - pos.stop_loss) / pos.stop_loss * 100 if pos.stop_loss else 999
                dist_target = (pos.target - current) / pos.target * 100 if pos.target else 999
            else:
                unrealized = (pos.entry_price - current) * pos.volume
                dist_stop = (pos.stop_loss - current) / pos.stop_loss * 100 if pos.stop_loss else 999
                dist_target = (current - pos.target) / pos.target * 100 if pos.target else 999

            unrealized_pct = unrealized / (pos.entry_price * pos.volume) * 100 if pos.entry_price * pos.volume else 0
            entry_dt = datetime.strptime(pos.entry_time, '%Y-%m-%d %H:%M:%S')
            days = (datetime.now() - entry_dt).days

            results.append({
                'symbol': symbol, 'direction': pos.direction,
                'volume': pos.volume, 'entry_price': pos.entry_price,
                'current_price': current, 'stop_loss': pos.stop_loss,
                'target': pos.target, 'atr': pos.atr,
                'unrealized_pnl': round(unrealized, 2),
                'unrealized_pnl_pct': round(unrealized_pct, 2),
                'distance_to_stop': round(dist_stop, 2),
                'distance_to_target': round(dist_target, 2),
                'days_held': days, 'entry_time': pos.entry_time,
            })
        results.sort(key=lambda x: x['unrealized_pnl'], reverse=True)
        return results
