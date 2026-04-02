"""
backtest.py - 回测引擎
=====================
支持多种回测模式，输出详细的分析报告
"""

import json
from datetime import datetime
from .strategy import PriceActionStrategy
from .risk import RiskManager, TradeExecutor


class BacktestEngine:
    """
    回测引擎
    =======
    
    支持功能：
    - 顺序回测（每根K线后评估）
    - 事件驱动交易
    - 详细统计报告
    - 交易记录导出
    """
    
    def __init__(self, 
                 initial_balance=100000,
                 commission=0.0002,
                 slippage=0.0005,
                 risk_percent=0.02):
        """
        Args:
            initial_balance: 初始资金
            commission: 手续费比例
            slippage: 滑点比例
            risk_percent: 单笔风险比例
        """
        self.initial_balance = initial_balance
        self.commission = commission
        self.slippage = slippage
        self.risk_percent = risk_percent
        
        # 策略和风控
        self.strategy = PriceActionStrategy(risk_percent=risk_percent)
        self.risk_manager = RiskManager()
        self.executor = TradeExecutor(slippage=slippage, commission=commission)
        
        # 账户状态
        self.balance = initial_balance
        self.positions = []  # 当前持仓
        self.trades = []  # 历史交易记录
        self.equity_curve = []  # 权益曲线
        
        # 统计
        self.stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0,
            'max_drawdown': 0,
            'max_drawdown_pct': 0,
            'win_rate': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'profit_factor': 0,
            'sharpe_ratio': 0,
            'avg_holding_bars': 0
        }
    
    def reset(self):
        """重置回测状态"""
        self.balance = self.initial_balance
        self.positions = []
        self.trades = []
        self.equity_curve = []
        self.risk_manager = RiskManager()
        
        # 重置策略统计
        self.strategy.stats = {
            'total_signals': 0,
            'bullish_signals': 0,
            'bearish_signals': 0
        }
    
    def run(self, df, progress_callback=None):
        """
        运行回测
        
        Args:
            df: DataFrame，需包含 open, high, low, close 列
            progress_callback: 进度回调函数
        
        Returns:
            回测统计结果
        """
        self.reset()
        
        # 确保数据格式正确
        if isinstance(df, dict):
            opens = df.get('open', df.get('Open', []))
            highs = df.get('high', df.get('High', []))
            lows = df.get('low', df.get('Low', []))
            closes = df.get('close', df.get('Close', []))
            volumes = df.get('volume', df.get('Volume', [0]*len(closes)))
        else:
            # DataFrame格式
            opens = df['open'].tolist() if 'open' in df else df['Open'].tolist()
            highs = df['high'].tolist() if 'high' in df else df['High'].tolist()
            lows = df['low'].tolist() if 'low' in df else df['Low'].tolist()
            closes = df['close'].tolist() if 'close' in df else df['Close'].tolist()
            volumes = df.get('volume', [0]*len(closes)).tolist() if 'volume' in df else [0]*len(closes)
        
        n = len(closes)
        
        # 更新风控初始余额
        self.risk_manager.peak_balance = self.initial_balance
        
        # 主回测循环
        for idx in range(n):
            # 1. 更新权益曲线
            current_equity = self.balance + sum(
                (closes[idx] - p['entry_price']) * p['size'] for p in self.positions
            )
            self.equity_curve.append(current_equity)
            self.risk_manager.update_balance(current_equity)
            
            # 2. 分析市场并生成信号
            if idx >= 20:  # 需要足够的历史数据
                analysis = self.strategy.analyze(opens, highs, lows, closes, idx)
                
                # 3. 执行交易逻辑
                self._process_signals(analysis, opens, highs, lows, closes, idx)
            
            # 4. 更新持仓状态
            self._update_positions(closes[idx])
            
            # 5. 进度报告
            if progress_callback and idx % 100 == 0:
                progress_callback(idx / n * 100)
        
        # 计算最终统计
        self._calculate_stats()
        
        return self.stats
    
    def _process_signals(self, analysis, opens, highs, lows, closes, idx):
        """处理交易信号"""
        # 如果已有持仓，先检查是否需要止损/止盈
        if self.positions:
            self._check_exit_conditions(opens, highs, lows, closes, idx)
            if self.positions:  # 检查后可能已平仓
                return
        
        # 没有持仓时才考虑开仓
        direction = analysis['final_direction']
        
        if direction == 'neutral':
            return
        
        # 检查风控
        can_trade, reason = self.risk_manager.can_open_position(self.balance)
        if not can_trade:
            return
        
        # 获取交易参数
        entry = analysis['entry']
        stop_loss = analysis['stop_loss']
        take_profit = analysis['take_profit']
        risk_reward = analysis['risk_reward']
        
        if entry is None or stop_loss is None:
            return
        
        # 计算仓位
        position_sizer = self.positions and self.positions[0] if self.positions else None
        
        # 使用策略的仓位计算
        risk_amount = self.balance * self.risk_percent
        risk_per_unit = abs(entry - stop_loss)
        
        if risk_per_unit == 0:
            return
        
        size = risk_amount / risk_per_unit
        
        # 考虑手续费和滑点后的实际入场价
        if direction == 'bullish':
            actual_entry = entry * (1 + self.slippage)
            actual_cost = actual_entry * size * self.commission
        else:
            actual_entry = entry * (1 - self.slippage)
            actual_cost = actual_entry * size * self.commission
        
        # 扣除手续费
        if self.balance < actual_cost:
            return
        
        self.balance -= actual_cost
        
        # 开仓
        position = {
            'direction': direction,
            'entry_price': actual_entry,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'size': size,
            'entry_idx': idx,
            'entry_time': idx,  # 用索引代替时间
            'risk_reward': risk_reward,
            'patterns': analysis.get('patterns', []),
            'trend': analysis.get('trend'),
            'pnl_realized': 0,
            'pnl_unrealized': 0
        }
        
        self.positions.append(position)
    
    def _check_exit_conditions(self, opens, highs, lows, closes, idx):
        """检查持仓是否需要止损或止盈"""
        current_price = closes[idx]
        to_close = []
        
        for i, pos in enumerate(self.positions):
            direction = pos['direction']
            entry = pos['entry_price']
            stop_loss = pos['stop_loss']
            take_profit = pos['take_profit']
            size = pos['size']
            
            should_close = False
            exit_reason = None
            exit_price = current_price
            
            # 止损检查
            if direction == 'bullish' and current_price <= stop_loss:
                should_close = True
                exit_reason = 'stop_loss'
                exit_price = stop_loss * (1 - self.slippage)  # 考虑滑点
            elif direction == 'bearish' and current_price >= stop_loss:
                should_close = True
                exit_reason = 'stop_loss'
                exit_price = stop_loss * (1 + self.slippage)
            
            # 止盈检查
            if not should_close:
                if direction == 'bullish' and current_price >= take_profit:
                    should_close = True
                    exit_reason = 'take_profit'
                    exit_price = take_profit * (1 - self.slippage)
                elif direction == 'bearish' and current_price <= take_profit:
                    should_close = True
                    exit_reason = 'take_profit'
                    exit_price = take_profit * (1 + self.slippage)
            
            if should_close:
                # 计算盈亏
                if direction == 'bullish':
                    pnl = (exit_price - entry) * size
                else:
                    pnl = (entry - exit_price) * size
                
                # 扣除手续费
                commission = exit_price * size * self.commission
                net_pnl = pnl - commission
                
                # 记录交易
                trade = {
                    'entry_idx': pos['entry_idx'],
                    'exit_idx': idx,
                    'direction': direction,
                    'entry_price': entry,
                    'exit_price': exit_price,
                    'size': size,
                    'pnl': net_pnl,
                    'exit_reason': exit_reason,
                    'holding_bars': idx - pos['entry_idx'],
                    'patterns': pos.get('patterns', []),
                    'trend': pos.get('trend'),
                    'risk_reward': pos.get('risk_reward')
                }
                
                self.trades.append(trade)
                self.balance += net_pnl
                to_close.append(i)
        
        # 平仓
        for i in reversed(to_close):
            self.positions.pop(i)
    
    def _update_positions(self, current_price):
        """更新持仓的未实现盈亏"""
        for pos in self.positions:
            if pos['direction'] == 'bullish':
                pos['pnl_unrealized'] = (current_price - pos['entry_price']) * pos['size']
            else:
                pos['pnl_unrealized'] = (pos['entry_price'] - current_price) * pos['size']
    
    def _calculate_stats(self):
        """计算回测统计"""
        if not self.trades:
            return
        
        total_trades = len(self.trades)
        winning_trades = [t for t in self.trades if t['pnl'] > 0]
        losing_trades = [t for t in self.trades if t['pnl'] <= 0]
        
        total_pnl = sum(t['pnl'] for t in self.trades)
        total_wins = sum(t['pnl'] for t in winning_trades)
        total_losses = abs(sum(t['pnl'] for t in losing_trades)) if losing_trades else 0
        
        # 最大回撤
        equity = self.equity_curve
        peak = equity[0]
        max_dd = 0
        max_dd_pct = 0
        
        for e in equity:
            if e > peak:
                peak = e
            dd = peak - e
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd / peak if peak > 0 else 0
        
        # 计算盈亏持仓时间
        holding_bars = [t['holding_bars'] for t in self.trades]
        
        # 更新统计
        self.stats = {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'total_pnl': total_pnl,
            'final_balance': self.balance,
            'max_drawdown': max_dd,
            'max_drawdown_pct': max_dd_pct * 100,
            'win_rate': len(winning_trades) / total_trades if total_trades > 0 else 0,
            'avg_win': total_wins / len(winning_trades) if winning_trades else 0,
            'avg_loss': total_losses / len(losing_trades) if losing_trades else 0,
            'profit_factor': total_wins / total_losses if total_losses > 0 else float('inf'),
            'avg_holding_bars': sum(holding_bars) / len(holding_bars) if holding_bars else 0,
            'roi': (self.balance - self.initial_balance) / self.initial_balance * 100,
            'sharpe_ratio': self._calculate_sharpe()
        }
    
    def _calculate_sharpe(self, risk_free_rate=0.02):
        """计算夏普比率"""
        if len(self.equity_curve) < 2:
            return 0
        
        # 计算日收益率
        returns = []
        for i in range(1, len(self.equity_curve)):
            r = (self.equity_curve[i] - self.equity_curve[i-1]) / self.equity_curve[i-1]
            returns.append(r)
        
        if not returns:
            return 0
        
        import statistics
        avg_return = statistics.mean(returns)
        std_return = statistics.stdev(returns) if len(returns) > 1 else 0
        
        if std_return == 0:
            return 0
        
        sharpe = (avg_return - risk_free_rate / 252) / std_return * (252 ** 0.5)
        
        return sharpe
    
    def get_trade_log(self):
        """获取交易记录"""
        return self.trades
    
    def get_equity_curve(self):
        """获取权益曲线"""
        return self.equity_curve
    
    def print_report(self):
        """打印回测报告"""
        stats = self.stats
        
        print("\n" + "="*60)
        print("              PRICE ACTION 回测报告")
        print("="*60)
        print(f"初始资金:        ${self.initial_balance:,.2f}")
        print(f"最终资金:        ${stats['final_balance']:,.2f}")
        print(f"总收益率:        {stats['roi']:.2f}%")
        print("-"*60)
        print(f"总交易次数:      {stats['total_trades']}")
        print(f"盈利交易:        {stats['winning_trades']}")
        print(f"亏损交易:        {stats['losing_trades']}")
        print(f"胜率:            {stats['win_rate']*100:.2f}%")
        print("-"*60)
        print(f"总盈亏:          ${stats['total_pnl']:,.2f}")
        print(f"平均盈利:        ${stats['avg_win']:,.2f}")
        print(f"平均亏损:        ${stats['avg_loss']:,.2f}")
        print(f"盈亏比:          {stats['profit_factor']:.2f}")
        print("-"*60)
        print(f"最大回撤:        ${stats['max_drawdown']:,.2f} ({stats['max_drawdown_pct']:.2f}%)")
        print(f"夏普比率:        {stats['sharpe_ratio']:.2f}")
        print(f"平均持仓K线数:   {stats['avg_holding_bars']:.1f}")
        print("="*60)
        
        # 策略信号统计
        print("\n策略信号统计:")
        print(f"总信号数:        {self.strategy.stats['total_signals']}")
        print(f"做多信号:        {self.strategy.stats['bullish_signals']}")
        print(f"做空信号:        {self.strategy.stats['bearish_signals']}")
    
    def export_results(self, filename):
        """导出回测结果到JSON"""
        results = {
            'config': {
                'initial_balance': self.initial_balance,
                'commission': self.commission,
                'slippage': self.slippage,
                'risk_percent': self.risk_percent
            },
            'stats': self.stats,
            'trades': self.trades,
            'equity_curve': self.equity_curve
        }
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"结果已导出到: {filename}")


class WalkForwardBacktest:
    """
     Walk-Forward 回测
    =================
    使用滚动窗口进行前向测试，减少过拟合
    """
    
    def __init__(self, train_window=100, test_window=20, step=10):
        """
        Args:
            train_window: 训练窗口大小
            test_window: 测试窗口大小
            step: 滚动步长
        """
        self.train_window = train_window
        self.test_window = test_window
        self.step = step
    
    def run(self, df):
        """运行 Walk-Forward 回测"""
        n = len(df)
        results = []
        
        train_start = 0
        test_start = train_start + self.train_window
        
        while test_start + self.test_window <= n:
            # 训练数据
            train_df = df[train_start:test_start]
            
            # 测试数据
            test_df = df[test_start:test_start + self.test_window]
            
            # 创建并运行回测
            engine = BacktestEngine()
            stats = engine.run(train_df)
            
            results.append({
                'train_period': (train_start, test_start),
                'test_period': (test_start, test_start + self.test_window),
                'stats': stats
            })
            
            # 滚动
            train_start += self.step
            test_start += self.step
        
        return results
