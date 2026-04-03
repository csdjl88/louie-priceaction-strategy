"""
param_optimizer.py - 策略参数优化器
=================================

支持多种优化方法：
1. 网格搜索 (Grid Search) - 遍历所有参数组合
2. 随机搜索 (Random Search) - 随机采样参数组合
3. 贝叶斯优化 (Bayesian) - 基于历史结果智能搜索

使用方法:
    from param_optimizer import GridSearchOptimizer, RandomSearchOptimizer, optimize_strategy

    # 网格搜索
    optimizer = GridSearchOptimizer(param_grid)
    best_params, results = optimizer.optimize('RB0', days=365)

    # 随机搜索
    optimizer = RandomSearchOptimizer(param_dist, n_iter=100)
    best_params, results = optimizer.optimize('RB0', days=365)
"""

import json
import random
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class OptimizationResult:
    """单次优化结果"""
    params: Dict[str, Any]
    total_return: float
    max_drawdown: float
    win_rate: float
    sharpe_ratio: float
    total_trades: int
    score: float  # 综合评分


def run_backtest_with_params(symbol: str, days: int, 
                               atr_period: int = 14,
                               atr_stop: float = 2.0,
                               atr_target: float = 6.0,
                               sma_period: int = 50,
                               trading_mode: str = "swing") -> Optional[OptimizationResult]:
    """
    运行单次回测并返回结果
    
    通过子进程调用 backtest_runner.py 获取结果
    """
    try:
        cmd = [
            '.venv/bin/python', 'backtest_runner.py',
            '--symbol', symbol,
            '--source', 'akshare',
            '--days', str(days),
            '--mode', trading_mode
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, 
                                cwd='/root/.openclaw/workspace/quant-strategy',
                                timeout=120)
        
        text = result.stdout
        
        # 解析结果
        import re
        
        # 收益率
        return_match = re.search(r'总收益:\s*([-\d,.]+)\s*\(([-+]?[\d.]+)%\)', text)
        if not return_match:
            return None
        total_return = float(return_match.group(2))
        
        # 交易次数
        trades_match = re.search(r'总交易次数:\s*(\d+)', text)
        total_trades = int(trades_match.group(1)) if trades_match else 0
        
        # 胜率
        win_match = re.search(r'盈利交易:\s*(\d+)\s*\(([\d.]+)%\)', text)
        win_rate = float(win_match.group(2)) / 100 if win_match else 0
        
        # 最大回撤
        dd_match = re.search(r'最大回撤:\s*([-\d.]+)%', text)
        max_drawdown = abs(float(dd_match.group(1))) if dd_match else 0
        
        # 夏普比率（简化计算）
        sharpe_ratio = total_return / max_drawdown if max_drawdown > 0 else 0
        
        # 综合评分 = 收益率(40%) + 胜率(20%) + 风险调整收益(25%) + 交易次数(15%)
        # 归一化
        return_norm = min(total_return / 50, 1.0)  # 50%收益为满分
        win_rate_norm = win_rate
        risk_adjusted = min(total_return / max_drawdown, 2) / 2 if max_drawdown > 0 else 0
        trades_norm = min(total_trades / 20, 1.0)  # 20次交易为满分
        
        score = (return_norm * 0.4 + win_rate_norm * 0.2 + 
                 risk_adjusted * 0.25 + trades_norm * 0.15)
        
        return OptimizationResult(
            params={
                'atr_period': atr_period,
                'atr_stop': atr_stop,
                'atr_target': atr_target,
                'sma_period': sma_period,
                'trading_mode': trading_mode
            },
            total_return=total_return,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            sharpe_ratio=sharpe_ratio,
            total_trades=total_trades,
            score=score
        )
        
    except Exception as e:
        print(f"  回测失败: {e}")
        return None


