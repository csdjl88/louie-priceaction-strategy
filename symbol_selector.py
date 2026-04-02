"""
symbol_selector.py - 品种波动性筛选模块
======================================

基于 ATR 和波动率对期货品种进行排序和筛选，为多品种回测提供高质量候选品种。

使用方法:
    from symbol_selector import select_top_symbols, get_volatility_report

    # 筛选高波动品种
    results = select_top_symbols(symbols=['rb', 'cu', 'au'], days=60, top_n=10)

    # 生成报告
    report = get_volatility_report(symbols=['rb', 'cu', 'au'], days=60)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from data_fetcher import fetch_multi_futures_data
from indicators import atr
from china_futures_strategy import FUTURES_CONFIG


@dataclass
class VolatilityResult:
    """波动性筛选结果"""
    symbol: str
    name: str
    atr: float
    daily_vol_amount: float  # 日均波动金额 = ATR × contract_size
    volatility_rate: float   # 波动率 = ATR / closes[-1] × 100%
    avg_volume: int          # 最近 20 日平均成交量


def _compute_symbol_volatility(data: Dict, period: int = 14) -> Optional[VolatilityResult]:
    """
    计算单个品种的波动性指标

    Args:
        data: 品种数据字典，包含 opens, highs, lows, closes, volumes
        period: ATR 计算周期

    Returns:
        VolatilityResult 或 None（数据不足时）
    """
    closes = data.get('closes', [])
    highs = data.get('highs', [])
    lows = data.get('lows', [])
    opens = data.get('opens', [])
    volumes = data.get('volumes', [])

    if len(closes) < 2:
        return None

    symbol = data.get('symbol', '')
    name = FUTURES_CONFIG.get(symbol, {}).get('name', symbol)
    contract_size = FUTURES_CONFIG.get(symbol, {}).get('contract_size', 10)

    # 在最后一个有效索引处计算 ATR
    idx = len(closes) - 1
    current_atr = atr(opens, highs, lows, closes, idx, period)

    # 日均波动金额 = ATR × contract_size
    daily_vol_amount = current_atr * contract_size

    # 波动率 = ATR / closes[-1] × 100%
    volatility_rate = (current_atr / closes[-1]) * 100 if closes[-1] > 0 else 0

    # 最近 20 日平均成交量
    avg_volume = int(sum(volumes[-20:]) / len(volumes[-20:])) if len(volumes) >= 20 else int(sum(volumes) / len(volumes))

    return VolatilityResult(
        symbol=symbol,
        name=name,
        atr=current_atr,
        daily_vol_amount=daily_vol_amount,
        volatility_rate=volatility_rate,
        avg_volume=avg_volume
    )


def select_top_symbols(
    symbols: Optional[List[str]] = None,
    days: int = 60,
    top_n: int = 10,
    min_vol_rate: float = 0.015,
    max_vol_rate: float = 0.04,
    min_volume: int = 10000,
    period: int = 14
) -> List[VolatilityResult]:
    """
    基于波动性筛选品种

    Args:
        symbols: 品种列表，None 时获取全部品种
        days: 历史数据天数
        top_n: 返回最多 top_n 个结果
        min_vol_rate: 最小波动率（过滤过低波动品种）
        max_vol_rate: 最大波动率（过滤过高波动品种）
        min_volume: 最小平均成交量
        period: ATR 计算周期

    Returns:
        按波动率降序排列的 VolatilityResult 列表
    """
    # 获取多品种数据
    multi_data = fetch_multi_futures_data(symbols, days)

    results = []
    for symbol, data in multi_data.items():
        try:
            vol_result = _compute_symbol_volatility(data, period)
            if vol_result is None:
                print(f"警告: 品种 {symbol} 数据不足，已跳过")
                continue

            # 过滤波动率范围和成交量
            if not (min_vol_rate <= vol_result.volatility_rate <= max_vol_rate):
                continue
            if vol_result.avg_volume < min_volume:
                continue

            results.append(vol_result)
        except Exception as e:
            print(f"警告: 品种 {symbol} 计算失败: {e}，已跳过")
            continue

    # 按波动率降序排序
    results.sort(key=lambda x: x.volatility_rate, reverse=True)

    return results[:top_n]


def get_volatility_report(
    symbols: Optional[List[str]] = None,
    days: int = 60,
    top_n: int = 20
) -> str:
    """
    生成波动性筛选报告

    Args:
        symbols: 品种列表，None 时获取全部品种
        days: 历史数据天数
        top_n: 显示最多 top_n 个品种

    Returns:
        格式化的表格字符串
    """
    results = select_top_symbols(
        symbols=symbols,
        days=days,
        top_n=top_n,
        min_vol_rate=0.0,  # 不过滤
        max_vol_rate=1.0,  # 不过滤
        min_volume=0       # 不过滤
    )

    if not results:
        return "无品种数据"

    # 表头
    header = f"{'Rank':<6}{'Symbol':<8}{'Name':<10}{'Volatility%':<14}{'DailyVolAmt':<14}{'AvgVolume':<12}"
    lines = [header, "-" * 64]

    for i, r in enumerate(results, 1):
        line = f"{i:<6}{r.symbol:<8}{r.name:<10}{r.volatility_rate:<14.3f}{r.daily_vol_amount:<14.2f}{r.avg_volume:<12}"
        lines.append(line)

    return "\n".join(lines)
