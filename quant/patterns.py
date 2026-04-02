"""
patterns.py - 价格行为形态检测
==============================
纯K线形态识别，不使用任何技术指标
"""

from .indicators import highest, lowest, atr


# ==================== Pin Bar 家族 ====================

def is_hammer(opens, closes, highs, lows, idx, body_ratio=2.0, shadow_ratio=2.0):
    """
    锤子线 (Hammer) - 底部反转信号
    特征：下影线很长，至少是实体的2倍，上影线很短或没有
    
    Args:
        body_ratio: 下影线/实体 最小比例
        shadow_ratio: 下影线/上影线 最小比例
    """
    if idx < 1:
        return False
    
    o, c = opens[idx], closes[idx]
    h, l = highs[idx], lows[idx]
    
    body = abs(c - o)
    if body == 0:
        return False
    
    lower_shadow = min(o, c) - l
    upper_shadow = h - max(o, c)
    
    # 锤子线：下影线很长，阳线
    if (lower_shadow >= body * body_ratio and 
        lower_shadow >= upper_shadow * shadow_ratio and
        c > o):
        return True
    
    return False


def is_shooting_star(opens, closes, highs, lows, idx, body_ratio=2.0, shadow_ratio=2.0):
    """
    射击星 (Shooting Star) - 顶部反转信号
    特征：上影线很长，至少是实体的2倍，下影线很短或没有
    """
    if idx < 1:
        return False
    
    o, c = opens[idx], closes[idx]
    h, l = highs[idx], lows[idx]
    
    body = abs(c - o)
    if body == 0:
        return False
    
    lower_shadow = min(o, c) - l
    upper_shadow = h - max(o, c)
    
    # 射击星：上影线很长，阴线
    if (upper_shadow >= body * body_ratio and 
        upper_shadow >= lower_shadow * shadow_ratio and
        c < o):
        return True
    
    return False


def is_pin_bar(opens, closes, highs, lows, idx, body_ratio=2.0, shadow_ratio=2.0):
    """
    Pin Bar - 锤子线和射击星的统称
    判断条件：影线是实体的2倍以上，且影线长度超过另一端影线的2倍
    """
    return is_hammer(opens, closes, highs, lows, idx, body_ratio, shadow_ratio) or \
           is_shooting_star(opens, closes, highs, lows, idx, body_ratio, shadow_ratio)


# ==================== 吞没形态 ====================

def is_engulfing(opens, closes, idx):
    """
    吞没形态 (Engulfing Pattern)
    - 阳包阴（看涨）：第一天阴线，第二天阳线且完全吞没第一天的实体
    - 阴包阳（看跌）：第一天阳线，第二天阴线且完全吞没第一天的实体
    """
    if idx < 1:
        return False
    
    # 今天看涨吞没
    if closes[idx] > opens[idx] and closes[idx-1] < opens[idx-1]:
        if closes[idx] > opens[idx-1] and opens[idx] < closes[idx-1]:
            return 'bullish'
    
    # 今天看跌吞没
    if closes[idx] < opens[idx] and closes[idx-1] > opens[idx-1]:
        if closes[idx] < opens[idx-1] and opens[idx] > closes[idx-1]:
            return 'bearish'
    
    return False


def is_engulfing_bullish(opens, closes, idx):
    """看涨吞没"""
    result = is_engulfing(opens, closes, idx)
    return result == 'bullish'


def is_engulfing_bearish(opens, closes, idx):
    """看跌吞没"""
    result = is_engulfing(opens, closes, idx)
    return result == 'bearish'


# ==================== 母子形态 ====================

def is_harami(opens, closes, idx):
    """
    母子形态 (Harami) - 第二天实体在第一天实体内部
    - 锤子娘子（看涨）：第一天大阴线，第二天小阳线在第一天实体内
    - 乌云盖顶（看跌）：第一天大阳线，第二天小阴线在第一天实体内
    """
    if idx < 1:
        return False
    
    body1 = abs(closes[idx-1] - opens[idx-1])
    body2 = abs(closes[idx] - opens[idx])
    
    if body1 == 0 or body2 == 0:
        return False
    
    # 第二天实体在第一天实体内
    inside = (max(opens[idx], closes[idx]) < max(opens[idx-1], closes[idx-1]) and
              min(opens[idx], closes[idx]) > min(opens[idx-1], closes[idx-1]))
    
    if not inside:
        return False
    
    # 第二天实体远小于第一天
    if body2 >= body1 * 0.5:
        return False
    
    # 看涨母子：第一天阴线，第二天阳线
    if closes[idx-1] < opens[idx-1] and closes[idx] > opens[idx]:
        return 'bullish'
    
    # 看跌母子：第一天阳线，第二天阴线
    if closes[idx-1] > opens[idx-1] and closes[idx] < opens[idx]:
        return 'bearish'
    
    return False


# ==================== 内部结构 ====================

def is_inside_bar(opens, highs, lows, closes, idx):
    """
    内部形态 (Inside Bar)
    当天的高低点在昨天的范围内
    意味着市场在盘整，可能突破
    """
    if idx < 1:
        return False
    
    if (highs[idx] <= highs[idx-1] and 
        lows[idx] >= lows[idx-1]):
        return True
    
    return False


def is_outside_bar(opens, highs, lows, closes, idx):
    """
    外部形态 (Outside Bar)
    当天的高低点完全包含了昨天的高低点
    多空双方激烈博弈，可能反转
    """
    if idx < 1:
        return False
    
    if (highs[idx] > highs[idx-1] and 
        lows[idx] < lows[idx-1]):
        return 'bullish' if closes[idx] > opens[idx] else 'bearish'
    
    return False


