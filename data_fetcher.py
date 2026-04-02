"""
data_fetcher.py - 多品种期货数据获取和缓存模块
==============================================

支持:
1. AkShare 东方财富期货数据（真实数据）
2. 模拟数据（网络不可用时）

使用方法:
    from data_fetcher import get_all_futures_symbols, fetch_futures_data, fetch_multi_futures_data

    # 获取所有品种
    symbols = get_all_futures_symbols()

    # 单品种获取
    data = fetch_futures_data('rb', days=300)

    # 批量获取
    multi_data = fetch_multi_futures_data(symbols=['rb', 'cu', 'au'], days=300)
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional

try:
    import akshare as ak
    from akshare.futures.futures_zh_sina import futures_zh_daily_sina
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False

from china_futures_strategy import FUTURES_CONFIG


def get_all_futures_symbols() -> List[str]:
    """
    获取所有支持的期货品种代码列表

    Returns:
        品种代码列表，如 ['rb', 'hc', 'i', 'j', ...]
    """
    return list(FUTURES_CONFIG.keys())


def fetch_futures_data(symbol: str, days: int = 300) -> Optional[Dict]:
    """
    获取单个期货品种的历史数据

    Args:
        symbol: 品种代码 (rb, hc, cu, al, au, ag, sc 等)
        days: 获取天数

    Returns:
        包含 OHLCV 数据的字典，失败时返回 None
        数据格式: {'symbol': str, 'dates': List[str], 'opens': List[float],
                   'highs': List[float], 'lows': List[float],
                   'closes': List[float], 'volumes': List[int]}
    """
    # 验证品种是否在配置中
    if symbol.lower() not in FUTURES_CONFIG:
        return None

    # 尝试使用 AkShare
    if AKSHARE_AVAILABLE:
        data = _fetch_akshare_futures(symbol, days)
        if data is not None:
            return data

    # 回退到模拟数据
    return _generate_simulated_data(symbol, days)


def _fetch_akshare_futures(symbol: str, days: int = 300) -> Optional[Dict]:
    """使用 AkShare 获取期货数据

    使用 2025 年 12 月合约来获取完整的 2025 年数据
    """
    if not AKSHARE_AVAILABLE:
        return None

    # 2025 年 12 月到期的合约映射，覆盖完整 2025 年
    _CONTRACT_2025 = {
        'rb': 'rb2512', 'hc': 'hc2512', 'i': 'i2512', 'j': 'j2512', 'jm': 'jm2512',
        'cu': 'cu2512', 'al': 'al2512', 'zn': 'zn2512', 'ni': 'ni2512', 'sn': 'sn2512',
        'ru': 'ru2512', 'bu': 'bu2512', 'ma': 'ma2512', 'ta': 'ta2512', 'pp': 'pp2512',
        'l': 'l2512', 'v': 'v2512', 'm': 'm2512', 'y': 'y2512', 'p': 'p2512',
        'cs': 'cs2512', 'c': 'c2512', 'a': 'a2512', 'b': 'b2512',
        'oi': 'oi2512', 'rm': 'rm2512', 'cf': 'cf2512', 'sr': 'sr2512',
        'au': 'au2512', 'ag': 'ag2512', 'sc': 'sc2512',
        't': 't2512', 'tf': 'tf2512',
    }

    # 获取合约代码
    contract = _CONTRACT_2025.get(symbol.lower())
    if not contract:
        # 尝试直接使用品种代码
        contract = symbol.lower()

    try:
        df = futures_zh_daily_sina(symbol=contract)

        if df is None or df.empty:
            return None

        # 处理日期列
        if 'date' in df.columns:
            dates = df['date'].tolist()
        else:
            dates = [str(d) for d in df.index]

        # 只取最后 N 天
        if len(dates) > days:
            df = df.tail(days)
            if 'date' in df.columns:
                dates = df['date'].tolist()
            else:
                dates = [str(d) for d in df.index]

        return {
            'symbol': symbol,
            'dates': dates,
            'opens': df['open'].tolist(),
            'highs': df['high'].tolist(),
            'lows': df['low'].tolist(),
            'closes': df['close'].tolist(),
            'volumes': df['volume'].tolist(),
        }

    except Exception:
        return None


def _generate_simulated_data(symbol: str, days: int = 300) -> Dict:
    """生成模拟期货数据（几何布朗运动）"""
    base_prices = {
        'rb': 4500, 'hc': 4300, 'i': 900, 'j': 2500, 'jm': 1400,
        'cu': 68000, 'al': 18000, 'zn': 22000, 'ni': 130000, 'sn': 180000,
        'ru': 14000, 'bu': 3500, 'ma': 2500, 'ta': 4500, 'pp': 8000, 'l': 8000, 'v': 6000,
        'm': 3200, 'y': 7500, 'p': 6500, 'cs': 2800, 'c': 2500, 'a': 5000, 'b': 4000,
        'oi': 8000, 'rm': 2800, 'cf': 15000, 'sr': 5500,
        'au': 400, 'ag': 5500, 'sc': 450,
        't': 100, 'tf': 100,
    }

    base_price = base_prices.get(symbol.lower(), 5000)
    daily_volatility = 0.003  # 0.3% daily volatility
    prices = [base_price]

    for _ in range(days - 1):
        daily_return = random.gauss(0, daily_volatility)
        new_price = prices[-1] * (1 + daily_return)
        prices.append(max(new_price, base_price * 0.5))

    opens, highs, lows, closes, volumes = [], [], [], [], []
    dates = []
    # 2025 年数据回测
    start_date = datetime(2025, 1, 1)

    for i, close_price in enumerate(prices):
        date = start_date + timedelta(days=i)
        if date.weekday() >= 5:
            continue

        # 生成 open/high/low 基于 close，使用 daily_volatility
        open_price = close_price * (1 + random.uniform(-daily_volatility, daily_volatility))
        high_price = max(open_price, close_price) * (1 + random.uniform(0, daily_volatility))
        low_price = min(open_price, close_price) * (1 - random.uniform(0, daily_volatility))

        dates.append(date.strftime('%Y-%m-%d'))
        opens.append(round(open_price, 2))
        highs.append(round(high_price, 2))
        lows.append(round(low_price, 2))
        closes.append(round(close_price, 2))
        volumes.append(int(random.uniform(50000, 200000)))

    return {'symbol': symbol, 'dates': dates, 'opens': opens, 'highs': highs, 'lows': lows, 'closes': closes, 'volumes': volumes}


def fetch_multi_futures_data(symbols: Optional[List[str]] = None, days: int = 300) -> Dict[str, Dict]:
    """
    批量获取多个期货品种的历史数据

    Args:
        symbols: 品种代码列表，None 时获取全部品种
        days: 获取天数

    Returns:
        {symbol: data_dict} 的字典
        单个品种失败时打印警告并跳过，不影响其他品种
    """
    if symbols is None:
        symbols = get_all_futures_symbols()

    result = {}
    for symbol in symbols:
        try:
            data = fetch_futures_data(symbol, days)
            if data is not None:
                result[symbol] = data
            else:
                print(f"警告: 无法获取品种 {symbol} 的数据，已跳过")
        except Exception as e:
            print(f"警告: 获取品种 {symbol} 失败: {e}，已跳过")
            continue

    return result


class FuturesDataCache:
    """
    内存缓存已获取的期货数据，避免重复请求
    """

    def __init__(self):
        self._cache: Dict[str, Dict] = {}

    def get(self, symbol: str, days: int) -> Optional[Dict]:
        """从缓存获取数据"""
        key = f"{symbol}_{days}"
        return self._cache.get(key)

    def set(self, symbol: str, days: int, data: Dict) -> None:
        """设置缓存数据"""
        key = f"{symbol}_{days}"
        self._cache[key] = data

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()


# 全局默认缓存实例
_default_cache = FuturesDataCache()


def get_cache() -> FuturesDataCache:
    """获取全局默认缓存实例"""
    return _default_cache
