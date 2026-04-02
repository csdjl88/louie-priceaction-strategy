# 多品种日内交易 执行计划

**目标:** 支持国内期货所有品种的日内交易和波段交易模式，实现基于波动性的品种自动筛选

**技术栈:** Python 3.11+, AkShare, uv

**设计文档:** spec-design.md

## 改动总览

- **Task 1** 新建 `data_fetcher.py`，提供多品种数据获取和缓存功能，供 Task 2/4 使用
- **Task 2** 新建 `symbol_selector.py`，基于波动性筛选品种，供 Task 4 使用
- **Task 3** 修改 `china_futures_strategy.py`，增加 `trading_mode` 参数（"intraday"/"swing"），Task 4 的回测引擎通过该参数控制日内平仓行为
- **Task 4** 新建 `multi_backtest_runner.py`，整合 Task 1/2/3 的产出，实现多品种批量回测和排名报告
- 数据流：data_fetcher → symbol_selector → multi_backtest_runner；Task 3 为 Task 4 提供策略扩展

---

### Task 0: 环境准备

**背景:**
确保构建和测试工具链在当前开发环境中可用，避免后续 Task 因环境问题阻塞。

**执行步骤:**
- [x] 验证 uv 包管理器可用
  - `cd /Users/hse/projects/backend/quant && uv --version`
  - 预期: 输出 uv 版本号，无错误
- [x] 验证 Python 版本
  - `cd /Users/hse/projects/backend/quant && python3 --version`
  - 预期: 输出 Python 3.11+
- [x] 安装项目依赖
  - `cd /Users/hse/projects/backend/quant && uv sync`
  - 预期: 依赖安装成功，无错误

**检查步骤:**
- [x] 验证项目可导入
  - `cd /Users/hse/projects/backend/quant && uv run python -c "import akshare; print('akshare ok')"`
  - 预期: 输出 "akshare ok"，若不可用不影响 Task 执行（Task 会使用模拟数据）
- [x] 验证现有模块可导入
  - `cd /Users/hse/projects/backend/quant && uv run python -c "from china_futures_strategy import ChinaFuturesStrategy; from backtest_runner import run_backtest; print('modules ok')"`
  - 预期: 输出 "modules ok"

---

### Task 1: 多品种数据获取模块

**背景:**
当前量化系统仅支持单一品种（螺纹钢 rb）的数据获取，backtest_runner.py 中的 fetch_akshare_futures() 只能逐品种获取数据。需新建独立的 data_fetcher.py 模块，支持一次性获取 FUTURES_CONFIG 中所有国内期货品种的历史数据，为后续品种筛选和多品种回测提供统一的数据源。Task 2 的 symbol_selector 和 Task 4 的 multi_backtest_runner 均依赖本模块输出。

**涉及文件:**
- 新建: `backtest_runner.py` 同目录下的 `data_fetcher.py`
- 新建: `tests/test_data_fetcher.py`
- 修改: `pyproject.toml`（添加 pytest 依赖）

**执行步骤:**
- [x] 在 backtest_runner.py 同目录下新建 `data_fetcher.py`
  - 位置: `/Users/hse/projects/backend/quant/data_fetcher.py`
  - 导入 AkShare 的 futures_zh_daily_sina，复用 backtest_runner.py:36 fetch_akshare_futures() 的数据转换逻辑
  - 定义 `get_all_futures_symbols() -> List[str]`: 从 china_futures_strategy.py 读取 FUTURES_CONFIG 的所有 key
  - 定义 `fetch_futures_data(symbol: str, days: int = 300) -> Optional[Dict]`: 单品种获取，逻辑同 backtest_runner.py:36-90（复用于 data_fetcher 自身）
  - 定义 `fetch_multi_futures_data(symbols: Optional[List[str]] = None, days: int = 300) -> Dict[str, Dict]`: 批量获取多品种数据，symbols 为 None 时默认获取全部品种，返回 `{symbol: data_dict}`；单个品种失败时打印警告并跳过，不影响其他品种
  - 定义 `FuturesDataCache` 类: 内存缓存已获取的数据，避免重复请求；提供 `get(symbol, days)` / `set(symbol, days, data)` / `clear()` 接口
