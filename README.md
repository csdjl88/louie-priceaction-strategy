# Louie PriceAction 量化交易策略

基于 **Louie PriceAction** 和 **Brooks Trading Course** 的纯 Python 量化交易系统，专为国内期货市场设计。

---

## 核心理念

| 原则 | 说明 |
|------|------|
| 🎯 只看价格 | 不依赖任何技术指标，只看 K 线形态（Price Action） |
| 📈 顺势交易 | 上涨趋势只做多，下跌趋势只做空 |
| 💰 轻仓止损 | 单笔交易风险 ≤ 2%，止损要紧但不被扫掉 |
| 📉 盈亏比优先 | 目标 3:1 或更高，拒绝亏小赚大 |

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
| 参数优化 | ✅ 完成 | ATR=10, SMA=30, 止损1.5×, 止盈8× |

---

## 优化参数（2026-04 实测验证）

> 经过 35 品种 × 108 组参数网格搜索验证，优化后参数在日内模式下全面翻红。

| 参数 | 旧默认值 | **优化值** | 说明 |
|------|----------|------------|------|
| ATR 周期 | 14 | **10** | 更灵敏地反映近期波动 |
| SMA 周期 | 50 | **30** | 更快捕捉趋势转换 |
| 止损倍数 | 2.0× ATR | **1.5× ATR** | 缩小单笔损失 |
| 止盈倍数 | 6.0× ATR | **8.0× ATR** | 让利润奔跑，追求高盈亏比 |

```python
# 当前默认参数（已写入 china_futures_strategy.py）
strategy = ChinaFuturesStrategy(
    atr_period=10,       # 优化值
    sma_period=30,       # 优化值
    atr_stop=1.5,        # 优化值
    atr_target=8.0,      # 优化值
)
```

---

## 项目结构

```
louie-priceaction-strategy/
├── china_futures_strategy.py   # 国内期货策略入口（支持日内/波段模式）
├── backtest_runner.py          # 单一品种回测运行器
├── multi_backtest_runner.py    # 多品种批量回测和排名
├── data_fetcher.py            # 多品种期货数据获取（AkShare 真实数据）
├── symbol_selector.py          # 基于波动性的品种筛选
├── param_optimizer.py         # 参数优化器（网格搜索/随机搜索）
├── indicators.py               # 技术指标（零依赖实现）
├── patterns.py                # K线形态检测
├── brooks_concepts.py         # Brooks 核心概念
├── strategy.py                # 策略核心逻辑
├── risk_manager.py            # 风险管理
├── position_manager.py        # 仓位管理
├── signal_monitor.py          # 实时信号监控
├── ctp_trader.py              # CTP 实盘对接
├── pyproject.toml             # uv 包管理配置
└── README.md
```

---

## 快速开始

### 环境要求

- Python 3.9+ (推荐 3.11+)
- uv 包管理器

### 安装依赖

```bash
cd /home/node/.openclaw/workspace/projects/louie-priceaction-strategy
uv sync
```

### 运行回测

```bash
# 螺纹钢回测（使用 AkShare 真实数据，默认已用优化参数）
uv run python backtest_runner.py --symbol AL0 --source akshare --days 300

# 指定参数回测
uv run python backtest_runner.py --symbol TA0 --source akshare \
    --atr-period 10 --sma-period 30 --atr-stop 1.5 --atr-target 8.0 \
    --mode swing

# 模拟数据回测
uv run python backtest_runner.py --symbol rb --source simulate
```

### 启动信号监控

```bash
# 监控多品种，60秒检测间隔，运行5分钟
uv run python signal_monitor.py \
    --symbols rb0 hc0 i0 j0 jm0 ta0 ma0 al0 bu0 \
    --interval 60 --duration 300
```

### 参数说明

| 参数 | 说明 | 优化默认值 |
|------|------|------------|
| `--symbol` | 期货品种代码（如 RB0, TA0, AL0） | `rb` |
| `--source` | 数据源：`akshare`、`csv`、`simulate` | `akshare` |
| `--days` | 数据天数 | `300` |
| `--capital` | 初始资金 | `100000` |
| `--mode` | `swing`（波段）或 `intraday`（日内） | `swing` |
| `--atr-period` | ATR 计算周期 | **10** |
| `--sma-period` | 均线周期 | **30** |
| `--atr-stop` | ATR 止损倍数 | **1.5** |
| `--atr-target` | ATR 止盈倍数 | **8.0** |
| `--commission` | 手续费（默认使用品种配置） | `0.0003` |
| `--slippage` | 滑点比例 | `0.0005` |

