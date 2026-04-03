"""
risk_manager.py - 风险管理模块
=============================

功能:
1. 仓位管理 - 根据资金和风险计算开仓量
2. 止损止盈 - 自动执行风控规则
3. 单日风控 - 限制单日最大亏损
4. 持仓风控 - 监控持仓风险

使用方法:
    from risk_manager import RiskManager, Position, Account
    
    # 初始化
    risk_mgr = RiskManager(
        initial_balance=100000,
        max_position_pct=0.3,      # 最大持仓比例 30%
        max_loss_per_day_pct=0.05, # 单日最大亏损 5%
        max_loss_per_trade_pct=0.02 # 单笔最大亏损 2%
    )
    
    # 开仓前检查
    can_open, reason, max_volume = risk_mgr.check_before_open(
        symbol='rb',
        price=4100,
        direction='long',
        account=account,
        positions=positions
    )
    
    # 检查是否需要止损
    should_stop, reason = risk_mgr.check_stop_loss(
        position=pos,
        current_price=4050
    )
"""

import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, date


@dataclass
class Position:
    """持仓"""
    symbol: str
    direction: str       # 'long' or 'short'
    volume: int          # 持仓数量
    avg_price: float     # 开仓均价
    open_date: str       # 开仓日期
    stop_loss: float = 0.0    # 止损价
    take_profit: float = 0.0  # 止盈价


@dataclass
class Account:
    """账户"""
    balance: float       # 当前权益
    available: float     # 可用资金
    margin: float        # 占用保证金
    today_pnl: float = 0.0  # 今日盈亏


@dataclass
class RiskCheckResult:
    """风控检查结果"""
    allowed: bool
    reason: str
    max_volume: int = 0
   建议 action: str = ''