- [x] 在 pyproject.toml 中添加 pytest 到 dev-dependencies
  - 位置: `pyproject.toml` 的 `[tool.uv] dev-dependencies = []` 段
  - 添加 `"pytest"` 到 dev-dependencies 列表
- [x] 新建 `tests/` 目录（如不存在）
  - 位置: `/Users/hse/projects/backend/quant/tests/`
  - 创建 `tests/__init__.py`（空文件）
- [x] 为 data_fetcher.py 编写单元测试
  - 测试文件: `/Users/hse/projects/backend/quant/tests/test_data_fetcher.py`
  - 测试场景:
    - get_all_futures_symbols(): 输入 None → 返回包含 'rb', 'cu', 'au', 'sc' 等关键品种的 list，长度 >= 30
    - get_all_futures_symbols(): 返回的品种均为 str 类型
    - fetch_futures_data("rb", days=10): 返回 dict 且包含 keys: symbol, dates, opens, highs, lows, closes, volumes；dates 长度 == opens 长度 == highs 长度 == ... == volumes 长度
    - fetch_multi_futures_data(symbols=["rb", "cu"], days=10): 返回 dict，keys 包含 "rb" 和 "cu"，每个子 dict 包含上述 7 个 keys
    - fetch_multi_futures_data(symbols=["invalid_symbol"], days=10): 不抛出异常，返回的 dict 中不包含 "invalid_symbol"
    - FuturesDataCache: set 后 get 能取到相同数据；clear 后 get 返回 None
  - 运行命令: `cd /Users/hse/projects/backend/quant && uv run pytest tests/test_data_fetcher.py -v`
  - 预期: 所有测试通过（若 AkShare 不可用则回退到模拟数据模式，测试仍应通过）

**检查步骤:**
- [x] 验证 data_fetcher.py 文件存在且可导入
  - `cd /Users/hse/projects/backend/quant && uv run python -c "from data_fetcher import get_all_futures_symbols, fetch_futures_data, fetch_multi_futures_data, FuturesDataCache; print('import ok')"`
  - 预期: 输出 "import ok"，无 ImportError
- [x] 验证 fetch_multi_futures_data 能获取至少 30 个品种
  - `cd /Users/hse/projects/backend/quant && uv run python -c "from data_fetcher import get_all_futures_symbols, fetch_multi_futures_data; symbols = get_all_futures_symbols(); print(f'品种数量: {len(symbols)}')"`
  - 预期: 输出品种数量 >= 30
- [x] 验证 fetch_futures_data 返回数据格式正确
  - `cd /Users/hse/projects/backend/quant && uv run python -c "from data_fetcher import fetch_futures_data; d = fetch_futures_data('rb', days=5); print(sorted(d.keys()) if d else 'None')"`
  - 预期: 输出包含 symbol, dates, opens, highs, lows, closes, volumes 七个 key 的排序列表

---

### Task 2: 品种筛选模块

**背景:**
品种筛选模块负责根据波动性指标对国内期货全品种进行排序和筛选，为多品种回测提供高质量候选品种。现有系统没有波动性自动筛选机制，所有品种均需手动指定。通过 ATR 和波动率双重指标排序，可优先测试高波动、低成本的品种，提高策略开发效率。Task 2 依赖 Task 1 的 `fetch_multi_futures_data` 接口，输出供 Task 4 的多品种回测使用。

**涉及文件:**
- 新建: `backtest_runner.py` 同目录下的 `symbol_selector.py`
- 新建: `tests/test_symbol_selector.py`

