"""
position_manager.py - 持仓管理与交易执行
=====================================

功能:
1. 持仓同步 - 与CTP实时同步持仓
2. 交易执行 - 开仓/平仓/改单
3. 订单管理 - 追踪订单状态
4. 止盈止损执行 - 自动触发

使用方法:
    from position_manager import PositionManager
    from ctp_trader import CTPTader
    from risk_manager import RiskManager
    
    # 初始化
    pm = PositionManager(
        trader=ctp_trader,
        risk_manager=risk_mgr,
        strategy=strategy
    )
    
    # 启动交易
    pm.start()
    
    # 开仓信号
    pm.execute_signal(symbol='rb', direction='long', price=4100)
    
    # 停止
    pm.stop()
"""

import time
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict


@dataclass
class Order:
    """订单"""
    order_id: str
    symbol: str
    direction: str       # 'long' or 'short'
    offset: str          # 'open', 'close', 'close_today'
    price: float
    volume: int
    filled: int = 0
    avg_price: float = 0.0
    status: str = 'submitting'  # submitting, submitted, partial, filled, canceled, rejected
    create_time: str = ''
    update_time: str = ''
    error_msg: str = ''


@dataclass
class Position:
    """持仓"""
    symbol: str
    direction: str       # 'long' or 'short'
    volume: int          # 总持仓
    frozen: int          # 冻结（可平数量）
    yesterday: int       # 昨仓
    avg_price: float     # 均价
    open_price: float    # 开仓价
    stop_loss: float = 0.0
    take_profit: float = 0.0
    open_time: str = ''
    last_update: str = ''
    unrealized_pnl: float = 0.0


@dataclass
class TradeSignal:
    """交易信号"""
    symbol: str
    direction: str       # 'long', 'short', 'close_long', 'close_short'
    price: float
    volume: int
    reason: str = ''
    stop_loss: float = 0.0
    take_profit: float = 0.0
    priority: int = 0    # 优先级


