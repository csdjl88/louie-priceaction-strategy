#!/usr/bin/env python3
"""Test SMA function"""
import sys
sys.path.insert(0, '.')

from china_futures_strategy import sma

# 测试数据
closes = [10000 + i*20 for i in range(50)]

print("Testing sma function:")
for idx in [40, 35, 30, 25]:
    result = sma(closes, 20)
    print(f"  sma(closes[{idx-19}:{idx+1}], 20) = {result}")

# 检查函数签名
import inspect
print("\nFunction signature:")
print(inspect.signature(sma))