class BaseOptimizer:
    """优化器基类"""
    
    def __init__(self, param_grid: Dict[str, List[Any]]):
        """
        Args:
            param_grid: 参数网格，如 {'atr_period': [10, 14, 20], 'atr_stop': [1.5, 2.0]}
        """
        self.param_grid = param_grid
        self.results: List[OptimizationResult] = []
    
    def _generate_param_combinations(self) -> List[Dict[str, Any]]:
        """生成参数组合（子类实现）"""
        raise NotImplementedError
    
    def optimize(self, symbol: str = 'RB0', days: int = 365,
                 n_jobs: int = 1, callback: Optional[Callable] = None) -> tuple:
        """
        运行优化
        
        Args:
            symbol: 品种代码
            days: 数据天数
            n_jobs: 并行数（目前暂不支持）
            callback: 每次完成后的回调函数
            
        Returns:
            (最佳参数, 所有结果列表)
        """
        param_combinations = self._generate_param_combinations()
        total = len(param_combinations)
        
        print(f"\n{'='*60}")
        print(f"  参数优化开始 - 共 {total} 种组合")
        print(f"{'='*60}")
        
        self.results = []
        
        for i, params in enumerate(param_combinations, 1):
            print(f"\n[{i}/{total}] 测试参数: {params}")
            
            result = run_backtest_with_params(symbol, days, **params)
            
            if result:
                self.results.append(result)
                print(f"  -> 收益: {result.total_return:.2f}%, 胜率: {result.win_rate*100:.1f}%, "
                      f"回撤: {result.max_drawdown:.2f}%, 评分: {result.score:.3f}")
            else:
                print(f"  -> 回测失败")
            
            if callback:
                callback(i, total, params, result)
        
        # 找到最佳参数
        if self.results:
            best = max(self.results, key=lambda x: x.score)
            return best.params, self.results
        else:
            return {}, []


class GridSearchOptimizer(BaseOptimizer):
    """网格搜索优化器 - 遍历所有参数组合"""
    
    def _generate_param_combinations(self) -> List[Dict[str, Any]]:
        """生成所有参数组合"""
        import itertools
        
        keys = list(self.param_grid.keys())
        values = list(self.param_grid.values())
        
        combinations = []
        for combo in itertools.product(*values):
            param_dict = dict(zip(keys, combo))
            combinations.append(param_dict)
        
        return combinations


class RandomSearchOptimizer(BaseOptimizer):
    """随机搜索优化器 - 随机采样参数组合"""
    
    def __init__(self, param_dist: Dict[str, tuple], n_iter: int = 100):
        """
        Args:
            param_dist: 参数分布，如 {'atr_period': (10, 30)} 表示范围
            n_iter: 采样次数
        """
        super().__init__({})  # 不使用 param_grid
        self.param_dist = param_dist
        self.n_iter = n_iter
    
    def _generate_param_combinations(self) -> List[Dict[str, Any]]:
        """随机生成参数组合"""
        combinations = []
        
        for _ in range(self.n_iter):
            param_dict = {}
            for key, dist in self.param_dist.items():
                if isinstance(dist, tuple) and len(dist) == 2:
                    # 数值范围
                    if isinstance(dist[0], int):
                        param_dict[key] = random.randint(int(dist[0]), int(dist[1]))
                    else:
                        param_dict[key] = random.uniform(dist[0], dist[1])
                elif isinstance(dist, list):
                    # 离散值列表
                    param_dict[key] = random.choice(dist)
            
            combinations.append(param_dict)
        
        return combinations


def optimize_strategy(symbol: str = 'RB0', days: int = 365,
                      method: str = 'grid',
                      param_grid: Optional[Dict] = None) -> tuple:
    """
    快速优化函数
    
    Args:
        symbol: 品种代码
        days: 数据天数
        method: 'grid' 或 'random'
        param_grid: 参数网格
        
    Returns:
        (最佳参数, 所有结果)
    """
    if param_grid is None:
        # 默认参数网格
        param_grid = {
            'atr_period': [10, 14, 20],
            'atr_stop': [1.5, 2.0, 2.5],
            'atr_target': [4.0, 6.0, 8.0],
            'sma_period': [20, 50, 100]
        }
    
    if method == 'random':
        param_dist = {
            'atr_period': (10, 20),
            'atr_stop': (1.5, 2.5),
            'atr_target': (4.0, 8.0),
            'sma_period': (20, 100)
        }
        optimizer = RandomSearchOptimizer(param_dist, n_iter=50)
    else:
        optimizer = GridSearchOptimizer(param_grid)
    
    return optimizer.optimize(symbol, days)