**执行步骤:**
- [x] 在 backtest_runner.py 同目录下新建 `symbol_selector.py`
  - 位置: `/Users/hse/projects/backend/quant/symbol_selector.py`
  - 从 `data_fetcher` 导入 `fetch_multi_futures_data`（Task 1 产出）
  - 从 `indicators` 导入 `atr` 函数（已有，`indicators.py:68`，签名 `atr(opens, highs, lows, closes, idx, period=14)`）
  - 从 `china_futures_strategy` 导入 `FUTURES_CONFIG`（已有，`china_futures_strategy.py:32`，包含 `contract_size` 字段）
  - 定义 `VolatilityResult` 数据类，包含字段: symbol, name, atr, daily_vol_amount, volatility_rate, avg_volume
  - 定义 `_compute_symbol_volatility(data: Dict, period: int = 14) -> Optional[VolatilityResult]`:
    - 从 data 中提取 closes/highs/lows/opens/volumes
    - 在最后一个有效索引 idx = len(closes) - 1 处调用 `atr(opens, highs, lows, closes, idx, period)` 获取 ATR
    - 从 FUTURES_CONFIG 读取 contract_size
    - 日均波动金额 = ATR × contract_size
    - 波动率 = ATR / closes[-1] × 100%
    - 最近 20 日平均成交量作为 avg_volume
    - 返回 VolatilityResult 或 None（数据不足时）
  - 定义 `select_top_symbols(symbols: Optional[List[str]] = None, days: int = 60, top_n: int = 10, min_vol_rate: float = 0.015, max_vol_rate: float = 0.04, min_volume: int = 10000, period: int = 14) -> List[VolatilityResult]`:
    - 调用 `fetch_multi_futures_data(symbols, days)` 获取多品种数据（依赖 Task 1）
    - 对每个品种调用 `_compute_symbol_volatility` 计算波动性
    - 过滤: vol_rate 在 [min_vol_rate, max_vol_rate] 区间内 AND avg_volume >= min_volume
    - 按 vol_rate 降序排序，返回 top_n 个结果
    - 单个品种计算失败时打印警告并跳过
  - 定义 `get_volatility_report(symbols: Optional[List[str]] = None, days: int = 60, top_n: int = 20) -> str`:
    - 调用 `select_top_symbols` 获取排序列表
    - 格式化为可读表格字符串，每行: rank | symbol | name | volatility_rate% | daily_vol_amount | avg_volume
- [x] 为 symbol_selector.py 编写单元测试
  - 测试文件: `/Users/hse/projects/backend/quant/tests/test_symbol_selector.py`
  - 使用 pytest 框架
  - 测试场景:
    - `_compute_symbol_volatility` 使用模拟数据: valid data → 返回 VolatilityResult 且 volatility_rate > 0, daily_vol_amount > 0
    - `_compute_symbol_volatility` 数据不足（len < 2）→ 返回 None（不抛异常）
    - `select_top_symbols` 输入 ["rb", "cu"]，两个品种波动率均在范围内 → 返回按波动率降序排列的 list，长度 <= 2
    - `select_top_symbols` 波动率过滤: 两个品种一个在范围内、一个不在 → 只返回在范围内的品种
    - `select_top_symbols` 成交量过滤: 设置 min_volume=9999999 → 返回空列表（不抛异常）
    - `select_top_symbols` top_n 参数: 5 个品种、top_n=2 → 返回长度 2 的列表
    - `get_volatility_report` 返回非空字符串且包含 "symbol" 和 "volatility_rate" 表头
  - 运行命令: `cd /Users/hse/projects/backend/quant && uv run pytest tests/test_symbol_selector.py -v`
  - 预期: 所有测试通过（使用模拟数据，不依赖 AkShare 网络）

**检查步骤:**
- [x] 验证 symbol_selector.py 文件存在且可导入
  - `cd /Users/hse/projects/backend/quant && uv run python -c "from symbol_selector import select_top_symbols, get_volatility_report, VolatilityResult; print('import ok')"`
  - 预期: 输出 "import ok"，无 ImportError
