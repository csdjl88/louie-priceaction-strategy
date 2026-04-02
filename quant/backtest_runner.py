"""
backtest_runner.py - 期货策略回测运行器 (AkShare版)
=====================================================

支持数据源:
1. AkShare 东方财富期货数据（真实数据）
2. CSV文件导入
3. 模拟数据（演示用）

使用方法:
    # 螺纹钢真实数据回测
    python3 backtest_runner.py --symbol rb --source akshare
    
    # 模拟数据回测
    python3 backtest_runner.py --symbol rb --source simulate
"""

import csv
import json
import random
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    print("AkShare 未安装，将使用模拟数据")

from china_futures_strategy import ChinaFuturesStrategy


def fetch_akshare_futures(symbol: str, days: int = 300) -> Optional[Dict]:
    """
    使用 AkShare 获取期货数据
    
    Args:
        symbol: 品种代码 (rb, hc, i, j, cu, al, zn, ni, ru, ma, ta, au, ag, sc 等)
        days: 获取天数
    
    Returns:
        包含 OHLCV 数据的字典
    """
    if not AKSHARE_AVAILABLE:
        return None
    
    # AkShare 期货品种映射
    symbol_map = {
        'rb': 'rb',   # 螺纹钢
        'hc': 'hc',   # 热轧卷板
        'i': 'i',     # 铁矿石
        'j': 'j',     # 焦炭
        'jm': 'jm',   # 焦煤
        'cu': 'cu',   # 铜
        'al': 'al',   # 铝
        'zn': 'zn',   # 锌
        'ni': 'ni',   # 镍
        'ru': 'ru',   # 橡胶
        'bu': 'bu',   # 沥青
        'ma': 'ma',   # 甲醇
        'ta': 'ta',   # PTA
        'm': 'm',     # 豆粕
        'y': 'y',     # 豆油
        'p': 'p',     # 棕榈油
        'c': 'c',     # 玉米
        'cf': 'cf',   # 棉花
        'sr': 'sr',   # 白糖
        'au': 'au',   # 黄金
        'ag': 'ag',   # 白银
        'sc': 'sc',   # 原油
    }
    
    akshare_symbol = symbol_map.get(symbol.lower())
    if not akshare_symbol:
        print(f"不支持的品种: {symbol}")
        return None
    
    try:
        print(f"从 AkShare 获取 {symbol.upper()} 数据...")
        
        # 获取期货日线数据
        # 注意：AkShare 的期货数据接口可能因版本而异
        df = ak.futures_zh_daily_sina(symbol=akshare_symbol)
        
        if df is None or df.empty:
            print(f"未获取到 {symbol.upper()} 数据")
            return None
        
        # 数据格式调整
        df = df.iloc[::-1].tail(days)  # 反转并只取最后 N 天（按时间正序）
        
        # date 是索引，不是列
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
        
    except Exception as e:
        print(f"AkShare 获取失败: {e}")
        # 尝试备用接口
        try:
            print("尝试备用接口...")
            df = ak.futures_zh_daily_sina(symbol=akshare_symbol, adjust="qfq")
            if df is not None and not df.empty:
                df = df.tail(days)
                return {
                    'symbol': symbol,
                    'dates': [str(d) for d in df.index],
                    'opens': df['open'].tolist(),
                    'highs': df['high'].tolist(),
                    'lows': df['low'].tolist(),
                    'closes': df['close'].tolist(),
                    'volumes': df['volume'].tolist(),
                }
        except Exception as e2:
            print(f"备用接口也失败: {e2}")
        return None