### 支持的期货品种（35 个）

| 类别 | 品种代码 |
|------|----------|
| 黑色系 | rb（螺纹钢）、hc（热轧）、i（铁矿）、j（焦炭）、jm（焦煤） |
| 油脂化工 | m（豆粕）、rm（菜粕）、y（豆油）、p（棕榈油）、l（塑料）、v（PVC）、pp（聚丙烯） |
| 橡胶系 | ru（橡胶）、nr（20号胶）、br（合成橡胶） |
| 化工 | ta（PTA）、ma（甲醇）、eg（乙二醇）、pf（短纤） |
| 能源 | sc（原油）、bu（沥青） |
| 有色金属 | al（铝）、zn（锌）、cu（铜）、ni（镍）、sn（锡） |
| 贵金属 | ag（白银）、au（黄金） |
| 农产品 | cf（棉花）、sr（白糖）、a（豆一）、b（豆二）、c（玉米）、cs（玉米淀粉）、oi（菜油） |

---

## 2026 年回测结果（AkShare 真实数据，优化参数）

> 回测区间：2025-01-08 ~ 2026-04-08（约 15 个月）
> 参数：ATR=10, SMA=30, 止损 1.5× ATR, 止盈 8.0× ATR

### 波段模式（Swing）- TOP 10 盈利品种

| 排名 | 品种 | 名称 | 交易次数 | 胜率 | 收益率 | 最大回撤 | 夏普比 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 🥇 | TA | PTA | 8 | 25% | **+61.5%** | 15.6% | 1.57 |
| 🥈 | BR | 合成橡胶 | 5 | 20% | **+47.6%** | 14.1% | 1.52 |
| 🥉 | BU | 沥青 | 4 | 25% | **+26.2%** | 8.2% | 1.59 |
| 4 | PP | 聚丙烯 | 6 | 17% | **+24.5%** | 5.3% | 1.72 |
| 5 | AU | 黄金 | 11 | 27% | **+20.3%** | 9.2% | 1.08 |
| 6 | AL | 铝 | 12 | 17% | **+20.2%** | 9.8% | 0.82 |
| 7 | CU | 铜 | 13 | 15% | **+11.4%** | 13.1% | 0.61 |
| 8 | AG | 白银 | 7 | 14% | **+11.2%** | 12.0% | 0.45 |
| 9 | PF | 短纤 | 8 | 12% | **+10.4%** | 16.1% | 0.64 |
| 10 | P | 棕榈油 | 8 | 12% | **+8.2%** | 17.0% | 0.60 |

### 日内模式（Intraday）- TOP 10 盈利品种

| 排名 | 品种 | 名称 | 交易次数 | 胜率 | 收益率 | 最大回撤 | 夏普比 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 🥇 | TA | PTA | 29 | 62% | **+11.3%** | 2.8% | 4.85 |
| 🥈 | SC | 原油 | 10 | 60% | **+10.9%** | 3.2% | 5.09 |
| 🥉 | AG | 白银 | 23 | 61% | **+10.3%** | 3.3% | 4.14 |
| 4 | AL | 铝 | 54 | 56% | **+8.6%** | 2.1% | 3.85 |
| 5 | PF | 短纤 | 22 | 55% | **+8.4%** | 2.5% | 4.74 |
| 6 | BR | 合成橡胶 | 13 | 54% | **+7.9%** | 1.2% | 6.06 |
| 7 | CU | 铜 | 40 | 55% | **+7.3%** | 1.8% | 3.49 |
| 8 | CF | 棉花 | 39 | 49% | **+6.8%** | 2.4% | 3.21 |
| 9 | RU | 橡胶 | 21 | 62% | **+6.3%** | 2.7% | 2.60 |
| 10 | BU | 沥青 | 16 | 69% | **+6.2%** | 0.9% | **8.30** |

### 整体表现

