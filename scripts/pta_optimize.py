"""
PTA 策略优化方案对比测试
"""
import akshare as ak, json, time, statistics as st

def fetch_data(sym, days=300):
    for retry in range(3):
        try:
            df = ak.futures_zh_daily_sina(symbol=sym)
            if df is None or df.empty: raise ValueError('empty')
            df = df.tail(days).reset_index(drop=True)
            return {
                'dates': df['date'].astype(str).tolist(),
                'opens': [float(x) for x in df['open'].tolist()],
                'highs': [float(x) for x in df['high'].tolist()],
                'lows': [float(x) for x in df['low'].tolist()],
                'closes': [float(x) for x in df['close'].tolist()],
            }
        except: time.sleep(2)
    return None

def sma_slope(closes, period, idx, n=3):
    if idx < n + period: return 0.0
    vals = []
    for k in range(idx - n, idx + 1):
        if k < period - 1: continue
        vals.append(sum(closes[k-period+1:k+1]) / period)
    return (vals[-1] - vals[-2]) / vals[-2] * 100 if len(vals) >= 2 else 0.0

def run_bt(data, mode='intraday', sma_p=30, atr_p=10, atr_s=1.5,
          use_fixed=False, fixed_pct=0.015, use_slope=False, slope_th=0.05, name=''):
    C, H, L = data['closes'], data['highs'], data['lows']
    n = len(C)
    sma = [None]*n
    for i in range(sma_p-1, n): sma[i] = sum(C[i-sma_p+1:i+1])/sma_p
    tr = [0.0]
    for i in range(1, n): tr.append(max(H[i]-L[i], abs(H[i]-C[i-1]), abs(L[i]-C[i-1])))
    atr = [None]*n
    for i in range(atr_p-1, n): atr[i] = sum(tr[i-atr_p+1:i+1])/atr_p
    capital = 100000.0
    pos, ep, sp2, tp, eidx = 0, 0.0, 0.0, 0.0, 0
    trades, equity = [], [capital]
    for i in range(max(sma_p, atr_p), n):
        if sma[i] is None or atr[i] is None or atr[i] <= 0:
            equity.append(equity[-1]); continue
        cs, ps, px = sma[i], (sma[i-1] if sma[i-1] else sma[i]), C[i]
        if use_slope and abs(sma_slope(C, sma_p, i)) < slope_th:
            equity.append(equity[-1]); continue
        if pos == 0:
            if cs > ps and px <= cs*1.01 and px >= cs*0.99:
                pos=1; ep=px; sp2=px-atr_s*atr[i]
                tp = px*(1+fixed_pct) if use_fixed else px+8.0*atr[i]
                eidx = i
        else:
            if mode == 'intraday':
                r = (px-ep)/ep
                trades.append({'date':data['dates'][i],'ep':ep,'ex':px,
                    'atr':atr[eidx],'atr2':atr[i],'pnl':r*100,'money':capital*r,
                    'dist':(ep-cs)/cs*100,'reason':'日内平仓'})
                equity.append(equity[-1]*(1+r)); pos=0
            else:
                hit_s = px <= sp2
                hit_t = (use_fixed and px >= tp) or (not use_fixed and px >= tp)
                if hit_s:
                    r = -(atr_s*atr[i-1])/ep
                    trades.append({'date':data['dates'][i],'ep':ep,'ex':px,
                        'atr':atr[eidx],'atr2':atr[i],'pnl':r*100,'money':capital*r,
                        'dist':(ep-cs)/cs*100,'reason':'止损'})
                    equity.append(equity[-1]*(1+r)); pos=0
                elif hit_t:
                    r = fixed_pct if use_fixed else (8.0*atr[i-1])/ep
                    trades.append({'date':data['dates'][i],'ep':ep,'ex':px,
                        'atr':atr[eidx],'atr2':atr[i],'pnl':r*100,'money':capital*r,
                        'dist':(ep-cs)/cs*100,'reason':'止盈'})
                    equity.append(equity[-1]*(1+r)); pos=0
                else:
                    ns = px - atr_s*atr[i]
                    if ns > sp2: sp2 = ns
                    equity.append(equity[-1])
    if not trades: return None
    wins = [t for t in trades if t['pnl']>0]
    losses = [t for t in trades if t['pnl']<0]
    total_ret = sum(t['pnl'] for t in trades)
    peak = equity[0]; max_dd = 0.0
    for e in equity:
        if e > peak: peak = e
        dd = (peak-e)/peak*100
        if dd > max_dd: max_dd = dd
    aw = sum(t['pnl'] for t in wins)/len(wins) if wins else 0
    al = abs(sum(t['pnl'] for t in losses)/len(losses)) if losses else 0
    rr = aw/al if al > 0 else 0
    rs = [(equity[j]-equity[j-1])/equity[j-1] for j in range(1,len(equity)) if equity[j-1]>0]
    sh = (st.mean(rs)*252)/(st.stdev(rs)*(252**0.5)) if len(rs)>1 and st.stdev(rs)>0 else 0.0
    rc = {}
    for t in trades: rc[t['reason']] = rc.get(t['reason'],0)+1
    return {'name':name,'n':len(trades),'wins':len(wins),'losses':len(losses),
        'wr':round(len(wins)/len(trades)*100,1),'ret':round(total_ret,2),
        'cap':round(equity[-1],0),'dd':round(max_dd,2),
        'aw':round(aw,3),'al':round(al,3),'rr':round(rr,2),'sh':round(sh,2),
        'rc':rc,'trades':trades}