class RiskManager:
    """
    风险管理器
    
    负责:
    - 开仓前风险检查
    - 持仓监控与止损
    - 单日亏损限制
    - 仓位管理
    """
    
    def __init__(self,
                 initial_balance: float = 100000,
                 max_position_pct: float = 0.3,
                 max_loss_per_day_pct: float = 0.05,
                 max_loss_per_trade_pct: float = 0.02,
                 max_positions: int = 5,
                 min_balance: float = 10000):
        """
        初始化风控管理器
        
        Args:
            initial_balance: 初始资金
            max_position_pct: 单品种最大持仓比例 (0.3 = 30%)
            max_loss_per_day_pct: 单日最大亏损比例 (0.05 = 5%)
            max_loss_per_trade_pct: 单笔最大亏损比例 (0.02 = 2%)
            max_positions: 最大持仓品种数
            min_balance: 最小账户余额（低于此值禁止开仓）
        """
        self.initial_balance = initial_balance
        self.max_position_pct = max_position_pct
        self.max_loss_per_day_pct = max_loss_per_day_pct
        self.max_loss_per_trade_pct = max_loss_per_trade_pct
        self.max_positions = max_positions
        self.min_balance = min_balance
        
        # 合约配置（从 china_futures_strategy 导入）
        self._load_contract_config()
        
        # 状态
        self.today_pnl = 0.0
        self.max_today_pnl = 0.0  # 今日最大权益
        self.trade_count_today = 0
        self.last_trade_date = date.today()
        
        print(f"风控管理器初始化完成")
        print(f"  最大持仓比例: {max_position_pct*100:.0f}%")
        print(f"  单日最大亏损: {max_loss_per_day_pct*100:.0f}%")
        print(f"  单笔最大亏损: {max_loss_per_trade_pct*100:.0f}%")
    
    def _load_contract_config(self):
        """加载合约配置"""
        try:
            from china_futures_strategy import FUTURES_CONFIG
            self.contracts = FUTURES_CONFIG
        except:
            # 默认配置
            self.contracts = {
                'rb': {'contract_size': 10, 'tick_size': 1},
                'cu': {'contract_size': 5, 'tick_size': 10},
                'au': {'contract_size': 1000, 'tick_size': 0.02},
            }
    
    def get_contract_config(self, symbol: str) -> Dict:
        """获取合约配置"""
        symbol_base = symbol.lower().replace('0', '').replace('1', '').replace('2', '').replace('3', '').replace('4', '').replace('5', '').replace('6', '').replace('7', '').replace('8', '').replace('9', '')
        return self.contracts.get(symbol_base, {'contract_size': 10, 'tick_size': 1})
    
    # ==================== 开仓前检查 ====================
    
    def check_before_open(self, symbol: str, price: float, direction: str,
                          account: Account, positions: List[Position]) -> RiskCheckResult:
        """
        开仓前风险检查
        
        Args:
            symbol: 合约代码
            price: 开仓价格
            direction: 'long' or 'short'
            account: 账户信息
            positions: 当前持仓列表
            
        Returns:
            RiskCheckResult: 检查结果
        """
        # 检查日期，更新状态
        self._check_date_reset()
        
        # 1. 检查账户余额
        if account.balance < self.min_balance:
            return RiskCheckResult(
                allowed=False,
                reason=f"账户余额 {account.balance:.0f} 低于最小要求 {self.min_balance:.0f}",
                max_volume=0
            )
        
        # 2. 检查单日亏损
        if account.today_pnl < -self.initial_balance * self.max_loss_per_day_pct:
            return RiskCheckResult(
                allowed=False,
                reason=f"单日亏损已达到限制 {self.max_loss_per_day_pct*100:.0f}%",
                max_volume=0
            )
        
        # 3. 检查持仓数量
        if len(positions) >= self.max_positions:
            return RiskCheckResult(
                allowed=False,
                reason=f"持仓品种数 {len(positions)} 已达上限 {self.max_positions}",
                max_volume=0
            )
        
        # 4. 检查该品种是否已有持仓
        existing = [p for p in positions if p.symbol == symbol]
        if existing:
            # 反向持仓不允许加仓
            existing_dir = existing[0].direction
            if existing_dir != direction:
                return RiskCheckResult(
                    allowed=False,
                    reason=f"当前持有{existing_dir}仓，不允许反向开仓",
                    max_volume=0
                )
        
        # 5. 计算最大可开仓量
        config = self.get_contract_config(symbol)
        contract_size = config.get('contract_size', 10)
        
        # 保证金需求（按合约价值 10% 估算）
        margin_per_lot = price * contract_size * 0.1
        
        max_lots_by_margin = int(account.available / margin_per_lot)
        max_lots_by_pct = int(account.balance * self.max_position_pct / margin_per_lot)
        max_volume = min(max_lots_by_margin, max_lots_by_pct, 10)  # 最多10手
        
        if max_volume <= 0:
            return RiskCheckResult(
                allowed=False,
                reason="可用资金不足",
                max_volume=0
            )
        
        return RiskCheckResult(
            allowed=True,
            reason="检查通过",
            max_volume=max_volume
        )
    
    def calculate_position_size(self, symbol: str, price: float, 
                                account: Account, risk_pct: float = 0.02) -> int:
        """
        根据风险计算开仓量
        
        Args:
            symbol: 合约代码
            price: 开仓价格
            account: 账户信息
            risk_pct: 风险比例 (0.02 = 2%)
            
        Returns:
            开仓手数
        """
        config = self.get_contract_config(symbol)
        contract_size = config.get('contract_size', 10)
        tick_size = config.get('tick_size', 1)
        
        # 风险金额
        risk_amount = account.balance * risk_pct
        
        # 每手价值
        contract_value = price * contract_size
        
        # 止损点数（假设 2% 止损）
        stop_pct = 0.02
        stop_price = price * (1 - stop_pct if 'long' in direction else 1 + stop_pct)
        stop_points = abs(price - stop_price) / tick_size
        
        # 每手风险
        risk_per_lot = stop_points * tick_size * contract_size
        
        # 计算仓位
        if risk_per_lot > 0:
            volume = int(risk_amount / risk_per_lot)
        else:
            volume = 1
        
        # 限制最大仓位
        max_lots = int(account.balance * self.max_position_pct / (price * contract_size * 0.1))
        volume = min(volume, max_lots, 10)
        
        return max(volume, 1)  # 至少1手
    
    # ==================== 止损止盈检查 ====================
    
    def check_stop_loss(self, position: Position, current_price: float,
                        atr: float = 0) -> tuple:
        """
        检查是否触发止损
        
        Args:
            position: 持仓
            current_price: 当前价格
            atr: ATR 值（可选，用于动态止损）
            
        Returns:
            (是否止损, 原因)
        """
        # 固定止损
        if position.stop_loss > 0:
            if position.direction == 'long' and current_price <= position.stop_loss:
                return True, f"触发固定止损 {position.stop_loss}"
            elif position.direction == 'short' and current_price >= position.stop_loss:
                return True, f"触发固定止损 {position.stop_loss}"
        
        # 移动止损（如果有盈利）
        profit_pct = (current_price - position.avg_price) / position.avg_price
        if profit_pct > 0.03:  # 盈利超过 3%
            # 移动止损到成本价
            if position.direction == 'long' and current_price < position.avg_price * 1.02:
                return True, "移动止损触发"
            elif position.direction == 'short' and current_price > position.avg_price * 0.98:
                return True, "移动止损触发"
        
        # ATR 止损
        if atr > 0 and position.direction == 'long':
            if current_price < position.avg_price - atr * 2:
                return True, f"ATR止损: {position.avg_price - atr * 2}"
        elif atr > 0 and position.direction == 'short':
            if current_price > position.avg_price + atr * 2:
                return True, f"ATR止损: {position.avg_price + atr * 2}"
        
        return False, ""
    
    def check_take_profit(self, position: Position, current_price: float) -> tuple:
        """
        检查是否触发止盈
        
        Args:
            position: 持仓
            current_price: 当前价格
            
        Returns:
            (是否止盈, 原因)
        """
        if position.take_profit > 0:
            if position.direction == 'long' and current_price >= position.take_profit:
                return True, f"触发止盈 {position.take_profit}"
            elif position.direction == 'short' and current_price <= position.take_profit:
                return True, f"触发止盈 {position.take_profit}"
        
        # 移动止盈（盈利达到目标后部分止盈）
        profit_pct = (current_price - position.avg_price) / position.avg_price
        if profit_pct > 0.08:  # 盈利超过 8%
            return True, "达到目标盈利"
        
        return False, ""
    
    # ==================== 单日风控 ====================
    
    def check_daily_loss(self, account: Account) -> bool:
        """
        检查单日亏损是否超限
        
        Args:
            account: 账户信息
            
        Returns:
            是否超过限制
        """
        self._check_date_reset()
        
        loss_pct = abs(account.today_pnl) / self.initial_balance
        if account.today_pnl < 0 and loss_pct >= self.max_loss_per_day_pct:
            print(f"⚠️ 单日亏损 {loss_pct*100:.1f}% 已达限制 {self.max_loss_per_day_pct*100:.0f}%")
            return True
        
        return False
    
    def _check_date_reset(self):
        """检查并重置日期状态"""
        today = date.today()
        if today != self.last_trade_date:
            self.today_pnl = 0
            self.trade_count_today = 0
            self.max_today_pnl = self.initial_balance
            self.last_trade_date = today
    
    def update_daily_pnl(self, pnl: float):
        """更新当日盈亏"""
        self._check_date_reset()
        self.today_pnl += pnl
        if pnl > 0:
            self.trade_count_today += 1
    
    # ==================== 风险监控 ====================
    
    def get_risk_report(self, account: Account, positions: List[Position]) -> Dict:
        """
        获取风险报告
        
        Args:
            account: 账户信息
            positions: 持仓列表
            
        Returns:
            风险报告字典
        """
        # 计算持仓占比
        total_margin = account.margin
        position_pct = total_margin / account.balance if account.balance > 0 else 0
        
        # 计算风险度
        risk_level = "低"
        if position_pct > 0.7:
            risk_level = "高"
        elif position_pct > 0.5:
            risk_level = "中"
        
        # 统计
        long_positions = len([p for p in positions if p.direction == 'long'])
        short_positions = len([p for p in positions if p.direction == 'short'])
        
        return {
            '账户权益': account.balance,
            '可用资金': account.available,
            '保证金': total_margin,
            '持仓占比': f"{position_pct*100:.1f}%",
            '风险等级': risk_level,
            '多头持仓': long_positions,
            '空头持仓': short_positions,
            '今日盈亏': account.today_pnl,
            '今日交易次数': self.trade_count_today,
            '单日亏损限制': f"{self.max_loss_per_day_pct*100:.0f}%"
        }
    
    def print_risk_report(self, account: Account, positions: List[Position]):
        """打印风险报告"""
        report = self.get_risk_report(account, positions)
        
        print(f"\n{'='*50}")
        print(f"  风险监控报告")
        print(f"{'='*50}")
        for k, v in report.items():
            print(f"  {k}: {v}")
        print(f"{'='*50}")


