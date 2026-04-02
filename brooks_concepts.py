"""
brooks_concepts.py - Brooks Trading Course 特色概念
====================================================
包含 Brooks 独特的价格行为分析概念
"""

from .indicators import sma, atr


# ==================== Trend Day 趋势日 ====================

def detect_trend_day(opens, closes, highs, lows, idx, threshold=0.6):
    """
    Trend Day（趋势日）
    特征：开盘后快速突破，形成明显的单边行情
    - 趋势日当天均会有短暂回调
    - 顺势交易是最佳策略
    
    判断条件：
    1. 开盘30分钟后的走势超过当天区间的60%
    2. 回调幅度通常不超过38.2%
    3. 顺着趋势方向收盘
    
    Args:
        threshold: 趋势强度阈值（0-1），越高越严格
    """
    if idx < 5:
        return False
    
    # 获取当天数据
    day_range = highs[idx] - lows[idx]
    if day_range == 0:
        return False
    
    open_price = opens[idx]
    close_price = closes[idx]
    
    # 计算趋势强度
    if close_price > open_price:
        # 上涨趋势日
        move = close_price - open_price
        trend_strength = move / day_range
        
        if trend_strength >= threshold:
            return 'bullish'
    
    else:
        # 下跌趋势日
        move = open_price - close_price
        trend_strength = move / day_range
        
        if trend_strength >= threshold:
            return 'bearish'
    
    return False


def detect_trend_day_30min(opens, highs, lows, closes, idx, 
                            lookback_bars=3, trend_threshold=0.6, retrace_max=0.382):
    """
    基于30分钟数据的 Trend Day 检测
    模拟 Brooks 的开盘30分钟区间突破策略
    
    Args:
        lookback_bars: 向前看的K线数（每个bar代表一个时间单位）
        trend_threshold: 趋势强度阈值
        retrace_max: 最大回调比例（Fibonacci）
    """
    if idx < lookback_bars + 5:
        return False
    
    # 模拟30分钟区间
    # 用前N个bar作为"开盘区间"
    first_n = opens[max(0, idx-lookback_bars):idx]
    open_range_high = max(highs[max(0, idx-lookback_bars):idx])
    open_range_low = min(lows[max(0, idx-lookback_bars):idx])
    
    if open_range_high == open_range_low:
        return False
    
    current_close = closes[idx]
    current_high = highs[idx]
    current_low = lows[idx]
    
    # 突破开盘区间
    if current_close > open_range_high:
        # 向上突破
        pullback_low = min(lows[idx-lookback_bars:idx+1])
        pullback = current_high - pullback_low
        
        if pullback / (current_high - open_range_low) <= retrace_max:
            return 'bullish'
    
    elif current_close < open_range_low:
        # 向下突破
        pullback_high = max(highs[idx-lookback_bars:idx+1])
        pullback = pullback_high - current_low
        
        if pullback / (open_range_high - current_low) <= retrace_max:
            return 'bearish'
    
    return False


# ==================== Reversal Day 反转日 ====================

def detect_reversal_day(opens, closes, highs, lows, idx, threshold=0.5):
    """
    Reversal Day（反转日）
    特征：趋势反转信号
    - 开盘朝一个方向运行，然后反转
    - 反转后通常有强劲走势
    
    判断条件：
    1. 收盘与开盘方向相反
    2. 收盘位置超过区间的50%
    3. 反转幅度超过区间的30%
    """
    if idx < 1:
        return False
    
    day_range = highs[idx] - lows[idx]
    if day_range == 0:
        return False
    
    open_price = opens[idx]
    close_price = closes[idx]
    
    # 计算当天走势
    if close_price > open_price:
        # 阳线实体
        body = close_price - open_price
        # 开盘到高点
        open_to_high = highs[idx] - open_price
        # 反转幅度（高点到收盘）
        reversal = highs[idx] - close_price
        
        # 反转条件：开盘上涨后回落，收盘在低位
        if (reversal / day_range >= threshold and
            close_price < open_price + body * 0.5):
            return 'bearish_reversal'  # 冲高回落，看跌
    
    else:
        # 阴线实体
        body = open_price - close_price
        # 开盘到低点
        open_to_low = open_price - lows[idx]
        # 反转幅度（低点到收盘）
        reversal = close_price - lows[idx]
        
        # 反转条件：开盘下跌后反弹，收盘在高位
        if (reversal / day_range >= threshold and
            close_price > open_price - body * 0.5):
            return 'bullish_reversal'  # 探底反弹，看涨
    
    return False


