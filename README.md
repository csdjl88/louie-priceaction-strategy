# Louie PriceAction 量化交易策略

基于 **Louie PriceAction** 和 **Brooks Trading Course** 的纯 Python 量化交易系统，专为国内期货市场设计。

---

## 核心理念

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

## 项目状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 单一品种回测 | ✅ 完成 | `backtest_runner.py` |
| 多品种数据获取 | ✅ 完成 | `data_fetcher.py` |
| 波动性筛选 | ✅ 完成 | `symbol_selector.py` |
| 日内交易模式 | ✅ 完成 | `china_futures_strategy.py` |
| 多品种回测 | ✅ 完成 | `multi_backtest_runner.py` |

---

## 项目结构

```
quant/
├── china_futures_strategy.py   # 国内期货策略入口（支持日内/波段模式）
├── backtest_runner.py          # 单一品种回测运行器
├── data_fetcher.py            # 多品种期货数据获取（AkShare 真实数据）
├── symbol_selector.py         # 基于波动性的品种筛选
├── multi_backtest_runner.py   # 多品种批量回测和排名
├── indicators.py              # 技术指标（零依赖实现）
├── patterns.py                # K线形态检测
├── brooks_concepts.py         # Brooks 核心概念
├── strategy.py                # 策略核心逻辑
├── risk.py                    # 风险管理
├── backtest.py               # 回测引擎
├── price_action_framework.py  # 价格行为框架
├── pyproject.toml            # uv 包管理配置
└── README.md                 # 说明文档
```

---

## 快速开始

### 环境要求

- Python 3.9+ (推荐 3.11+)
- uv 包管理器

### 安装依赖

```bash
cd /Users/hse/projects/backend/quant
uv sync
```

### 运行回测

#### 单一品种回测

```bash
# 螺纹钢回测（使用 AkShare 真实数据）
uv run python backtest_runner.py --symbol rb --source akshare --days 300

# 模拟数据回测
uv run python backtest_runner.py --symbol rb --source simulate
```

#### 多品种回测（2025 年真实数据）

```bash
# 多品种波段模式回测
uv run python -c "
from multi_backtest_runner import run_multi_backtest, print_ranking_report
import warnings
warnings.filterwarnings('ignore')

results = run_multi_backtest(
    symbols=None,           # 自动筛选所有品种
    days=300,              # 约一年数据
    initial_capital=100000,
    trading_mode='swing',   # 波段模式（可持仓过夜）
    top_n=20,
    min_vol_rate=0.0,
    max_vol_rate=1.0,
    min_volume=0
)
print_ranking_report(results)
"

# 多品种日内模式回测
uv run python -c "
from multi_backtest_runner import run_multi_backtest, print_ranking_report
import warnings
warnings.filterwarnings('ignore')

results = run_multi_backtest(
    symbols=None,
    days=300,
    initial_capital=100000,
    trading_mode='intraday',  # 日内模式（当日平仓）
    top_n=20,
    min_vol_rate=0.0,
    max_vol_rate=1.0,
    min_volume=0
)
print_ranking_report(results)
"
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--symbol` | 期货品种代码 | `rb` |
| `--source` | 数据源：`akshare`、`simulate` | `akshare` |
| `--days` | 数据天数 | `300` |
| `--capital` | 初始资金 | `100000` |

### 支持的期货品种（33 个）

| 类别 | 品种代码 |
|------|----------|
| 黑色系 | rb（螺纹钢）、hc（热轧）、i（铁矿）、j（焦炭）、jm（焦煤） |
| 有色金属 | cu（铜）、al（铝）、zn（锌）、ni（镍）、sn（锡） |
| 化工系 | ru（橡胶）、bu（沥青）、ma（甲醇）、ta（PTA）、pp（聚丙烯）、l（塑料）、v（PVC） |
| 农产品 | m（豆粕）、y（豆油）、p（棕榈油）、c（玉米）、cs（玉米淀粉）、a（豆一）、b（豆二）、oi（菜油）、rm（菜粕）、cf（棉花）、sr（白糖） |
| 贵金属 | au（黄金）、ag（白银） |
| 能源 | sc（原油） |
| 国债 | t（10 年期国债）、tf（5 年期国债） |

---

## 核心功能

### 1. 多品种数据获取 (`data_fetcher.py`)

```python
from data_fetcher import get_all_futures_symbols, fetch_futures_data, fetch_multi_futures_data

# 获取所有品种
symbols = get_all_futures_symbols()  # 33 个品种

# 单品种获取
data = fetch_futures_data('rb', days=300)

# 批量获取
multi_data = fetch_multi_futures_data(['rb', 'cu', 'au'], days=300)
```

### 2. 波动性筛选 (`symbol_selector.py`)

