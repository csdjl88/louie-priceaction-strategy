import akshare as ak, json, time, statistics as st

def fetch_data(sym, days=300):
    for retry in range(3):
        try:
            df = ak.futures_zh_daily_sina(symbol=sym)
            if df is None or df.empty:
                raise ValueError('empty')
            df = df.tail(days).reset_index(drop=True)
            return {
                'symbol': sym,
                'dates': df['date'].astype(str).tolist(),
                'opens': [float(x) for x in df['open'].tolist()],
                'highs': [float(x) for x in df['high'].tolist()],
                'lows': [float(x) for x in df['low'].tolist()],
                'closes': [float(x) for x in df['close'].tolist()],
            }
        except:
            time.sleep(2)
    return None

def detailed_backtest(data, mode='intraday'):
    closes = data['closes']
    highs = data['highs']
    lows = data['lows']
    n = len(closes)
    sp, ap, st2, tg = 30, 10, 1.5, 8.0

    # SMA30
    sma = [None] * n
    for i in range(sp-1, n):
        sma[i] = sum(closes[i-sp+1:i+1]) / sp

    # ATR10
    tr_list = [0.0]
    for i in range(1, n):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        tr_list.append(tr)
    atr = [None] * n
    for i in range(ap-1, n):
        atr[i] = sum(tr_list[i-ap+1:i+1]) / ap

    capital = 100000.0
    pos, ep, sp2, tp = 0, 0.0, 0.0, 0.0
    entry_sma = 0.0
    entry_date = ''
    entry_idx = 0
    trades = []
    equity = [capital]

    for i in range(max(sp, ap), n):
        if sma[i] is None or atr[i] is None or atr[i] <= 0:
            equity.append(equity[-1])
            continue
        cs = sma[i]
        ps = sma[i-1] if sma[i-1] else sma[i]
        px = closes[i]

        if pos == 0:
            # 入场: 均线多头 + 价格回踩 ±1%
            if cs > ps and px <= cs * 1.01 and px >= cs * 0.99:
                pos = 1
                ep = px
                sp2 = px - st2 * atr[i]
                tp = px + tg * atr[i]
                entry_sma = cs
                entry_date = data['dates'][i]
                entry_idx = i
        else:
            if mode == 'intraday':
                ret = (px - ep) / ep
                dist_pct = (ep - entry_sma) / entry_sma * 100
                trades.append({
                    'entry_date': entry_date,
                    'exit_date': data['dates'][i],
                    'entry': round(ep, 2),
                    'exit': round(px, 2),
                    'atr_entry': round(atr[entry_idx], 2),
                    'atr_exit': round(atr[i], 2),
                    'sma_entry': round(entry_sma, 2),
                    'sma_exit': round(cs, 2),
                    'dist_to_sma_pct': round(dist_pct, 2),
                    'pnl_pct': round(ret * 100, 2),
                    'pnl_money': round(capital * ret, 0),
                    'reason': '日内平仓',
                })
                equity.append(equity[-1] * (1 + ret))
                pos = 0
            else:
                # 波段
                if px <= sp2:
                    ret = -(st2 * atr[i-1]) / ep
                    dist_pct = (ep - entry_sma) / entry_sma * 100
                    trades.append({
                        'entry_date': entry_date,
                        'exit_date': data['dates'][i],
                        'entry': round(ep, 2),
                        'exit': round(px, 2),
                        'atr_entry': round(atr[entry_idx], 2),
                        'atr_exit': round(atr[i], 2),
                        'sma_entry': round(entry_sma, 2),
                        'sma_exit': round(cs, 2),
                        'dist_to_sma_pct': round(dist_pct, 2),
                        'pnl_pct': round(ret * 100, 2),
                        'pnl_money': round(capital * ret, 0),
                        'reason': 'ATR止损',
                    })
                    equity.append(equity[-1] * (1 + ret))
                    pos = 0
                elif px >= tp:
                    ret = (tg * atr[i-1]) / ep
                    dist_pct = (ep - entry_sma) / entry_sma * 100
                    trades.append({
                        'entry_date': entry_date,
                        'exit_date': data['dates'][i],
                        'entry': round(ep, 2),
                        'exit': round(px, 2),
                        'atr_entry': round(atr[entry_idx], 2),
                        'atr_exit': round(atr[i], 2),
                        'sma_entry': round(entry_sma, 2),
                        'sma_exit': round(cs, 2),
                        'dist_to_sma_pct': round(dist_pct, 2),
                        'pnl_pct': round(ret * 100, 2),
                        'pnl_money': round(capital * ret, 0),
                        'reason': '目标止盈',
                    })
                    equity.append(equity[-1] * (1 + ret))
                    pos = 0
                else:
                    # 追踪止损
                    new_sp = px - st2 * atr[i]
                    if new_sp > sp2:
                        sp2 = new_sp
                    equity.append(equity[-1])

    if not trades:
        return None

    wins = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] < 0]
    total_ret_pct = sum(t['pnl_pct'] for t in trades)

    peak = equity[0]
    max_dd_pct = 0.0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100
        if dd > max_dd_pct:
            max_dd_pct = dd

    avg_win_pct = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0
    avg_loss_pct = abs(sum(t['pnl_pct'] for t in losses) / len(losses)) if losses else 0
    rr = avg_win_pct / avg_loss_pct if avg_loss_pct > 0 else 0

    rets_list = [(equity[j] - equity[j-1]) / equity[j-1] for j in range(1, len(equity)) if equity[j-1] > 0]
    if len(rets_list) > 1 and st.stdev(rets_list) > 0:
        sharpe = (st.mean(rets_list) * 252) / (st.stdev(rets_list) * (252 ** 0.5))
    else:
        sharpe = 0.0

    return {
        'trades': trades,
        'equity': [round(e, 2) for e in equity],
        'total_trades': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': round(len(wins) / len(trades) * 100, 1),
        'total_return_pct': round(total_ret_pct, 2),
        'final_capital': round(equity[-1], 2),
        'max_drawdown_pct': round(max_dd_pct, 2),
        'avg_win_pct': round(avg_win_pct, 2),
        'avg_loss_pct': round(avg_loss_pct, 2),
        'rr': round(rr, 2),
        'sharpe': round(sharpe, 2),
        'data_start': data['dates'][0],
        'data_end': data['dates'][-1],
    }

