"""
Price Action 交易框架
===================
整合 Louie PriceAction + Brooks Trading Course
核心理念：不依赖指标，轻仓顺势，结构止损

框架结构:
    price_action_framework
    ├── indicators      # 技术指标（自实现，无依赖）
    ├── patterns        # 价格行为形态
    ├── brooks_concepts # Brooks 特色概念
    ├── strategy        # 策略逻辑
    ├── risk            # 风险管理
    └── backtest        # 回测引擎

使用示例:
    from price_action_framework import PriceActionStrategy, BacktestEngine
    
    # 创建策略
    strategy = PriceActionStrategy(
        risk_percent=0.02,
        sma_period=50,
        atr_period=14
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
    atr, sma, highest, lowest,
    calculate_true_range, calculate_adx
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

__all__ = [
    # 版本
    '__version__',
    
    # 指标
    'atr', 'sma', 'highest', 'lowest', 
    'calculate_true_range', 'calculate_adx',
    
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
]

__version__ = '1.0.0'
__author__ = 'Price Action Trading System'