- [x] 验证 VolatilityResult 数据类字段完整
  - `cd /Users/hse/projects/backend/quant && uv run python -c "from symbol_selector import VolatilityResult; r = VolatilityResult(symbol='rb', name='螺纹钢', atr=50.0, daily_vol_amount=500.0, volatility_rate=0.025, avg_volume=50000); print(r.symbol, r.volatility_rate)"`
  - 预期: 输出 "rb 0.025"
- [x] 验证 select_top_symbols 过滤逻辑正确（使用模拟数据，不走网络）
  - `cd /Users/hse/projects/backend/quant && uv run python -c "from symbol_selector import select_top_symbols; result = select_top_symbols(symbols=['rb', 'cu'], days=60, min_vol_rate=0.0, max_vol_rate=1.0, min_volume=0); print(len(result))"`
  - 预期: 输出大于 0（至少返回可用品种）

---

### Task 3: 策略交易模式扩展

**背景:**
当前 `ChinaFuturesStrategy` 类仅支持波段持仓模式，无法区分日内（当日开平不过夜）和波段（可持仓过夜）两种交易场景。随着 Task 1/2 构建的多品种数据基础设施就绪，Task 4 的多品种回测需要策略支持日内模式下的收盘前强制平仓逻辑。由于回测数据为日线级别（每日一根 K 线），真正的"收盘前 5 分钟"无法精确到分钟级别，只能在下一根日线开盘时检测并平仓。本任务专注于策略层面的参数和标记增加，backtest_runner 的每日平仓协调逻辑在 Task 4 中实现。

**涉及文件:**
- 修改: `/Users/hse/projects/backend/quant/china_futures_strategy.py`

**执行步骤:**
- [x] 在 `ChinaFuturesStrategy.__init__()` 中增加 `trading_mode` 参数
  - 位置: `china_futures_strategy.py:539 __init__()` 签名处（约第 539 行）
  - 参数定义: `trading_mode: str = "swing"`，允许值 `"intraday"`（日内）和 `"swing"`（波段）
  - 在 `__init__` 方法体内添加: `self.trading_mode = trading_mode`
  - 原因: 新增参数需向后兼容，默认 "swing" 保证现有代码行为不变
- [x] 在 `analyze()` 方法返回结果中增加 `session_end_force_close` 字段
  - 位置: `china_futures_strategy.py:751 analyze()` 方法的 result 字典初始化处（约第 758 行）
  - 在 result 字典中添加: `'session_end_force_close': False`
  - 原因: 该字段标记本次分析是否要求在收盘前强制平仓，回测引擎读取此标记决定是否平仓
- [x] 在 `analyze()` 方法逻辑末尾（设置 `action` 字段之后）实现日内模式强制平仓检测
  - 位置: `china_futures_strategy.py:871 analyze()` 中 `action` 字段被设置之后（约第 873 行之后）
  - 逻辑: 当 `self.trading_mode == "intraday"` 时，如果当前有持仓（由 backtest_runner 告知，通过 `entry_idx` 在 result 中传递），且持仓已跨日（`idx - entry_idx > 0`），则设置 `result['session_end_force_close'] = True`
  - 伪代码:
    ```
    if self.trading_mode == 'intraday' and 'entry_idx' in result and (idx - result['entry_idx']) > 0:
        result['session_end_force_close'] = True
    ```
  - 原因: 由于 `analyze()` 本身不管理持仓（持仓由 backtest_runner 管理），通过 `entry_idx` 字段传递入场索引；当持仓跨日时强制平仓信号生效
- [x] 为 `china_futures_strategy.py` 编写单元测试
  - 测试文件: `/Users/hse/projects/backend/quant/tests/test_china_futures_strategy.py`
  - 使用 pytest 框架
  - 测试场景:
    - `__init__` 默认参数: `strategy = ChinaFuturesStrategy()` → `strategy.trading_mode == "swing"`（向后兼容）
    - `__init__` intraday 模式: `strategy = ChinaFuturesStrategy(trading_mode="intraday")` → `strategy.trading_mode == "intraday"`
    - `analyze()` 默认模式: `result = strategy.analyze(...)` → `'session_end_force_close' in result` 为 True 且值为 False
    - `analyze()` intraday 模式带跨日持仓: 构造包含 `entry_idx` 的 result，trading_mode="intraday"，idx - entry_idx > 0 → `session_end_force_close == True`
    - `analyze()` intraday 模式无跨日: trading_mode="intraday"，无 entry_idx 或 idx - entry_idx == 0 → `session_end_force_close == False`
  - 运行命令: `cd /Users/hse/projects/backend/quant && uv run pytest tests/test_china_futures_strategy.py -v`
  - 预期: 所有测试通过（使用模拟数据，不依赖 AkShare 网络）

