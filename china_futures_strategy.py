"""
china_futures_strategy.py - 国内期货 Price Action 策略
=====================================================
基于 Louie PriceAction + Brooks Trading Course
专为国内期货市场优化

作者: Price Action Trading System
版本: 1.0.0

国内期货特点：
- 交易时间碎片化（夜盘+日盘多个时段）
- 涨跌停板限制
- 主力合约换月跳空
- 高杠杆保证金制度

使用方法:
    from china_futures_strategy import ChinaFuturesStrategy
    
    strategy = ChinaFuturesStrategy(
        symbol='rb',  # 螺纹钢
        risk_percent=0.01,
        trading_hours='full'  # full=有夜盘, day=只有日盘
    )
"""

import math
from typing import Dict, List, Optional, Tuple, Any


# ==================== 国内期货品种配置 ====================
# 手续费说明 (交易所标准，期货公司可能加收):
# - 万分比: 手续费 = 合约价格 × contract_size × commission_rate
# - 固定金额: 固定手续费/手 (如黄金20元)
# 
# 交易费率 (2024年最新):
# | 品种 | 代码 | 手续费 | 备注 |
# |:---:|:---:|:---:|:---|
# | 螺纹钢 | rb | 万0.1 | 约4.5元/手 |
# | 热卷 | hc | 万0.1 | 约4.5元/手 |
# | 铁矿石 | i | 万0.1 | 10元/手 |
# | 焦炭 | j | 万0.1 | 约18元/手 |
# | 焦煤 | jm | 万0.1 | 约12元/手 |
# | 铜 | cu | 万0.5 | 约34元/手 |
# | 铝 | al | 万3 | 约9元/手 |
# | 锌 | zn | 万3 | 约12元/手 |
# | 镍 | ni | 万3 | 约12元/手 |
# | 锡 | sn | 万3 | 约18元/手 |
# | 橡胶 | ru | 万0.45 | 约9元/手 |
# | 沥青 | bu | 万1 | 约3.5元/手 |
# | 甲醇 | ma | 万2 | 约4元/手 |
# | PTA | ta | 万3 | 约4.5元/手 |
# | 纯碱 | TA | 万2 | 约8元/手 |
# | 原油 | sc | 万2.5 | 约22.5元/手 |
# | 黄金 | au | 20元/手 | 固定 |
# | 白银 | ag | 万0.5 | 约4元/手 |

