#!/usr/bin/env bash
# ============================================================================
# InfoRadar 数据库 + 配置备份
#
# 用法：bash /opt/inforadar/deploy/backup.sh
# 建议加进 crontab：  0 3 * * * bash /opt/inforadar/deploy/backup.sh >/dev/null 2>&1
#
# WAL 模式下不能用 cp 直接拷 radar.db —— 必须用 .backup / VACUUM INTO，
# 否则会丢 -wal 里还没合并的事务。
# ============================================================================
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/inforadar}"
KEEP_DAYS="${KEEP_DAYS:-14}"
DEST="${DEST:-$INSTALL_DIR/backups}"

mkdir -p "$DEST"
STAMP="$(date +%Y%m%d-%H%M%S)"

# SQLite 在线备份（安全，不影响正在跑的服务）
if [[ -f "$INSTALL_DIR/data/radar.db" ]]; then
  sqlite3 "$INSTALL_DIR/data/radar.db" ".backup '$DEST/radar-$STAMP.db'"
  gzip -9 "$DEST/radar-$STAMP.db"
  echo "已备份数据库: $DEST/radar-$STAMP.db.gz ($(du -h "$DEST/radar-$STAMP.db.gz" | cut -f1))"
else
  echo "跳过：$INSTALL_DIR/data/radar.db 不存在"
fi

# 配置（含密钥，权限收紧）
if [[ -f "$INSTALL_DIR/config.yaml" ]]; then
  install -m 0600 "$INSTALL_DIR/config.yaml" "$DEST/config-$STAMP.yaml"
  echo "已备份配置: $DEST/config-$STAMP.yaml"
fi

# 清理过期备份
find "$DEST" -maxdepth 1 -type f \( -name 'radar-*.db.gz' -o -name 'config-*.yaml' \) \
  -mtime "+$KEEP_DAYS" -delete 2>/dev/null || true
echo "保留最近 $KEEP_DAYS 天，当前备份文件数: $(find "$DEST" -maxdepth 1 -type f | wc -l)"
