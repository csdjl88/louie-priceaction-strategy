"""
data_fetcher.py - 多品种期货数据获取和缓存模块
==============================================

支持:
1. Sina 期货历史日线数据 (通过 curl)
2. Sina 期货实时盘中行情 (通过 curl) - fetch_realtime_quote()
3. 模拟数据（网络不可用时）

使用方法:
    from data_fetcher import get_all_futures_symbols, fetch_futures_data, fetch_multi_futures_data

    # 获取所有品种
    symbols = get_all_futures_symbols()

    # 单品种获取
    data = fetch_futures_data('rb', days=300)

    # 批量获取
    multi_data = fetch_multi_futures_data(symbols=['rb', 'cu', 'au'], days=300)

    # 实时行情（盘中）
    from data_fetcher import fetch_realtime_quote
    q = fetch_realtime_quote('ru')
    print(q['last_price'], q['change_pct'])
"""

import json
import random
import re
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional

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

    # 尝试使用 Sina API
    data = _fetch_sina_futures(symbol, days)
    if data is not None:
        return data

    # 回退到模拟数据
    return _generate_simulated_data(symbol, days)


def _fetch_sina_futures(symbol: str, days: int = 300) -> Optional[Dict]:
    """使用 Sina API 获取期货数据（通过 curl）
    
    由于 AkShare 的 Sina 接口失效，改为直接用 curl 调用 Sina API
    """
    try:
        # 使用 curl 获取数据
        symbol_upper = symbol.upper()
        if not symbol_upper.endswith('0'):
            # 主力合约需要加 0 后缀
            symbol_upper = symbol_upper + '0'
            
        cmd = [
            'curl', '-s',
            f'https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_{symbol_upper}=/InnerFuturesNewService.getDailyKLine',
            '--data', f'symbol={symbol_upper}&type=2025_04_03'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        text = result.stdout.strip()
        
        if not text or 'var' not in text:
            return None
        
        # 解析 JSON: var _SYMBOL=([...]); 
        match = re.search(r'var \w+=\(\[.*\]\);', text)
        if not match:
            return None
        
        # 提取 JSON 数组
        json_str = match.group(0)
        # 去掉 var SYMBOL=( 和最后的 ); 
        json_str = json_str.split('=(')[1][:-2]
        
        data = json.loads(json_str)
        
        if not data:
            return None
        
        # 只取最后 N 天
        if len(data) > days:
            data = data[-days:]
        
        # 转换为标准格式
        dates = [d['d'] for d in data]
        opens = [float(d['o']) for d in data]
        highs = [float(d['h']) for d in data]
        lows = [float(d['l']) for d in data]
        closes = [float(d['c']) for d in data]
        volumes = [int(d['v']) for d in data]
        
        return {
            'symbol': symbol,
            'dates': dates,
            'opens': opens,
            'highs': highs,
            'lows': lows,
            'closes': closes,
            'volumes': volumes,
        }
        
    except Exception as e:
        print(f"获取 {symbol} 数据失败: {e}")
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


def fetch_realtime_quote(symbol: str) -> Optional[Dict]:
    """
    获取期货实时盘中行情（新浪财经）

    Args:
        symbol: 品种代码，如 'ru', 'rb', 'cu', 'au' 等

    Returns:
        包含实时行情的字典，失败返回 None
        格式:
        {
            'symbol': str,       # 品种代码
            'name': str,         # 合约名称
            'datetime': str,     # 更新时间
            'open': float,       # 开盘价
            'high': float,       # 最高价
            'low': float,        # 最低价
            'last_price': float, # 最新价
            'settlement': float,# 结算价
            'prev_close': float, # 昨收盘
            'prev_settlement': float, # 昨结算
            'volume': int,       # 成交量
            'open_interest': int, # 持仓量
            'bid': List[dict],   # 买五档 [{price, volume}, ...]
            'ask': List[dict],   # 卖五档 [{price, volume}, ...]
            'change': float,    # 涨跌额（相对昨结算）
            'change_pct': float, # 涨跌幅（%）
        }
    """
    try:
        code = f'nf_{symbol.upper()}0'
        cmd = [
            'curl', '-s', '--max-time', '5',
            '-H', 'Referer: https://finance.sina.com.cn',
            '-H', 'User-Agent: Mozilla/5.0',
            f'https://hq.sinajs.cn/rn=10&list={code}'
        ]
        result = subprocess.run(cmd, capture_output=True)
        text = result.stdout.decode('gbk', errors='replace').strip()

        if not text:
            return None

        match = re.search(r'hq_str_\w+="([^"]+)"', text)
        if not match or len(match.group(1)) < 10:
            return None

        f = match.group(1).split(',')
        n = len(f)

        if n < 15:
            return None

        last = float(f[8]) if f[8] and f[8] not in ('', '0') else 0
        prev = float(f[10]) if f[10] and f[10] not in ('', '0') else 0
        vol = int(float(f[13])) if f[13] and f[13] not in ('', '0') else 0

        # 5档买卖盘：从字段28开始，买盘10字段，卖盘10字段
        bids, asks = [], []
        start = 28
        for i in range(5):
            bp = float(f[start + i*2]) if n > start + i*2 and f[start + i*2] not in ('', '0') else 0
            bv = int(float(f[start + i*2 + 1])) if n > start + i*2 + 1 and f[start + i*2 + 1] not in ('', '0') else 0
            ap = float(f[start + 10 + i*2]) if n > start + 10 + i*2 and f[start + 10 + i*2] not in ('', '0') else 0
            av = int(float(f[start + 10 + i*2 + 1])) if n > start + 10 + i*2 + 1 and f[start + 10 + i*2 + 1] not in ('', '0') else 0
            bids.append({'price': bp, 'volume': bv})
            asks.append({'price': ap, 'volume': av})

        # 日期时间
        dt = f[17] if n > 17 and '-' in str(f[17]) else ''
        tm = f[1] if n > 1 else ''
        if len(tm) >= 6:
            dt_str = f'{dt} {tm[:2]}:{tm[2:4]}:{tm[4:6]}'
        else:
            dt_str = f'{dt} {tm}'

        return {
            'symbol': symbol.upper(),
            'name': f[0],
            'datetime': dt_str,
            'open': float(f[2]) if f[2] else 0,
            'high': float(f[3]) if f[3] else 0,
            'low': float(f[4]) if f[4] else 0,
            'last_price': last,
            'settlement': float(f[6]) if f[6] else 0,
            'prev_close': float(f[7]) if f[7] else 0,
            'prev_settlement': prev,
            'volume': vol,
            'open_interest': int(float(f[9])) if n > 9 and f[9] and f[9] not in ('0', '') else 0,
            'bid': bids,
            'ask': asks,
            'change': round(last - prev, 2) if last and prev else 0,
            'change_pct': round((last - prev) / prev * 100, 2) if prev else 0,
        }

    except Exception as e:
        print(f"获取 {symbol} 实时行情失败: {e}")
        return None


def fetch_multi_realtime_quotes(symbols: List[str]) -> Dict[str, Dict]:
    """
    批量获取多个期货品种的实时行情

    Args:
        symbols: 品种代码列表，如 ['ru', 'rb', 'cu']

    Returns:
        {symbol: quote_dict} 的字典，失败条目被跳过
    """
    result = {}
    for symbol in symbols:
        try:
            q = fetch_realtime_quote(symbol)
            if q is not None:
                result[symbol.lower()] = q
        except Exception:
            continue
    return result