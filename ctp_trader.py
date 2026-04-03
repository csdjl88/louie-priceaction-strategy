"""
ctp_trader.py - CTP 实盘交易接口
==============================

支持上期技术 CTP 接口的实盘交易

前置要求:
1. 期货账户（CTP服务）
2. 安装 CTP API: pip install miniqi 或 ctp

使用方法:
    from ctp_trader import CTPTader
    
    # 初始化
    trader = CTPTader(
        broker_id='9999',           # 期货公司代码
        user_id='your_account',     # 交易账号
        password='your_password',   # 密码
        app_id='your_app_id',       # 认证AppID
        auth_code='your_code'       # 认证码
    )
    
    # 连接
    trader.connect()
    
    # 交易
    trader.buy('rb2405', 4100, 1)   # 做多
    trader.sell('rb2405', 4200, 1)  # 平多
    
    # 查持仓
    print(trader.get_position('rb2405'))
"""

import time
import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class Order:
    """订单"""
    order_id: str
    symbol: str
    direction: str  # 'long' or 'short'
    offset: str    # 'open', 'close', 'close_today'
    price: float
    volume: int
    status: str    # 'submitted', 'partial', 'filled', 'canceled', 'rejected'
    filled: int = 0
    avg_price: float = 0.0


@dataclass 
class Position:
    """持仓"""
    symbol: str
    direction: str   # 'long' or 'short'
    volume: int      # 总持仓
    frozen: int      # 冻结数量
    avg_price: float
    yesterday: int   # 昨仓
    today: int       # 今仓
    position_pnl: float = 0.0
    open_pnl: float = 0.0


@dataclass
class Account:
    """账户"""
    account_id: str
    balance: float         # 账户总权益
    available: float       # 可用资金
    commission: float      # 手续费
    margin: float          # 保证金
    position_pnl: float    # 持仓盈亏
    close_pnl: float       # 平仓盈亏
    yesterday_pnl: float   # 昨仓盈亏