**检查步骤:**
- [x] 验证 `ChinaFuturesStrategy` 可导入且默认 trading_mode 为 "swing"
  - `cd /Users/hse/projects/backend/quant && uv run python -c "from china_futures_strategy import ChinaFuturesStrategy; s = ChinaFuturesStrategy(); print(s.trading_mode)"`
  - 预期: 输出 "swing"
- [x] 验证 intraday 模式可正常设置
  - `cd /Users/hse/projects/backend/quant && uv run python -c "from china_futures_strategy import ChinaFuturesStrategy; s = ChinaFuturesStrategy(trading_mode='intraday'); print(s.trading_mode)"`
  - 预期: 输出 "intraday"
- [x] 验证 analyze() 结果包含 session_end_force_close 字段
  - `cd /Users/hse/projects/backend/quant && uv run python -c "
from china_futures_strategy import ChinaFuturesStrategy
import random
random.seed(42)
n = 100
prices = [4000]
for _ in range(1, n): prices.append(prices[-1] * (1 + random.uniform(-0.02, 0.025)))
opens = [p * (1 + random.uniform(-0.005, 0.005)) for p in prices]
highs = [max(p, o) * (1 + random.uniform(0, 0.01)) for p, o in zip(prices, opens)]
lows = [min(p, o) * (1 - random.uniform(0, 0.01)) for p, o in zip(prices, opens)]
closes = prices
strategy = ChinaFuturesStrategy()
result = strategy.analyze(opens, highs, lows, closes, len(closes)-1)
print('session_end_force_close' in result, result.get('session_end_force_close'))
"`
  - 预期: 输出 "True False"（字段存在但默认 False）

---

### Task 4: 多品种回测运行器

**背景:**
在 Task 1/2/3 构建的数据基础设施和策略扩展就绪后，需要一个统一的入口将多品种数据、波动性筛选和策略执行串联起来。现有 `backtest_runner.py` 的 `run_backtest()` 仅支持单一品种，无法满足多品种横向对比和批量回测的需求。新建 `multi_backtest_runner.py`，整合 `data_fetcher`（Task 1）、`symbol_selector`（Task 2）和扩展后的 `ChinaFuturesStrategy`（Task 3），实现批量回测、品种排名和推荐交易列表输出。Task 4 依赖 Task 1/2/3 的产出模块。

**涉及文件:**
- 新建: `backtest_runner.py` 同目录下的 `multi_backtest_runner.py`
- 新建: `tests/test_multi_backtest_runner.py`