FUTURES_CONFIG = {
    # 黑色系
    'rb': {'name': '螺纹钢', 'session': 'full', 'tick_size': 1, 'contract_size': 10, 'commission': 0.0001, 'commission_type': 'ratio'},
    'hc': {'name': '热轧卷板', 'session': 'full', 'tick_size': 1, 'contract_size': 10, 'commission': 0.0001, 'commission_type': 'ratio'},
    'i': {'name': '铁矿石', 'session': 'full', 'tick_size': 0.5, 'contract_size': 100, 'commission': 0.0001, 'commission_type': 'ratio'},
    'j': {'name': '焦炭', 'session': 'full', 'tick_size': 0.5, 'contract_size': 100, 'commission': 0.0001, 'commission_type': 'ratio'},
    'jm': {'name': '焦煤', 'session': 'full', 'tick_size': 0.5, 'contract_size': 60, 'commission': 0.0001, 'commission_type': 'ratio'},
    
    # 有色金属
    'cu': {'name': '铜', 'session': 'full', 'tick_size': 10, 'contract_size': 5, 'commission': 0.0005, 'commission_type': 'ratio'},
    'al': {'name': '铝', 'session': 'full', 'tick_size': 5, 'contract_size': 5, 'commission': 0.0003, 'commission_type': 'ratio'},
    'zn': {'name': '锌', 'session': 'full', 'tick_size': 5, 'contract_size': 5, 'commission': 0.0003, 'commission_type': 'ratio'},
    'ni': {'name': '镍', 'session': 'full', 'tick_size': 10, 'contract_size': 1, 'commission': 0.0003, 'commission_type': 'ratio'},
    'sn': {'name': '锡', 'session': 'full', 'tick_size': 10, 'contract_size': 1, 'commission': 0.0003, 'commission_type': 'ratio'},
    
    # 化工系
    'ru': {'name': '橡胶', 'session': 'full', 'tick_size': 5, 'contract_size': 10, 'commission': 0.000045, 'commission_type': 'ratio'},
    'bu': {'name': '沥青', 'session': 'full', 'tick_size': 2, 'contract_size': 10, 'commission': 0.0001, 'commission_type': 'ratio'},
    'ma': {'name': '甲醇', 'session': 'full', 'tick_size': 1, 'contract_size': 10, 'commission': 0.0002, 'commission_type': 'ratio'},
    'ta': {'name': 'PTA', 'session': 'full', 'tick_size': 2, 'contract_size': 5, 'commission': 0.0003, 'commission_type': 'ratio'},
    'ta0': {'name': 'PTA', 'session': 'full', 'tick_size': 2, 'contract_size': 5, 'commission': 0.0002, 'commission_type': 'ratio'},  # 纯碱
    'pp': {'name': '聚丙烯', 'session': 'full', 'tick_size': 1, 'contract_size': 5, 'commission': 0.0001, 'commission_type': 'ratio'},
    'l': {'name': '塑料', 'session': 'full', 'tick_size': 5, 'contract_size': 5, 'commission': 0.0001, 'commission_type': 'ratio'},
    'v': {'name': 'PVC', 'session': 'full', 'tick_size': 5, 'contract_size': 5, 'commission': 0.0001, 'commission_type': 'ratio'},
    
    # 农产品
    'm': {'name': '豆粕', 'session': 'full', 'tick_size': 1, 'contract_size': 10, 'commission': 0.0001, 'commission_type': 'ratio'},
    'y': {'name': '豆油', 'session': 'full', 'tick_size': 2, 'contract_size': 10, 'commission': 0.0002, 'commission_type': 'ratio'},
    'p': {'name': '棕榈油', 'session': 'full', 'tick_size': 2, 'contract_size': 10, 'commission': 0.00025, 'commission_type': 'ratio'},
    'cs': {'name': '玉米淀粉', 'session': 'day', 'tick_size': 1, 'contract_size': 10, 'commission': 0.00012, 'commission_type': 'ratio'},
    'c': {'name': '玉米', 'session': 'day', 'tick_size': 1, 'contract_size': 10, 'commission': 0.00012, 'commission_type': 'ratio'},
    'a': {'name': '黄大豆', 'session': 'day', 'tick_size': 1, 'contract_size': 10, 'commission': 0.0002, 'commission_type': 'ratio'},
    'b': {'name': '黄大豆', 'session': 'day', 'tick_size': 1, 'contract_size': 10, 'commission': 0.0002, 'commission_type': 'ratio'},
    
    # 油脂
    'oi': {'name': '菜籽油', 'session': 'full', 'tick_size': 1, 'contract_size': 10, 'commission': 0.0002, 'commission_type': 'ratio'},
    'rm': {'name': '菜籽粕', 'session': 'day', 'tick_size': 1, 'contract_size': 10, 'commission': 0.00015, 'commission_type': 'ratio'},
    
    # 软商品
    'cf': {'name': '棉花', 'session': 'day', 'tick_size': 5, 'contract_size': 5, 'commission': 0.00024, 'commission_type': 'ratio'},
    'sr': {'name': '白糖', 'session': 'day', 'tick_size': 1, 'contract_size': 10, 'commission': 0.00024, 'commission_type': 'ratio'},
    
    # 贵金属
    'au': {'name': '黄金', 'session': 'full', 'tick_size': 0.02, 'contract_size': 1000, 'commission': 20, 'commission_type': 'fixed'},
    'ag': {'name': '白银', 'session': 'full', 'tick_size': 1, 'contract_size': 15, 'commission': 0.00005, 'commission_type': 'ratio'},
    
    # 能源
    'sc': {'name': '原油', 'session': 'full', 'tick_size': 0.1, 'contract_size': 1000, 'commission': 0.00025, 'commission_type': 'ratio'},
    
    # 国债
    't': {'name': '10年期国债', 'session': 'day', 'tick_size': 0.005, 'contract_size': 10000, 'commission': 0.00012, 'commission_type': 'ratio'},
    'tf': {'name': '5年期国债', 'session': 'day', 'tick_size': 0.005, 'contract_size': 10000, 'commission': 0.00012, 'commission_type': 'ratio'},
}

# 交易时段配置
TRADING_SESSIONS = {
    'full': {  # 有夜盘的品种
        'night': {'start': 21, 'end': 23, 'next_day': True},
        'morning': {'start': 9, 'end': 10.25},
        'mid': {'start': 10.25, 'end': 10.5},  # 休盘
        'afternoon1': {'start': 10.5, 'end': 11.5},
        'afternoon2': {'start': 13.5, 'end': 15},
    },
    'day': {  # 只有日盘的品种
        'morning': {'start': 9, 'end': 10.15},
        'mid': {'start': 10.15, 'end': 10.3},
        'afternoon1': {'start': 10.3, 'end': 11.5},
        'afternoon2': {'start': 13.5, 'end': 15},
    }
}


# ==================== 指标计算（复用 price_action_framework） ====================

def highest(values: List[float], period: int) -> float:
    """N日内最高值"""
    if len(values) < period:
        return max(values) if values else 0
    return max(values[-period:])


def lowest(values: List[float], period: int) -> float:
    """N日内最低值"""
    if len(values) < period:
        return min(values) if values else 0
    return min(values[-period:])


def sma(values: List[float], period: int) -> Optional[float]:
    """简单移动平均"""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def atr(opens: List[float], highs: List[float], lows: List[float], 
        closes: List[float], idx: int, period: int = 14) -> float:
    """平均真实波幅"""
    if idx < 1:
        return highs[idx] - lows[idx]
    
    tr_list = []
    for i in range(max(1, idx - period + 1), idx + 1):
        prev_close = closes[i - 1]
        high = highs[i]
        low = lows[i]
        
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        tr_list.append(max(tr1, tr2, tr3))
    
    return sum(tr_list) / len(tr_list)