class CTPTader:
    """
    CTP 交易接口
    
    支持功能:
    - 行情订阅
    - 开仓/平仓
    - 撤单
    - 持仓查询
    - 账户查询
    """
    
    def __init__(self, 
                 broker_id: str = '',
                 user_id: str = '',
                 password: str = '',
                 app_id: str = '',
                 auth_code: str = '',
                 td_address: str = '',
                 md_address: str = '',
                 use_ansi: bool = False):
        """
        初始化 CTP 交易接口
        
        Args:
            broker_id: 期货公司代码
            user_id: 交易账号
            password: 密码
            app_id: AppID (穿透式监管需要)
            auth_code: 认证码 (穿透式监管需要)
            td_address: 交易服务器地址
            md_address: 行情服务器地址
            use_ansi: 是否使用ANSI编码
        """
        self.broker_id = broker_id
        self.user_id = user_id
        self.password = password
        self.app_id = app_id
        self.auth_code = auth_code
        self.td_address = td_address or os.getenv('CTP_TD_ADDRESS', '')
        self.md_address = md_address or os.getenv('CTP_MD_ADDRESS', '')
        self.use_ansi = use_ansi
        
        # 状态
        self.connected = False
        self.logged_in = False
        
        # 数据存储
        self.orders: Dict[str, Order] = {}
        self.positions: Dict[str, Position] = {}
        self.account: Optional[Account] = None
        self.contracts: Dict[str, Any] = {}
        
        # 合约信息缓存
        self._contract_info = {}
        
        print(f"CTP交易接口初始化完成")
        print(f"  账号: {user_id}")
        print(f"  经纪商: {broker_id}")
    
    def connect(self, timeout: int = 30) -> bool:
        """
        连接交易服务器
        
        Args:
            timeout: 超时时间(秒)
            
        Returns:
            是否连接成功
        """
        print(f"\n连接交易服务器...")
        
        if not self.td_address:
            print("⚠️ 未配置交易服务器地址 (td_address)")
            print("   请设置环境变量 CTP_TD_ADDRESS 或在初始化时传入")
            return False
        
        try:
            # 尝试导入 CTP 库
            try:
                from miniapi import TraderAPI
                self._api = TraderAPI(
                    broker_id=self.broker_id,
                    user_id=self.user_id,
                    password=self.password,
                    app_id=self.app_id,
                    auth_code=self.auth_code,
                    address=self.td_address,
                    use_ansi=self.use_ansi
                )
            except ImportError:
                # miniqi 不可用，尝试其他库
                try:
                    from ctp import Trader
                    self._api = Trader(
                        broker_id=self.broker_id,
                        user_id=self.user_id,
                        password=self.password
                    )
                except ImportError:
                    print("❌ 未安装 CTP 库")
                    print("   请安装: pip install miniqi")
                    print("   或: pip install ctp")
                    return False
            
            # 连接
            self._api.connect()
            
            # 等待登录成功
            start_time = time.time()
            while not self.logged_in and time.time() - start_time < timeout:
                time.sleep(0.1)
            
            if self.logged_in:
                print("✅ 连接成功")
                # 查询初始数据
                self._query_initial_data()
                return True
            else:
                print("❌ 连接超时")
                return False
                
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return False
    
    def _query_initial_data(self):
        """查询初始数据（持仓、账户等）"""
        print("查询账户和持仓信息...")
        
        # 查询账户
        if self.account:
            print(f"  账户权益: {self.account.balance:,.2f}")
            print(f"  可用资金: {self.account.available:,.2f}")
        
        # 查询持仓
        if self.positions:
            print(f"  持仓数量: {len(self.positions)}")
    
    def buy(self, symbol: str, price: float, volume: int, 
            offset: str = 'open', order_type: str = 'limit') -> Optional[str]:
        """
        买入开仓
        
        Args:
            symbol: 合约代码 (如 'rb2405')
            price: 价格
            volume: 数量
            offset: 开仓方式 ('open', 'close', 'close_today')
            order_type: 订单类型 ('limit', 'market')
            
        Returns:
            订单ID，失败返回 None
        """
        return self._send_order(symbol, 'long', offset, price, volume, order_type)
    
    def sell(self, symbol: str, price: float, volume: int,
             offset: str = 'close', order_type: str = 'limit') -> Optional[str]:
        """
        卖出平仓
        
        Args:
            symbol: 合约代码
            price: 价格
            volume: 数量
            offset: 平仓方式 ('close', 'close_today')
            order_type: 订单类型
            
        Returns:
            订单ID
        """
        return self._send_order(symbol, 'short', offset, price, volume, order_type)
    
    def _send_order(self, symbol: str, direction: str, offset: str,
                   price: float, volume: int, order_type: str) -> Optional[str]:
        """
        发送订单
        """
        if not self.logged_in:
            print("❌ 未登录，请先调用 connect()")
            return None
        
        try:
            order_id = self._api.send_order(
                symbol=symbol,
                direction=direction,
                offset=offset,
                price=price,
                volume=volume,
                order_type=order_type
            )
            
            # 创建订单对象
            order = Order(
                order_id=order_id,
                symbol=symbol,
                direction=direction,
                offset=offset,
                price=price,
                volume=volume,
                status='submitted'
            )
            self.orders[order_id] = order
            
            print(f"📤 订单已提交: {symbol} {direction} {offset} @ {price} x {volume}")
            return order_id
            
        except Exception as e:
            print(f"❌ 下单失败: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """
        撤单
        
        Args:
            order_id: 订单ID
            
        Returns:
            是否成功
        """
        if not self.logged_in:
            print("❌ 未登录")
            return False
        
        try:
            self._api.cancel_order(order_id)
            print(f"✅ 撤单请求已发送: {order_id}")
            return True
        except Exception as e:
            print(f"❌ 撤单失败: {e}")
            return False
    
    def get_position(self, symbol: str = None) -> Optional[Position]:
        """
        获取持仓
        
        Args:
            symbol: 合约代码，None表示全部
            
        Returns:
            持仓信息
        """
        if symbol is None:
            return self.positions
        
        return self.positions.get(symbol)
    
    def get_order(self, order_id: str = None) -> Optional[Order]:
        """
        获取订单
        
        Args:
            order_id: 订单ID，None表示全部
            
        Returns:
            订单信息
        """
        if order_id is None:
            return self.orders
        
        return self.orders.get(order_id)
    
    def get_account(self) -> Optional[Account]:
        """
        获取账户信息
        """
        return self.account
    
    def get_quote(self, symbol: str) -> Optional[Dict]:
        """
        获取行情（需要行情服务）
        """
        # 这个需要单独连接行情服务
        return self._api.get_quote(symbol) if hasattr(self._api, 'get_quote') else None
    
    def subscribe(self, symbols: List[str]) -> bool:
        """
        订阅行情
        
        Args:
            symbols: 合约代码列表
        """
        print(f"订阅行情: {symbols}")
        # 需要连接行情服务
        return True
    
    def disconnect(self):
        """断开连接"""
        if hasattr(self, '_api'):
            self._api.disconnect()
        self.connected = False
        self.logged_in = False
        print("✅ 已断开连接")
    
    # ==================== 回调函数 ====================
    
    def on_connect(self):
        """连接成功回调"""
        self.connected = True
        print("🔗 已连接到交易服务器")
    
    def on_login(self, error_msg: str = ''):
        """登录成功回调"""
        if error_msg:
            print(f"❌ 登录失败: {error_msg}")
            self.logged_in = False
        else:
            print("✅ 登录成功")
            self.logged_in = True
    
    def on_order(self, order: Order):
        """订单状态变化回调"""
        self.orders[order.order_id] = order
        status_emoji = {
            'submitted': '📤',
            'partial': '📊',
            'filled': '✅',
            'canceled': '❌',
            'rejected': '🚫'
        }
        emoji = status_emoji.get(order.status, '❓')
        print(f"{emoji} 订单状态: {order.order_id} - {order.status}")
    
    def on_trade(self, order_id: str, trade_id: str, price: float, volume: int):
        """成交回报回调"""
        print(f"💰 成交: {order_id} @ {price} x {volume}")
    
    def on_position(self, position: Position):
        """持仓变化回调"""
        self.positions[position.symbol] = position
    
    def on_account(self, account: Account):
        """账户变化回调"""
        self.account = account
    
    def on_error(self, error_msg: str):
        """错误回调"""
        print(f"❌ 错误: {error_msg}")


# ==================== 便捷函数 ====================

def create_trader_from_config(config_file: str = 'ctp_config.json') -> Optional[CTPTader]:
    """
    从配置文件创建交易员
    
    Args:
        config_file: 配置文件路径
        
    Returns:
        CTPTader 实例
    """
    if not os.path.exists(config_file):
        print(f"❌ 配置文件不存在: {config_file}")
        return None
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        return CTPTader(
            broker_id=config.get('broker_id', ''),
            user_id=config.get('user_id', ''),
            password=config.get('password', ''),
            app_id=config.get('app_id', ''),
            auth_code=config.get('auth_code', ''),
            td_address=config.get('td_address', ''),
            md_address=config.get('md_address', '')
        )
    except Exception as e:
        print(f"❌ 加载配置失败: {e}")
        return None


def save_config(config_file: str, broker_id: str, user_id: str, 
                password: str, td_address: str, md_address: str = '',
                app_id: str = '', auth_code: str = ''):
    """保存配置到文件"""
    config = {
        'broker_id': broker_id,
        'user_id': user_id,
        'password': password,
        'td_address': td_address,
        'md_address': md_address,
        'app_id': app_id,
        'auth_code': auth_code
    }
    
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 配置已保存到: {config_file}")


# CLI 入口
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='CTP 实盘交易')
    parser.add_argument('--config', '-c', default='ctp_config.json', help='配置文件')
    parser.add_argument('--action', '-a', choices=['connect', 'query', 'status'], default='status',
                       help='操作')
    parser.add_argument('--symbol', '-s', help='合约代码')
    parser.add_argument('--price', '-p', type=float, help='价格')
    parser.add_argument('--volume', '-v', type=int, help='数量')
    parser.add_argument('--direction', '-d', choices=['buy', 'sell'], help='方向')
    
    args = parser.parse_args()
    
    if args.action == 'connect':
        trader = create_trader_from_config(args.config)
        if trader:
            trader.connect()
    elif args.action == 'status':
        trader = create_trader_from_config(args.config)
        if trader:
            trader.connect()
            if trader.logged_in:
                account = trader.get_account()
                if account:
                    print(f"\n账户信息:")
                    print(f"  权益: {account.balance:,.2f}")
                    print(f"  可用: {account.available:,.2f}")
                    print(f"  保证金: {account.margin:,.2f}")
                    print(f"  持仓盈亏: {account.position_pnl:,.2f}")
                trader.disconnect()
    elif args.action == 'query':
        if not args.symbol:
            print("❌ 请指定 --symbol")
        else:
            trader = create_trader_from_config(args.config)
            if trader:
                trader.connect()
                pos = trader.get_position(args.symbol)
                if pos:
                    print(f"\n{args.symbol} 持仓:")
                    print(f"  多头: {pos.get('long', {}).get('volume', 0)}")
                    print(f"  空头: {pos.get('short', {}).get('volume', 0)}")
                trader.disconnect()