# ==================== 便捷函数 ====================

def create_test_account(balance: float = 100000) -> Account:
    """创建测试账户"""
    return Account(
        balance=balance,
        available=balance,
        margin=0,
        today_pnl=0
    )


def create_test_position(symbol: str = 'rb', direction: str = 'long',
                        volume: int = 1, avg_price: float = 4100) -> Position:
    """创建测试持仓"""
    return Position(
        symbol=symbol,
        direction=direction,
        volume=volume,
        avg_price=avg_price,
        open_date=datetime.now().strftime('%Y-%m-%d')
    )


# 测试
if __name__ == '__main__':
    # 创建风控管理器
    risk_mgr = RiskManager(initial_balance=100000)
    
    # 测试账户
    account = create_test_account(100000)
    
    # 测试开仓检查
    result = risk_mgr.check_before_open('rb', 4100, 'long', account, [])
    print(f"\n开仓检查结果: {result.allowed} - {result.reason}")
    print(f"最大可开仓量: {result.max_volume}")
    
    # 测试持仓止损
    pos = create_test_position('rb', 'long', 1, 4100)
    pos.stop_loss = 4050
    should_stop, reason = risk_mgr.check_stop_loss(pos, 4040)
    print(f"\n止损检查: {should_stop} - {reason}")
    
    # 风险报告
    risk_mgr.print_risk_report(account, [pos])