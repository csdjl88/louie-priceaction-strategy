"""
signal_monitor.py - 交易信号实时监听
===================================

功能:
1. 实时监控多个品种
2. 当策略产生交易信号时回调
3. 支持 CTA 策略信号检测

使用方法:
    from signal_monitor import SignalMonitor
    
    # 创建监控器
    monitor = SignalMonitor(
        symbols=['RB0', 'TA0', 'BR0'],  # 监控品种
        strategy='price_action',        # 策略类型
        interval=5                      # 检测间隔(秒)
    )
    
    # 设置信号回调
    def on_signal(symbol, signal_type, direction, price, reason):
        print(f"📢 信号: {symbol} {direction} @ {price}")
    
    monitor.set_callback(on_signal)
    
    # 启动监控
    monitor.start()
    
    # 停止
    monitor.stop()
"""

import time
import threading
import subprocess
import re
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from dataclasses import dataclass


@dataclass
class TradingSignal:
    """交易信号"""
    symbol: str
    timestamp: str
    signal_type: str      # 'long', 'short', 'close_long', 'close_short'
    direction: str        # 'bullish', 'bearish', 'neutral'
    price: float
    confidence: float     # 信心度 0-1
    reason: str           # 信号原因
    atr: float = 0
    trend: str = 'unknown'