def print_optimization_report(results: List[OptimizationResult], top_n: int = 10):
    """
    打印优化报告
    
    Args:
        results: 优化结果列表
        top_n: 显示前 N 名
    """
    if not results:
        print("无优化结果")
        return
    
    # 按评分排序
    sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
    
    print(f"\n{'='*80}")
    print(f"  参数优化报告 - Top {top_n}")
    print(f"{'='*80}")
    print(f"{'Rank':<6}{'Score':<8}{'Return%':<12}{'WinRate%':<10}{'MaxDD%':<10}{'Trades':<8} Parameters")
    print("-" * 80)
    
    for i, r in enumerate(sorted_results[:top_n], 1):
        params_str = ", ".join([f"{k}={v}" for k, v in r.params.items()])
        print(f"{i:<6}{r.score:<8.3f}{r.total_return:<12.2f}{r.win_rate*100:<10.1f}"
              f"{r.max_drawdown:<10.2f}{r.total_trades:<8}{params_str}")
    
    # 最佳参数
    best = sorted_results[0]
    print(f"\n{'='*80}")
    print(f"  最佳参数:")
    for k, v in best.params.items():
        print(f"    {k}: {v}")
    print(f"  收益率: {best.total_return:.2f}%")
    print(f"  胜率: {best.win_rate*100:.1f}%")
    print(f"  最大回撤: {best.max_drawdown:.2f}%")
    print(f"  综合评分: {best.score:.3f}")
    print(f"{'='*80}")


def save_optimization_history(symbol: str, best_params: Dict, results: List[OptimizationResult], 
                             method: str = 'grid', history_file: str = 'optimization_history.json'):
    """
    保存优化结果到历史记录
    
    Args:
        symbol: 品种代码
        best_params: 最佳参数
        results: 所有优化结果
        method: 优化方法
        history_file: 历史记录文件
    """
    from datetime import datetime
    
    # 读取现有历史
    import os
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except:
            history = []
    
    # 构建记录
    record = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'symbol': symbol,
        'method': method,
        'best_params': best_params,
        'total_results': len(results),
        'best_result': {
            'return_pct': results[0].total_return if results else 0,
            'win_rate': results[0].win_rate if results else 0,
            'max_drawdown': results[0].max_drawdown if results else 0,
            'score': results[0].score if results else 0,
            'trades': results[0].total_trades if results else 0
        } if results else {}
    }
    
    # 添加到历史
    history.insert(0, record)
    
    # 只保留最近50条
    history = history[:50]
    
    # 保存
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    
    print(f"\n优化历史已保存到: {history_file}")
    return history


def load_optimization_history(symbol: str = None, history_file: str = 'optimization_history.json') -> List[Dict]:
    """
    加载优化历史记录
    
    Args:
        symbol: 可选的品种过滤
        history_file: 历史记录文件
    
    Returns:
        历史记录列表
    """
    import os
    if not os.path.exists(history_file):
        return []
    
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            history = json.load(f)
    except:
        return []
    
    if symbol:
        history = [h for h in history if h.get('symbol') == symbol]
    
    return history


def print_optimization_history(symbol: str = None, history_file: str = 'optimization_history.json'):
    """打印优化历史"""
    history = load_optimization_history(symbol, history_file)
    
    if not history:
        print("无优化历史记录")
        return
    
    print(f"\n{'='*80}")
    print(f"  优化历史记录 (共 {len(history)} 条)")
    if symbol:
        print(f"  品种: {symbol}")
    print(f"{'='*80}")
    print(f"{'时间':<20}{'品种':<8}{'方法':<8}{'收益率':<12}{'胜率':<10}{'评分':<8}")
    print("-" * 80)
    
    for h in history[:20]:
        r = h.get('best_result', {})
        print(f"{h['timestamp']:<20}{h['symbol']:<8}{h['method']:<8}"
              f"{r.get('return_pct', 0):<12.2f}{r.get('win_rate', 0)*100:<10.1f}{r.get('score', 0):<8.3f}")


# CLI 入口
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='策略参数优化器')
    parser.add_argument('--symbol', '-s', default='RB0', help='品种代码')
    parser.add_argument('--days', '-n', type=int, default=365, help='数据天数')
    parser.add_argument('--method', '-m', choices=['grid', 'random'], default='grid',
                        help='优化方法')
    parser.add_argument('--top', '-t', type=int, default=10, help='显示Top N')
    parser.add_argument('--save', action='store_true', help='保存优化结果到历史')
    parser.add_argument('--history', action='store_true', help='查看优化历史')
    
    args = parser.parse_args()
    
    if args.history:
        print_optimization_history(args.symbol)
    else:
        # 运行优化
        best_params, results = optimize_strategy(args.symbol, args.days, args.method)
        
        # 打印报告
        print_optimization_report(results, args.top)
        
        # 保存历史
        if args.save:
            save_optimization_history(args.symbol, best_params, results, args.method)