**执行步骤:**
- [x] 在 backtest_runner.py 同目录下新建 `multi_backtest_runner.py`
  - 位置: `/Users/hse/projects/backend/quant/multi_backtest_runner.py`
  - 导入 `fetch_multi_futures_data`（Task 1 产出，`data_fetcher.py`）
  - 导入 `select_top_symbols` 和 `get_volatility_report`（Task 2 产出，`symbol_selector.py`）
  - 导入 `ChinaFuturesStrategy`（Task 3 产出，`china_futures_strategy.py`）
  - 定义 `BacktestResult` 数据类，包含字段: symbol, name, total_trades, winning_trades, losing_trades, win_rate, total_return, max_drawdown, final_capital, initial_capital, total_pnl, comprehensive_score, trades
  - 定义 `compute_comprehensive_score(result: BacktestResult) -> float`:
    - 综合评分 = 收益率权重(40%) + 胜率权重(20%) + 风险调整收益权重(25%，即 return/drawdown) + 交易次数权重(15%，归一化)
    - 各指标均做 min-max 归一化到 [0, 1]
  - 定义 `_run_single_backtest(symbol: str, data: Dict, initial_capital: float, trading_mode: str) -> BacktestResult`:
    - 参考 backtest_runner.py:163-320 的 `run_backtest()` 逻辑，但提取为单品种函数
    - 构造 `ChinaFuturesStrategy(symbol=symbol, trading_mode=trading_mode)`（Task 3 新增参数）
    - 遍历 `range(30, len(dates))`，调用 `strategy.analyze()`，管理持仓逻辑
    - 日内模式（trading_mode="intraday"）: 读取 result 中的 `session_end_force_close`（Task 3），若为 True 则强制平仓
    - 返回 BacktestResult（包含 comprehensive_score 初始为 0，后续由调用方填充）
    - 单品种失败时打印警告并返回 None
  - 定义 `run_multi_backtest(symbols: Optional[List[str]] = None, days: int = 60, initial_capital: float = 100000, trading_mode: str = "swing", top_n: int = 10, min_vol_rate: float = 0.015, max_vol_rate: float = 0.04, min_volume: int = 10000) -> List[BacktestResult]`:
    - 调用 `select_top_symbols(symbols=symbols, days=days, top_n=top_n, min_vol_rate=min_vol_rate, max_vol_rate=max_vol_rate, min_volume=min_volume)` 获取候选品种（依赖 Task 2）
    - 对候选品种列表调用 `fetch_multi_futures_data` 获取历史数据（依赖 Task 1）
    - 遍历品种列表，对每个品种调用 `_run_single_backtest`（顺序执行，不做并行以简化实现）
    - 对返回的 BacktestResult 列表调用 `compute_comprehensive_score` 计算综合评分
    - 按 comprehensive_score 降序排列
    - 返回排序后的结果列表
  - 定义 `print_ranking_report(results: List[BacktestResult]) -> None`:
    - 打印表头: 排名 | 品种 | 名称 | 收益率% | 最大回撤% | 胜率% | 综合评分
    - 遍历 results，每行打印一个品种的绩效
    - 在报告末尾打印推荐交易品种列表（综合评分排名前 5 且 total_trades >= 3 的品种）
- [x] 为 multi_backtest_runner.py 编写单元测试
  - 测试文件: `/Users/hse/projects/backend/quant/tests/test_multi_backtest_runner.py`
  - 使用 pytest 框架
  - 测试场景:
    - `BacktestResult` 数据类: 构造实例并验证各字段可访问
    - `compute_comprehensive_score`: 构造两个 BacktestResult（一个有收益、一个亏损），调用后分数高的排名在前
    - `_run_single_backtest`: 使用模拟数据（generate_simulated_data），返回 BacktestResult 且 symbol 正确
    - `_run_single_backtest`: 无效 symbol 返回 None（不抛异常）
    - `run_multi_backtest`: symbols=["rb", "cu"]，trading_mode="swing"，返回长度 <= 2 的结果列表
    - `run_multi_backtest`: top_n=1 时只返回 1 个结果
    - `print_ranking_report`: 传入空列表不抛异常
    - `run_multi_backtest` intraday 模式: trading_mode="intraday" 时正常执行，不抛异常
  - 运行命令: `cd /Users/hse/projects/backend/quant && uv run pytest tests/test_multi_backtest_runner.py -v`
  - 预期: 所有测试通过（使用模拟数据，不依赖 AkShare 网络）

**检查步骤:**
- [x] 验证 multi_backtest_runner.py 文件存在且可导入
  - `cd /Users/hse/projects/backend/quant && uv run python -c "from multi_backtest_runner import run_multi_backtest, print_ranking_report, BacktestResult; print('import ok')"`
  - 预期: 输出 "import ok"，无 ImportError