# === 主程序 ===
sym = 'TA0'
print(f'获取 {sym} 数据...')
d = fetch_data(sym, 300)
if not d:
    print('数据获取失败')
    exit()

r = detailed_backtest(d, mode='intraday')

print()
print('=' * 80)
print(f'  PTA(TA0) 详细回测报告  |  日内模式')
print(f'  数据区间: {r["data_start"]} ~ {r["data_end"]}')
print(f'  策略: ATR=10, SMA=30, 止损1.5x, 止盈8.0x')
print('=' * 80)

print()
print('  【整体绩效】')
print('  ' + '-' * 60)
print(f'  总交易次数:   {r["total_trades"]} 笔')
print(f'  盈利交易:    {r["wins"]} 笔  ({r["win_rate"]}%)')
print(f'  亏损交易:    {r["losses"]} 笔')
print(f'  总收益率:    {r["total_return_pct"]:+.2f}%')
print(f'  期末资金:    {r["final_capital"]:,.0f} 元  (初始 100,000 元)')
print(f'  最大回撤:    {r["max_drawdown_pct"]:.2f}%')
print(f'  平均盈利:    +{r["avg_win_pct"]:.2f}% / 笔')
print(f'  平均亏损:    -{r["avg_loss_pct"]:.2f}% / 笔')
print(f'  盈亏比:      {r["rr"]:.2f}')
print(f'  夏普比率:    {r["sharpe"]:.2f}')

print()
print('  【交易明细】')
print('  ' + '-' * 80)
print(f'  {"#":<3} {"入场日期":<12} {"入场价":>8} {"ATR":>6} {"偏离SMA%":>9} {"出场价":>8} {"盈亏%":>8} {"金额(元)":>9} {"原因"}')
print('  ' + '-' * 80)