# ==================== 趋势延续形态 ====================

def is_momentum(opens, closes, idx, period=3):
    """
    动能信号 - 连续N天上涨/下跌
    说明市场有明确趋势
    """
    if idx < period - 1:
        return False
    
    # 连续上涨
    if all(closes[idx-i] > closes[idx-i-1] for i in range(period)):
        return 'bullish'
    
    # 连续下跌
    if all(closes[idx-i] < closes[idx-i-1] for i in range(period)):
        return 'bearish'
    
    return False


def is_three_push(opens, closes, highs, idx, lookback=10):
    """
    三推形态 (Three Push) - 类似三次底部/顶部
    可能形成强支撑/阻力
    """
    if idx < lookback:
        return False
    
    recent_closes = closes[idx-lookback+1:idx+1]
    
    # 简单实现：检测低点抬高（上涨趋势中的回调）
    lows_local = []
    for i in range(1, lookback-1):
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            lows_local.append(lows[i])
    
    if len(lows_local) >= 3:
        # 检查是否三次低点逐步抬高
        if lows_local[-1] > lows_local[-2] > lows_local[-3]:
            return 'bullish'
    
    return False


# ==================== 突破形态 ====================

def is_breakout(highs, lows, closes, idx, lookback=20):
    """
    突破检测 - 价格突破N日高低点
    """
    if idx < lookback:
        return False
    
    current_close = closes[idx]
    highest_high = highest(highs, lookback)
    lowest_low = lowest(lows, lookback)
    
    if highest_high is None or lowest_low is None:
        return False
    
    # 突破20日高点
    if current_close > highest_high:
        return 'up'
    
    # 跌破20日低点
    if current_close < lowest_low:
        return 'down'
    
    return False


def is_false_breakout(opens, highs, lows, closes, idx, lookback=20):
    """
    假突破 (False Breakout)
    先突破关键位，然后迅速回落
    高概率反转信号
    """
    if idx < lookback + 2:
        return False
    
    # 昨天突破
    yesterday_breakout = is_breakout(highs, lows, closes, idx-1, lookback)
    
    if not yesterday_breakout:
        return False
    
    # 今天重新回到区间内
    highest_high = highest(highs, lookback)
    lowest_low = lowest(lows, lookback)
    
    if yesterday_breakout == 'up':
        # 向上假突破：突破后今天下跌
        if closes[idx] < opens[idx-1]:
            return 'bearish'
    
    if yesterday_breakout == 'down':
        # 向下假突破：跌破后今天上涨
        if closes[idx] > opens[idx-1]:
            return 'bullish'
    
    return False


# ==================== 形态扫描器 ====================

class PatternScanner:
    """
    价格形态扫描器
    一次扫描检测多种形态
    """
    
    def __init__(self):
        self.patterns = {}
    
    def scan(self, opens, closes, highs, lows, idx):
        """
        扫描所有形态
        返回检测到的所有形态列表
        """
        detected = []
        
        # Pin Bar
        if is_pin_bar(opens, closes, highs, lows, idx):
            detected.append('pin_bar')
        
        # 吞没
        engulf = is_engulfing(opens, closes, idx)
        if engulf:
            detected.append(f'engulfing_{engulf}')
        
        # 母子
        harami = is_harami(opens, closes, idx)
        if harami:
            detected.append(f'harami_{harami}')
        
        # 内外
        if is_inside_bar(opens, highs, lows, closes, idx):
            detected.append('inside_bar')
        
        outside = is_outside_bar(opens, highs, lows, closes, idx)
        if outside:
            detected.append(f'outside_bar_{outside}')
        
        # 动能
        momentum = is_momentum(opens, closes, idx)
        if momentum:
            detected.append(f'momentum_{momentum}')
        
        # 突破
        breakout = is_breakout(highs, lows, closes, idx)
        if breakout:
            detected.append(f'breakout_{breakout}')
        
        # 假突破
        false_breakout = is_false_breakout(opens, highs, lows, closes, idx)
        if false_breakout:
            detected.append(f'false_breakout_{false_breakout}')
        
        return detected
    
    def get_signals(self, opens, closes, highs, lows, idx):
        """
        获取综合信号
        返回：(方向, 强度, 形态列表)
        """
        patterns = self.scan(opens, closes, highs, lows, idx)
        
        bullish = sum(1 for p in patterns if 'bullish' in p or 'hammer' in p or 'engulfing_bull' in p or 'breakout_up' in p)
        bearish = sum(1 for p in patterns if 'bearish' in p or 'shooting' in p or 'engulfing_bear' in p or 'breakout_down' in p)
        
        strength = abs(bullish - bearish)
        direction = 'bullish' if bullish > bearish else 'bearish' if bearish > bullish else 'neutral'
        
        return direction, strength, patterns


# ==================== 便捷函数 ====================

def detect_all_patterns(opens, closes, highs, lows, idx):
    """一次性检测所有形态，返回格式化结果"""
    scanner = PatternScanner()
    direction, strength, patterns = scanner.get_signals(opens, closes, highs, lows, idx)
    
    return {
        'direction': direction,
        'strength': strength,
        'patterns': patterns,
        'bullish_count': len([p for p in patterns if 'bullish' in p]),
        'bearish_count': len([p for p in patterns if 'bearish' in p])
    }