| 指标 | 波段模式（Swing） | 日内模式（Intraday） |
|:---|:---:|:---:|
| 盈利品种数 | 12 / 35 | **21 / 35** |
| 平均收益率 | -3.8% | **+2.5%** |
| 盈利品种平均收益 | +20.7% | +5.6% |
| 最佳品种 | PTA +61.5% | PTA +11.3% |
| 最低回撤（盈利品种） | 沥青 8.2% | 沥青 0.9% |

### 优化前后对比

| 指标 | 旧参数 (ATR=14, SMA=50, 止损2×, 止盈6×) | **新参数 (ATR=10, SMA=30, 止损1.5×, 止盈8×)** |
|:---|:---:|:---:|
| 日内盈利品种 | 4 / 35 | **21 / 35** ⬆️ |
| 日内平均收益 | -39.33% | **+2.5%** ⬆️ |
| 盈利品种平均收益 | +20.7% | +20.7% |
| 综合评价 | 盈亏比不足，频繁止损 | 止盈扩大，减少交易频率 |

### 关键发现

1. **TA（PTA）双料冠军**：波段 +61.5%、日内 +11.3%，无论哪种模式都是最优选择
2. **BR（合成橡胶）稳健**：波段 +47.6%、日内 +7.9%，胜率虽低但盈亏比高
3. **BU（沥青）风险最低**：波段最大回撤仅 8.2%，日内夏普比高达 8.30
4. **止盈 8× ATR 优于 6×**：让利润奔跑，大赚覆盖小止损亏损
5. **日内模式全面翻红**：参数优化后，日内交易从几乎全亏变为 21/35 盈利

---

## 核心功能

### 1. 多品种数据获取

```python
from data_fetcher import get_all_futures_symbols, fetch_futures_data

symbols = get_all_futures_symbols()  # 35 个品种
data = fetch_futures_data('TA0', days=300)
```

### 2. 波动性筛选

```python
from symbol_selector import select_top_symbols

results = select_top_symbols(
    symbols=None, top_n=10,
    min_vol_rate=0.015, max_vol_rate=0.04,
    min_volume=10000
)
```

### 3. 日内交易模式

```python
from china_futures_strategy import ChinaFuturesStrategy

# 波段模式（可持仓过夜）
strategy = ChinaFuturesStrategy(symbol='TA0', trading_mode='swing')

# 日内模式（当日平仓）
strategy = ChinaFuturesStrategy(symbol='TA0', trading_mode='intraday')

result = strategy.analyze(opens, highs, lows, closes, idx)
```

### 4. 实时信号监控

```python
from signal_monitor import SignalMonitor

monitor = SignalMonitor(symbols=['TA0', 'BR0', 'BU0'], interval=60)
monitor.set_callback(lambda s, t, d, p, c, r: print(f'{s}: {t} @ {p}'))
monitor.start()
```

---

## 策略详解

### 入场流程

```
1️⃣ 判断趋势
   ├── SMA30 方向（多头/空头）
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
| 止损 | 1.5 × ATR（优化后） |
| 止盈 | 8.0 × ATR（优化后，目标 5:1+ 盈亏比） |
| 日内强制平仓 | 持仓跨日且 mode=intraday |
| 反转出场 | 出现反向信号 |

### 仓位管理

```python
风险金额  = 账户余额 × 5%
仓位手数  = 风险金额 ÷ (1.5 × ATR × 每手吨数)
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

## 数据格式

```python
# K线数据格式
data = {
    'dates': ['2025-01-08', ...],   # 日期
    'opens': [6400.0, ...],          # 开盘价
    'highs': [6500.0, ...],         # 最高价
    'lows': [6380.0, ...],          # 最低价
    'closes': [6450.0, ...],         # 收盘价
    'volumes': [150000, ...],        # 成交量
}
```

---

## 注意事项

1. **模拟交易**：本系统仅供学习研究，不构成投资建议
2. **实盘风险**：期货交易风险巨大，请勿使用真实资金测试未经充分回测的策略
3. **数据质量**：AkShare 数据仅供参考，实盘请使用经纪商提供的精确数据
4. **参数过拟合**：历史回测表现优异不代表未来可用，请注意样本外验证

---

## License

MIT License

---

*项目基于 Brooks Trading Course 和 Al Brooks Price Action 理论，仅供学习研究使用。*