def generate_simulated_data(symbol: str, days: int = 300) -> Dict:
    """生成模拟期货数据（几何布朗运动）"""
    print(f"生成 {symbol.upper()} 模拟数据 ({days} 天)...")
    
    base_prices = {
        'rb': 4500, 'hc': 4300, 'i': 900, 'j': 2500, 'jm': 1400,
        'cu': 68000, 'al': 18000, 'zn': 22000, 'ni': 130000,
        'ru': 14000, 'ma': 2500, 'ta': 4500, 'au': 400, 'ag': 5500, 'sc': 450,
    }
    
    base_price = base_prices.get(symbol.lower(), 5000)
    volatility = base_price * 0.02
    prices = [base_price]
    trend = 0
    
    for _ in range(days - 1):
        if random.random() < 0.1:
            trend = random.uniform(-0.5, 0.5) * volatility
        daily_return = trend / base_price + random.gauss(0, volatility / base_price)
        new_price = prices[-1] * (1 + daily_return)
        prices.append(max(new_price, base_price * 0.5))
    
    opens, highs, lows, closes, volumes = [], [], [], [], []
    dates = []
    start_date = datetime(2024, 1, 1)
    
    for i, close_price in enumerate(prices):
        date = start_date + timedelta(days=i)
        if date.weekday() >= 5:
            continue
        
        dates.append(date.strftime('%Y-%m-%d'))
        open_price = close_price * random.uniform(0.98, 1.02)
        high_price = max(open_price, close_price) * random.uniform(1.0, 1.02)
        low_price = min(open_price, close_price) * random.uniform(0.98, 1.0)
        
        opens.append(round(open_price, 2))
        highs.append(round(high_price, 2))
        lows.append(round(low_price, 2))
        closes.append(round(close_price, 2))
        volumes.append(int(random.uniform(50000, 200000)))
    
    return {'symbol': symbol, 'dates': dates, 'opens': opens, 'highs': highs, 'lows': lows, 'closes': closes, 'volumes': volumes}


def load_csv_data(file_path: str) -> Optional[Dict]:
    """从CSV文件加载数据"""
    try:
        dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                dates.append(row.get('date', row.get('Date', '')))
                opens.append(float(row.get('open', row.get('Open', 0))))
                highs.append(float(row.get('high', row.get('High', 0))))
                lows.append(float(row.get('low', row.get('Low', 0))))
                closes.append(float(row.get('close', row.get('Close', 0))))
                volumes.append(int(row.get('volume', row.get('Volume', 0))))
        
        if len(dates) < 50:
            print(f"数据太少 ({len(dates)} 行)，至少需要50条")
            return None
            
        return {'dates': dates, 'opens': opens, 'highs': highs, 'lows': lows, 'closes': closes, 'volumes': volumes}
    except Exception as e:
        print(f"加载CSV失败: {e}")
        return None


