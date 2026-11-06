# -*- coding: utf-8 -*-
"""启动 InfoRadar 服务（端口 7100，含静态页面）。

更新策略（常驻公开站模式）：
- 启动时：距上次成功更新 ≥ STARTUP_STALE_HOURS 小时则立即更新一次；
- 运行中：每隔 CHECK_INTERVAL_MINUTES 检查一次，距上次成功更新
  ≥ PERIODIC_STALE_HOURS 小时就自动刷新，保证内容持续更新。
"""
import logging
import logging.handlers
import os
import threading
import time
from datetime import datetime

import uvicorn

from app import db, load_config, pipeline  # noqa: F401  db 确保建表
from app.api import app

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "docs", "audit")
LOG_PATH = os.path.join(LOG_DIR, "app.log")

# 日志同时写文件与 stderr。
# 写文件是必须的：用 Windows 计划任务托管后进程没有控制台，
# stdout/stderr 会被丢弃；且 uvicorn 通过 log_config=None 复用这套 handler，
# 连访问日志也会带上时间戳（以前 access log 没有时间列，排障很难）。
os.makedirs(LOG_DIR, exist_ok=True)
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_handlers = [
    logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"),
    logging.StreamHandler(),
]
logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT, handlers=_handlers)
log = logging.getLogger("auto-update")

STARTUP_STALE_HOURS = 2
PERIODIC_STALE_HOURS = 4
CHECK_INTERVAL_MINUTES = 30


def _hours_since_last_success():
    for row in db.get_last_logs(10):
        if row["status"] not in ("success", "partial"):
            continue
        try:
            last = datetime.strptime(row["finished_at"], "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            return None
        return (datetime.now() - last).total_seconds() / 3600
    return None


def _run_one_update():
    config = load_config()
    log_id = db.start_update_log()
    try:
        new_count, errors = pipeline.run_update(config)
        if errors:
            db.finish_update_log(log_id, "partial", new_count, "; ".join(errors))
            log.warning("更新完成（部分失败）：新增 %d 条；失败: %s", new_count, errors)
        else:
            db.finish_update_log(log_id, "success", new_count, "")
            log.info("更新完成：新增 %d 条", new_count)
    except Exception as e:
        log.exception("更新失败")
        db.finish_update_log(log_id, "failed", 0, str(e))


def _update_loop():
    first = True
    while True:
        try:
            stale = STARTUP_STALE_HOURS if first else PERIODIC_STALE_HOURS
            hours = _hours_since_last_success()
            if hours is None or hours >= stale:
                log.info("距上次成功更新 %s，开始自动更新",
                         "无记录" if hours is None else f"{hours:.1f} 小时")
                _run_one_update()
            else:
                log.info("距上次成功更新 %.1f 小时（阈值 %d），跳过", hours, stale)
        except Exception:
            log.exception("自动更新线程异常")
        first = False
        time.sleep(CHECK_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    db.init_db()
    threading.Thread(target=_update_loop, daemon=True).start()
    # log_config=None：不让 uvicorn 覆盖上面的 logging 配置，
    # 这样它的 error / access 日志也走同一套 handler（带时间戳、写进文件）
    uvicorn.run(app, host="127.0.0.1", port=7100, log_level="info",
                log_config=None)
