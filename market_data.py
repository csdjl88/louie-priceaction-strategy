"""
market_data.py - 实时行情推送
=============================

支持:
1. WebSocket 行情推送
2. 实时价格监控
3. 价格预警
4. 数据缓存

使用方法:
    from market_data import MarketData, PriceAlert
    
    # 初始化
    md = MarketData()
    
    # 订阅行情
    md.subscribe(['rb', 'cu', 'au'])
    
    # 启动推送
    md.start()
    
    # 获取实时价格
    price = md.get_price('rb')
    
    # 设置预警
    alert = PriceAlert('rb', 4000, 4100, callback=on_alert)
    md.add_alert(alert)
    
    # 停止
    md.stop()
"""

import time
import threading
import json
import subprocess
import re
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict


@dataclass
class Quote:
    """行情数据"""
    symbol: str
    last: float = 0.0        # 最新价
    open: float = 0.0        # 开盘价
    high: float = 0.0        # 最高价
    low: float = 0.0         # 最低价
    volume: int = 0          # 成交量
    amount: float = 0.0      # 成交额
    bid1: float = 0.0        # 买一价
    ask1: float = 0.0        # 卖一价
    bid_vol1: int = 0        # 买一量
    ask_vol1: int = 0        # 卖一量
    open_interest: int = 0   # 持仓量
    update_time: str = ''    # 更新时间
    change: float = 0.0      # 涨跌
    change_pct: float = 0.0  # 涨跌幅


@dataclass
class PriceAlert:
    """价格预警"""
    symbol: str
    low_price: float = 0     # 低价预警
    high_price: float = 0    # 高价预警
    callback: Callable = None  # 回调函数
    triggered: bool = False
    create_time: str = ''


