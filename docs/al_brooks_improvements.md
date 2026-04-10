# Al Brooks Price Action 理念落地笔记
# ======================================

> 目标：用代码实现 Al Brooks 价格行为学的核心思想

---

## 1. 三种市场状态识别

### 状态定义

| 状态 | 条件 | 交易策略 |
|------|-------|---------|
| **趋势（Trend）** |  EMA20 > EMA50（多头趋势）或 EMA20 < EMA50（空头趋势） | 顺势回调入场（H1/H2） |
| **震荡（Trading Range）** | 价格在 EMA20 上下穿梭，方向不明 | 边界高抛低吸，止损在区间外 |
| **过渡（Transition）** | 突破均线后停滞，或趋势减弱 | 观望，等待下一根确认 |

### 代码实现

```python
def identify_market_state(closes, ema_fast, ema_slow):
    """
    识别市场状态
    返回: 'trend_bull', 'trend_bear', 'range', 'transition'
    """
    ema_diff = ema_fast - ema_slow
    ema_diff_pct = ema_diff / ema_slow * 100
    
    # 趋势判断
    if ema_diff_pct > 0.5:  # EMA 开口扩张
        return 'trend_bull'
    elif ema_diff_pct < -0.5:
        return 'trend_bear'
    elif abs(ema_diff_pct) < 0.2:
        return 'range'
    else:
        return 'transition'
```

---

## 2. 入场方式：H1 / H2 回调

### Brooks 的核心

- **H1** = 趋势中的第一次回调（较激进）
- **H2** = 趋势中的第二次回调（更可靠）
- **最好**的入场 = 趋势中的 H2，在支撑区域，有看涨 K 线确认

### H1 / H2 的代码识别

```python
def detect_h1_h2_pullback(opens, highs, lows, closes, idx, trend):
    """
    检测 H1 / H2 回调入场点
    
    H1: 趋势中第一根逆势回调 K 线
    H2: 趋势中第二根逆势回调 K 线（在 H1 之后）
    
    返回: 'h1', 'h2', 或 None
    """
    if idx < 3:
        return None
    
    # 检测回调：K 线逆趋势方向移动
    if trend == 'trend_bull':
        # 回调特征：K 线低点低于前一根低点
        pullback_count = 0
        for i in range(idx, max(0, idx-5), -1):
            if lows[i] < lows[i-1]:
                pullback_count += 1
            else:
                break
        return 'h2' if pullback_count >= 2 else 'h1'
    
    elif trend == 'trend_bear':
        # 空头趋势中，价格反弹
        pullback_count = 0
        for i in range(idx, max(0, idx-5), -1):
            if highs[i] > highs[i-1]:
                pullback_count += 1
            else:
                break
        return 'h2' if pullback_count >= 2 else 'h1'
    
    return None
```

---

## 3. 假突破识别（Fakeout Filter）

### Brooks 的关键洞察

> "大部分突破是假的，是机构收割韭菜的手段"

### 假突破特征

| 类型 | 特征 |
|------|------|
| 假突破（真反向） | 突破后迅速拉回，K 线实体收回区间内 |
| 突破后盘整 | 突破后连续小 K 线，不加速 |
| 真突破 | 突破后连续大实体 K 线，加速离开 |

### 代码实现

```python
def is_fake_breakout(highs, lows, closes, idx, breakout_level, direction='up'):
    """
    判断是否为假突破
    direction: 'up' = 假突破上方，'down' = 假突破下方
    """
    if direction == 'up':
        # 真突破：收盘价在突破位上方，且有加速
        if closes[idx] < breakout_level:
            return True  # 假突破
        # 真突破特征：收盘在高位，且高于前一根
        return closes[idx] > closes[idx-1] and closes[idx] > max(closes[idx-2:idx])
    else:
        if closes[idx] > breakout_level:
            return True  # 假突破
        return closes[idx] < closes[idx-1] and closes[idx] < min(closes[idx-2:idx])
```

---

## 4. 支撑阻力区域（Zone）替代精确线

### Brooks 的观点

> 支撑阻力不是精确的线，而是**区域**

```python
def get_support_resistance_zone(highs, lows, closes, idx, lookback=20):
    """
    计算支撑/阻力区域（Zone）
    返回: (support_zone, resistance_zone)
    """
    recent_lows = sorted(lows[idx-lookback:idx])[:5]
    recent_highs = sorted(highs[idx-lookback:idx], reverse=True)[:5]
    
    # 支撑区域 = 近期低点的密集区
    support_zone = (min(recent_lows), sum(recent_lows)/len(recent_lows))
    resistance_zone = (sum(recent_highs)/len(recent_highs), max(recent_highs))
    
    return support_zone, resistance_zone
```

