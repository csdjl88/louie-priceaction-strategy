#!/bin/bash
# 期货信号定时检测脚本 - 后台运行
# 检测时间: 09:30, 13:30, 21:00 (周一至周五)

PROJECT_DIR="/home/node/.openclaw/workspace/projects/louie-priceaction-strategy"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

echo "期货信号定时检测已启动 $(date)"
echo "检测时间: 09:30, 13:30, 21:00 (周一至周五)"

while true; do
    # 获取当前时间和星期几
    now=$(date +%H%M%w)
    hour=$(date +%H)
    minute=$(date +%M)
    weekday=$(date +%w)  # 0=周日, 1=周一, ..., 6=周六
    
    # 只在周一至周五运行 (1-5)
    if [ "$weekday" -ge 1 ] && [ "$weekday" -le 5 ]; then
        current_time="${hour}${minute}"
        
        # 09:30
        if [ "$current_time" = "0930" ]; then
            echo "=== $(date) 日盘信号检测 ===" >> "$LOG_DIR/signal_0930.log"
            cd "$PROJECT_DIR" && bash scripts/signal_check.sh >> "$LOG_DIR/signal_0930.log" 2>&1
            echo "检测完成" >> "$LOG_DIR/signal_0930.log"
            sleep 70  # 避免重复执行
        fi
        
        # 13:30
        if [ "$current_time" = "1330" ]; then
            echo "=== $(date) 午盘信号检测 ===" >> "$LOG_DIR/signal_1330.log"
            cd "$PROJECT_DIR" && bash scripts/signal_check.sh >> "$LOG_DIR/signal_1330.log" 2>&1
            echo "检测完成" >> "$LOG_DIR/signal_1330.log"
            sleep 70
        fi
        
        # 21:00
        if [ "$current_time" = "2100" ]; then
            echo "=== $(date) 夜盘信号检测 ===" >> "$LOG_DIR/signal_2100.log"
            cd "$PROJECT_DIR" && bash scripts/signal_check.sh >> "$LOG_DIR/signal_2100.log" 2>&1
            echo "检测完成" >> "$LOG_DIR/signal_2100.log"
            sleep 70
        fi
    fi
    
    sleep 30
done