class MarketData:
    """
    实时行情数据服务
    
    功能:
    - 实时行情推送
    - 价格监控预警
    - 多个数据源支持
    """
    
    def __init__(self, use_ctp: bool = False):
        """
        初始化
        
        Args:
            use_ctp: 是否使用CTP行情（需要实盘）
        """
        self.use_ctp = use_ctp
        
        # 行情数据
        self.quotes: Dict[str, Quote] = {}
        self.subscribed: set = set()
        
        # 价格预警
        self.alerts: List[PriceAlert] = []
        
        # 回调函数
        self.price_callbacks: List[Callable] = []
        
        # 状态
        self.running = False
        self.fetch_thread = None
        
        # 缓存
        self.last_fetch_time = {}
        self.cache_ttl = 5  # 缓存有效期(秒)
        
        print(f"行情数据服务初始化完成")
        if use_ctp:
            print(f"  数据源: CTP")
        else:
            print(f"  数据源: Sina (模拟)")
    
    # ==================== 订阅 ====================
    
    def subscribe(self, symbols: List[str]):
        """
        订阅行情
        
        Args:
            symbols: 合约代码列表
        """
        for symbol in symbols:
            self.subscribed.add(symbol.upper())
            # 初始化空行情
            if symbol.upper() not in self.quotes:
                self.quotes[symbol.upper()] = Quote(symbol=symbol.upper())
        
        print(f"已订阅: {', '.join(self.subscribed)}")
    
    def unsubscribe(self, symbols: List[str]):
        """取消订阅"""
        for symbol in symbols:
            self.subscribed.discard(symbol.upper())
    
    # ==================== 生命周期 ====================
    
    def start(self):
        """启动行情服务"""
        if self.running:
            return
        
        self.running = True
        
        # 启动获取线程
        self.fetch_thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self.fetch_thread.start()
        
        print("✅ 行情服务已启动")
    
    def stop(self):
        """停止行情服务"""
        self.running = False
        if self.fetch_thread:
            self.fetch_thread.join(timeout=5)
        print("✅ 行情服务已停止")
    
    # ==================== 数据获取 ====================
    
    def _fetch_loop(self):
        """数据获取循环"""
        print("🔄 行情获取已启动")
        
        while self.running:
            try:
                if self.use_ctp:
                    self._fetch_from_ctp()
                else:
                    self._fetch_from_sina()
                
                # 检查预警
                self._check_alerts()
                
                # 触发回调
                self._trigger_callbacks()
                
                # 等待
                time.sleep(2)  # 2秒刷新
                
            except Exception as e:
                print(f"❌ 行情获取异常: {e}")
                time.sleep(5)
        
        print("🔄 行情获取已停止")
    
    def _fetch_from_sina(self):
        """从 Sina 获取行情（模拟）"""
        for symbol in list(self.subscribed):
            try:
                # 尝试用 curl 获取
                result = subprocess.run(
                    ['curl', '-s', f'https://hq.sinajs.cn/list=nf{symbol.upper()}'],
                    capture_output=True, text=True, timeout=5
                )
                
                text = result.stdout
                if 'var hq_str' in text:
                    # 解析数据
                    data = text.split('"')[1].split(',')
                    if len(data) > 10:
                        quote = Quote(symbol=symbol)
                        quote.open = float(data[1]) if data[1] else 0
                        quote.high = float(data[2]) if data[2] else 0
                        quote.low = float(data[3]) if data[3] else 0
                        quote.last = float(data[4]) if data[4] else 0
                        quote.volume = int(float(data[5])) if data[5] else 0
                        quote.amount = float(data[6]) if data[6] else 0
                        quote.open_interest = int(float(data[7])) if data[7] else 0
                        quote.update_time = data[8] + ' ' + data[9]
                        
                        # 计算涨跌幅
                        if quote.open > 0:
                            quote.change = quote.last - quote.open
                            quote.change_pct = quote.change / quote.open * 100
                        
                        self.quotes[symbol] = quote
                        
            except Exception as e:
                pass  # 静默失败
    
    def _fetch_from_ctp(self):
        """从 CTP 获取行情"""
        # 需要 CTP 行情服务
        pass
    
    # ==================== 价格预警 ====================
    
    def add_alert(self, alert: PriceAlert):
        """添加预警"""
        alert.create_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.alerts.append(alert)
        print(f"✅ 已添加预警: {alert.symbol} {alert.low_price} - {alert.high_price}")
    
    def remove_alert(self, symbol: str):
        """移除预警"""
        self.alerts = [a for a in self.alerts if a.symbol != symbol]
    
    def _check_alerts(self):
        """检查预警"""
        for alert in self.alerts:
            if alert.triggered:
                continue
            
            quote = self.quotes.get(alert.symbol)
            if not quote or quote.last == 0:
                continue
            
            # 检查是否触发
            if alert.low_price > 0 and quote.last <= alert.low_price:
                alert.triggered = True
                self._trigger_alert(alert, 'low', quote.last)
            elif alert.high_price > 0 and quote.last >= alert.high_price:
                alert.triggered = True
                self._trigger_alert(alert, 'high', quote.last)
    
    def _trigger_alert(self, alert: PriceAlert, alert_type: str, price: float):
        """触发预警"""
        msg = f"🚨 价格预警: {alert.symbol} 当前价 {price}"
        if alert_type == 'low':
            msg += f" 低于低价 {alert.low_price}"
        else:
            msg += f" 高于高价 {alert.high_price}"
        
        print(msg)
        
        # 调用回调
        if alert.callback:
            try:
                alert.callback(alert.symbol, price, alert_type)
            except Exception as e:
                print(f"❌ 预警回调失败: {e}")
    
    # ==================== 回调 ====================
    
    def add_price_callback(self, callback: Callable):
        """添加价格回调"""
        self.price_callbacks.append(callback)
    
    def _trigger_callbacks(self):
        """触发回调"""
        for callback in self.price_callbacks:
            try:
                callback(self.quotes)
            except Exception as e:
                print(f"❌ 回调失败: {e}")
    
    # ==================== 数据查询 ====================
    
    def get_price(self, symbol: str) -> Optional[Quote]:
        """获取实时价格"""
        return self.quotes.get(symbol.upper())
    
    def get_all_quotes(self) -> Dict[str, Quote]:
        """获取所有行情"""
        return self.quotes.copy()
    
    def get_spread(self, symbol: str) -> Optional[float]:
        """获取买卖价差"""
        quote = self.quotes.get(symbol.upper())
        if quote and quote.ask1 > 0 and quote.bid1 > 0:
            return quote.ask1 - quote.bid1
        return None
    
    # ==================== 打印 ====================
    
    def print_quotes(self):
        """打印行情"""
        print(f"\n{'='*80}")
        print(f"  实时行情")
        print(f"{'='*80}")
        print(f"{'合约':<8}{'最新价':<10}{'涨跌':<10}{'涨跌幅':<10}{'成交量':<12}{'持仓量':<12}")
        print("-" * 80)
        
        for symbol, quote in self.quotes.items():
            if quote.last > 0:
                print(f"{symbol:<8}{quote.last:<10.2f}{quote.change:<10.2f}"
                      f"{quote.change_pct:<10.2f}%{quote.volume:<12}{quote.open_interest:<12}")
        
        print(f"{'='*80}")


