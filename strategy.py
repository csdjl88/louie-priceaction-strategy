"""
strategy.py - Price Action 策略核心
====================================
整合所有模块，形成完整的交易策略
"""

from .indicators import atr, sma, highest, lowest
from .patterns import (
    is_pin_bar, is_engulfing, is_inside_bar, is_outside_bar,
    is_momentum, is_breakout, is_false_breakout,
    PatternScanner
)
from .brooks_concepts import (
    detect_trend_day, detect_reversal_day,
    detect_opening_range_breakout, BrooksAnalyzer
)
from .risk import PositionSizer, RiskManager


class PriceActionStrategy:
    """
    Price Action 交易策略
    ====================
    
    核心理念：
    1. 趋势判断：只用SMA判断方向
    2. 关键位：支撑/阻力、趋势线
    3. 信号：Pin Bar、吞没、突破、假突破
    4. 止损：结构止损 + ATR止损
    5. 仓位：2%风险原则
    
    入场流程：
    1. 判断趋势（上涨/下跌/震荡）
    2. 等待价格接近关键位
    3. 等待价格行为确认
    4. 执行入场
    """
    
    def __init__(self, 
                 atr_period=10,      # 优化值：10（默认14）
                 sma_period=30,      # 优化值：30（默认50）
                 risk_percent=0.02,
                 atr_stop_multiplier=1.5,  # 优化值：1.5（默认2.0）
                 min_body_ratio=2.0,
                 min_shadow_ratio=2.0,
                 lookback_period=20,
                 require_trend_confirmation=True,
                 use_brooks=True,
                 brooks_window=5):
        """
        初始化策略参数
        
        Args:
            atr_period: ATR计算周期
            sma_period: 均线周期，用于判断趋势
            risk_percent: 单笔风险比例（默认2%）
            atr_stop_multiplier: ATR止损倍数
            min_body_ratio: Pin Bar下影线/实体最小比例
            min_shadow_ratio: 下影线/上影线最小比例
            lookback_period: 关键位回溯周期
            require_trend_confirmation: 是否要求趋势确认
            use_brooks: 是否使用Brooks特色分析
            brooks_window: Brooks分析窗口
        """
        self.atr_period = atr_period
        self.sma_period = sma_period
        self.risk_percent = risk_percent
        self.atr_stop_multiplier = atr_stop_multiplier
        self.min_body_ratio = min_body_ratio
        self.min_shadow_ratio = min_shadow_ratio
        self.lookback_period = lookback_period
        self.require_trend_confirmation = require_trend_confirmation
        self.use_brooks = use_brooks
        self.brooks_window = brooks_window
        
        # 初始化子模块
        self.pattern_scanner = PatternScanner()
        self.brooks_analyzer = BrooksAnalyzer(window=brooks_window, lookback=lookback_period)
        self.position_sizer = PositionSizer(risk_percent=risk_percent)
        self.risk_manager = RiskManager(max_drawdown=0.2)
        
        # 状态
        self.current_trend = None
        self.last_signal = None
        self.last_signal_idx = None
        
        # 统计
        self.stats = {
            'total_signals': 0,
            'bullish_signals': 0,
            'bearish_signals': 0
        }
    
    def detect_trend(self, closes):
        """判断趋势方向"""
        if len(closes) < self.sma_period:
            return 'neutral'
        
        sma_value = sma(closes, self.sma_period)
        current_price = closes[-1]
        
        if current_price > sma_value:
            return 'bullish'
        elif current_price < sma_value:
            return 'bearish'
        else:
            return 'neutral'
    
    def find_support_resistance(self, highs, lows, closes, idx):
        """
        找到关键支撑/阻力位
        """
        lookback = self.lookback_period
        
        if idx < lookback:
            return None, None
        
        # 最近N天的最低点和最高点作为关键位
        resistance = highest(highs, lookback)
        support = lowest(lows, lookback)
        
        return support, resistance
    
    def check_key_level_approach(self, closes, highs, lows, support, resistance, tolerance=0.005):
        """
        检查价格是否接近关键位
        """
        current_price = closes[-1]
        
        # 检查是否接近支撑
        if support is not None:
            if abs(current_price - support) / support <= tolerance:
                return 'support'
        
        # 检查是否接近阻力
        if resistance is not None:
            if abs(current_price - resistance) / resistance <= tolerance:
                return 'resistance'
        
        return None
    
    def detect_signals(self, opens, closes, highs, lows, idx):
        """
        检测所有价格行为信号
        """
        signals = []
        
        # Pin Bar
        if is_pin_bar(opens, closes, highs, lows, idx, 
                      body_ratio=self.min_body_ratio, 
                      shadow_ratio=self.min_shadow_ratio):
            signals.append('pin_bar')
        
        # 吞没
        engulf = is_engulfing(opens, closes, idx)
        if engulf:
            signals.append(f'engulfing_{engulf}')
        
        # Inside Bar
        if is_inside_bar(opens, highs, lows, closes, idx):
            signals.append('inside_bar')
        
        # Outside Bar
        outside = is_outside_bar(opens, highs, lows, closes, idx)
        if outside:
            signals.append(f'outside_bar_{outside}')
        
        # Momentum
        momentum = is_momentum(opens, closes, idx)
        if momentum:
            signals.append(f'momentum_{momentum}')
        
        # Breakout
        breakout = is_breakout(highs, lows, closes, idx, lookback=self.lookback_period)
        if breakout:
            signals.append(f'breakout_{breakout}')
        
        # False Breakout
        false_breakout = is_false_breakout(opens, highs, lows, closes, idx, lookback=self.lookback_period)
        if false_breakout:
            signals.append(f'false_breakout_{false_breakout}')
        
        return signals
    
    def get_signal_direction(self, signals, trend):
        """
        根据信号和趋势判断方向
        """
        bullish_signals = ['pin_bar', 'engulfing_bullish', 'outside_bar_bullish', 
                          'momentum_bullish', 'breakout_up', 'false_breakout_bullish']
        bearish_signals = ['shooting_star', 'engulfing_bearish', 'outside_bar_bearish',
                          'momentum_bearish', 'breakout_down', 'false_breakout_bearish']
        
        bullish_count = sum(1 for s in signals if any(b in s for b in bullish_signals))
        bearish_count = sum(1 for s in signals if any(b in s for b in bearish_signals))
        
        if bullish_count > bearish_count:
            return 'bullish'
        elif bearish_count > bullish_count:
            return 'bearish'
        else:
            return 'neutral'
    
    def calculate_stop_loss(self, opens, highs, lows, closes, idx, direction, support, resistance):
        """
        计算止损位置
        优先结构止损，其次ATR止损
        """
        atr_value = atr(opens, highs, lows, closes, idx, period=self.atr_period)
        current_price = closes[idx]
        
        if direction == 'bullish':
            # 多头止损：跌破前低或ATR止损
            structure_stop = lowest(lows, self.lookback_period)
            atr_stop = current_price - atr_value * self.atr_stop_multiplier
            
            # 取较高的止损（对多头更安全）
            stop_loss = max(structure_stop, atr_stop)
            
            return stop_loss
        
        else:  # bearish
            # 空头止损：突破前高或ATR止损
            structure_stop = highest(highs, self.lookback_period)
            atr_stop = current_price + atr_value * self.atr_stop_multiplier
            
            # 取较低的止损（对空头更安全）
            stop_loss = min(structure_stop, atr_stop)
            
            return stop_loss
    
    def calculate_take_profit(self, entry, stop_loss, direction, risk_reward=2.0):
        """
        计算止盈位置
        默认2:1盈亏比
        """
        risk = abs(entry - stop_loss)
        
        if direction == 'bullish':
            take_profit = entry + risk * risk_reward
        else:
            take_profit = entry - risk * risk_reward
        
        return take_profit
    
    def analyze(self, opens, highs, lows, closes, idx):
        """
        综合分析 - 策略核心
        返回完整的分析结果和交易建议
        """
        result = {
            'idx': idx,
            'close': closes[idx],
            'trend': None,
            'support': None,
            'resistance': None,
            'near_key_level': None,
            'patterns': [],
            'pattern_direction': 'neutral',
            'brooks_signal': None,
            'brooks_strength': 0,
            'final_direction': 'neutral',
            'confidence': 0,
            'entry': None,
            'stop_loss': None,
            'take_profit': None,
            'risk_reward': None,
            'signal_strength': 0
        }
        
        # 1. 趋势判断
        trend = self.detect_trend(closes)
        result['trend'] = trend
        
        # 如果要求趋势确认且趋势不明确，返回
        if self.require_trend_confirmation and trend == 'neutral':
            return result
        
        # 2. 找关键位
        support, resistance = self.find_support_resistance(highs, lows, closes, idx)
        result['support'] = support
        result['resistance'] = resistance
        
        # 3. 检查是否接近关键位
        near_level = self.check_key_level_approach(closes, highs, lows, support, resistance)
        result['near_key_level'] = near_level
        
        # 4. 检测价格行为信号
        patterns = self.detect_signals(opens, closes, highs, lows, idx)
        result['patterns'] = patterns
        result['pattern_direction'] = self.get_signal_direction(patterns, trend)
        
        # 5. Brooks 分析
        if self.use_brooks:
            brooks_direction, brooks_strength, brooks_signals = \
                self.brooks_analyzer.get_brooks_signal(opens, highs, lows, closes, idx)
            result['brooks_signal'] = brooks_direction
            result['brooks_strength'] = brooks_strength
        
        # 6. 综合判断
        directions = []
        confidences = []
        
        # 趋势
        if trend != 'neutral':
            directions.append(trend)
            confidences.append(2 if result['near_key_level'] else 1)
        
        # 价格行为
        if result['pattern_direction'] != 'neutral':
            directions.append(result['pattern_direction'])
            confidences.append(2)
        
        # Brooks
        if self.use_brooks and result['brooks_signal'] != 'neutral':
            directions.append(result['brooks_signal'])
            confidences.append(result['brooks_strength'])
        
        # 统计最终方向
        bullish = directions.count('bullish')
        bearish = directions.count('bearish')
        
        if bullish > bearish:
            result['final_direction'] = 'bullish'
            result['confidence'] = bullish / len(directions) if directions else 0
        elif bearish > bullish:
            result['final_direction'] = 'bearish'
            result['confidence'] = bearish / len(directions) if directions else 0
        
        # 7. 计算交易参数（如果有信号）
        if result['final_direction'] != 'neutral':
            direction = result['final_direction']
            
            # 入场价：当前价格
            entry = closes[idx]
            
            # 止损
            stop_loss = self.calculate_stop_loss(opens, highs, lows, closes, idx, 
                                                 direction, support, resistance)
            
            # 止盈（2:1盈亏比）
            take_profit = self.calculate_take_profit(entry, stop_loss, direction)
            
            # 计算实际盈亏比
            risk = abs(entry - stop_loss)
            reward = abs(take_profit - entry)
            risk_reward = reward / risk if risk > 0 else 0
            
            result['entry'] = entry
            result['stop_loss'] = stop_loss
            result['take_profit'] = take_profit
            result['risk_reward'] = risk_reward
            result['signal_strength'] = sum(confidences)
            
            # 更新统计
            self.stats['total_signals'] += 1
            if direction == 'bullish':
                self.stats['bullish_signals'] += 1
            else:
                self.stats['bearish_signals'] += 1
        
        return result
    
    def __repr__(self):
        return (f"PriceActionStrategy(atr_period={self.atr_period}, "
                f"sma_period={self.sma_period}, risk={self.risk_percent*100}%, "
                f"trend_conf={'Y' if self.require_trend_confirmation else 'N'})")
