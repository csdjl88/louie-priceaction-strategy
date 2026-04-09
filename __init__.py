"""
Price Action 交易框架
===================
整合 Louie PriceAction + Brooks Trading Course
核心理念：不依赖指标，轻仓顺势，结构止损

框架结构:
    quant/
    ├── __init__.py                  # 统一入口
    ├── indicators.py               # 技术指标（自实现，无依赖）
    ├── patterns.py                 # 价格行为形态
    ├── brooks_concepts.py          # Brooks 特色概念
    ├── strategy.py                 # 策略逻辑
    ├── risk.py                     # 风险管理
    ├── backtest.py                 # 回测引擎
    ├── example_demo.py             # 使用演示
    └── price_action_framework.py   # 主入口（导出所有模块）

使用示例:
    from quant import PriceActionStrategy, BacktestEngine
    
    # 创建策略
    strategy = PriceActionStrategy(
        risk_percent=0.02,
        sma_period=30,       # 优化值：30（默认50）
        atr_period=10        # 优化值：10（默认14）
    )
    
    # 创建回测引擎
    engine = BacktestEngine(
        initial_balance=100000,
        risk_percent=0.02
    )
    
    # 运行回测
    stats = engine.run(data)
    engine.print_report()
"""

from .indicators import (
    atr, sma, ema, highest, lowest,
    calculate_true_range, calculate_support_resistance,
    adx, rsi, bollinger_bands, keltner_channels,
    atr_trailing_stop, fibonacci_retracement
)
from .patterns import (
    is_pin_bar, is_hammer, is_shooting_star,
    is_engulfing, is_engulfing_bullish, is_engulfing_bearish,
    is_harami, is_inside_bar, is_outside_bar,
    is_momentum, is_breakout, is_false_breakout,
    PatternScanner, detect_all_patterns
)
from .brooks_concepts import (
    detect_trend_day, detect_trend_day_30min,
    detect_reversal_day, detect_double_top_bottom,
    detect_opening_range_breakout, is_near_trendline,
    BrooksAnalyzer
)
from .strategy import PriceActionStrategy
from .risk import PositionSizer, RiskManager, StopLossCalculator, TradeExecutor
from .backtest import BacktestEngine, WalkForwardBacktest
from .china_futures_strategy import (
    ChinaFuturesStrategy,
    FUTURES_CONFIG,
    TRADING_SESSIONS,
    is_pin_bar, is_engulfing, is_inside_bar,
    is_momentum, is_breakout, is_false_breakout,
    detect_trend_day, detect_reversal_day, detect_orb,
    detect_limit_move, detect_gap
)

__all__ = [
    # 版本
    '__version__',
    
    # 指标
    'atr', 'sma', 'ema', 'highest', 'lowest',
    'calculate_true_range', 'calculate_support_resistance',
    'adx', 'rsi', 'bollinger_bands', 'keltner_channels',
    'atr_trailing_stop', 'fibonacci_retracement',
    
    # 形态
    'is_pin_bar', 'is_hammer', 'is_shooting_star',
    'is_engulfing', 'is_engulfing_bullish', 'is_engulfing_bearish',
    'is_harami', 'is_inside_bar', 'is_outside_bar',
    'is_momentum', 'is_breakout', 'is_false_breakout',
    'PatternScanner', 'detect_all_patterns',
    
    # Brooks 概念
    'detect_trend_day', 'detect_trend_day_30min',
    'detect_reversal_day', 'detect_double_top_bottom',
    'detect_opening_range_breakout', 'is_near_trendline',
    'BrooksAnalyzer',
    
    # 策略
    'PriceActionStrategy',
    
    # 风控
    'PositionSizer', 'RiskManager', 'StopLossCalculator', 'TradeExecutor',
    
    # 回测
    'BacktestEngine', 'WalkForwardBacktest',
    
    # 国内期货策略
    'ChinaFuturesStrategy',
    'FUTURES_CONFIG',
    'TRADING_SESSIONS',
    'detect_limit_move', 'detect_gap',
]

__version__ = '1.0.0'
__author__ = 'Price Action Trading System'
