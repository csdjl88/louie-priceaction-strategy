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
    from akshare.futures.futures_zh_sina import futures_zh_daily_sina
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
               也可以用带后缀的如 RB0, RU0, NR0, BR0 等获取主力合约
        days: 获取天数
    
    Returns:
        包含 OHLCV 数据的字典
    """
    if not AKSHARE_AVAILABLE:
        return None
    
    try:
        print(f"从 AkShare 获取 {symbol.upper()} 数据...")
        
        # 直接传入品种代码获取数据
        df = futures_zh_daily_sina(symbol=symbol)
        
        if df is None or df.empty:
            print(f"未获取到 {symbol.upper()} 数据，尝试备用方式")
            return None
        
        # 检查是否有 date 列
        if 'date' in df.columns:
            dates = df['date'].tolist()
        else:
            # 索引就是日期
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
        
    except Exception as e:
        print(f"AkShare 获取失败: {e}")
        import traceback
        traceback.print_exc()
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
                  risk_percent: float = 0.05, atr_stop: float = 1.5, atr_target: float = 8.0,
                  trading_mode: str = "swing", atr_period: int = 10, sma_period: int = 30,
                  commission: float = None, slippage: float = 0.0005,
                  use_vol_filter: bool = True,
                  vol_threshold: float = 0.5) -> Dict:
    """运行回测
    
    Args:
        trading_mode: 交易模式，"intraday"=日内平仓，"swing"=波段持仓
        atr_period: ATR周期
        sma_period: 均线周期
        commission: 手续费比例 (None=使用品种默认配置)
        slippage: 滑点比例 (默认万分之5)
    """
    # 获取品种配置
    from china_futures_strategy import FUTURES_CONFIG
    # 尝试多种匹配方式
    symbol_lower = symbol.lower()
    config = FUTURES_CONFIG.get(symbol_lower)  # 如 RB0, RU0
    if config is None:
        config = FUTURES_CONFIG.get(symbol_lower.replace('0', ''))  # 如 rb, ru
    if config is None:
        config = FUTURES_CONFIG.get(symbol_lower + '0')  # 如 rb0 -> rb0
    if config is None:
        config = {}  # 默认配置
    
    # 确定手续费
    if commission is None:
        if config.get('commission_type') == 'fixed':
            # 固定手续费（如黄金20元/手）
            commission_rate = config.get('commission', 20)
            commission_type = 'fixed'
        else:
            # 按比例收费（默认万1）
            commission_rate = config.get('commission', 0.0001)
            commission_type = 'ratio'
    else:
        commission_rate = commission
        commission_type = 'ratio'
    
    contract_size = config.get('contract_size', 10)
    
    print(f"\n{'='*60}")
    print(f"  {symbol.upper()} 期货策略回测")
    print(f"  参数: ATR={atr_period}, SMA={sma_period}, {trading_mode}模式")
    if commission_type == 'fixed':
        print(f"  成本: 手续费={commission_rate}元/手, 滑点={slippage*10000:.1f}‰")
    else:
        print(f"  成本: 手续费={commission_rate*10000:.2f}‰, 滑点={slippage*10000:.1f}‰")
    print(f"{'='*60}")
    
    # 增大默认仓位到5%以确保能开仓（1%对螺纹钢等品种会导致仓位为0）
    effective_risk = max(risk_percent, 0.05)
    strategy = ChinaFuturesStrategy(
        symbol=symbol, 
        risk_percent=effective_risk,
        atr_period=atr_period,
        sma_period=sma_period,
        atr_stop=atr_stop, 
        atr_target=atr_target,
        trading_mode=trading_mode,
        use_vol_filter=use_vol_filter,
        vol_threshold=vol_threshold,
    )
    
    dates, opens, highs, lows, closes = data['dates'], data['opens'], data['highs'], data['lows'], data['closes']
    volumes = data.get('volumes', [None] * len(dates))

    # 成交量过滤器：入场要求今日成交量 > vol_threshold × 60日均量
    vol_avg = sum(volumes[-60:]) / min(60, len([v for v in volumes[-60:] if v])) if volumes and any(v and v > 0 for v in volumes[-60:]) else None
    if use_vol_filter and vol_avg and vol_avg > 0:
        vol_note = f"成交量过滤>×{vol_threshold}均量"
    else:
        vol_note = "成交量过滤关闭"
    print(f"  {vol_note}，阈值={vol_avg*vol_threshold:,.0f}" if vol_avg else "")

    # 提取日期部分用于日内判断
    date_only = [d.split()[0] if ' ' in str(d) else str(d) for d in dates]
    
    trades, equity_curve = [], [initial_capital]
    current_capital, position, entry_price = initial_capital, 0, 0
    entry_date = None  # 记录入场日期，用于判断是否跨日
    
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
        
        # 入场 - 支持做多和做空
        # 成交量过滤：要求今日成交量 > vol_threshold × 60日均量
        vol_ok = (not use_vol_filter) or (vol_avg is None) or (not volumes or not volumes[i] or volumes[i] >= vol_avg * vol_threshold)
        if position == 0 and atr > 0 and vol_ok:
            position_size = int((current_capital * effective_risk) / (atr * atr_stop * 10))
            if position_size <= 0:
                position_size = 1  # 最小仓位
            
            # 计算手续费函数
            def calc_commission(price, size):
                if commission_type == 'fixed':
                    return commission_rate * abs(size)  # 固定手续费 × 手数
                else:
                    return price * abs(size) * contract_size * commission_rate
            
            # 记录入场日期
            current_date = date_only[i] if i < len(date_only) else str(dates[i])
            
            # 做多 - 考虑滑点（滑点会增加入场成本）
            if signal == 1 or action == 'long':
                entry_price = closes[i] * (1 + slippage)  # 滑点让入场价更高
                position = position_size
                entry_date = current_date  # 记录入场日期
                # 入场时扣除手续费
                entry_commission = calc_commission(entry_price, position)
                current_capital -= entry_commission
                trades.append({
                    'date': dates[i], 'type': 'LONG', 'entry_price': entry_price,
                    'position': position, 'stop_loss': atr * atr_stop,
                    'commission': entry_commission,
                    'entry_date': entry_date,
                    'reason': f"{trend} trend, signal={signal}"
                })
            # 做空 - 考虑滑点
            elif signal == -1 or action == 'short':
                entry_price = closes[i] * (1 - slippage)  # 滑点让入场价更低
                position = -position_size
                entry_date = current_date  # 记录入场日期
                # 入场时扣除手续费
                entry_commission = calc_commission(entry_price, position)
                current_capital -= entry_commission
                trades.append({
                    'date': dates[i], 'type': 'SHORT', 'entry_price': entry_price,
                    'position': position, 'stop_loss': atr * atr_stop,
                    'commission': entry_commission,
                    'entry_date': entry_date,
                    'reason': f"{trend} trend, signal={signal}"
                })
        
        # 出场
        elif position != 0:
            # 多头出场
            if position > 0:
                pnl = (closes[i] - entry_price) * position * 10
                should_stop, reason = False, ""
                
                # 日内模式：检测是否需要强制平仓（同一天必须平仓）
                current_date = date_only[i] if i < len(date_only) else str(dates[i])
                force_close = False
                if trading_mode == 'intraday' and entry_date and current_date != entry_date:
                    force_close = True
                    reason = "Intraday Close (EOD)"
                
                if closes[i] < entry_price - atr * atr_stop:
                    should_stop, reason = True, "ATR Stop Loss"
                elif closes[i] > entry_price + atr * atr_target:
                    should_stop, reason = True, "Take Profit"
                elif force_close:
                    should_stop, reason = True, reason
                elif signal == -1 or action == 'short':
                    should_stop, reason = True, "Reverse to Short"
            # 空头出场
            else:
                pnl = (entry_price - closes[i]) * abs(position) * 10
                should_stop, reason = False, ""
                
                # 日内模式：检测是否需要强制平仓（同一天必须平仓）
                current_date = date_only[i] if i < len(date_only) else str(dates[i])
                force_close = False
                if trading_mode == 'intraday' and entry_date and current_date != entry_date:
                    force_close = True
                    reason = "Intraday Close (EOD)"
                
                if closes[i] > entry_price + atr * atr_stop:
                    should_stop, reason = True, "ATR Stop Loss"
                elif closes[i] < entry_price - atr * atr_target:
                    should_stop, reason = True, "Take Profit"
                elif force_close:
                    should_stop, reason = True, reason
                elif signal == 1 or action == 'long':
                    should_stop, reason = True, "Reverse to Long"
            
            if should_stop:
                # 出场时考虑滑点
                if position > 0:
                    exit_price = closes[i] * (1 - slippage)  # 滑点让出场价更低
                else:
                    exit_price = closes[i] * (1 + slippage)  # 滑点让出场价更高
                
                exit_date = date_only[i] if i < len(date_only) else str(dates[i])
                is_intraday = entry_date and exit_date == entry_date
                
                # 出场手续费
                exit_commission = calc_commission(exit_price, position)
                net_pnl = pnl - exit_commission
                
                current_capital += net_pnl
                trades[-1].update({
                    'exit_price': exit_price, 
                    'pnl': net_pnl, 
                    'exit_commission': exit_commission,
                    'exit_date': exit_date,
                    'intraday': is_intraday,
                    'exit_reason': reason
                })
                position, entry_price = 0, 0
                entry_date = None
        
        equity_curve.append(current_capital)
    
    # 平仓（最后持仓按收盘价平掉）
    if position > 0:
        exit_price = closes[-1] * (1 - slippage)
        pnl = (exit_price - entry_price) * position * 10
        exit_commission = calc_commission(exit_price, position)
        net_pnl = pnl - exit_commission
        current_capital += net_pnl
        trades[-1].update({'exit_price': exit_price, 'pnl': net_pnl, 'exit_commission': exit_commission, 'exit_reason': 'End of Backtest'})
    elif position < 0:
        exit_price = closes[-1] * (1 + slippage)
        pnl = (entry_price - exit_price) * abs(position) * 10
        exit_commission = calc_commission(exit_price, position)
        net_pnl = pnl - exit_commission
        current_capital += net_pnl
        trades[-1].update({'exit_price': exit_price, 'pnl': net_pnl, 'exit_commission': exit_commission, 'exit_reason': 'End of Backtest'})
    
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
    parser.add_argument('--mode', '-m', choices=['intraday', 'swing'], default='swing',
                        help='交易模式: intraday=日内平仓, swing=波段持仓')
    parser.add_argument('--atr-period', type=int, default=10, help='ATR周期（优化值：10）')
    parser.add_argument('--atr-stop', type=float, default=1.5, help='ATR止损倍数（优化值：1.5）')
    parser.add_argument('--atr-target', type=float, default=8.0, help='ATR止盈倍数（优化值：8.0）')
    parser.add_argument('--sma-period', type=int, default=30, help='均线周期（优化值：30）')
    parser.add_argument('--commission', type=float, default=None, help='手续费 (默认使用品种配置)')
    parser.add_argument('--slippage', type=float, default=0.0005, help='滑点比例 (默认万分之5)')
    parser.add_argument('--no-vol-filter', dest='use_vol_filter', action='store_false',
                       help='关闭成交量过滤（默认开启，成交量>0.5×60日均量）')
    parser.add_argument('--vol-threshold', type=float, default=0.5,
                       help='成交量过滤阈值（默认0.5，即>0.5×60日均量）')
    
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
    
    result = run_backtest(data, args.symbol, args.capital, 
                          atr_stop=args.atr_stop, atr_target=args.atr_target,
                          trading_mode=args.mode, 
                          atr_period=args.atr_period, sma_period=args.sma_period,
                          commission=args.commission, slippage=args.slippage,
                          use_vol_filter=args.use_vol_filter,
                          vol_threshold=args.vol_threshold)
    
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