```python
from symbol_selector import select_top_symbols, get_volatility_report

# 筛选高波动性品种
results = select_top_symbols(
    symbols=None,           # None = 全部品种
    days=60,
    top_n=10,
    min_vol_rate=0.015,    # 最小波动率 1.5%
    max_vol_rate=0.04,     # 最大波动率 4%
    min_volume=10000        # 最小成交量
)

# 打印波动性报告
print(get_volatility_report(top_n=20))
```

### 3. 日内交易模式 (`china_futures_strategy.py`)

```python
from china_futures_strategy import ChinaFuturesStrategy

# 波段模式（默认，可持仓过夜）
strategy_swing = ChinaFuturesStrategy(symbol='rb', trading_mode='swing')

# 日内模式（当日开平，不过夜）
strategy_intraday = ChinaFuturesStrategy(symbol='rb', trading_mode='intraday')

# 分析市场
result = strategy.analyze(opens, highs, lows, closes, idx)
# result 包含 session_end_force_close 标记日内平仓信号
```

### 4. 多品种回测 (`multi_backtest_runner.py`)

```python
from multi_backtest_runner import run_multi_backtest, print_ranking_report, BacktestResult

# 运行多品种回测
results = run_multi_backtest(
    symbols=None,           # 自动筛选
    days=300,
    initial_capital=100000,
    trading_mode='swing',   # 或 'intraday'
    top_n=20
)

# 打印排名报告
print_ranking_report(results)

# 综合评分计算
from multi_backtest_runner import compute_comprehensive_score
for r in results:
    r.comprehensive_score = compute_comprehensive_score(r)
```

---

## 策略详解

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
| 止盈 | 6 × ATR（3:1 盈亏比） |
| 日内强制平仓 | 持仓跨日且 mode=intraday |
| 反转出场 | 出现反向信号 |

### 仓位管理

```python
风险金额 = 账户余额 × 5%
仓位手数 = 风险金额 ÷ (2 × ATR × 每手吨数)
```

---

## 技术指标（零依赖）

所有指标均在 `indicators.py` 中实现，无需安装任何第三方库：

| 指标 | 说明 |
|------|------|
| ATR | 平均真实波幅 |
| SMA/EMA | 移动平均 |
| Bollinger Bands | 布林带 |
| Keltner Channels | 肯特纳通道 |
| ADX | 趋势强度 |
| RSI | 相对强弱 |

---

## 2025 年回测结果（AkShare 真实数据）

### 波段模式（Swing）- 持仓可过夜

| 排名 | 品种 | 名称 | 收益率% | 最大回撤% | 胜率% | 评分 |
|------|------|------|---------|-----------|-------|------|
| 1 | pp | 聚丙烯 | **+93.79%** | 6.26 | 83.3% | 0.747 |
| 2 | ni | 镍 | **+196.00%** | 35.50 | 57.1% | 0.737 |
| 3 | l | 塑料 | **+74.81%** | 17.22 | 62.5% | 0.537 |
| 4 | sr | 白糖 | **+46.36%** | 6.62 | 80.0% | 0.490 |
| 5 | rm | 菜籽粕 | **+32.53%** | 14.40 | 57.1% | 0.377 |

### 日内模式（Intraday）- 当日平仓不过夜

| 排名 | 品种 | 名称 | 收益率% | 最大回撤% | 胜率% | 评分 |
|------|------|------|---------|-----------|-------|------|
| 1 | ni | 镍 | **+196.00%** | 35.50 | 57.1% | 0.734 |
| 2 | pp | 聚丙烯 | **+93.79%** | 6.26 | 83.3% | 0.732 |
| 3 | oi | 菜籽油 | **+23.94%** | 5.87 | 57.1% | 0.386 |
| 4 | cf | 棉花 | **+9.64%** | 15.52 | 50.0% | 0.245 |
| 5 | ru | 橡胶 | **+18.84%** | 8.18 | 40.0% | 0.222 |

### 关键发现

1. **镍（ni）** 表现最为突出，收益率高达 **196%**，但回撤也较大（35.5%）
2. **聚丙烯（pp）** 风险调整后表现最佳，收益率 93.79% 且回撤仅 6.26%
3. **塑料（l）** 和 **白糖（sr）** 也表现稳健
4. 农产品（玉米、豆粕）和国债期货在 2025 年表现较差

---

## 数据格式

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

---

## 注意事项

1. **模拟交易**：本系统仅供学习研究，不构成投资建议
2. **实盘风险**：期货交易风险巨大，请勿使用真实资金测试未经充分回测的策略
3. **数据质量**：AkShare 数据仅供参考，实盘请使用经纪商提供的精确数据

---

## License

MIT License

---

*项目基于 Brooks Trading Course 和 Al Brooks Price Action 理论，仅供学习研究使用。*
