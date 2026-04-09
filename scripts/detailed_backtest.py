import akshare as ak, json, time, statistics as st

def fetch_data(sym, days=300):
    for retry in range(3):
        try:
            df = ak.futures_zh_daily_sina(symbol=sym)
            if df is None or df.empty: raise ValueError('empty')
            df = df.tail(days).reset_index(drop=True)
            return {
                'symbol': sym,
                'dates':   df['date'].astype(str).tolist(),
                'opens':   [float(x) for x in df['open'].tolist()],
                'highs':   [float(x) for x in df['high'].tolist()],
                'lows':    [float(x) for x in df['low'].tolist()],
                'closes':  [float(x) for x in df['close'].tolist()],
            }
        except: time.sleep(2)
    return None

def detailed_backtest(data, mode='intraday'):
    closes = data['closes']; highs = data['highs']; lows = data['lows']
    n = len(closes)
    sp, ap, st2, tg = 30, 10, 1.5, 8.0

    sma = [None]*n
    for i in range(sp-1, n): sma[i] = sum(closes[i-sp+1:i+1])/sp

    tr_list = [0.0]
    for i in range(1, n):
        tr_list.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    atr = [None]*n
    for i in range(ap-1, n): atr[i] = sum(tr_list[i-ap+1:i+1])/ap

    capital = 100000.0
    pos, ep, sp2, tp = 0, 0.0, 0.0, 0.0
    trades = []; equity = [capital]

    for i in range(max(sp, ap), n):
        if sma[i] is None or atr[i] is None or atr[i] <= 0:
            equity.append(equity[-1]); continue
        cs = sma[i]
        ps = sma[i-1] if sma[i-1] else sma[i]
        px = closes[i]

        if pos == 0:
            if cs > ps and px <= cs*1.01 and px >= cs*0.99:
                pos=1; ep=px; sp2=px-st2*atr[i]; tp=px+tg*atr[i]
                entry_i = i
        else:
            if mode == 'intraday':
                ret = (px-ep)/ep
                trades.append({
                    'entry_date': data['dates'][entry_i],
                    'exit_date': data['dates'][i],
                    'entry': round(ep,2), 'exit': round(px,2),
                    'atr_entry': round(atr[entry_i],2),
                    'pnl_pct': round(ret*100,2),
                    'pnl_money': round(capital*ret,0),
                    'reason': '日内平仓',
                    'sma30': round(cs,2),
                    'dist_to_sma_pct': round((px-cs)/cs*100,2),
                })
                equity.append(equity[-1]*(1+ret)); pos=0
            else:
                if px <= sp2:
                    ret = -(st2*atr[i-1])/ep
                    trades.append({
                        'entry_date': data['dates'][entry_i], 'exit_date': data['dates'][i],
                        'entry': round(ep,2), 'exit': round(px,2),
                        'atr_entry': round(atr[entry_i],2),
                        'pnl_pct': round(ret*100,2), 'pnl_money': round(capital*ret,0),
                        'reason': 'ATR止损',
                        'sma30': round(cs,2),
                        'dist_to_sma_pct': round((px-cs)/cs*100,2),
                    })
                    equity.append(equity[-1]*(1+ret)); pos=0
                elif px >= tp:
                    ret = (tg*atr[i-1])/ep
                    trades.append({
                        'entry_date': data['dates'][entry_i], 'exit_date': data['dates'][i],
                        'entry': round(ep,2), 'exit': round(px,2),
                        'atr_entry': round(atr[entry_i],2),
                        'pnl_pct': round(ret*100,2), 'pnl_money': round(capital*ret,0),
                        'reason': '目标止盈',
                        'sma30': round(cs,2),
                        'dist_to_sma_pct': round((px-cs)/cs*100,2),
                    })
                    equity.append(equity[-1]*(1+ret)); pos=0
                else:
                    ns = px - st2*atr[i]
                    if ns > sp2: sp2 = ns
                    equity.append(equity[-1])

    wins = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] < 0]
    total_ret = sum(t['pnl_pct'] for t in trades)
    peak = equity[0]; max_dd_pct = 0.0
    for e in equity:
        if e > peak: peak = e
        dd = (peak-e)/peak*100
        if dd > max_dd_pct: max_dd_pct = dd
    avg_win_pct = sum(t['pnl_pct'] for t in wins)/len(wins) if wins else 0
    avg_loss_pct = abs(sum(t['pnl_pct'] for t in losses)/len(losses)) if losses else 0
    rr = avg_win_pct/avg_loss_pct if avg_loss_pct > 0 else 0
    rets_list = [(equity[j]-equity[j-1])/equity[j-1] for j in range(1,len(equity)) if equity[j-1]>0]
    sharpe = (st.mean(rets_list)*252)/(st.stdev(rets_list)*(252**0.5)) if len(rets_list)>1 and st.stdev(rets_list)>0 else 0.0

    return {
        'trades': trades,
        'equity': [round(e,2) for e in equity],
        'total_trades': len(trades),
        'wins': len(wins), 'losses': len(losses),
        'win_rate': round(len(wins)/len(trades)*100,1) if trades else 0,
        'total_return_pct': round(total_ret*100,2),
        'final_capital': round(equity[-1],2),
        'max_drawdown_pct': round(max_dd_pct,2),
        'avg_win_pct': round(avg_win_pct,2),
        'avg_loss_pct': round(avg_loss_pct,2),
        'rr': round(rr,2),
        'sharpe': round(sharpe,2),
        'data_start': data['dates'][0],
        'data_end': data['dates'][-1],
    }