---

## 5. K 线形态优先级

Brooks 最重视的形态（按重要性排序）：

| 优先级 | 形态 | 信号强度 |
|--------|------|---------|
| ⭐⭐⭐ | 吞没（Engulfing） | 强反转 |
| ⭐⭐⭐ | Pin Bar / 锤子线 | 强反转 |
| ⭐⭐ | Inside Bar | 中继/反转 |
| ⭐⭐ | 十字星（Doji） | 多空平衡 |
| ⭐ | Trend Bar（大实体） | 趋势延续 |

### 吞没检测代码

```python
def is_engulfing(opens, highs, lows, closes, idx):
    """
    检测看涨/看跌吞没形态
    """
    if idx < 1:
        return None
    
    prev_body_top = max(opens[idx-1], closes[idx-1])
    prev_body_bot = min(opens[idx-1], closes[idx-1])
    curr_body_top = max(opens[idx], closes[idx])
    curr_body_bot = min(opens[idx], closes[idx])
    
    # 看涨吞没：今日 K 线实体完全包裹昨日
    if curr_body_bot < prev_body_bot and curr_body_top > prev_body_top and closes[idx] > opens[idx]:
        return 'bullish_engulfing'
    
    # 看跌吞没
    if curr_body_top > prev_body_top and curr_body_bot < prev_body_bot and closes[idx] < opens[idx]:
        return 'bearish_engulfing'
    
    return None
```

---

## 6. 完整的 Brooks 式信号检测流程

```python
def brooks_signal(opens, highs, lows, closes, idx):
    """
    完整的 Brooks 式信号检测
    
    流程：
    1. 识别市场状态（趋势/震荡/过渡）
    2. 在趋势中找 H1/H2 回调
    3. 在边界找 K 线形态确认
    4. 过滤假突破
    5. 给出入场/止损/目标
    """
    # Step 1: 市场状态
    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    state = identify_market_state(closes, ema20, ema50)
    
    # Step 2: H1/H2 回调
    pullback = detect_h1_h2_pullback(opens, highs, lows, closes, idx, state)
    
    # Step 3: K 线形态
    pattern = detect_key_pattern(opens, highs, lows, closes, idx)
    
    # Step 4: 综合信号
    if state == 'trend_bull' and pullback in ('h1', 'h2'):
        if pattern in ('bullish_engulfing', 'hammer', 'bullish_pin_bar'):
            return Signal(
                action='long',
                entry=closes[idx],
                stop_loss=lows[idx] - 2 * atr,
                target=closes[idx] + 6 * atr,
                confidence=0.8 if pullback == 'h2' else 0.6,
                reason=f'{pullback.upper()} pullback in uptrend with {pattern}'
            )
    
    elif state == 'trend_bear' and pullback in ('h1', 'h2'):
        if pattern in ('bearish_engulfing', 'shooting_star', 'bearish_pin_bar'):
            return Signal(
                action='short',
                entry=closes[idx],
                stop_loss=highs[idx] + 2 * atr,
                target=closes[idx] - 6 * atr,
                confidence=0.8 if pullback == 'h2' else 0.6,
                reason=f'{pullback.upper()} pullback in downtrend with {pattern}'
            )
    
    return Signal(action='none')
```

---

## 7. 与现有策略的对比

| Brooks 理念 | 现有实现 | 差距 |
|------------|---------|------|
| 市场状态识别 | EMA20/EMA50 | ⚠️ 只有趋势判断，无震荡/过渡 |
| H1/H2 入场 | 回踩入场 | ⚠️ 未区分 H1/H2 |
| 吞没/Pin Bar | 有检测 | ✅ 已有 |
| Inside Bar | 有检测 | ✅ 已有 |
| 假突破过滤 | ❌ 无 | 需增加 |
| 支撑阻力 Zone | 精确止损价 | ⚠️ 需改成区域 |
| K 线故事解读 | 无 | 部分已有 |

---

## 8. 改进优先级

1. **P0 - 立即实现**：增加市场状态识别（趋势/震荡/过渡）
2. **P1 - 高优先级**：增加 H1/H2 回调检测，区分第一次/第二次入场
3. **P1 - 高优先级**：增加假突破过滤
4. **P2 - 中优先级**：支撑阻力改为 Zone
5. **P3 - 低优先级**：完整的 Brooks 信号流程

---

## 参考资料

- Brooks Trading Course (brookspriceaction.com) - 98+ 小时视频课程
- Trading Price Action Trends / Ranges / Reversals 三部曲
- Brooks Price Action Pro (TradingView 指标)
