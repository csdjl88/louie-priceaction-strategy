# Louie PriceAction 量化交易策略

基于 YouTube 频道 [@LouiePriceAction](https://www.youtube.com/@LouiePriceAction) 总结的量化交易系统。

## 策略概述

### 核心理念
- **价格行为交易**：不看指标，只看K线
- **概率思维**：60%打平，40%赚大钱
- **轻仓纪律**：单笔风险 ≤2% 账户
- **重复尝试**：前提成立→反复入场

### 入场条件
1. 关键支撑/阻力位（20日低点附近）
2. 价格行为信号（Pin Bar / 吞没形态 / 动量）
3. 趋势过滤（上涨趋势只做多）

### 止损/止盈
- 止损：结构止损（跌破前低）+ ATR止损
- 止盈：2:1 盈亏比
- 移动止损：保本后跟踪

## 文件说明

| 文件 | 说明 |
|------|------|
| `louie_strategy_zero_dep.py` | 零依赖版本，直接运行 |
| `louie_cn_futures.py` | 国内期货版 |
| `louie_priceaction_strategy.py` | 完整版（需要backtrader） |
| `louie_strategy_simple.py` | 简化版（Pandas） |

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/csdjl88/louie-priceaction-strategy.git
cd louie-priceaction-strategy

# 运行回测
python3 louie_strategy_zero_dep.py

# 回测国内期货
python3 louie_cn_futures.py
```

## 策略参数

```python
risk_per_trade = 0.02      # 单笔风险 2%
reward_risk_ratio = 2.0    # 盈亏比 2:1
atr_period = 14            # ATR周期
trend_period = 50          # 趋势均线周期
```

## 交易品种

- 黄金、白银、比特币
- 国内期货：螺纹钢、铁矿石、焦煤、焦炭、沪铜、沪金
- 美股、ETF、期权

## 视频学习来源

- 边做边讲系列：实盘演示
- 踏上交易之路系列：基础知识教学

---
**注意**：此策略仅供学习研究，不构成投资建议。交易有风险，入市需谨慎。