# 获取PTA数据
sym = 'TA0'
print(f"获取 {sym} 数据...")
d = fetch_data(sym, 300)
if not d: print("数据获取失败"); exit()

r = detailed_backtest(d, mode='intraday')

print(f"""
{'='*75}
  PTA(TA0) 详细回测报告
  数据区间: {r['data_start']} ~ {r['data_end']}
  策略: 日内模式 | ATR=10, SMA=30, 止损1.5x, 止盈8.0x
{'='*75}

📊 整体绩效
{'─'*60}
  总交易次数:   {r['total_trades']} 笔
  盈利交易:    {r['wins']} 笔 ({r['win_rate']}%)
  亏损交易:    {r['losses']} 笔
  总收益率:    {r['total_return_pct']:+.2f}%
  期末资金:    {r['final_capital']:,.2f} 元（初始 100,000 元）
  最大回撤:    {r['max_drawdown_pct']:.2f}%
  平均盈利:    {r['avg_win_pct']:.2f}% / 笔
  平均亏损:    -{r['avg_loss_pct']:.2f}% / 笔
  盈亏比:     {r['rr']:.2f}
  夏普比:     {r['sharpe']:.2f}
""")

print(f"""
📋 交易明细
{'─'*80}
{'#':<3} {'入场日期':<12} {'入场价':>8} {'ATR':>6} {'SMA30':>8} {'偏离%':>7} {'出场价':>8} {'盈亏%':>8} {'金额':>8} {'出场原因'}
{'-'*80}""")

for i, t in enumerate(r['trades'], 1):
    pnl_str = f"{t['pnl_pct']:+.2f}%"
    money_str = f"{t['pnl_money']:+,.0f}"
    flag = '🟢' if t['pnl_pct'] > 0 else '🔴'
    print(f" {i:<3} {t['entry_date']:<12} {t['entry']:>8.2f} {t['atr_entry']:>6.2f} {t['sma30']:>8.2f} {t['dist_to_sma_pct']:>+6.2f}% {t['exit']:>8.2f} {pnl_str:>8} {money_str:>>8} {flag} {t['reason']}")

# 月度统计
print(f"\n📅 月度统计")
print(f"{'─'*60}")
monthly_stats = {}
for t in r['trades']:
    month = t['exit_date'][:7]  # YYYY-MM
    if month not in monthly_stats:
        monthly_stats[month] = {'wins': 0, 'losses': 0, 'net': 0, 'trades': 0}
    monthly_stats[month]['trades'] += 1
    monthly_stats[month]['net'] += t['pnl_pct']
    if t['pnl_pct'] > 0: monthly_stats[month]['wins'] += 1
    else: monthly_stats[month]['losses'] += 1

for month in sorted(monthly_stats.keys()):
    s = monthly_stats[month]
    wr = s['wins']/s['trades']*100 if s['trades'] else 0
    flag = '★' if s['net'] > 0 else '☆'
    print(f"  {month}  {s['trades']:>2}笔  胜率{wr:>5.0f}%  净收益{s['net']:>+6.2f}% {flag}")

# 季度统计
print(f"\n📆 季度统计")
print(f"{'─'*60}")
quarterly = {}
for t in r['trades']:
    q = t['exit_date'][:4] + '-Q' + str((int(t['exit_date'][5:7])-1)//3 + 1)
    if q not in quarterly: quarterly[q] = {'wins':0,'losses':0,'net':0,'trades':0}
    quarterly[q]['trades'] += 1
    quarterly[q]['net'] += t['pnl_pct']
    if t['pnl_pct'] > 0: quarterly[q]['wins'] += 1
    else: quarterly[q]['losses'] += 1

for q in sorted(quarterly.keys()):
    s = quarterly[q]
    wr = s['wins']/s['trades']*100 if s['trades'] else 0
    flag = '★' if s['net'] > 0 else '☆'
    print(f"  {q}  {s['trades']:>2}笔  胜率{wr:>5.0f}%  净收益{s['net']:>+6.2f}% {flag}")

# 入场时机分析
print(f"\n🎯 入场时机分析（偏离SMA30多少时入场效果最好）")
print(f"{'─'*60}")
bucket = {'<-3%': [], '-3%~-2%': [], '-2%~-1%': [], '-1%~0%': [], '0%~1%': []}
for t in r['trades']:
    d2s = t['dist_to_sma_pct']
    if d2s < -3: bucket['<-3%'].append(t)
    elif d2s < -2: bucket['-3%~-2%'].append(t)
    elif d2s < -1: bucket['-2%~-1%'].append(t)
    elif d2s < 0: bucket['-1%~0%'].append(t)
    else: bucket['0%~1%'].append(t)

for label, ts in bucket.items():
    if not ts: continue
    net = sum(t['pnl_pct'] for t in ts)
    wr = sum(1 for t in ts if t['pnl_pct']>0)/len(ts)*100
    avg = net/len(ts)
    flag = '★' if net > 0 else '☆'
    print(f"  偏离SMA30 {label:>10}: {len(ts)}笔  胜率{wr:>5.0f}%  均收益{avg:>+6.2f}%  合计{net:>+6.2f}% {flag}")

# 保存
with open('/home/node/.openclaw/workspace/projects/louie-priceaction-strategy/data/pta_detail.json','w') as f:
    json.dump(r, f, ensure_ascii=False, indent=2)
print(f"\n详细数据已保存: data/pta_detail.json")