# ==================== WebSocket 推送 ====================

class WebSocketMarketFeed:
    """
    WebSocket 行情推送（可选功能）
    
    需要额外的 WebSocket 库支持
    """
    
    def __init__(self, host: str = '0.0.0.0', port: int = 8765):
        self.host = host
        self.port = port
        self.clients = set()
        self.running = False
    
    async def start(self):
        """启动 WebSocket 服务器"""
        try:
            import websockets
            self.running = True
            
            async with websockets.serve(self.handle_client, self.host, self.port):
                print(f"✅ WebSocket 行情服务启动: ws://{self.host}:{self.port}")
                while self.running:
                    await asyncio.sleep(1)
        except ImportError:
            print("⚠️ 需要安装 websockets: pip install websockets")
    
    async def handle_client(self, websocket, path):
        """处理客户端连接"""
        self.clients.add(websocket)
        print(f"🔗 WebSocket 客户端连接: {path}")
        
        try:
            async for message in websocket:
                # 处理消息
                data = json.loads(message)
                await self.process_message(websocket, data)
        except:
            pass
        finally:
            self.clients.remove(websocket)
    
    async def process_message(self, websocket, data):
        """处理客户端消息"""
        cmd = data.get('cmd')
        
        if cmd == 'subscribe':
            symbols = data.get('symbols', [])
            # 订阅逻辑
            pass
        elif cmd == 'unsubscribe':
            symbols = data.get('symbols', [])
            # 取消订阅逻辑
            pass
    
    async def broadcast(self, quotes: Dict[str, Quote]):
        """广播行情"""
        if not self.clients:
            return
        
        message = {
            'type': 'quotes',
            'data': {symbol: {
                'last': q.last,
                'change': q.change,
                'change_pct': q.change_pct,
                'volume': q.volume
            } for symbol, q in quotes.items()}
        }
        
        msg_text = json.dumps(message)
        
        for client in list(self.clients):
            try:
                await client.send(msg_text)
            except:
                pass
    
    def stop(self):
        """停止"""
        self.running = False


# ==================== 便捷函数 ====================

def create_market_monitor(symbols: List[str], alert_callback: Callable = None) -> MarketData:
    """
    创建行情监控器
    
    Args:
        symbols: 监控的合约列表
        alert_callback: 预警回调函数
    
    Returns:
        MarketData 实例
    """
    md = MarketData()
    md.subscribe(symbols)
    
    if alert_callback:
        md.add_price_callback(alert_callback)
    
    return md


# CLI 入口
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='实时行情')
    parser.add_argument('--symbols', '-s', nargs='+', default=['RB0', 'CU0', 'AU0'],
                       help='订阅的合约')
    parser.add_argument('--interval', '-i', type=int, default=5, help='刷新间隔(秒)')
    
    args = parser.parse_args()
    
    # 创建行情服务
    md = MarketData()
    md.subscribe(args.symbols)
    md.start()
    
    try:
        while True:
            md.print_quotes()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        md.stop()
        print("\n已退出")