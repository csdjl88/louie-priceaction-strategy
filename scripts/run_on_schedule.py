#!/usr/bin/env python3
"""
run_on_schedule.py - 按国内期货开盘时间自动运行 auto_trader
========================================================

使用 systemd 定时器管理，确保只在交易时间运行：
  日盘：周一~周五 08:55 ~ 15:05
  夜盘：周一~周五 20:55 ~ 02:05（次日）

使用方法:
  # 安装定时器
  python run_on_schedule.py --install

  # 手动启动/停止
  python run_on_schedule.py --start
  python run_on_schedule.py --stop

  # 查看状态
  python run_on_schedule.py --status
"""

import argparse
import os
import sys
import subprocess
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.join(PROJECT_DIR, 'scripts')
AUTO_TRADER = os.path.join(SCRIPT_DIR, 'auto_trader.py')
LOGS_DIR = os.path.join(PROJECT_DIR, 'logs')
UNIT_DIR = os.path.expanduser('~/.config/systemd/user')

LOCK_FILE = os.path.join(LOGS_DIR, 'auto_trader.lock')
SERVICE_NAME = 'auto-trader'


def write_unit(name: str, content: str):
    os.makedirs(UNIT_DIR, exist_ok=True)
    path = os.path.join(UNIT_DIR, name)
    with open(path, 'w') as f:
        f.write(content)
    print(f"已写入: {path}")


def install_systemd():
    """安装 systemd 定时器（需要 systemd 环境）"""
    unit = f"""[Unit]
Description=Louie PriceAction Auto Trader
After=network-online.target

[Service]
Type=simple
WorkingDirectory={PROJECT_DIR}
Environment=UV_CACHE_DIR={PROJECT_DIR}/.uv-cache
ExecStart=/home/node/.local/bin/uv run python {AUTO_TRADER} --capital 100000
Restart=no
StandardOutput=append:{LOGS_DIR}/systemd.log
StandardError=append:{LOGS_DIR}/systemd.log

[Install]
WantedBy=multi-user.target
"""

    timer = """[Unit]
Description=Louie PriceAction Auto Trader - 按期货开盘时间调度
Requires=auto-trader.service

[Timer]
OnCalendar=Mon..Fri 08:55:00
Unit=auto-trader.service

OnCalendar=Tue..Sat 02:05:00
Unit=auto-trader.service

[Install]
WantedBy=timers.target
"""

    write_unit(f'{SERVICE_NAME}.service', unit)
    write_unit(f'{SERVICE_NAME}.timer', timer)

    subprocess.run(['systemctl', '--user', 'daemon-reload'], capture_output=True)
    result = subprocess.run(['systemctl', '--user', 'enable', '--now', f'{SERVICE_NAME}.timer'],
                          capture_output=True, text=True)
    if result.returncode != 0:
        print("systemd 不可用，请手动设置 cron 或使用 --nohup 方式运行")
        print(f"Unit 文件已生成在: {UNIT_DIR}/")
        return

    print()
    print("✅ systemd 定时器已安装！")
    print(f"  Service: {SERVICE_NAME}.service")
    print(f"  Timer:   {SERVICE_NAME}.timer")
    print()
    print("日盘: 周一~周五 08:55 ~ 15:05")
    print("夜盘: 周一~周五 20:55 ~ 02:05（次日）")
    print()
    print("常用命令:")
    print(f"  systemctl --user status {SERVICE_NAME}")
    print(f"  systemctl --user stop {SERVICE_NAME}")
    print(f"  journalctl --user -u {SERVICE_NAME} -f")


def uninstall():
    subprocess.run(['systemctl', '--user', 'stop', f'{SERVICE_NAME}.timer'], capture_output=True)
    subprocess.run(['systemctl', '--user', 'disable', f'{SERVICE_NAME}.timer'], capture_output=True)
    for f in [f'{SERVICE_NAME}.service', f'{SERVICE_NAME}.timer']:
        p = os.path.join(UNIT_DIR, f)
        if os.path.exists(p):
            os.remove(p)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], capture_output=True)
    print("已卸载 systemd 定时器")


def start():
    os.makedirs(LOGS_DIR, exist_ok=True)
    # 使用 lock file 防止重复
    if os.path.exists(LOCK_FILE):
        pid = int(open(LOCK_FILE).read().strip())
        try:
            os.kill(pid, 0)
            print(f"进程已在运行 (PID {pid})")
            return
        except OSError:
            pass

    log_file = os.path.join(LOGS_DIR, f'auto_trader_{time.strftime("%Y%m%d_%H%M%S")}.log')
    env = os.environ.copy()
    env['UV_CACHE_DIR'] = f'{PROJECT_DIR}/.uv-cache'

    proc = subprocess.Popen(
        ['/home/node/.local/bin/uv', 'run', 'python', AUTO_TRADER, '--capital', '100000'],
        cwd=PROJECT_DIR,
        env=env,
        stdout=open(log_file, 'a'),
        stderr=subprocess.STDOUT,
    )
    with open(LOCK_FILE, 'w') as f:
        f.write(str(proc.pid))
    print(f"已启动 PID {proc.pid}，日志: {log_file}")


def stop():
    if os.path.exists(LOCK_FILE):
        pid = int(open(LOCK_FILE).read().strip())
        try:
            os.kill(pid, 15)
            time.sleep(2)
            print(f"已停止 PID {pid}")
        except OSError:
            print(f"PID {pid} 不存在")
        os.remove(LOCK_FILE)
    else:
        print("进程未运行")


def status():
    if os.path.exists(LOCK_FILE):
        pid = int(open(LOCK_FILE).read().strip())
        try:
            os.kill(pid, 0)
            print(f"运行中 (PID {pid})")
        except OSError:
            print("Lock 文件存在但进程已停止")
    else:
        print("未运行")

    # 也检查 systemd
    result = subprocess.run(['systemctl', '--user', 'is-active', f'{SERVICE_NAME}.timer'],
                         capture_output=True, text=True)
    print(f"定时器状态: {result.stdout.strip()}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--install', action='store_true', help='安装 systemd 定时器')
    parser.add_argument('--uninstall', action='store_true', help='卸载定时器')
    parser.add_argument('--start', action='store_true', help='手动启动')
    parser.add_argument('--stop', action='store_true', help='手动停止')
    parser.add_argument('--status', action='store_true', help='查看状态')
    args = parser.parse_args()

    if args.install:
        install_systemd()
    elif args.uninstall:
        uninstall()
    elif args.start:
        start()
    elif args.stop:
        stop()
    elif args.status:
        status()
    else:
        parser.print_help()