data = fetch_data('TA0', 300)
if not data: print('FAIL'); exit()
print(f'PTA 数据: {data["dates"][0]} ~ {data["dates"][-1]}  {len(data["closes"])}K\n')

V = [
    ('[基准] ATR10 SMA30 止盈8x',         30,10,1.5, False,0.000, False,0.05),
    ('[A] 固定1.5%止盈',                  30,10,1.5, True,0.015, False,0.05),
    ('[B] 固定2.0%止盈',                  30,10,1.5, True,0.020, False,0.05),
    ('[C] 固定1.0%止盈',                  30,10,1.5, True,0.010, False,0.05),
    ('[D] SMA20(更快转向)',               20,10,1.5, False,0.000, False,0.05),
    ('[E] SMA20+固定1.5%',                20,10,1.5, True,0.015, False,0.05),
    ('[F] 趋势过滤(斜率>0.05%)',          30,10,1.5, False,0.000, True,0.05),
    ('[G] 趋势过滤+固定1.5%',             30,10,1.5, True,0.015, True,0.05),
    ('[H] SMA20+趋势过滤+1.5%(全优化)',   20,10,1.5, True,0.015, True,0.05),
    ('[I] SMA20+趋势过滤+1.0%',          20,10,1.5, True,0.010, True,0.05),
]

results = []
for nm, sp, ap, ass, uf, fp, usl, sth in V:
    r = run_bt(data, sma_p=sp, atr_p=ap, atr_s=ass,
               use_fixed=uf, fixed_pct=fp, use_slope=usl, slope_th=sth, name=nm)
    if r:
        results.append(r)
        rc_str = ' '.join(f'{k}:{v}' for k,v in r['rc'].items())
        print(f"  {r['n']:>2}笔 胜{r['wr']:>5.1f}%  ret{r['ret']:>+6.2f}%  DD{r['dd']:>5.2f}%  RR{r['rr']:>4.2f}  SR{r['sh']:>5.2f}  {nm}  ({rc_str})")
    else:
        print(f"  无信号  {nm}")
    time.sleep(0.3)

def sc(r):
    return (0.40*max(0,min(1,(r['ret']+15)/25))
        + 0.15*(r['wr']/100)
        + 0.20*max(0,min(1,(r['rr']-0.5)/2.5))
        + 0.15*max(0,min(1,(r['sh']+2)/8))
        + 0.10*max(0,min(1,r['n']/50))

ranked = sorted(results, key=sc, reverse=True)
print()
print('='*90)
print('  综合排名（收益40% + 胜率15% + 盈亏比20% + 夏普15% + 交易次数10%）')
print('='*90)
print(f"\n{'#':<3}{'方案':<35}{'笔':>4}{'胜率':>7}{'收益':>9}{'DD':>8}{'RR':>7}{'SR':>7}{'评分':>6}")
print('-'*90)
for i,r in enumerate(ranked,1):
    tag = ' ← 最优' if i==1 else ''
    print(f" {i:<2}{r['name']:<35}{r['n']:>4}{r['wr']:>6.1f}% {r['ret']:>+7.2f}% {r['dd']:>7.2f}% {r['rr']:>6.2f} {r['sh']:>6.2f} {sc(r):>6.3f}{tag}")

best = ranked[0]
baseline = next((x for x in results if '基准' in x['name']), ranked[0])
print()
print('='*90)
print(f"  月度对比: {baseline['name']} vs {best['name']}")
print('='*90)

def mo_stats(trades):
    m = {}
    for t in trades:
        mo = t['date'][:7]
        m[mo] = m.get(mo,0) + t['pnl']
    return m

bm = mo_stats(baseline['trades'])
be = mo_stats(best['trades'])
all_mo = sorted(set(bm.keys()) | set(be.keys()))
print(f"\n{'月份':<10}{baseline['name']:<32}{best['name']:<32}{'变化':>8}")
print('-'*90)
for mo in all_mo:
    bv = bm.get(mo,0); ev = be.get(mo,0)
    print(f"  {mo:<8}{bv:>+8.2f}%  {' '*13}{ev:>+8.2f}%  {' '*13}{ev-bv:>+7.2f}% {'↑' if ev>bv else '↓' if ev<bv else '-'}")

bt = sum(bm.values()); et = sum(be.values())
print(f"  {'合计':<8}{bt:>+8.2f}%  {' '*13}{et:>+8.2f}%  {' '*13}{et-bt:>+7.2f}%")

out = {'best': dict(name=best['name'], ret=best['ret'], wr=best['wr'], dd=best['dd'], rr=best['rr'], sh=best['sh']),
       'baseline': dict(name=baseline['name'], ret=baseline['ret'], wr=baseline['wr'], dd=baseline['dd'], rr=baseline['rr'], sh=baseline['sh']),
       'all': [{'name':r['name'],'n':r['n'],'wr':r['wr'],'ret':r['ret'],'dd':r['dd'],'rr':r['rr'],'sh':r['sh'],'score':sc(r)} for r in ranked]}
with open('/home/node/.openclaw/workspace/projects/louie-priceaction-strategy/data/pta_optimization.json','w') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print()
print('Saved: data/pta_optimization.json')