def detect_double_top_bottom(opens, highs, lows, closes, idx, 
                              lookback=20, tolerance=0.02):
    """
    双顶/双底形态
    Brooks 强调的重要反转形态
    
    Args:
        lookback: 回溯周期
        tolerance: 允许的偏差比例（2%以内认为是同一水平）
    """
    if idx < lookback:
        return None
    
    # 简化实现：检测类似高点的出现
    recent_highs = highs[idx-lookback+1:idx+1]
    recent_lows = lows[idx-lookback+1:idx+1]
    
    current_high = highs[idx]
    current_low = lows[idx]
    
    # 检测双顶
    high_threshold = current_high * (1 - tolerance)
    for i in range(idx-lookback, idx):
        if abs(recent_highs[i] - current_high) / current_high < tolerance:
            # 找到相近的高点
            return 'double_top'
    
    # 检测双底
    low_threshold = current_low * (1 + tolerance)
    for i in range(idx-lookback, idx):
        if abs(recent_lows[i] - current_low) / current_low < tolerance:
            # 找到相近的低点
            return 'double_bottom'
    
    return None


# ==================== Opening Range Breakout 开盘区间突破 ====================

def detect_opening_range_breakout(opens, highs, lows, closes, idx, 
                                   window=5, atr_multiplier=0.5):
    """
    Opening Range Breakout（开盘区间突破）
    Brooks 最喜欢的交易策略之一
    
    步骤：
    1. 确定开盘区间（通常用开盘后N根K线）
    2. 等待突破
    3. 顺势交易
    4. 止损设在区间另一端
    
    Args:
        window: 开盘区间K线数
        atr_multiplier: 区间宽度参考ATR的比例
    """
    if idx < window + 1:
        return None
    
    # 确定开盘区间
    range_high = max(highs[idx-window:idx])
    range_low = min(lows[idx-window:idx])
    range_width = range_high - range_low
    
    # 计算ATR
    current_atr = atr(opens, highs, lows, closes, idx, period=14)
    
    # 区间太小，跳过
    if range_width < current_atr * atr_multiplier:
        return None
    
    current_close = closes[idx]
    current_high = highs[idx]
    current_low = lows[idx]
    
    # 向上突破
    if current_close > range_high:
        stop_loss = range_low
        take_profit1 = range_high + range_width
        take_profit2 = range_high + range_width * 2
        
        return {
            'direction': 'long',
            'entry': range_high,
            'stop_loss': stop_loss,
            'take_profit': take_profit2,
            'risk_reward': (take_profit2 - range_high) / (range_high - stop_loss),
            'range_width': range_width
        }
    
    # 向下突破
    elif current_close < range_low:
        stop_loss = range_high
        take_profit1 = range_low - range_width
        take_profit2 = range_low - range_width * 2
        
        return {
            'direction': 'short',
            'entry': range_low,
            'stop_loss': stop_loss,
            'take_profit': take_profit2,
            'risk_reward': (range_low - take_profit2) / (stop_loss - range_low),
            'range_width': range_width
        }
    
    return None


# ==================== Trend Line Trading 趋势线交易 ====================

def find_trendline_points(highs_or_lows, idx, lookback=10):
    """
    找到趋势线的关键点
    简化版本：找最近的高点/低点连接点
    """
    points = []
    for i in range(max(0, idx-lookback), idx):
        is_local_high = True
        is_local_low = True
        
        # 检查是否是局部高点
        for j in range(max(0, i-2), min(idx, i+3)):
            if highs_or_lows[j] > highs_or_lows[i]:
                is_local_high = False
            if highs_or_lows[j] < highs_or_lows[i]:
                is_local_low = False
        
        if is_local_high:
            points.append((i, highs_or_lows[i], 'high'))
        elif is_local_low:
            points.append((i, highs_or_lows[i], 'low'))
    
    return points


