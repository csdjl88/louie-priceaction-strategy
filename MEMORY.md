# 记忆归纳

## 关于用户

- 用户：openclaw-control-ui
- 时区：Asia/Shanghai
- 语言：中文
- 项目：量化交易策略

## 今天完成的工作

### 1. 项目初始化
- 在 `quant-strategy` 目录克隆了 GitHub 项目 `louie-priceaction-strategy`
- 安装了 uv 工具和项目依赖（akshare 等）

### 2. 回测系统
- 修复了 AkShare 数据接口适配问题
- 修改 `backtest_runner.py` 支持做空交易
- 代码已提交到 GitHub

### 3. 2024年回测结果

| 品种 | 代码 | 交易次数 | 胜率 | 收益率 | 最大回撤 |
|:---:|------|:---:|:---:|:---:|:---:|
| 螺纹钢 | rb | 7 | 71.4% | **+42.5%** | 9.4% |
| 橡胶(主力) | RU0 | 14 | 64.3% | **+20.4%** | 13.6% |
| 合成橡胶 | BR0 | 14 | ~43% | **+3.9%** | ~15% |
| 天然橡胶 | NR0 | 12 | 33% | **-8.2%** | 18.7% |

### 4. 2025年数据回测
- 数据获取正常（AKShare 接口可用）
- 由于 exec 权限限制，未能完成回测
- 代码已修复支持做空，等待运行验证

## 技术细节

### AkShare 期货接口
- 使用 `futures_zh_daily_sina(symbol='RB0')` 获取数据
- 品种代码格式：RB0（螺纹钢主力）、RU0（橡胶主力）、NR0（天然橡胶）、BR0（合成橡胶）

### 回测命令
```bash
cd /root/.openclaw/workspace/quant-strategy/louie-priceaction-strategy
.venv/bin/python backtest_runner.py --symbol RB0 --source akshare --days 500
```

## 待办
- 完成 2025 年数据的回测验证
- 可能需要优化 NR0/BR0 的策略参数

## 教训
- 2024 年策略在螺纹钢和橡胶主力上表现优秀
- 天然橡胶和合成橡胶需要参数优化
- AkShare API 可能随时变化，需要注意适配