"""
multi_backtest_runner.py - 多品种回测运行器
==========================================

整合 data_fetcher、symbol_selector 和 ChinaFuturesStrategy，实现多品种批量回测和排名报告。

使用方法:
    from multi_backtest_runner import run_multi_backtest, print_ranking_report

    # 运行多品种回测
    results = run_multi_backtest(symbols=['rb', 'cu', 'au'], days=60, top_n=10)

    # 打印排名报告
    print_ranking_report(results)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from data_fetcher import fetch_multi_futures_data
from symbol_selector import select_top_symbols, get_volatility_report
from china_futures_strategy import ChinaFuturesStrategy


@dataclass
class BacktestResult:
    """回测结果"""
    symbol: str
    name: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return: float
    max_drawdown: float
    final_capital: float
    initial_capital: float
    total_pnl: float
    comprehensive_score: float
    trades: List[Dict] = field(default_factory=list)


def compute_comprehensive_score(result: BacktestResult) -> float:
    """
    计算综合评分（单结果版本，使用固定基准归一化）

    综合评分 = 收益率权重(40%) + 胜率权重(20%) + 风险调整收益权重(25%，即 return/drawdown) + 交易次数权重(15%，归一化)
    各指标均做 min-max 归一化到 [0, 1]
    """
    # 固定归一化基准
    RETURN_MIN, RETURN_MAX = -100.0, 100.0
    WIN_RATE_MIN, WIN_RATE_MAX = 0.0, 100.0
    RISK_ADJ_MIN, RISK_ADJ_MAX = -10.0, 10.0
    TRADES_MIN, TRADES_MAX = 0.0, 100.0

    def norm(value: float, vmin: float, vmax: float) -> float:
        if vmax == vmin:
            return 0.5
        return max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))

    risk_adj = result.total_return / result.max_drawdown if result.max_drawdown > 0 else 0.0

    norm_return = norm(result.total_return, RETURN_MIN, RETURN_MAX)
    norm_win_rate = norm(result.win_rate, WIN_RATE_MIN, WIN_RATE_MAX)
    norm_risk_adj = norm(risk_adj, RISK_ADJ_MIN, RISK_ADJ_MAX)
    norm_trades = norm(float(result.total_trades), TRADES_MIN, TRADES_MAX)

    score = (0.40 * norm_return + 0.20 * norm_win_rate +
             0.25 * norm_risk_adj + 0.15 * norm_trades)
    return score


def compute_comprehensive_score_for_results(results: List['BacktestResult']) -> None:
    """
    批量计算综合评分

    对所有结果进行归一化，计算综合评分
    """
    if not results:
        return

    # 提取各指标
    returns = [r.total_return for r in results]
    win_rates = [r.win_rate for r in results]
    # 风险调整收益 = return / max_drawdown（避免除零）
    risk_adjusted = [r.total_return / r.max_drawdown if r.max_drawdown > 0 else 0 for r in results]
    trade_counts = [r.total_trades for r in results]

    # Min-max 归一化
    def normalize(values: List[float]) -> List[float]:
        min_val, max_val = min(values), max(values)
        if max_val == min_val:
            return [0.5] * len(values)
        return [(v - min_val) / (max_val - min_val) for v in values]

    norm_returns = normalize(returns)
    norm_win_rates = normalize(win_rates)
    norm_risk_adjusted = normalize(risk_adjusted)
    norm_trade_counts = normalize(trade_counts)

    # 计算综合评分
    weights = {'return': 0.40, 'win_rate': 0.20, 'risk_adjusted': 0.25, 'trade_count': 0.15}
    for i, r in enumerate(results):
        score = (weights['return'] * norm_returns[i] +
                 weights['win_rate'] * norm_win_rates[i] +
                 weights['risk_adjusted'] * norm_risk_adjusted[i] +
                 weights['trade_count'] * norm_trade_counts[i])
        r.comprehensive_score = score


def _run_single_backtest(
    symbol: str,
    data: Dict,
    initial_capital: float,
    trading_mode: str
) -> Optional[BacktestResult]:
    """
    运行单品种回测

    Args:
        symbol: 品种代码
        data: 品种数据字典
        initial_capital: 初始资金
        trading_mode: 交易模式 ("intraday" 或 "swing")

    Returns:
        BacktestResult 或 None（失败时）
    """
    try:
        from china_futures_strategy import FUTURES_CONFIG

        # 验证品种是否在配置中
        if symbol.lower() not in FUTURES_CONFIG:
            print(f"警告: 品种 {symbol} 不在配置中，已跳过")
            return None

        name = FUTURES_CONFIG.get(symbol, {}).get('name', symbol)
        dates = data.get('dates', [])
        opens = data.get('opens', [])
        highs = data.get('highs', [])
        lows = data.get('lows', [])
        closes = data.get('closes', [])

        if len(dates) < 30:
            print(f"警告: 品种 {symbol} 数据不足 ({len(dates)} 天)，已跳过")
            return None

        # 构造策略实例（使用 Task 3 新增的 trading_mode 参数）
        strategy = ChinaFuturesStrategy(
            symbol=symbol,
            trading_mode=trading_mode,
            risk_percent=0.05,
            atr_stop=2.0,
            atr_target=6.0
        )

        trades = []
        equity_curve = [initial_capital]
        current_capital = initial_capital
        position = 0
        entry_price = 0
        entry_idx = 0

        # 持仓信息（用于日内模式强制平仓）
        position_entry_idx = None  # 入场索引

        for i in range(30, len(dates)):
            result = strategy.analyze(opens, highs, lows, closes, i)

            # 如果 result 中有 entry_idx（由 backtest_runner 设置），记录入场索引
            if 'entry_idx' in result:
                position_entry_idx = result['entry_idx']

            action = result.get('action', '')
            signal = result.get('signal', 0)
            trend = result.get('trend', 'unknown')
            atr = result.get('atr', 0)

            # 入场
            if position == 0 and atr > 0:
                position_size = int((current_capital * 0.05) / (atr * 2.0 * 10))
                if position_size <= 0:
                    position_size = 1

                # 多头
                if signal == 1 or action == 'long':
                    position = position_size
                    entry_price = closes[i]
                    entry_idx = i
                    position_entry_idx = i
                    trades.append({
                        'date': dates[i],
                        'type': 'LONG',
                        'entry_price': entry_price,
                        'position': position,
                        'stop_loss': atr * 2.0,
                        'reason': f"{trend} trend"
                    })
                # 空头
                elif signal == -1 or action == 'short':
                    position = -position_size
                    entry_price = closes[i]
                    entry_idx = i
                    position_entry_idx = i
                    trades.append({
                        'date': dates[i],
                        'type': 'SHORT',
                        'entry_price': entry_price,
                        'position': position,
                        'stop_loss': atr * 2.0,
                        'reason': f"{trend} trend"
                    })

            # 出场
            elif position != 0:
                should_stop = False
                reason = ""
                pnl = 0

                if position > 0:  # 多头
                    pnl = (closes[i] - entry_price) * position * 10
                    if closes[i] < entry_price - atr * 2.0:
                        should_stop, reason = True, "ATR Stop Loss"
                    elif closes[i] > entry_price + atr * 6.0:
                        should_stop, reason = True, "Take Profit"
                    elif signal == -1 or action == 'short':
                        should_stop, reason = True, "Reverse to Short"
                else:  # 空头
                    pnl = (entry_price - closes[i]) * abs(position) * 10
                    if closes[i] > entry_price + atr * 2.0:
                        should_stop, reason = True, "ATR Stop Loss"
                    elif closes[i] < entry_price - atr * 6.0:
                        should_stop, reason = True, "Take Profit"
                    elif signal == 1 or action == 'long':
                        should_stop, reason = True, "Reverse to Long"

                # 日内模式：检查 session_end_force_close
                if result.get('session_end_force_close', False) and not should_stop:
                    should_stop, reason = True, "Intraday Force Close"

                if should_stop:
                    current_capital += pnl
                    if trades:
                        trades[-1].update({
                            'exit_price': closes[i],
                            'pnl': pnl,
                            'exit_reason': reason
                        })
                    position, entry_price = 0, 0
                    position_entry_idx = None

            equity_curve.append(current_capital)

        # 回测结束时平仓
        if position > 0:
            pnl = (closes[-1] - entry_price) * position * 10
            current_capital += pnl
            if trades:
                trades[-1].update({
                    'exit_price': closes[-1],
                    'pnl': pnl,
                    'exit_reason': 'End of Backtest'
                })
        elif position < 0:
            pnl = (entry_price - closes[-1]) * abs(position) * 10
            current_capital += pnl
            if trades:
                trades[-1].update({
                    'exit_price': closes[-1],
                    'pnl': pnl,
                    'exit_reason': 'End of Backtest'
                })

        # 统计
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
        losing_trades = [t for t in trades if t.get('pnl', 0) <= 0]
        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
        total_pnl = current_capital - initial_capital
        total_return = total_pnl / initial_capital * 100

        # 最大回撤
        peak, max_drawdown = initial_capital, 0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak * 100 if peak > 0 else 0
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return BacktestResult(
            symbol=symbol,
            name=name,
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            total_return=total_return,
            max_drawdown=max_drawdown,
            final_capital=current_capital,
            initial_capital=initial_capital,
            total_pnl=total_pnl,
            comprehensive_score=0.0,
            trades=trades
        )

    except Exception as e:
        print(f"警告: 品种 {symbol} 回测失败: {e}")
        return None


def run_multi_backtest(
    symbols: Optional[List[str]] = None,
    days: int = 60,
    initial_capital: float = 100000,
    trading_mode: str = "swing",
    top_n: int = 10,
    min_vol_rate: float = 0.015,
    max_vol_rate: float = 0.04,
    min_volume: int = 10000
) -> List[BacktestResult]:
    """
    运行多品种回测

    Args:
        symbols: 品种列表，None 时自动筛选
        days: 历史数据天数
        initial_capital: 初始资金
        trading_mode: 交易模式 ("intraday" 或 "swing")
        top_n: 最多回测品种数
        min_vol_rate: 最小波动率
        max_vol_rate: 最大波动率
        min_volume: 最小成交量

    Returns:
        按综合评分降序排列的 BacktestResult 列表
    """
    # 筛选品种（依赖 Task 2）
    selected = select_top_symbols(
        symbols=symbols,
        days=days,
        top_n=top_n,
        min_vol_rate=min_vol_rate,
        max_vol_rate=max_vol_rate,
        min_volume=min_volume
    )

    if not selected:
        print("警告: 无品种满足筛选条件")
        return []

    # 获取历史数据（依赖 Task 1）
    selected_symbols = [s.symbol for s in selected]
    multi_data = fetch_multi_futures_data(selected_symbols, days)

    # 逐品种回测
    results = []
    for vol_result in selected:
        symbol = vol_result.symbol
        if symbol not in multi_data:
            print(f"警告: 品种 {symbol} 无数据，已跳过")
            continue

        result = _run_single_backtest(symbol, multi_data[symbol], initial_capital, trading_mode)
        if result is not None:
            results.append(result)

    # 计算综合评分
    compute_comprehensive_score_for_results(results)

    # 按综合评分降序排列
    results.sort(key=lambda x: x.comprehensive_score, reverse=True)

    return results


def print_ranking_report(results: List[BacktestResult]) -> None:
    """
    打印排名报告

    Args:
        results: BacktestResult 列表
    """
    if not results:
        print("无回测结果")
        return

    # 表头
    header = f"{'Rank':<6}{'Symbol':<8}{'Name':<10}{'Return%':<12}{'MaxDD%':<10}{'WinRate%':<10}{'Score':<8}"
    print("\n" + "=" * 70)
    print("  多品种回测排名报告")
    print("=" * 70)
    print(header)
    print("-" * 70)

    # 每行数据
    for i, r in enumerate(results, 1):
        print(f"{i:<6}{r.symbol:<8}{r.name:<10}{r.total_return:<12.2f}{r.max_drawdown:<10.2f}{r.win_rate:<10.1f}{r.comprehensive_score:<8.3f}")

    # 推荐交易品种（综合评分前5且 total_trades >= 3）
    recommended = [r for r in results if r.total_trades >= 3][:5]
    if recommended:
        print("\n推荐交易品种（综合评分前5且交易次数>=3）:")
        for i, r in enumerate(recommended, 1):
            print(f"  {i}. {r.symbol} ({r.name}) - 收益率: {r.total_return:.2f}%, 胜率: {r.win_rate:.1f}%, 评分: {r.comprehensive_score:.3f}")
