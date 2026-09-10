# -*- coding: utf-8 -*-
"""独立更新脚本：供定时任务（schtasks）与手动调用。

用法: python update.py
退出码: 0=全部成功, 1=部分源失败, 2=更新失败
"""
import logging
import sys

from app import load_config, db, pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("update")


def main():
    db.init_db()
    config = load_config()
    log_id = db.start_update_log()
    try:
        new_count, errors = pipeline.run_update(config)
        if errors:
            db.finish_update_log(log_id, "partial", new_count, "; ".join(errors))
            log.warning("更新完成（部分失败）：新增 %d 条；失败: %s", new_count, errors)
            return 1
        db.finish_update_log(log_id, "success", new_count, "")
        log.info("更新完成：新增 %d 条", new_count)
        return 0
    except Exception as e:
        log.exception("更新失败")
        db.finish_update_log(log_id, "failed", 0, str(e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