# ==================== 价格行为形态 ====================

def is_pin_bar(opens: List[float], closes: List[float], 
               highs: List[float], lows: List[float], 
               idx: int, body_ratio: float = 2.0, 
               shadow_ratio: float = 2.0) -> bool:
    """
    Pin Bar 检测
    下影线或上影线是实体的2倍以上
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
    
    # 锤子线（看涨）
    if (lower_shadow >= body * body_ratio and 
        lower_shadow >= upper_shadow * shadow_ratio and
        c > o):
        return True
    
    # 射击星（看跌）
    if (upper_shadow >= body * body_ratio and 
        upper_shadow >= lower_shadow * shadow_ratio and
        c < o):
        return True
    
    return False


def is_engulfing(opens: List[float], closes: List[float], idx: int) -> str:
    """
    吞没形态
    """
    if idx < 1:
        return ''
    
    # 看涨吞没
    if (closes[idx] > opens[idx] and closes[idx-1] < opens[idx-1] and
        closes[idx] > opens[idx-1] and opens[idx] < closes[idx-1]):
        return 'bullish'
    
    # 看跌吞没
    if (closes[idx] < opens[idx] and closes[idx-1] > opens[idx-1] and
        closes[idx] < opens[idx-1] and opens[idx] > closes[idx-1]):
        return 'bearish'
    
    return ''


def is_inside_bar(opens: List[float], highs: List[float], 
                  lows: List[float], closes: List[float], 
                  idx: int) -> bool:
    """
    内部形态 (Inside Bar)
    当日高低点在昨日范围内
    """
    if idx < 1:
        return False
    
    return (highs[idx] <= highs[idx-1] and 
            lows[idx] >= lows[idx-1])


def is_momentum(opens: List[float], closes: List[float], 
                idx: int, period: int = 3) -> str:
    """
    动能信号 - 连续N天同向移动
    """
    if idx < period - 1:
        return ''
    
    # 连续上涨
    if all(closes[idx-i] > closes[idx-i-1] for i in range(period)):
        return 'bullish'
    
    # 连续下跌
    if all(closes[idx-i] < closes[idx-i-1] for i in range(period)):
        return 'bearish'
    
    return ''


def is_breakout(highs: List[float], lows: List[float], 
                closes: List[float], idx: int, 
                lookback: int = 20) -> str:
    """
    突破检测
    """
    if idx < lookback:
        return ''
    
    highest_high = highest(highs, lookback)
    lowest_low = lowest(lows, lookback)
    
    if closes[idx] > highest_high:
        return 'up'
    elif closes[idx] < lowest_low:
        return 'down'
    
    return ''


def is_false_breakout(opens: List[float], highs: List[float], 
                      lows: List[float], closes: List[float], 
                      idx: int, lookback: int = 20) -> str:
    """
    假突破检测
    突破后迅速回落（对突破反向交易）
    """
    if idx < lookback + 2:
        return ''
    
    yesterday_breakout = is_breakout(highs, lows, closes, idx-1, lookback)
    
    if not yesterday_breakout:
        return ''
    
    if yesterday_breakout == 'up' and closes[idx] < opens[idx-1]:
        return 'bearish'
    elif yesterday_breakout == 'down' and closes[idx] > opens[idx-1]:
        return 'bullish'
    
    return ''


# ==================== 国内期货专用分析 ====================

def detect_limit_move(opens: List[float], closes: List[float], 
                      highs: List[float], lows: List[float], 
                      idx: int, limit_pct: float = 0.06) -> str:
    """
    检测涨跌停
    国内期货涨跌停一般在4%-6%
    """
    if idx < 1:
        return ''
    
    prev_close = closes[idx-1]
    upper_limit = prev_close * (1 + limit_pct)
    lower_limit = prev_close * (1 - limit_pct)
    
    # 涨停
    if highs[idx] >= upper_limit and closes[idx] >= upper_limit * 0.999:
        return 'limit_up'
    
    # 跌停
    if lows[idx] <= lower_limit and closes[idx] <= lower_limit * 1.001:
        return 'limit_down'
    
    return ''


def detect_gap(highs: List[float], lows: List[float], 
               closes: List[float], opens: List[float], idx: int) -> Dict[str, Any]:
    """
    检测隔夜跳空
    国内期货夜盘结束后到次日开盘有跳空风险
    """
    if idx < 1:
        return {'has_gap': False}
    
    prev_close = closes[idx-1]
    today_open = opens[idx] if idx < len(opens) else closes[idx]
    
    gap_size = (today_open - prev_close) / prev_close * 100
    
    if abs(gap_size) > 0.5:  # 超过0.5%认为有跳空
        return {
            'has_gap': True,
            'gap_size': gap_size,
            'direction': 'up' if gap_size > 0 else 'down',
            'gap_type': 'up_gap' if gap_size > 0 else 'down_gap'
        }
    
    return {'has_gap': False}


def analyze_session(open_price: float, close_price: float, 
                    high_price: float, low_price: float,
                    prev_close: float) -> Dict[str, Any]:
    """
    分析单个交易时段
    判断是趋势段还是震荡段
    """
    range_size = high_price - low_price
    body_size = abs(close_price - open_price)
    
    # 判断方向
    if close_price > open_price:
        direction = 'bullish'
        upper_shadow = high_price - close_price
        lower_shadow = open_price - low_price
    else:
        direction = 'bearish'
        upper_shadow = high_price - open_price
        lower_shadow = close_price - low_price
    
    # 上影线比例
    upper_shadow_ratio = upper_shadow / range_size if range_size > 0 else 0
    # 下影线比例
    lower_shadow_ratio = lower_shadow / range_size if range_size > 0 else 0
    
    # 趋势强度：实体占比超过60%
    body_ratio = body_size / range_size if range_size > 0 else 0
    
    return {
        'direction': direction,
        'range': range_size,
        'body_ratio': body_ratio,
        'upper_shadow_ratio': upper_shadow_ratio,
        'lower_shadow_ratio': lower_shadow_ratio,
        'is_trend': body_ratio > 0.6,
        'is_reversal': upper_shadow_ratio > 0.6 or lower_shadow_ratio > 0.6
    }


def detect_trend_day(opens: List[float], closes: List[float], 
                     highs: List[float], lows: List[float], 
                     idx: int, threshold: float = 0.65) -> str:
    """
    Trend Day 检测（Brooks概念）
    单边趋势日：实体占区间的65%以上
    """
    if idx < 1:
        return ''
    
    day_range = highs[idx] - lows[idx]
    if day_range == 0:
        return ''
    
    open_price = opens[idx]
    close_price = closes[idx]
    
    if close_price > open_price:
        body = close_price - open_price
        strength = body / day_range
        if strength >= threshold:
            return 'bullish'
    else:
        body = open_price - close_price
        strength = body / day_range
        if strength >= threshold:
            return 'bearish'
    
    return ''


def detect_reversal_day(opens: List[float], closes: List[float], 
                        highs: List[float], lows: List[float], 
                        idx: int, threshold: float = 0.5) -> str:
    """
    Reversal Day 检测（Brooks概念）
    反转日：开盘朝一个方向走，然后反转收盘
    特征：上影线或下影线占区间的50%以上
    """
    if idx < 1:
        return ''
    
    day_range = highs[idx] - lows[idx]
    if day_range == 0:
        return ''
    
    open_price = opens[idx]
    close_price = closes[idx]
    
    if close_price > open_price:
        # 阳线：检查是否冲高回落（长上影）
        upper_shadow = highs[idx] - close_price
        reversal_ratio = upper_shadow / day_range
        if reversal_ratio >= threshold and close_price < (highs[idx] + lows[idx]) / 2:
            return 'bearish_reversal'  # 冲高回落
    else:
        # 阴线：检查是否探底反弹（长下影）
        lower_shadow = close_price - lows[idx]
        reversal_ratio = lower_shadow / day_range
        if reversal_ratio >= threshold and close_price > (highs[idx] + lows[idx]) / 2:
            return 'bullish_reversal'  # 探底反弹
    
    return ''


def detect_double_top_bottom(opens: List[float], closes: List[float],
                             highs: List[float], lows: List[float],
                             idx: int, lookback: int = 20,
                             tolerance: float = 0.02) -> str:
    """
    双顶/双底检测
    重要反转形态
    """
    if idx < lookback:
        return ''
    
    current_high = highs[idx]
    current_low = lows[idx]
    
    # 检测双顶
    for i in range(idx - lookback, idx):
        if abs(highs[i] - current_high) / current_high < tolerance:
            return 'double_top'
    
    # 检测双底
    for i in range(idx - lookback, idx):
        if abs(lows[i] - current_low) / current_low < tolerance:
            return 'double_bottom'
    
    return ''


def detect_orb(opens: List[float], highs: List[float], 
               lows: List[float], closes: List[float], 
               idx: int, window: int = 5,
               atr_multiplier: float = 0.5) -> Dict[str, Any]:
    """
    Opening Range Breakout (ORB) 检测
    开盘区间突破 - Brooks 最喜欢的策略之一
    
    步骤：
    1. 取开盘后N根K线的高低点作为区间
    2. 价格突破区间后顺势交易
    3. 止损设在区间另一端
    """
    if idx < window + 1:
        return {}
    
    range_high = max(highs[idx-window:idx])
    range_low = min(lows[idx-window:idx])
    range_width = range_high - range_low
    
    if range_width == 0:
        return {}
    
    current_atr = atr(opens, highs, lows, closes, idx, period=14)
    
    # 区间太小，跳过
    if range_width < current_atr * atr_multiplier:
        return {}
    
    current_close = closes[idx]
    current_high = highs[idx]
    
    # 向上突破
    if current_close > range_high:
        return {
            'direction': 'long',
            'entry': range_high,
            'stop_loss': range_low,
            'take_profit': range_high + range_width,
            'risk_reward': range_width / (range_high - range_low) if range_high > range_low else 0
        }
    
    # 向下突破
    elif current_close < range_low:
        return {
            'direction': 'short',
            'entry': range_low,
            'stop_loss': range_high,
            'take_profit': range_low - range_width,
            'risk_reward': range_width / (range_high - range_low) if range_high > range_low else 0
        }
    
    return {}


# ==================== 主策略类 ====================

class ChinaFuturesStrategy:
    """
    国内期货 Price Action 策略
    =========================
    
    核心理念（来自 Louie + Brooks）：
    1. 不依赖指标，只看K线
    2. 趋势判断：均线方向 + 结构高低点
    3. 入场：关键位 + 价格行为确认
    4. 止损：结构止损（2倍ATR）
    5. 仓位：单笔风险≤2%
    
    国内期货特殊处理：
    - 夜盘跳空检测
    - 涨跌停板限制
    - 交易时段分析
    - 主力合约换月提醒
    """
    
    def __init__(self,
                 symbol: str = 'rb',
                 risk_percent: float = 0.05,  # 5%仓位（确保能开仓）
                 atr_period: int = 14,
                 sma_period: int = 50,
                 atr_stop: float = 2.0,
                 atr_target: float = 6.0,
                 lookback_period: int = 20,
                 body_ratio: float = 2.0,
                 shadow_ratio: float = 2.0,
                 require_trend: bool = True,
                 use_limit_filter: bool = True,
                 max_loss_per_day: float = 0.05,
                 trading_mode: str = "swing"):
        """
        初始化策略参数

        Args:
            symbol: 合约代码（如 'rb', 'i', 'cu'）
            risk_percent: 单笔风险比例（默认2%）
            atr_period: ATR计算周期
            sma_period: 均线周期
            atr_stop: ATR止损倍数
            lookback_period: 关键位回溯周期
            body_ratio: Pin Bar身体比例
            shadow_ratio: Pin Bar影子比例
            require_trend: 是否要求趋势确认
            use_limit_filter: 是否过滤涨跌停附近的交易
            max_loss_per_day: 单日最大亏损比例
            trading_mode: 交易模式，"intraday"（日内） 或 "swing"（波段）
        """
        self.symbol = symbol
        self.trading_mode = trading_mode
        self.config = FUTURES_CONFIG.get(symbol, FUTURES_CONFIG['rb'])
        self.risk_percent = risk_percent
        self.atr_period = atr_period
        self.sma_period = sma_period
        self.atr_stop = atr_stop
        self.atr_target = atr_target
        self.lookback_period = lookback_period
        self.body_ratio = body_ratio
        self.shadow_ratio = shadow_ratio
        self.require_trend = require_trend
        self.use_limit_filter = use_limit_filter
        self.max_loss_per_day = max_loss_per_day
        
        # 状态
        self.daily_loss = 0.0
        self.positions = []
        self.signals = []
    
    def detect_trend(self, closes: List[float]) -> str:
        """
        判断趋势方向
        """
        if len(closes) < self.sma_period:
            return 'neutral'
        
        sma_value = sma(closes, self.sma_period)
        if sma_value is None:
            return 'neutral'
        
        current_price = closes[-1]
        
        if current_price > sma_value:
            return 'bullish'
        elif current_price < sma_value:
            return 'bearish'
        else:
            return 'neutral'
    
    def find_key_levels(self, highs: List[float], lows: List[float],
                        closes: List[float], idx: int) -> Tuple[float, float]:
        """
        找关键支撑阻力位
        """
        lookback = self.lookback_period
        
        if idx < lookback:
            return 0, float('inf')
        
        resistance = highest(highs, lookback)
        support = lowest(lows, lookback)
        
        return support, resistance
    
    def check_near_key_level(self, price: float, support: float,
                             resistance: float, tolerance: float = 0.005) -> str:
        """
        检查价格是否接近关键位
        """
        if support > 0 and abs(price - support) / support <= tolerance:
            return 'support'
        if resistance < float('inf') and abs(price - resistance) / resistance <= tolerance:
            return 'resistance'
        return ''
    
    def detect_signals(self, opens: List[float], closes: List[float],
                      highs: List[float], lows: List[float],
                      idx: int) -> List[str]:
        """
        检测所有价格行为信号
        """
        signals = []
        
        # Pin Bar
        if is_pin_bar(opens, closes, highs, lows, idx,
                      body_ratio=self.body_ratio,
                      shadow_ratio=self.shadow_ratio):
            signals.append('pin_bar')
        
        # 吞没
        engulf = is_engulfing(opens, closes, idx)
        if engulf:
            signals.append(f'engulfing_{engulf}')
        
        # Inside Bar
        if is_inside_bar(opens, highs, lows, closes, idx):
            signals.append('inside_bar')
        
        # Momentum
        momentum = is_momentum(opens, closes, idx)
        if momentum:
            signals.append(f'momentum_{momentum}')
        
        # Breakout
        breakout = is_breakout(highs, lows, closes, idx,
                               lookback=self.lookback_period)
        if breakout:
            signals.append(f'breakout_{breakout}')
        
        # False Breakout
        false_breakout = is_false_breakout(opens, highs, lows, closes, idx,
                                           lookback=self.lookback_period)
        if false_breakout:
            signals.append(f'false_breakout_{false_breakout}')
        
        # Trend Day
        trend_day = detect_trend_day(opens, closes, highs, lows, idx)
        if trend_day:
            signals.append(f'trend_day_{trend_day}')
        
        # Reversal Day
        reversal_day = detect_reversal_day(opens, closes, highs, lows, idx)
        if reversal_day:
            signals.append(f'reversal_day_{reversal_day}')
        
        # ORB
        orb = detect_orb(opens, highs, lows, closes, idx)
        if orb:
            signals.append(f'orb_{orb["direction"]}')
        
        return signals
    
    def get_signal_direction(self, signals: List[str], trend: str) -> str:
        """
        根据信号和趋势判断方向
        """
        bullish_signals = ['pin_bar', 'engulfing_bullish',
                          'momentum_bullish', 'breakout_up',
                          'false_breakout_bullish', 'trend_day_bullish',
                          'reversal_day_bullish_reversal', 'orb_long']
        
        bearish_signals = ['shooting_star', 'engulfing_bearish',
                          'momentum_bearish', 'breakout_down',
                          'false_breakout_bearish', 'trend_day_bearish',
                          'reversal_day_bearish_reversal', 'orb_short']
        
        bullish_count = sum(1 for s in signals if any(b in s for b in bullish_signals))
        bearish_count = sum(1 for s in signals if any(b in s for b in bearish_signals))
        
        if bullish_count > bearish_count:
            return 'bullish'
        elif bearish_count > bullish_count:
            return 'bearish'
        else:
            return 'neutral'
    
    def calculate_stop_loss(self, opens: List[float], closes: List[float],
                           highs: List[float], lows: List[float],
                           idx: int, direction: str,
                           support: float, resistance: float) -> float:
        """
        计算止损位
        优先结构止损，其次ATR止损
        """
        atr_value = atr(opens, highs, lows, closes, idx,
                       period=self.atr_period)
        current_price = closes[idx]
        
        if direction == 'bullish':
            # 多头止损：跌破前低或ATR止损
            structure_stop = lowest(lows, self.lookback_period)
            atr_stop = current_price - atr_value * self.atr_stop
            return max(structure_stop, atr_stop)
        else:
            # 空头止损：突破前高或ATR止损
            structure_stop = highest(highs, self.lookback_period)
            atr_stop = current_price + atr_value * self.atr_stop
            return min(structure_stop, atr_stop)
    
    def calculate_take_profit(self, entry: float, stop_loss: float,
                              direction: str, risk_reward: float = None) -> float:
        """
        计算止盈位（默认使用 atr_target 作为盈亏比）
        """
        if risk_reward is None:
            risk_reward = self.atr_target
        risk = abs(entry - stop_loss)
        
        if direction == 'bullish':
            return entry + risk * risk_reward
        else:
            return entry - risk * risk_reward
    
    def analyze(self, opens: List[float], highs: List[float],
                lows: List[float], closes: List[float],
                idx: int) -> Dict[str, Any]:
        """
        综合分析 - 策略核心
        返回完整的分析结果和交易建议
        """
        result = {
            'symbol': self.symbol,
            'idx': idx,
            'close': closes[idx],
            'trend': 'neutral',
            'support': 0,
            'resistance': float('inf'),
            'near_key_level': '',
            'signals': [],
            'signal_direction': 'neutral',
            'limit_move': '',
            'has_gap': False,
            'final_direction': 'neutral',
            'confidence': 0,
            'entry': 0,
            'stop_loss': 0,
            'take_profit': 0,
            'risk_reward': 0,
            'action': 'none',
            'reason': '',
            'session_end_force_close': False
        }
        
        # 1. 趋势判断
        trend = self.detect_trend(closes)
        result['trend'] = trend
        
        # 如果要求趋势确认且趋势不明确
        if self.require_trend and trend == 'neutral':
            result['reason'] = '趋势不明确'
            return result
        
        # 2. 找关键位
        support, resistance = self.find_key_levels(highs, lows, closes, idx)
        result['support'] = support
        result['resistance'] = resistance
        
        # 3. 检查是否接近关键位
        near_level = self.check_near_key_level(closes[idx], support, resistance)
        result['near_key_level'] = near_level
        
        # 4. 检测涨跌停
        if self.use_limit_filter:
            limit_move = detect_limit_move(opens, closes, highs, lows, idx)
            result['limit_move'] = limit_move
        
        # 5. 检测跳空
        gap_info = detect_gap(highs, lows, closes, opens, idx)
        result['has_gap'] = gap_info['has_gap']
        result['gap_size'] = gap_info.get('gap_size', 0)
        
        # 6. 检测价格行为信号
        signals = self.detect_signals(opens, closes, highs, lows, idx)
        result['signals'] = signals
        result['signal_direction'] = self.get_signal_direction(signals, trend)
        
        # 7. 综合判断
        directions = []
        confidences = []
        
        # 趋势
        if trend != 'neutral':
            directions.append(trend)
            confidences.append(2 if near_level else 1)
        
        # 价格行为
        if result['signal_direction'] != 'neutral':
            directions.append(result['signal_direction'])
            confidences.append(2)
        
        # 统计最终方向
        bullish = directions.count('bullish')
        bearish = directions.count('bearish')
        
        if bullish > bearish:
            result['final_direction'] = 'bullish'
            result['confidence'] = bullish / len(directions) if directions else 0
        elif bearish > bullish:
            result['final_direction'] = 'bearish'
            result['confidence'] = bearish / len(directions) if directions else 0
        
        # 8. 计算交易参数
        if result['final_direction'] != 'neutral':
            direction = result['final_direction']
            
            # 涨跌停过滤
            if self.use_limit_filter and limit_move:
                result['reason'] = f'涨跌停限制 ({limit_move})'
                return result
            
            # 跳空过滤（大幅跳空开反向仓位风险大）
            if gap_info['has_gap'] and abs(gap_info.get('gap_size', 0)) > 1.0:
                result['reason'] = f'跳空过大 ({gap_info.get("gap_size", 0):.2f}%)'
                # 不直接返回，但降低信心
            
            entry = closes[idx]
            # 计算 ATR 并添加到结果
            result['atr'] = atr(opens, highs, lows, closes, idx, period=self.atr_period)
            stop_loss = self.calculate_stop_loss(opens, closes, highs, lows, idx,
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
            
            # 判断是否建议交易
            if result['confidence'] >= 0.5 and risk_reward >= 1.5:
                result['action'] = 'long' if direction == 'bullish' else 'short'
                result['reason'] = f"信号确认 {result['confidence']:.0%} 信心"
            else:
                result['action'] = 'none'
                result['reason'] = f"信心不足 ({result['confidence']:.0%}) 或盈亏比不佳 ({risk_reward:.2f})"

        # 日内模式：持仓跨日时强制平仓检测
        if self.trading_mode == 'intraday' and 'entry_idx' in result and (idx - result['entry_idx']) > 0:
            result['session_end_force_close'] = True

        # 确保 ATR 在返回结果中
        if 'atr' not in result:
            result['atr'] = atr(opens, highs, lows, closes, idx, period=self.atr_period)
        
        return result
    
    def print_analysis(self, result: Dict[str, Any]):
        """
        打印分析结果
        """
        print(f"\n{'='*50}")
        print(f"国内期货 Price Action 分析 - {result['symbol'].upper()}")
        print(f"{'='*50}")
        print(f"行情: {result['close']:.2f}")
        print(f"趋势: {result['trend']}")
        print(f"支撑: {result['support']:.2f}")
        print(f"阻力: {result['resistance']:.2f}")
        print(f"接近关键位: {result['near_key_level'] or '否'}")
        print(f"涨跌停: {result['limit_move'] or '正常'}")
        
        if result['has_gap']:
            print(f"跳空: {result['gap_size']:.2f}% ({result.get('gap_direction', 'N/A')})")
        
        print(f"\n信号列表: {result['signals'] or '无'}")
        print(f"信号方向: {result['signal_direction']}")
        print(f"综合方向: {result['final_direction']}")
        print(f"信心度: {result['confidence']:.0%}")
        
        if result['action'] != 'none':
            print(f"\n>>> 建议: {result['action'].upper()} <<<")
            print(f"入场价: {result['entry']:.2f}")
            print(f"止损: {result['stop_loss']:.2f}")
            print(f"止盈: {result['take_profit']:.2f}")
            print(f"盈亏比: {result['risk_reward']:.2f}")
        else:
            print(f"\n不建议开仓: {result['reason']}")
        
        print(f"{'='*50}")
    
    def run_backtest(self, data: Dict[str, List[float]],
                    initial_balance: float = 100000,
                    commission: float = 0.0001,
                    slippage: float = 0.0005) -> Dict[str, Any]:
        """
        简单回测
        
        Args:
            data: 包含 open, high, low, close 的字典
            initial_balance: 初始资金
            commission: 手续费比例
            slippage: 滑点比例
        
        Returns:
            回测统计结果
        """
        opens = data['open']
        highs = data['high']
        lows = data['low']
        closes = data['close']
        
        balance = initial_balance
        positions = []
        trades = []
        equity_curve = [initial_balance]
        
        stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0,
            'max_drawdown': 0,
            'win_rate': 0,
            'profit_factor': 0
        }
        
        for idx in range(50, len(closes)):
            # 更新权益
            current_equity = balance + sum(
                (closes[idx] - p['entry']) * p['size'] * (1 if p['direction'] == 'long' else -1)
                for p in positions
            )
            equity_curve.append(current_equity)
            
            # 分析
            result = self.analyze(opens, highs, lows, closes, idx)
            
            # 如果有持仓，先检查止损止盈
            if positions:
                for i, pos in list(enumerate(positions)):
                    current_price = closes[idx]
                    
                    # 止损检查
                    if pos['direction'] == 'long' and current_price <= pos['stop_loss']:
                        pnl = (pos['stop_loss'] - pos['entry']) * pos['size']
                        balance += pnl - pos['entry'] * pos['size'] * commission
                        trades.append({**pos, 'exit': pos['stop_loss'], 'pnl': pnl, 'exit_reason': 'stop_loss'})
                        positions.pop(i)
                        stats['total_trades'] += 1
                        if pnl > 0:
                            stats['winning_trades'] += 1
                        else:
                            stats['losing_trades'] += 1
                        continue
                    
                    # 止盈检查
                    if pos['direction'] == 'long' and current_price >= pos['take_profit']:
                        pnl = (pos['take_profit'] - pos['entry']) * pos['size']
                        balance += pnl - pos['entry'] * pos['size'] * commission
                        trades.append({**pos, 'exit': pos['take_profit'], 'pnl': pnl, 'exit_reason': 'take_profit'})
                        positions.pop(i)
                        stats['total_trades'] += 1
                        if pnl > 0:
                            stats['winning_trades'] += 1
                        else:
                            stats['losing_trades'] += 1
            
            # 无持仓时检查是否开仓
            if not positions and result['action'] != 'none':
                direction = result['action']
                entry = result['entry']
                stop_loss = result['stop_loss']
                take_profit = result['take_profit']
                
                # 考虑滑点
                if direction == 'long':
                    actual_entry = entry * (1 + slippage)
                else:
                    actual_entry = entry * (1 - slippage)
                
                # 计算仓位
                risk_amount = balance * self.risk_percent
                risk_per_unit = abs(entry - stop_loss)
                if risk_per_unit > 0:
                    size = risk_amount / risk_per_unit
                    
                    positions.append({
                        'direction': direction,
                        'entry': actual_entry,
                        'stop_loss': stop_loss,
                        'take_profit': take_profit,
                        'size': size,
                        'entry_idx': idx
                    })
        
        # 平仓剩余持仓
        for pos in positions:
            exit_price = closes[-1]
            if pos['direction'] == 'long':
                pnl = (exit_price - pos['entry']) * pos['size']
            else:
                pnl = (pos['entry'] - exit_price) * pos['size']
            balance += pnl
            trades.append({**pos, 'exit': exit_price, 'pnl': pnl, 'exit_reason': 'end_of_data'})
        
        # 统计
        if trades:
            stats['total_pnl'] = sum(t['pnl'] for t in trades)
            stats['win_rate'] = stats['winning_trades'] / stats['total_trades']
            
            wins = [t['pnl'] for t in trades if t['pnl'] > 0]
            losses = [abs(t['pnl']) for t in trades if t['pnl'] < 0]
            if losses:
                stats['profit_factor'] = sum(wins) / sum(losses) if sum(losses) > 0 else float('inf')
        
        # 计算最大回撤
        peak = equity_curve[0]
        max_dd = 0
        for e in equity_curve:
            if e > peak:
                peak = e
            dd = peak - e
            if dd > max_dd:
                max_dd = dd
        stats['max_drawdown'] = max_dd
        stats['final_balance'] = balance
        stats['roi'] = (balance - initial_balance) / initial_balance * 100
        
        return stats
    
    def print_backtest_report(self, stats: Dict[str, Any]):
        """
        打印回测报告
        """
        print("\n" + "="*50)
        print("国内期货策略回测报告")
        print("="*50)
        print(f"初始资金: ¥{100000:,.2f}")
        print(f"最终资金: ¥{stats.get('final_balance', 0):,.2f}")
        print(f"总收益率: {stats.get('roi', 0):.2f}%")
        print("-"*50)
        print(f"总交易次数: {stats['total_trades']}")
        print(f"盈利交易: {stats['winning_trades']}")
        print(f"亏损交易: {stats['losing_trades']}")
        print(f"胜率: {stats['win_rate']*100:.2f}%")
        print(f"盈亏比: {stats['profit_factor']:.2f}")
        print(f"最大回撤: ¥{stats['max_drawdown']:,.2f}")
        print("="*50)


# ==================== 使用示例 ====================

def demo():
    """
    演示函数
    """
    import random
    random.seed(42)
    
    # 生成示例数据
    n = 300
    prices = [4000]
    for _ in range(1, n):
        change = random.uniform(-0.02, 0.025)
        prices.append(prices[-1] * (1 + change))
    
    opens = [p * (1 + random.uniform(-0.005, 0.005)) for p in prices]
    highs = [max(p, o) * (1 + random.uniform(0, 0.01)) for p, o in zip(prices, opens)]
    lows = [min(p, o) * (1 - random.uniform(0, 0.01)) for p, o in zip(prices, opens)]
    closes = prices
    
    data = {
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes
    }
    
    # 创建策略
    strategy = ChinaFuturesStrategy(
        symbol='rb',
        risk_percent=0.01,
        sma_period=50,
        atr_period=14
    )
    
    # 单次分析
    idx = len(closes) - 1
    result = strategy.analyze(opens, highs, lows, closes, idx)
    strategy.print_analysis(result)
    
    # 回测
    print("\n运行回测...")
    stats = strategy.run_backtest(data)
    strategy.print_backtest_report(stats)


if __name__ == '__main__':
    demo()