for i, t in enumerate(r['trades'], 1):
    flag = '  ' if t['pnl_pct'] >= 0 else '  '
    dist = t['dist_to_sma_pct']
    print(f"  {i:<3} {t['entry_date']:<12} {t['entry']:>8.2f} {t['atr_entry']:>6.2f} {dist:>+8.2f}% {t['exit']:>8.2f} {t['pnl_pct']:>+7.2f}% {t['pnl_money']:>+8,.0f}{flag}{t['reason']}")

# 月度统计
print()
print('  【月度统计】')
print('  ' + '-' * 60)
monthly = {}
for t in r['trades']:
    month = t['exit_date'][:7]
    if month not in monthly:
        monthly[month] = {'wins': 0, 'losses': 0, 'net': 0, 'count': 0}
    monthly[month]['count'] += 1
    monthly[month]['net'] += t['pnl_pct']
    if t['pnl_pct'] > 0:
        monthly[month]['wins'] += 1

for month in sorted(monthly.keys()):
    s = monthly[month]
    wr = s['wins'] / s['count'] * 100 if s['count'] else 0
    print(f"  {month}  {s['count']:>2}笔  胜率{wr:>5.0f}%  净收益{s['net']:>+6.2f}%  {'★' if s['net'] > 0 else '☆'}")

# 入场时机分析
print()
print('  【入场时机分析（入场价偏离 SMA30 的程度）】')
print('  ' + '-' * 60)
buckets = {
    '< -2.0% (深跌入场)': [],
    '-2.0% ~ -1.5%': [],
    '-1.5% ~ -1.0%': [],
    '-1.0% ~ -0.5%': [],
    '-0.5% ~ 0% (最佳)': [],
    '0% ~ +0.5%': [],
}
for t in r['trades']:
    d2s = t['dist_to_sma_pct']
    if d2s < -2.0:
        buckets['< -2.0% (深跌入场)'].append(t)
    elif d2s < -1.5:
        buckets['-2.0% ~ -1.5%'].append(t)
    elif d2s < -1.0:
        buckets['-1.5% ~ -1.0%'].append(t)
    elif d2s < -0.5:
        buckets['-1.0% ~ -0.5%'].append(t)
    elif d2s < 0:
        buckets['-0.5% ~ 0% (最佳)'].append(t)
    else:
        buckets['0% ~ +0.5%'].append(t)

for label, ts in buckets.items():
    if not ts:
        continue
    net = sum(t['pnl_pct'] for t in ts)
    wr = sum(1 for t in ts if t['pnl_pct'] > 0) / len(ts) * 100
    avg = net / len(ts)
    avg_dist = sum(t['dist_to_sma_pct'] for t in ts) / len(ts)
    print(f"  {label:<22}: {len(ts):>2}笔  胜率{wr:>5.0f}%  均收益{avg:>+6.2f}%  均偏离{avg_dist:>+6.2f}%  合计{net:>+6.2f}%  {'★' if net > 0 else '☆'}")

# 止损 vs 止盈 分布
print()
print('  【出场原因统计】')
print('  ' + '-' * 60)
reason_stats = {}
for t in r['trades']:
    reason = t['reason']
    if reason not in reason_stats:
        reason_stats[reason] = {'count': 0, 'wins': 0, 'net': 0}
    reason_stats[reason]['count'] += 1
    reason_stats[reason]['net'] += t['pnl_pct']
    if t['pnl_pct'] > 0:
        reason_stats[reason]['wins'] += 1

for reason, s in reason_stats.items():
    wr = s['wins'] / s['count'] * 100 if s['count'] else 0
    avg = s['net'] / s['count']
    print(f"  {reason}: {s['count']}笔  胜率{wr:>5.0f}%  均收益{avg:>+6.2f}%  合计{s['net']:>+6.2f}%")

# 保存
with open('/home/node/.openclaw/workspace/projects/louie-priceaction-strategy/data/pta_detail.json', 'w') as f:
    json.dump(r, f, ensure_ascii=False, indent=2)
print()
print('  数据已保存: data/pta_detail.json')
