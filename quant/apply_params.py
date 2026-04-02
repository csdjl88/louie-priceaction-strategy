#!/usr/bin/env python3
"""Apply optimized parameters to the strategy"""
import re

# Update china_futures_strategy.py
with open('china_futures_strategy.py', 'r') as f:
    content = f.read()

# Update default risk_percent from 0.02 to 0.01 in __init__
content = content.replace(
    "def __init__(self,\n                 symbol: str = 'rb',\n                 risk_percent: float = 0.02,",
    "def __init__(self,\n                 symbol: str = 'rb',\n                 risk_percent: float = 0.01,\n                 atr_stop: float = 2.0,\n                 atr_target: float = 6.0,"
)

# Update default value in dataclass
content = content.replace("risk_percent=0.02,", "risk_percent=0.01,")

with open('china_futures_strategy.py', 'w') as f:
    f.write(content)

print("Updated china_futures_strategy.py")

# Update backtest_runner.py 
with open('backtest_runner.py', 'r') as f:
    content = f.read()

# Replace hardcoded values with parameters
content = content.replace("current_capital * 0.02", "current_capital * risk_percent")
content = content.replace("atr * 2", "atr * atr_stop")
content = content.replace("atr * 4", "atr * atr_target")

# Update default parameter values in run_backtest function
content = content.replace(
    "def run_backtest(data: pd.DataFrame, symbol: str, initial_capital: float = 100000,\n                     risk_percent: float = 0.02, atr_stop: float = 2.0, atr_target: float = 4.0):",
    "def run_backtest(data: pd.DataFrame, symbol: str, initial_capital: float = 100000,\n                     risk_percent: float = 0.01, atr_stop: float = 2.0, atr_target: float = 6.0):"
)

with open('backtest_runner.py', 'w') as f:
    f.write(content)

print("Updated backtest_runner.py")
print("Done!")