class PositionManager:
    """
    持仓管理与交易执行
    
    核心功能:
    - 持仓管理：同步CTP持仓
    - 交易执行：处理开仓/平仓信号
    - 订单追踪：监控订单状态
    - 风控集成：执行止损止盈
    """
    
    def __init__(self,
                 trader: Any = None,
                 risk_manager: Any = None,
                 strategy: Any = None,
                 check_interval: float = 1.0):
        """
        初始化
        
        Args:
            trader: CTP交易接口 (CTPTader)
            risk_manager: 风险管理器
            strategy: 策略对象 (ChinaFuturesStrategy)
            check_interval: 检查间隔(秒)
        """
        self.trader = trader
        self.risk_manager = risk_manager
        self.strategy = strategy
        self.check_interval = check_interval
        
        # 数据存储
        self.orders: Dict[str, Order] = {}       # order_id -> Order
        self.positions: Dict[str, Position] = {} # symbol -> Position
        self.pending_signals: List[TradeSignal] = []  # 待执行信号
        
        # 合约配置
        self._load_contract_config()
        
        # 状态
        self.running = False
        self.monitor_thread = None
        
        # 统计
        self.today_trades = 0
        self.today_pnl = 0.0
        
        print(f"持仓管理器初始化完成")
        if trader:
            print(f"  交易接口: 已连接" if trader.logged_in else "  交易接口: 未连接")
        if risk_manager:
            print(f"  风控: 已启用")
    
    def _load_contract_config(self):
        """加载合约配置"""
        try:
            from china_futures_strategy import FUTURES_CONFIG
            self.contracts = FUTURES_CONFIG
        except:
            self.contracts = {}
    
    def get_contract_config(self, symbol: str) -> Dict:
        """获取合约配置"""
        symbol_base = symbol.lower().replace('0', '')
        return self.contracts.get(symbol_base, {'contract_size': 10})
    
    # ==================== 生命周期 ====================
    
    def start(self):
        """启动持仓管理"""
        if self.running:
            print("⚠️ 已经在运行中")
            return
        
        self.running = True
        
        # 同步持仓
        self.sync_positions()
        
        # 启动监控线程
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        print("✅ 持仓管理已启动")
    
    def stop(self):
        """停止持仓管理"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        print("✅ 持仓管理已停止")
    
    # ==================== 持仓同步 ====================
    
    def sync_positions(self):
        """同步持仓"""
        if not self.trader or not self.trader.logged_in:
            print("⚠️ 交易接口未登录")
            return
        
        try:
            # 从CTP获取持仓
            ctp_positions = self.trader.get_position()
            
            self.positions.clear()
            
            for symbol, pos in ctp_positions.items():
                # 转换持仓格式
                position = Position(
                    symbol=symbol,
                    direction=pos.direction,
                    volume=pos.volume,
                    frozen=pos.frozen,
                    yesterday=pos.yesterday,
                    avg_price=pos.avg_price,
                    open_price=pos.avg_price,
                    unrealized_pnl=pos.open_pnl
                )
                self.positions[symbol] = position
            
            print(f"✅ 已同步 {len(self.positions)} 个持仓")
            
        except Exception as e:
            print(f"❌ 同步持仓失败: {e}")
    
    # ==================== 交易执行 ====================
    
    def execute_signal(self, symbol: str, direction: str, price: float,
                      volume: int = 1, reason: str = '',
                      stop_loss: float = 0, take_profit: float = 0) -> Optional[str]:
        """
        执行交易信号
        
        Args:
            symbol: 合约代码
            direction: 'long', 'short', 'close_long', 'close_short'
            price: 价格
            volume: 数量
            reason: 原因
            stop_loss: 止损价
            take_profit: 止盈价
            
        Returns:
            订单ID，失败返回None
        """
        if not self.trader or not self.trader.logged_in:
            print("❌ 交易接口未登录")
            return None
        
        # 风控检查
        if self.risk_manager:
            account = self.trader.get_account()
            if account:
                check_result = self.risk_manager.check_before_open(
                    symbol, price, direction, account, list(self.positions.values())
                )
                if not check_result.allowed:
                    print(f"⚠️ 风控拦截: {check_result.reason}")
                    return None
                
                # 限制开仓量
                volume = min(volume, check_result.max_volume)
        
        # 执行交易
        try:
            if direction == 'long':
                order_id = self.trader.buy(symbol, price, volume, 'open')
            elif direction == 'short':
                order_id = self.trader.sell(symbol, price, volume, 'open')
            elif direction == 'close_long':
                order_id = self.trader.sell(symbol, price, volume, 'close')
            elif direction == 'close_short':
                order_id = self.trader.buy(symbol, price, volume, 'close')
            else:
                print(f"❌ 未知方向: {direction}")
                return None
            
            if order_id:
                # 创建订单对象
                order = Order(
                    order_id=order_id,
                    symbol=symbol,
                    direction=direction,
                    offset='open' if 'long' in direction or 'short' in direction else 'close',
                    price=price,
                    volume=volume,
                    create_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                )
                self.orders[order_id] = order
                
                print(f"✅ 已提交订单: {symbol} {direction} @ {price} x {volume}")
                self.today_trades += 1
                
                return order_id
            
        except Exception as e:
            print(f"❌ 下单失败: {e}")
        
        return None
    
    def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        if not self.trader:
            return False
        
        try:
            return self.trader.cancel_order(order_id)
        except Exception as e:
            print(f"❌ 撤单失败: {e}")
            return False
    
    # ==================== 止损止盈执行 ====================
    
    def check_and_execute_stops(self, prices: Dict[str, float]):
        """
        检查并执行止损止盈
        
        Args:
            prices: {symbol: price} 当前价格字典
        """
        for symbol, position in self.positions.items():
            if symbol not in prices:
                continue
            
            current_price = prices[symbol]
            
            # 检查止损
            if self.risk_manager:
                should_stop, reason = self.risk_manager.check_stop_loss(
                    position, current_price
                )
                if should_stop:
                    print(f"🛑 触发止损: {symbol} @ {current_price} - {reason}")
                    # 平仓
                    direction = 'close_long' if position.direction == 'long' else 'close_short'
                    self.execute_signal(symbol, direction, current_price, position.volume, reason)
                    continue
            
            # 检查止盈
            if self.risk_manager:
                should_tp, reason = self.risk_manager.check_take_profit(
                    position, current_price
                )
                if should_tp:
                    print(f"🎯 触发止盈: {symbol} @ {current_price} - {reason}")
                    # 平仓
                    direction = 'close_long' if position.direction == 'long' else 'close_short'
                    self.execute_signal(symbol, direction, current_price, position.volume, reason)
    
    # ==================== 监控循环 ====================
    
    def _monitor_loop(self):
        """监控循环"""
        print("🔄 持仓监控已启动")
        
        while self.running:
            try:
                # 更新订单状态
                self._update_orders()
                
                # 检查止损止盈
                if self.trader and self.trader.logged_in:
                    # 获取行情（需要行情服务）
                    prices = self._get_current_prices()
                    if prices:
                        self.check_and_execute_stops(prices)
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                print(f"❌ 监控循环异常: {e}")
                time.sleep(5)
        
        print("🔄 持仓监控已停止")
    
    def _update_orders(self):
        """更新订单状态"""
        for order_id, order in list(self.orders.items()):
            if order.status in ['filled', 'canceled', 'rejected']:
                continue
            
            # 从CTP获取订单状态
            if self.trader:
                ctp_order = self.trader.get_order(order_id)
                if ctp_order:
                    order.status = ctp_order.status
                    order.filled = ctp_order.filled
                    order.avg_price = ctp_order.avg_price
    
    def _get_current_prices(self) -> Dict[str, float]:
        """获取当前价格"""
        prices = {}
        
        if self.trader and hasattr(self.trader, '_quotes'):
            for symbol in self.positions.keys():
                if symbol in self.trader._quotes:
                    prices[symbol] = self.trader._quotes[symbol].get('last', 0)
        
        return prices
    
    # ==================== 状态查询 ====================
    
    def get_position(self, symbol: str = None) -> Optional[Position]:
        """获取持仓"""
        if symbol:
            return self.positions.get(symbol)
        return self.positions
    
    def get_order(self, order_id: str = None) -> Optional[Order]:
        """获取订单"""
        if order_id:
            return self.orders.get(order_id)
        return self.orders
    
    def get_working_orders(self) -> List[Order]:
        """获取未完成订单"""
        return [o for o in self.orders.values() 
                if o.status not in ['filled', 'canceled', 'rejected']]
    
    def print_status(self):
        """打印状态"""
        print(f"\n{'='*60}")
        print(f"  持仓管理状态")
        print(f"{'='*60}")
        print(f"  运行状态: {'运行中' if self.running else '已停止'}")
        print(f"  持仓数量: {len(self.positions)}")
        print(f"  活跃订单: {len(self.get_working_orders())}")
        print(f"  今日交易: {self.today_trades} 笔")
        
        if self.positions:
            print(f"\n  持仓明细:")
            for symbol, pos in self.positions.items():
                print(f"    {symbol}: {pos.direction} {pos.volume}手 @ {pos.avg_price:.2f} (盈亏: {pos.unrealized_pnl:.2f})")
        
        if self.orders:
            print(f"\n  订单明细:")
            for order_id, order in self.orders.items():
                if order.status not in ['filled', 'canceled', 'rejected']:
                    print(f"    {order_id}: {order.symbol} {order.direction} {order.status}")
        
        print(f"{'='*60}")


# ==================== 便捷函数 ====================

def create_demo_manager() -> PositionManager:
    """创建演示用的持仓管理器（无实盘）"""
    return PositionManager(
        trader=None,
        risk_manager=None,
        strategy=None
    )


# 测试
if __name__ == '__main__':
    # 创建持仓管理器
    pm = create_demo_manager()
    
    # 模拟持仓
    pm.positions['rb'] = Position(
        symbol='rb',
        direction='long',
        volume=2,
        frozen=2,
        yesterday=0,
        avg_price=4100,
        open_price=4100,
        unrealized_pnl=500
    )
    
    # 模拟订单
    pm.orders['test001'] = Order(
        order_id='test001',
        symbol='rb',
        direction='long',
        offset='open',
        price=4150,
        volume=1,
        status='submitted'
    )
    
    # 打印状态
    pm.print_status()