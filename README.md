# Louie PriceAction 量化交易策略

基于 **Louie PriceAction** 和 **Brooks Trading Course** 的纯 Python 量化交易系统，专为国内期货市场设计。

---

## 📊 项目背景

### 核心理念

| 原则 | 说明 |
|------|------|
| 🎯 只看价格 | 不依赖任何技术指标，只看 K 线形态（Price Action） |
| 📈 顺势交易 | 上涨趋势只做多，下跌趋势只做空 |
| 💰 轻仓止损 | 单笔交易风险 ≤ 2%，止损要紧但不被扫掉 |
| 📉 盈亏比优先 | 目标 2:1 或 3:1，拒绝亏小赚大 |

### 策略基础

本策略基于两位 Price Action 大师的理论：

- **Al Brooks**：趋势结构、连续结构、回调入场
- **Lance Edwards**：供需区、入场确认、风险管理

---

## 📁 项目结构

```
quant/
├── china_futures_strategy.py   # 🏠 国内期货专用策略入口
├── backtest_runner.py          # 📈 回测运行器
├── indicators.py              # 📐 技术指标（零依赖实现）
├── patterns.py                # 🔍 K线形态检测
├── brooks_concepts.py         # 📚 Brooks 核心概念
├── strategy.py                # ⚙️ 策略核心逻辑
├── risk.py                    # 🛡️ 风险管理
├── backtest.py                # 🔄 回测引擎
├── price_action_framework.py  # 🔧 价格行为框架
├── pyproject.toml             # 📦 uv 包管理配置
└── README.md                  # 📖 说明文档
```

---

## 🚀 快速开始

### 环境要求

- Python 3.11+
- uv 包管理器

### 安装依赖

```bash
cd quant
uv sync
```

### 运行回测

```bash
# 螺纹钢回测（使用 AkShare 真实数据）
uv run python backtest_runner.py --symbol rb --source akshare --days 300

# 模拟数据回测
uv run python backtest_runner.py --symbol rb --source simulate

# CSV 文件回测
uv run python backtest_runner.py --symbol rb --source csv --file data.csv
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--symbol` | 期货品种代码 | `rb` |
| `--source` | 数据源：`akshare`、`simulate`、`csv` | `akshare` |
| `--days` | 数据天数 | `300` |
| `--capital` | 初始资金 | `100000` |
| `--file` | CSV 文件路径（csv 模式） | `data.csv` |

### 支持的期货品种

| 类别 | 品种代码 |
|------|----------|
| 黑色系 | rb（螺纹钢）、hc（热轧）、i（铁矿）、j（焦炭）、jm（焦煤） |
| 有色金属 | cu（铜）、al（铝）、zn（锌）、ni（镍） |
| 化工系 | ru（橡胶）、bu（沥青）、ma（甲醇）、ta（PTA） |
| 农产品 | m（豆粕）、y（豆油）、p（棕榈油）、c（玉米） |
| 贵金属 | au（黄金）、ag（白银） |
| 能源 | sc（原油） |

---

## 📖 策略详解

### 入场流程

```
1️⃣ 判断趋势
   ├── 均线方向（SMA 20/50）
   └── 结构高低点（HH/HL 或 LH/LL）

2️⃣ 找到关键位
   ├── 支撑/阻力位
   ├── 趋势线
   └── 供需区

3️⃣ 等入场确认
   ├── Pin Bar（锤子线/射击星）
   ├── 吞没形态
   └── Inside Bar（内部K线）
```

### 出场规则

| 类型 | 条件 |
|------|------|
| 止损 | 2 × ATR |
| 止盈 | 4 × ATR（2:1 盈亏比） |
| 时间止损 | 持仓 > N 根 K 线无盈利 |
| 反转出场 | 出现反向信号 |

### 仓位管理

```python
风险金额 = 账户余额 × 2%
仓位手数 = 风险金额 ÷ (止损ATR × 每手吨数)
```

---

## 📐 技术指标（零依赖）

所有指标均在 `indicators.py` 中实现，无需安装任何第三方库：

| 指标 | 说明 |
|------|------|
| ATR | 平均真实波幅 |
| SMA/EMA | 移动平均 |
| Bollinger Bands | 布林带 |
| Keltner Channels | 肯特纳通道 |
| ADX | 趋势强度 |
| RSI | 相对强弱 |
| Support/Resistance | 支撑阻力位 |
| Fibonacci | 斐波那契回撤 |

---

## 📈 回测结果（AkShare 真实数据）

### RB 螺纹钢（2024-04-08 至 2025-04-01）

| 指标 | 数值 |
|------|------|
| 总交易次数 | 16 笔 |
| 胜率 | 37.5% |
| 总收益率 | -6.66% |
| 最大回撤 | 15.54% |
| 盈亏比 | 0.98 |

### 💡 结论

- 震荡行情中胜率较低（~40%）
- 趋势行情中盈亏比优秀（可达 2:1+）
- **核心问题**：缺少趋势过滤器，在震荡行情中入场过多

### 待优化方向

- [ ] 增加趋势过滤器（只在大趋势中入场）
- [ ] 加入供需区识别
- [ ] 调整盈亏比目标（3:1）
- [ ] 多品种组合策略

---

## 🔧 开发指南

### 编写自己的策略

```python
from china_futures_strategy import ChinaFuturesStrategy

# 初始化策略
strategy = ChinaFuturesStrategy(symbol='rb', risk_percent=0.02)

# 分析当前市场
result = strategy.analyze(opens, highs, lows, closes, idx)

# result 包含:
# - signal: 1(做多), -1(做空), 0(观望)
# - trend: 'uptrend', 'downtrend', 'unknown'
# - atr: 平均真实波幅
# - pattern: 检测到的形态
# - entry_price: 建议入场价
# - stop_loss: 建议止损价
```

### 数据格式

```python
# K线数据格式
data = {
    'dates': ['2024-01-01', ...],   # 日期
    'opens': [4500.0, ...],          # 开盘价
    'highs': [4550.0, ...],          # 最高价
    'lows': [4480.0, ...],           # 最低价
    'closes': [4520.0, ...],         # 收盘价
    'volumes': [150000, ...],        # 成交量
}
```

### CSV 文件格式

```csv
date,open,high,low,close,volume
2024-01-01,4500,4550,4480,4520,150000
2024-01-02,4520,4580,4510,4560,180000
```

---

## 📝 注意事项

1. **模拟交易**：本系统仅供学习研究，不构成投资建议
2. **实盘风险**：期货交易风险巨大，请勿使用真实资金测试未经充分回测的策略
3. **数据质量**：AkShare 数据仅供参考，实盘请使用经纪商提供的精确数据

---

## 📜 License

MIT License

---

*项目基于 Brooks Trading Course 和 Al Brooks Price Action 理论，仅供学习研究使用。*
