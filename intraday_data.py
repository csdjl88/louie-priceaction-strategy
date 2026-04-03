"""
intraday_data.py - 分钟级数据获取
===============================

支持获取分钟级别的期货数据，用于区分日内和波段交易

使用方法:
    from intraday_data import fetch_minute_data, fetch_5min_data, fetch_15min_data
    
    # 获取5分钟数据
    data = fetch_5min_data('rb', days=30)
    
    # 获取15分钟数据
    data = fetch_15min_data('rb', days=30)
    
    # 获取日内数据（用于日内交易）
    data = fetch_intraday_data('rb', days=60, freq='5min')
"""

import json
import subprocess
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional


def fetch_minute_data(symbol: str, days: int = 30, freq: str = '5min') -> Optional[Dict]:
    """
    获取分钟级数据
    
    Args:
        symbol: 合约代码 (rb, cu, au 等)
        days: 获取天数
        freq: 频率 (1min, 5min, 15min, 30min, 60min)
    
    Returns:
        包含 OHLCV 的字典
    """
    try:
        # Sina 分钟数据 URL
        # 格式: https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_xxx=/InnerFuturesNewService.getMiniKLine
        symbol_upper = symbol.upper()
        if not symbol_upper.endswith('0'):
            symbol_upper = symbol_upper + '0'
        
        # 频率映射
        freq_map = {
            '1min': '60',
            '5min': '300',
            '15min': '900',
            '30min': '1800',
            '60min': '3600'
        }
        freq_param = freq_map.get(freq, '300')
        
        # 计算获取的数据点数（每天约240分钟，取足够数据）
        total_mins = days * 240
        
        cmd = [
            'curl', '-s',
            f'https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_{symbol_upper}=/InnerFuturesNewService.getMiniKLine',
            '--data', f'symbol={symbol_upper}&type={freq_param}'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        text = result.stdout.strip()
        
        if not text or 'var' not in text:
            return None
        
        # 解析 JSON
        match = re.search(r'var \w+=\(\[.*\]\);', text)
        if not match:
            return None
        
        json_str = match.group(0)
        json_str = json_str.split('=(')[1][:-2]
        
        data = json.loads(json_str)
        
        if not data:
            return None
        
        # 取最后 N 条数据
        if len(data) > total_mins:
            data = data[-total_mins:]
        
        # 转换格式
        dates = [d['d'] for d in data]
        times = [d['t'] for d in data]
        opens = [float(d['o']) for d in data]
        highs = [float(d['h']) for d in data]
        lows = [float(d['l']) for d in data]
        closes = [float(d['c']) for d in data]
        volumes = [int(d['v']) for d in data]
        
        return {
            'symbol': symbol,
            'dates': dates,
            'times': times,
            'opens': opens,
            'highs': highs,
            'lows': lows,
            'closes': closes,
            'volumes': volumes,
            'freq': freq
        }
        
    except Exception as e:
        print(f"获取 {symbol} {freq} 数据失败: {e}")
        return None


def fetch_5min_data(symbol: str, days: int = 30) -> Optional[Dict]:
    """获取5分钟K线数据"""
    return fetch_minute_data(symbol, days, '5min')


def fetch_15min_data(symbol: str, days: int = 30) -> Optional[Dict]:
    """获取15分钟K线数据"""
    return fetch_minute_data(symbol, days, '15min')


def fetch_60min_data(symbol: str, days: int = 60) -> Optional[Dict]:
    """获取60分钟K线数据"""
    return fetch_minute_data(symbol, days, '60min')


def fetch_intraday_data(symbol: str, days: int = 30, freq: str = '5min') -> Optional[Dict]:
    """
    获取日内交易数据
    
    Args:
        symbol: 合约代码
        days: 天数
        freq: K线频率
    
    Returns:
        分钟级数据
    """
    return fetch_minute_data(symbol, days, freq)


def get_trading_sessions(dates: List[str], times: List[str]) -> List[Dict]:
    """
    分割交易时段
    
    由于期货有夜盘，需要将数据按交易日分割
    
    Args:
        dates: 日期列表
        times: 时间列表
    
    Returns:
        交易时段列表
    """
    sessions = []
    current_session = []
    current_date = ''
    
    for i, (date, time) in enumerate(zip(dates, times)):
        # 夜盘21:00-02:30 属于第二天的交易
        hour = int(time.split(':')[0]) if time else 0
        
        if hour < 12:  # 夜盘或早盘
            # 新的交易日开始
            if current_session:
                sessions.append(current_session)
            current_session = [(date, time)]
            current_date = date
        else:
            current_session.append((date, time))
    
    if current_session:
        sessions.append(current_session)
    
    return sessions


# ==================== 修改后的回测支持 ====================

def prepare_intraday_backtest(symbol: str, freq: str = '5min', days: int = 60) -> Optional[Dict]:
    """
    准备日内交易回测数据
    
    自动区分:
    - 日内模式: 同一交易日开平仓
    - 波段模式: 跨交易日持仓
    
    Returns:
        包含日内/波段标记的数据
    """
    data = fetch_minute_data(symbol, days, freq)
    if not data:
        return None
    
    # 标记每个Bar属于哪个交易日
    trading_days = []
    current_day = None
    
    for date, time in zip(data['dates'], data['times']):
        hour = int(time.split(':')[0]) if time else 0
        
        # 夜盘(21:00-02:30) 属于下一个交易日
        if hour < 12:
            # 新的交易日
            trading_day = datetime.strptime(date, '%Y-%m-%d').date()
            if current_day and current_day != trading_day:
                # 新的一天
                pass
            current_day = trading_day
        else:
            # 日盘
            trading_day = datetime.strptime(date, '%Y-%m-%d').date()
        
        trading_days.append(str(trading_day))
    
    data['trading_days'] = trading_days
    
    return data


# CLI 测试
if __name__ == '__main__':
    import sys
    
    symbol = sys.argv[1] if len(sys.argv) > 1 else 'rb'
    freq = sys.argv[2] if len(sys.argv) > 2 else '5min'
    
    print(f"获取 {symbol} {freq} 数据...")
    data = fetch_minute_data(symbol, 5, freq)
    
    if data:
        print(f"✅ 成功获取 {len(data['dates'])} 条数据")
        print(f"日期范围: {data['dates'][0]} {data['times'][0]} ~ {data['dates'][-1]} {data['times'][-1]}")
        print(f"最新价: {data['closes'][-1]}")
    else:
        print(f"❌ 获取失败")