def is_near_trendline(price, highs_or_lows, idx, lookback=10, tolerance=0.005):
    """
    检测价格是否接近趋势线
    """
    points = find_trendline_points(highs_or_lows, idx, lookback)
    
    if len(points) < 2:
        return None
    
    # 用最近的两个点画趋势线
    recent_points = points[-2:]
    
    x1, y1, _ = recent_points[0]
    x2, y2, _ = recent_points[1]
    
    if x2 == x1:
        return None
    
    # 计算趋势线上的预期价格
    slope = (y2 - y1) / (x2 - x1)
    expected_price = y1 + slope * (idx - x1)
    
    # 检查当前价格是否接近趋势线
    diff = abs(price - expected_price) / expected_price
    
    if diff <= tolerance:
        return {
            'expected_price': expected_price,
            'actual_price': price,
            'diff_percent': diff * 100,
            'slope': slope,
            'type': 'resistance' if slope < 0 else 'support'  # 下跌趋势线是阻力
        }
    
    return None


# ==================== Brooks 综合分析器 ====================

class BrooksAnalyzer:
    """
    Brooks 价格行为分析器
    整合所有 Brooks 特色概念
    """
    
    def __init__(self, window=5, lookback=20):
        self.window = window
        self.lookback = lookback
    
    def analyze(self, opens, highs, lows, closes, idx):
        """
        综合分析
        返回所有检测到的 Brooks 概念
        """
        results = {
            'trend_day': None,
            'reversal_day': None,
            'orb': None,
            'double': None,
            'near_trendline': None
        }
        
        # Trend Day
        results['trend_day'] = detect_trend_day(opens, closes, highs, lows, idx)
        
        # Reversal Day
        results['reversal_day'] = detect_reversal_day(opens, closes, highs, lows, idx)
        
        # Opening Range Breakout
        results['orb'] = detect_opening_range_breakout(opens, highs, lows, closes, idx, window=self.window)
        
        # Double Top/Bottom
        results['double'] = detect_double_top_bottom(opens, highs, lows, closes, idx, lookback=self.lookback)
        
        # Near Trendline (using closes as reference)
        results['near_trendline'] = is_near_trendline(closes[idx], closes, idx, lookback=self.lookback)
        
        return results
    
    def get_brooks_signal(self, opens, highs, lows, closes, idx):
        """
        获取 Brooks 风格的交易信号
        """
        analysis = self.analyze(opens, highs, lows, closes, idx)
        
        signals = []
        
        # Trend Day 信号
        if analysis['trend_day']:
            signals.append(('trend_day', analysis['trend_day'], 3))
        
        # Reversal Day 信号
        if analysis['reversal_day']:
            direction = 'bullish' if 'bullish' in analysis['reversal_day'] else 'bearish'
            signals.append(('reversal_day', direction, 2))
        
        # ORB 信号
        if analysis['orb']:
            signals.append(('orb', analysis['orb']['direction'], 3))
        
        # 双顶/底
        if analysis['double']:
            direction = 'bearish' if 'top' in analysis['double'] else 'bullish'
            signals.append(('double', direction, 2))
        
        # 趋势线
        if analysis['near_trendline']:
            direction = 'bearish' if analysis['near_trendline']['type'] == 'resistance' else 'bullish'
            signals.append(('trendline', direction, 1))
        
        if not signals:
            return None, 0, []
        
        # 统计信号
        bullish = sum(1 for s in signals if s[1] == 'bullish')
        bearish = sum(1 for s in signals if s[1] == 'bearish')
        strength = sum(s[2] for s in signals)
        
        if bullish > bearish:
            return 'bullish', strength, signals
        elif bearish > bullish:
            return 'bearish', strength, signals
        else:
            return 'neutral', strength, signals
