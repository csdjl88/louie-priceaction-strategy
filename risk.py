"""
risk.py - 风险管理模块
====================
包含仓位计算、止损管理、风控规则
"""

from .indicators import atr


class PositionSizer:
    """
    仓位计算器
    =========
    根据账户规模和风险比例计算仓位
    """
    
    def __init__(self, risk_percent=0.02):
        """
        Args:
            risk_percent: 单笔风险比例（默认2%）
        """
        self.risk_percent = risk_percent
    
    def calculate(self, account_balance, entry_price, stop_loss_price):
        """
        计算仓位大小
        
        公式：position_size = account_balance * risk_percent / risk_per_unit
        
        Args:
            account_balance: 账户余额
            entry_price: 入场价格
            stop_loss_price: 止损价格
        
        Returns:
            仓位数量
        """
        if entry_price <= 0 or stop_loss_price <= 0:
            return 0
        
        risk_per_unit = abs(entry_price - stop_loss_price)
        
        if risk_per_unit == 0:
            return 0
        
        # 可承受的风险金额
        risk_amount = account_balance * self.risk_percent
        
        # 仓位数量
        position_size = risk_amount / risk_per_unit
        
        return max(0, position_size)
    
    def calculate_with_fraction(self, account_balance, entry_price, stop_loss_price, fraction=1.0):
        """
        计算仓位（支持使用部分资金）
        
        Args:
            fraction: 仓位比例（0-1），默认使用全部可用资金
        """
        full_position = self.calculate(account_balance, entry_price, stop_loss_price)
        return full_position * fraction
    
    def calculate_risk_amount(self, account_balance):
        """计算可承受的风险金额"""
        return account_balance * self.risk_percent


class RiskManager:
    """
    风险管理器
    =========
    管理整体风险，包括最大回撤、单日亏损等
    """
    
    def __init__(self, 
                 max_drawdown=0.20,
                 max_daily_loss=0.05,
                 max_positions=3,
                 max_correlation=0.7):
        """
        Args:
            max_drawdown: 最大回撤比例（默认20%）
            max_daily_loss: 单日最大亏损（默认5%）
            max_positions: 最大同时持仓数
            max_correlation: 仓位最大相关性
        """
        self.max_drawdown = max_drawdown
        self.max_daily_loss = max_daily_loss
        self.max_positions = max_positions
        self.max_correlation = max_correlation
        
        # 状态
        self.peak_balance = 0
        self.current_drawdown = 0
        self.daily_pnl = 0
        self.positions = []
    
    def update_balance(self, current_balance):
        """更新账户余额和回撤"""
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
        
        if self.peak_balance > 0:
            self.current_drawdown = (self.peak_balance - current_balance) / self.peak_balance
    
    def can_open_position(self, current_balance):
        """检查是否可以开新仓位"""
        # 检查回撤
        if self.current_drawdown >= self.max_drawdown:
            return False, "max_drawdown_reached"
        
        # 检查持仓数量
        if len(self.positions) >= self.max_positions:
            return False, "max_positions_reached"
        
        # 检查日亏损
        if abs(self.daily_pnl) / current_balance >= self.max_daily_loss:
            return False, "max_daily_loss_reached"
        
        return True, "ok"
    
    def add_position(self, symbol, size, entry_price, stop_loss):
        """添加持仓"""
        position = {
            'symbol': symbol,
            'size': size,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'pnl': 0
        }
        self.positions.append(position)
        return position
    
    def remove_position(self, symbol):
        """移除持仓"""
        self.positions = [p for p in self.positions if p['symbol'] != symbol]
    
    def update_positions_pnl(self, current_prices):
        """更新所有持仓的盈亏"""
        for position in self.positions:
            symbol = position['symbol']
            if symbol in current_prices:
                current_price = current_prices[symbol]
                entry = position['entry_price']
                size = position['size']
                
                # 简单计算（假设做多）
                position['pnl'] = (current_price - entry) * size
    
    def get_total_pnl(self):
        """获取总盈亏"""
        return sum(p['pnl'] for p in self.positions)
    
    def reset_daily(self):
        """重置日亏损统计"""
        self.daily_pnl = 0


class StopLossCalculator:
    """
    止损计算器
    =========
    提供多种止损计算方式
    """
    
    @staticmethod
    def structure_stop(highs, lows, direction, lookback=20):
        """
        结构止损 - 基于高低点
        """
        if direction == 'bullish':
            return min(lows[-lookback:])
        else:
            return max(highs[-lookback:])
    
    @staticmethod
    def atr_stop(entry_price, atr_value, direction, multiplier=2.0):
        """
        ATR止损
        """
        if direction == 'bullish':
            return entry_price - atr_value * multiplier
        else:
            return entry_price + atr_value * multiplier
    
    @staticmethod
    def chandelier_stop(highs, lows, closes, direction, period=22, multiplier=3.0):
        """
        Chandelier止损（基于ATR的高点/低点追踪）
        """
        import numpy as np
        
        if len(closes) < period:
            return None
        
        # 计算True Range
        trs = []
        for i in range(1, min(period, len(closes))):
            tr = max(
                highs[-i] - lows[-i],
                abs(highs[-i] - closes[-i-1]),
                abs(lows[-i] - closes[-i-1])
            )
            trs.append(tr)
        
        if not trs:
            return None
        
        avg_atr = np.mean(trs)
        
        if direction == 'bullish':
            highest_high = max(highs[-period:])
            return highest_high - avg_atr * multiplier
        else:
            lowest_low = min(lows[-period:])
            return lowest_low + avg_atr * multiplier
    
    @staticmethod
    def pending_stop(current_price, direction, pending_pips=20):
        """
        固定点数止损
        """
        if direction == 'bullish':
            return current_price - pending_pips
        else:
            return current_price + pending_pips


class TradeExecutor:
    """
    交易执行器（模拟）
    ===============
    模拟订单执行，用于回测
    """
    
    def __init__(self, slippage=0.0005, commission=0.0002):
        """
        Args:
            slippage: 滑点比例（默认0.05%）
            commission: 手续费比例（默认0.02%）
        """
        self.slippage = slippage
        self.commission = commission
    
    def execute_market_order(self, direction, price, size):
        """
        执行市价单
        
        Returns:
            (成交价格, 手续费)
        """
        # 考虑滑点
        if direction == 'buy':
            fill_price = price * (1 + self.slippage)
        else:
            fill_price = price * (1 - self.slippage)
        
        # 手续费
        cost = fill_price * size * self.commission
        
        return fill_price, cost
    
    def execute_limit_order(self, direction, limit_price, current_price, size):
        """
        执行限价单
        只有当当前价格达到限价时才成交
        """
        if direction == 'buy' and current_price <= limit_price:
            return self.execute_market_order(direction, limit_price, size)
        elif direction == 'sell' and current_price >= limit_price:
            return self.execute_market_order(direction, limit_price, size)
        else:
            return None, None  # 未成交
    
    def calculate_margin_required(self, price, size, leverage=1.0):
        """计算保证金需求"""
        return price * size / leverage
    
    def calculate_pnl(self, direction, entry_price, exit_price, size):
        """
        计算盈亏
        
        Args:
            direction: 'long' or 'short'
            entry_price: 入场价格
            exit_price: 出场价格
            size: 持仓数量
        """
        if direction == 'long':
            pnl = (exit_price - entry_price) * size
        else:
            pnl = (entry_price - exit_price) * size
        
        return pnl