class SignalMonitor:
    """
    交易信号实时监听器
    
    工作原理:
    1. 定时获取最新行情数据
    2. 运行策略分析
    3. 检测是否产生交易信号
    4. 触发回调
    """
    
    def __init__(self,
                 symbols: List[str] = None,
                 strategy: str = 'price_action',
                 interval: int = 60,
                 use_ctp: bool = False):
        """
        初始化
        
        Args:
            symbols: 监控的品种列表
            strategy: 策略类型
            interval: 检测间隔(秒)
            use_ctp: 是否使用CTP实盘
        """
        self.symbols = symbols or ['RB0', 'TA0', 'BR0', 'AL0', 'BU0']
        self.strategy = strategy
        self.interval = interval
        self.use_ctp = use_ctp
        
        # 回调函数
        self.signal_callback: Optional[Callable] = None
        self.status_callback: Optional[Callable] = None
        
        # 状态
        self.running = False
        self.monitor_thread = None
        
        # 缓存最新行情
        self.latest_quotes: Dict[str, Dict] = {}
        
        # 上一次信号（避免重复）
        self.last_signals: Dict[str, str] = {}
        
        print(f"信号监听器初始化")
        print(f"  监控品种: {', '.join(self.symbols)}")
        print(f"  检测间隔: {interval}秒")
        print(f"  策略: {strategy}")
    
    def set_callback(self, callback: Callable):
        """设置信号回调"""
        self.signal_callback = callback
    
    def set_status_callback(self, callback: Callable):
        """设置状态回调"""
        self.status_callback = callback
    
    # ==================== 生命周期 ====================
    
    def start(self):
        """启动监听"""
        if self.running:
            print("⚠️ 监听器已在运行")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        print("✅ 信号监听已启动")
    
    def stop(self):
        """停止监听"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        print("✅ 信号监听已停止")
    
    # ==================== 监控循环 ====================
    
    def _monitor_loop(self):
        """监控主循环"""
        print("🔄 开始监控...")
        
        while self.running:
            try:
                # 获取各品种行情
                for symbol in self.symbols:
                    self._check_signal(symbol)
                
                # 状态回调
                if self.status_callback:
                    self.status_callback({
                        'symbols': self.symbols,
                        'quotes': self.latest_quotes,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                
                time.sleep(self.interval)
                
            except Exception as e:
                print(f"❌ 监控异常: {e}")
                time.sleep(10)
        
        print("🔄 监控已停止")
    
    def _check_signal(self, symbol: str):
        """检测单个品种的信号"""
        try:
            # 获取实时数据
            data = self._fetch_latest_data(symbol)
            if not data:
                return
            
            # 运行策略分析
            signal = self._analyze_signal(symbol, data)
            
            if signal and signal.signal_type != 'none':
                # 检查是否重复
                signal_key = f"{symbol}_{signal.signal_type}"
                if self.last_signals.get(symbol) != signal_key:
                    self.last_signals[symbol] = signal_key
                    
                    # 触发回调
                    if self.signal_callback:
                        self.signal_callback(
                            symbol=symbol,
                            signal_type=signal.signal_type,
                            direction=signal.direction,
                            price=signal.price,
                            confidence=signal.confidence,
                            reason=signal.reason
                        )
        
        except Exception as e:
            pass  # 静默处理
    
    def _fetch_latest_data(self, symbol: str) -> Optional[Dict]:
        """获取最新数据"""
        try:
            if self.use_ctp:
                return self._fetch_from_ctp(symbol)
            else:
                return self._fetch_from_sina(symbol)
        except:
            return None
    
    def _fetch_from_sina(self, symbol: str) -> Optional[Dict]:
        """从Sina获取数据"""
        try:
            result = subprocess.run(
                ['curl', '-s', f'https://hq.sinajs.cn/list=nf{symbol.upper()}'],
                capture_output=True, text=True, timeout=5
            )
            
            text = result.stdout
            if 'var hq_str' in text:
                data = text.split('"')[1].split(',')
                if len(data) > 10:
                    return {
                        'symbol': symbol,
                        'open': float(data[1]) if data[1] else 0,
                        'high': float(data[2]) if data[2] else 0,
                        'low': float(data[3]) if data[3] else 0,
                        'close': float(data[4]) if data[4] else 0,
                        'volume': int(float(data[5])) if data[5] else 0,
                        'timestamp': data[8] + ' ' + data[9]
                    }
        except:
            pass
        return None

    def _fetch_history_data(self, symbol: str, days: int = 60) -> Optional[Dict]:
        """
        获取历史K线数据（用于策略分析）
        
        Returns:
            包含 opens, highs, lows, closes, volumes, dates 的字典
        """
        try:
            import json
            import re
            
            # 获取日K数据
            result = subprocess.run(
                ['curl', '-s',
                 f'https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_{symbol.upper()}=/InnerFuturesNewService.getDailyKLine',
                 '--data', f'symbol={symbol.upper()}&type=2025_04_03'],
                capture_output=True, text=True, timeout=30
            )
            
            text = result.stdout.strip()
            if not text or 'var' not in text:
                return None
            
            # 解析 JSON
            match = re.search(r'var \w+=\(\[.*\]\);', text)
            if not match:
                return None
            
            json_str = match.group(0).split('=(')[1][:-2]
            kline_data = json.loads(json_str)
            
            if not kline_data:
                return None
            
            # 取最近 N 天
            if len(kline_data) > days:
                kline_data = kline_data[-days:]
            
            # 转换为策略需要的格式
            dates = [d['d'] for d in kline_data]
            opens = [float(d['o']) for d in kline_data]
            highs = [float(d['h']) for d in kline_data]
            lows = [float(d['l']) for d in kline_data]
            closes = [float(d['c']) for d in kline_data]
            volumes = [int(d['v']) for d in kline_data]
            
            return {
                'symbol': symbol,
                'dates': dates,
                'opens': opens,
                'highs': highs,
                'lows': lows,
                'closes': closes,
                'volumes': volumes
            }
            
        except Exception as e:
            print(f"获取历史数据失败: {e}")
            return None
    
    def _fetch_from_ctp(self, symbol: str) -> Optional[Dict]:
        """从CTP获取数据"""
        # 需要CTP连接
        return None
    
    def _analyze_signal(self, symbol: str, data: Dict) -> Optional[TradingSignal]:
        """使用策略分析信号"""
        try:
            close = data.get('close', 0)
            if close == 0:
                return None
            
            # 获取历史数据用于策略分析
            history = self._fetch_history_data(symbol, days=60)
            
            signal = TradingSignal(
                symbol=symbol,
                timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                signal_type='none',
                direction='neutral',
                price=close,
                confidence=0,
                reason=''
            )
            
            # 如果获取到历史数据，使用完整策略分析
            if history and len(history.get('closes', [])) > 30:
                signal = self._analyze_with_strategy(symbol, history, data)
            else:
                # 降级到简单策略
                signal = self._simple_analysis(symbol, data)
            
            # 缓存最新行情
            self.latest_quotes[symbol] = data
            
            return signal
            
        except Exception as e:
            print(f"分析信号异常: {e}")
            return None
    
    def _analyze_with_strategy(self, symbol: str, history: Dict, current_data: Dict) -> TradingSignal:
        """
        使用 china_futures_strategy 进行完整策略分析
        """
        try:
            # 延迟导入避免循环依赖
            from china_futures_strategy import ChinaFuturesStrategy
            
            # 准备数据 - 添加最新行情
            # 如果实时数据获取失败，使用历史最后一条
            if current_data is None:
                current_data = {
                    'open': history['opens'][-1] if history['opens'] else 0,
                    'high': history['highs'][-1] if history['highs'] else 0,
                    'low': history['lows'][-1] if history['lows'] else 0,
                    'close': history['closes'][-1] if history['closes'] else 0,
                    'volume': history['volumes'][-1] if history['volumes'] else 0
                }
            
            opens = history['opens'] + [current_data.get('open', 0)]
            highs = history['highs'] + [current_data.get('high', 0)]
            lows = history['lows'] + [current_data.get('low', 0)]
            closes = history['closes'] + [current_data.get('close', 0)]
            volumes = history['volumes'] + [current_data.get('volume', 0)]
            
            # 创建策略实例
            symbol_base = symbol.lower().replace('0', '')
            strategy = ChinaFuturesStrategy(
                symbol=symbol_base,
                require_trend=True  # 要求趋势确认
            )
            
            # 获取最新K线的索引
            idx = len(closes) - 1
            
            # 运行策略分析
            result = strategy.analyze(opens, highs, lows, closes, idx)
            
            # 解析结果
            action = result.get('action', 'none')
            confidence = result.get('confidence', 0)
            trend = result.get('trend', 'unknown')
            reason = result.get('reason', result.get('signal_direction', 'neutral'))
            atr = result.get('atr', 0)
            
            signal = TradingSignal(
                symbol=symbol,
                timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                signal_type=action,
                direction=result.get('signal_direction', 'neutral'),
                price=closes[-1],
                confidence=confidence,
                reason=reason or trend,
                atr=atr,
                trend=trend
            )
            
            return signal
            
        except Exception as e:
            print(f"策略分析失败: {e}")
            return self._simple_analysis(symbol, current_data)
    
    def _simple_analysis(self, symbol: str, data: Dict) -> TradingSignal:
        """简单策略分析（降级方案）"""
        if data is None:
            return None
        close = data.get('close', 0)
        open_price = data.get('open', 0)
        
        if close == 0:
            return None
        
        change_pct = (close - open_price) / open_price * 100 if open_price > 0 else 0
        
        signal = TradingSignal(
            symbol=symbol,
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            signal_type='none',
            direction='neutral',
            price=close,
            confidence=0,
            reason=''
        )
        
        if change_pct > 2:
            signal.signal_type = 'long'
            signal.direction = 'bullish'
            signal.confidence = 0.6
            signal.reason = f'涨幅+{change_pct:.1f}%'
        elif change_pct < -2:
            signal.signal_type = 'short'
            signal.direction = 'bearish'
            signal.confidence = 0.6
            signal.reason = f'跌幅{change_pct:.1f}%'
        elif change_pct > 1:
            signal.signal_type = 'long'
            signal.direction = 'bullish'
            signal.confidence = 0.4
            signal.reason = f'涨幅+{change_pct:.1f}%'
        elif change_pct < -1:
            signal.signal_type = 'short'
            signal.direction = 'bearish'
            signal.confidence = 0.4
            signal.reason = f'跌幅{change_pct:.1f}%'
        
        return signal
    
    # ==================== 便捷方法 ====================
    
    def get_quotes(self) -> Dict[str, Dict]:
        """获取当前行情"""
        return self.latest_quotes.copy()
    
    def get_status(self) -> Dict:
        """获取状态"""
        return {
            'running': self.running,
            'symbols': self.symbols,
            'interval': self.interval,
            'quotes_count': len(self.latest_quotes)
        }


# ==================== CLI 测试 ====================

def demo_callback(symbol, signal_type, direction, price, confidence, reason):
    """信号回调示例"""
    emoji = '🟢' if signal_type == 'long' else '🔴'
    print(f"{emoji} {symbol}: {signal_type} @ {price:.2f} (信心:{confidence:.0%})")
    print(f"   原因: {reason}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='交易信号监听')
    parser.add_argument('--symbols', '-s', nargs='+', default=['RB0', 'TA0', 'BR0'],
                       help='监控品种')
    parser.add_argument('--interval', '-i', type=int, default=30, help='检测间隔(秒)')
    parser.add_argument('--duration', '-d', type=int, default=120, help='运行时间(秒)')
    
    args = parser.parse_args()
    
    print(f"启动信号监听器...")
    print(f"品种: {args.symbols}")
    print(f"间隔: {args.interval}秒")
    print(f"持续: {args.duration}秒")
    
    # 创建监控器
    monitor = SignalMonitor(
        symbols=args.symbols,
        interval=args.interval
    )
    
    # 设置回调
    monitor.set_callback(demo_callback)
    
    # 启动
    monitor.start()
    
    # 运行指定时间
    try:
        time.sleep(args.duration)
    except KeyboardInterrupt:
        pass
    
    # 停止
    monitor.stop()
    
    # 打印最终状态
    print(f"\n最终行情:")
    for symbol, quote in monitor.get_quotes().items():
        print(f"  {symbol}: {quote.get('close', 0):.2f}")