def run_backtest(data: Dict, symbol: str, initial_capital: float = 100000,
                  risk_percent: float = 0.01, atr_stop: float = 2.0, atr_target: float = 6.0) -> Dict:
    """运行回测"""
    print(f"\n{'='*60}")
    print(f"  {symbol.upper()} 期货策略回测")
    print(f"{'='*60}")
    
    # 使用传入的参数
    strategy = ChinaFuturesStrategy(symbol=symbol, risk_percent=risk_percent,
                                     atr_stop=atr_stop, atr_target=atr_target)
    
    dates, opens, highs, lows, closes = data['dates'], data['opens'], data['highs'], data['lows'], data['closes']
    
    trades, equity_curve = [], [initial_capital]
    current_capital, position, entry_price = initial_capital, 0, 0
    
    print(f"\n数据范围: {dates[0]} ~ {dates[-1]}")
    print(f"数据条数: {len(dates)} 根K线")
    print(f"初始资金: {initial_capital:,.2f}\n")
    print("开始回测...\n")
    
    for i in range(30, len(dates)):
        result = strategy.analyze(opens, highs, lows, closes, i)
        action = result.get('action', '')
        # 兼容 signal 和 action 两种返回格式
        signal_map = {'long': 1, 'short': -1}
        signal = result.get('signal', signal_map.get(action, 0))
        trend, atr = result.get('trend', 'unknown'), result.get('atr', 0)
        
        # 入场
        if (signal == 1 or action == 'long') and position == 0:
            if atr > 0:
                position_size = int((current_capital * risk_percent) / (atr * atr_stop * 10))
                position = position_size
                entry_price = closes[i]
                trades.append({
                    'date': dates[i], 'type': 'LONG', 'entry_price': entry_price,
                    'position': position, 'stop_loss': atr * atr_stop,
                    'reason': f"{trend} trend, signal={signal}"
                })
        
        # 出场
        elif position > 0:
            pnl = (closes[i] - entry_price) * position * 10
            should_stop, reason = False, ""
            
            if closes[i] < entry_price - atr * atr_stop:
                should_stop, reason = True, "ATR Stop Loss"
            elif closes[i] > entry_price + atr * atr_target:
                should_stop, reason = True, "Take Profit"
            elif signal == -1 or action == 'short':
                should_stop, reason = True, "Short Signal"
            
            if should_stop:
                current_capital += pnl
                trades[-1].update({'exit_price': closes[i], 'pnl': pnl, 'exit_reason': reason})
                position, entry_price = 0, 0
        
        equity_curve.append(current_capital)
    
    # 平仓
    if position > 0:
        pnl = (closes[-1] - entry_price) * position * 10
        current_capital += pnl
        trades[-1].update({'exit_price': closes[-1], 'pnl': pnl, 'exit_reason': 'End of Backtest'})
    
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
        drawdown = (peak - equity) / peak * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    # 输出结果
    print(f"\n{'='*60}")
    print(f"  回测结果")
    print(f"{'='*60}")
    print(f"\n📊 交易统计:")
    print(f"   总交易次数: {total_trades}")
    print(f"   盈利交易: {len(winning_trades)} ({len(winning_trades)/total_trades*100:.1f}%)" if total_trades > 0 else "   盈利交易: 0")
    print(f"   亏损交易: {len(losing_trades)}")
    print(f"\n💰 收益统计:")
    print(f"   初始资金: {initial_capital:,.2f}")
    print(f"   最终资金: {current_capital:,.2f}")
    print(f"   总收益: {total_pnl:,.2f} ({total_return:.2f}%)")
    print(f"   最大回撤: {max_drawdown:.2f}%")
    
    if winning_trades:
        avg_win = sum(t['pnl'] for t in winning_trades) / len(winning_trades)
        avg_loss = sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
        print(f"\n📈 盈亏分析:")
        print(f"   平均盈利: {avg_win:,.2f}")
        print(f"   平均亏损: {avg_loss:,.2f}")
        print(f"   盈亏比: {abs(avg_win/avg_loss):.2f}" if avg_loss != 0 else "   盈亏比: N/A")
    
    print(f"\n📋 交易明细 (前10笔):")
    print("-" * 60)
    for i, trade in enumerate(trades[:10], 1):
        pnl_str = f"{trade.get('pnl', 0):+,.2f}"
        print(f"  {i}. {trade['date']} | {trade['type']} @ {trade['entry_price']:.2f}", end="")
        if 'exit_price' in trade:
            print(f" → {trade['exit_price']:.2f} | {trade.get('exit_reason', '')} | PnL: {pnl_str}")
        else:
            print(f" → (持仓中)")
    
    if len(trades) > 10:
        print(f"  ... 还有 {len(trades) - 10} 笔交易")
    print(f"\n{'='*60}")
    
    return {
        'symbol': symbol, 'total_trades': total_trades, 'winning_trades': len(winning_trades),
        'losing_trades': len(losing_trades), 'win_rate': win_rate,
        'initial_capital': initial_capital, 'final_capital': current_capital,
        'total_pnl': total_pnl, 'total_return': total_return,
        'max_drawdown': max_drawdown, 'equity_curve': equity_curve, 'trades': trades
    }


def main():
    parser = argparse.ArgumentParser(description='期货策略回测运行器')
    parser.add_argument('--symbol', '-s', default='rb', help='品种代码 (默认: rb)')
    parser.add_argument('--source', '-d', choices=['akshare', 'csv', 'simulate'], default='akshare',
                       help='数据源: akshare=真实数据, csv=CSV文件, simulate=模拟数据')
    parser.add_argument('--file', '-f', default='data.csv', help='CSV文件路径')
    parser.add_argument('--days', '-n', type=int, default=300, help='数据天数')
    parser.add_argument('--capital', '-c', type=float, default=100000, help='初始资金')
    
    args = parser.parse_args()
    
    # 获取数据
    if args.source == 'akshare':
        data = fetch_akshare_futures(args.symbol, args.days)
        if not data:
            print("AkShare 获取失败，自动切换为模拟数据")
            data = generate_simulated_data(args.symbol, args.days)
    elif args.source == 'csv':
        data = load_csv_data(args.file)
        if not data:
            print("CSV加载失败，退出")
            return
    else:
        data = generate_simulated_data(args.symbol, args.days)
    
    result = run_backtest(data, args.symbol, args.capital)
    
    # 保存结果
    result_file = f"backtest_result_{args.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump({
            'summary': {k: v for k, v in result.items() if k not in ['equity_curve', 'trades']},
            'trade_count': len(result['trades']),
            'trades': result['trades'][:50]
        }, f, indent=2, ensure_ascii=False)
    print(f"\n结果已保存: {result_file}")


if __name__ == '__main__':
    main()