- [x] 验证 run_multi_backtest 使用模拟数据可正常执行
  - `cd /Users/hse/projects/backend/quant && uv run python -c "from multi_backtest_runner import run_multi_backtest; results = run_multi_backtest(symbols=['rb', 'hc'], days=60, top_n=2, min_vol_rate=0.0, max_vol_rate=1.0, min_volume=0); print(f'结果数量: {len(results)}')"`
  - 预期: 输出 "结果数量: 2" 或 "结果数量: 1"（取决于数据是否足够），不抛异常
- [x] 验证综合评分计算正确
  - `cd /Users/hse/projects/backend/quant && uv run python -c "from multi_backtest_runner import BacktestResult, compute_comprehensive_score; r1 = BacktestResult(symbol='rb', name='螺纹钢', total_trades=10, winning_trades=7, losing_trades=3, win_rate=70.0, total_return=5.0, max_drawdown=2.0, final_capital=105000, initial_capital=100000, total_pnl=5000, comprehensive_score=0, trades=[]); r2 = BacktestResult(symbol='cu', name='铜', total_trades=10, winning_trades=3, losing_trades=7, win_rate=30.0, total_return=-2.0, max_drawdown=5.0, final_capital=98000, initial_capital=100000, total_pnl=-2000, comprehensive_score=0, trades=[]); s1 = compute_comprehensive_score(r1); s2 = compute_comprehensive_score(r2); print(f'rb_score={s1:.3f}, cu_score={s2:.3f}, rb>cu={s1>s2}')"`
  - 预期: 输出 "rb_score=1.000, cu_score=0.000, rb>cu=True"（或接近该比例）

---

### Task 5: 多品种日内交易 验收

**前置条件:**
- 已完成 Task 0-4 的全部执行步骤和检查步骤
- 测试数据：使用 AkShare 真实数据或模拟数据均可

**端到端验证:**

1. 运行完整测试套件确保无回归
   - `cd /Users/hse/projects/backend/quant && uv run pytest tests/ -v`
   - 预期: 所有测试通过，无 ERROR
   - 失败排查: 检查各 Task 的单元测试步骤

2. 验证多品种数据获取（Task 1）
   - `cd /Users/hse/projects/backend/quant && uv run python -c "from data_fetcher import get_all_futures_symbols; symbols = get_all_futures_symbols(); print(f'支持品种数: {len(symbols)}')"`
   - 预期: 输出支持品种数 >= 30
   - 失败排查: 检查 data_fetcher.py 的 FUTURES_CONFIG 导入

3. 验证波动性筛选（Task 2）
   - `cd /Users/hse/projects/backend/quant && uv run python -c "from symbol_selector import select_top_symbols; r = select_top_symbols(symbols=['rb','cu','au','hc'], days=60, min_vol_rate=0.0, max_vol_rate=1.0, min_volume=0); print(f'筛选结果: {[x.symbol for x in r]}')"`
   - 预期: 输出筛选结果列表，不抛异常
   - 失败排查: 检查 symbol_selector.py 的 atr 调用和 FUTURES_CONFIG.contract_size 读取

4. 验证日内交易模式（Task 3）
   - `cd /Users/hse/projects/backend/quant && uv run python -c "from china_futures_strategy import ChinaFuturesStrategy; s = ChinaFuturesStrategy(trading_mode='intraday'); print(f'trading_mode: {s.trading_mode}')"`
   - 预期: 输出 "trading_mode: intraday"
   - 失败排查: 检查 china_futures_strategy.py 的 __init__ 参数

5. 验证多品种回测运行（Task 4）
   - `cd /Users/hse/projects/backend/quant && uv run python -c "from multi_backtest_runner import run_multi_backtest; results = run_multi_backtest(symbols=['rb','hc'], days=60, top_n=2, min_vol_rate=0.0, max_vol_rate=1.0, min_volume=0); print(f'回测品种数: {len(results)}')"`
   - 预期: 输出 "回测品种数: 2" 或 "回测品种数: 1"，不抛异常
   - 失败排查: 检查 multi_backtest_runner.py 的 import 和 BacktestResult 数据类


