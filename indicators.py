"""
indicators.py - 技术指标（自实现，零依赖）
==========================================
纯 Python + Pandas 实现，不使用任何外部技术指标库
"""

import math


# ==================== 基础统计 ====================

def highest(values, period):
    """N日内最高值"""
    if len(values) < period:
        return max(values) if values else None
    return max(values[-period:])


def lowest(values, period):
    """N日内最低值"""
    if len(values) < period:
        return min(values) if values else None
    return min(values[-period:])


def sma(values, period):
    """简单移动平均 (SMA)"""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema(values, period):
    """指数移动平均 (EMA)"""
    if len(values) < period:
        return None
    
    multiplier = 2 / (period + 1)
    ema_value = sum(values[:period]) / period
    
    for price in values[period:]:
        ema_value = (price - ema_value) * multiplier + ema_value
    
    return ema_value


# ==================== ATR 相关 ====================

def calculate_true_range(opens, highs, lows, closes, idx):
    """
    计算 True Range
    TR = max(H-L, |H-PC|, |L-PC|)
    """
    if idx == 0:
        return highs[idx] - lows[idx]
    
    prev_close = closes[idx - 1]
    current_high = highs[idx]
    current_low = lows[idx]
    
    tr1 = current_high - current_low
    tr2 = abs(current_high - prev_close)
    tr3 = abs(current_low - prev_close)
    
    return max(tr1, tr2, tr3)


def atr(opens, highs, lows, closes, idx, period=14):
    """
    平均真实波幅 (ATR)
    """
    if idx < period:
        # 数据不足，用简单平均
        tr_sum = sum(
            calculate_true_range(opens, highs, lows, closes, i)
            for i in range(idx + 1)
        )
        return tr_sum / (idx + 1)
    
    # 使用 EMA 方式计算
    tr_sum = sum(
        calculate_true_range(opens, highs, lows, closes, i)
        for i in range(idx - period + 1, idx + 1)
    )
    
    return tr_sum / period


def atr_trailing_stop(opens, highs, lows, closes, idx, period=14, multiplier=3.0):
    """
    ATR 追踪止损
    """
    if idx < period:
        return None
    
    current_atr = atr(opens, highs, lows, closes, idx, period)
    
    # 多头止损
    highest_close = max(closes[idx - period + 1:idx + 1])
    trailing_stop = highest_close - current_atr * multiplier
    
    return trailing_stop


# ==================== 趋势判断 ====================

def adx(opens, highs, lows, closes, idx, period=14):
    """
    平均趋向指数 (ADX)
    简化版本：基于价格变动率判断趋势强度
    """
    if len(closes) < period + 1:
        return None
    
    # 计算价格变化
    changes = []
    for i in range(1, min(period + 1, len(closes))):
        change = (closes[-i] - closes[-i - 1]) / closes[-i - 1]
        changes.append(abs(change))
    
    if not changes:
        return None
    
    # 平均变化率作为趋势强度指标
    avg_change = sum(changes) / len(changes)
    
    # 转换为类似 ADX 的 0-100 范围
    adx_value = min(avg_change * 1000, 100)
    
    return adx_value


def rsi(prices, period=14):
    """
    相对强弱指数 (RSI)
    简化版本
    """
    if len(prices) < period + 1:
        return None
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    if len(gains) < period:
        return None
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi_value = 100 - (100 / (1 + rs))
    
    return rsi_value


# ==================== 支撑阻力 ====================

def calculate_support_resistance(highs, lows, period=20):
    """
    计算支撑和阻力位
    返回：(支撑位, 阻力位, 枢轴)
    """
    if len(highs) < period or len(lows) < period:
        return None, None, None
    
    # 最近 N 日的高低点
    resistance = max(highs[-period:])
    support = min(lows[-period:])
    
    # 枢轴点
    pivot = (resistance + support + (highs[-1] + lows[-1]) / 2) / 3
    
    return support, resistance, pivot


def fibonacci_retracement(high, low, levels=[0.236, 0.382, 0.5, 0.618, 0.786]):
    """
    斐波那契回撤位
    """
    diff = high - low
    retracements = {}
    
    for level in levels:
        retracements[level] = high - diff * level
    
    return retracements


# ==================== 波动性 ====================

def bollinger_bands(prices, period=20, std_dev=2):
    """
    布林带
    返回：(中轨, 上轨, 下轨)
    """
    if len(prices) < period:
        return None, None, None
    
    middle = sma(prices, period)
    
    # 计算标准差
    mean = middle
    variance = sum((p - mean) ** 2 for p in prices[-period:]) / period
    std = math.sqrt(variance)
    
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    
    return middle, upper, lower


def keltner_channels(opens, highs, lows, closes, idx, period=20, atr_period=14, multiplier=2):
    """
    肯特纳通道
    """
    if idx < period:
        return None, None, None
    
    middle = sma(closes, period)
    current_atr = atr(opens, highs, lows, closes, idx, atr_period)
    
    upper = middle + multiplier * current_atr
    lower = middle - multiplier * current_atr
    
    return middle, upper, lower
