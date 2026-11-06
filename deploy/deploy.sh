#!/usr/bin/env bash
# ============================================================================
# InfoRadar 更新部署脚本（改完代码后把新版本推上服务器用）
#
# 用法（服务器上，项目目录内）：
#   sudo bash deploy/deploy.sh
#
# 做四件事：备份数据库 → 同步代码（保留 data/ 与 config.yaml）→ 装依赖 → 重启
# ============================================================================
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/inforadar}"
APP_USER="${APP_USER:-inforadar}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log()  { printf '\033[1;36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
die()  { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "请用 root 运行：sudo bash deploy/deploy.sh"
[[ -f "$SRC_DIR/run.py" ]] || die "找不到 run.py（SRC_DIR=$SRC_DIR）"

if [[ "$SRC_DIR" != "$INSTALL_DIR" ]]; then
  log "1/4 备份当前数据库"
  [[ -x "$INSTALL_DIR/deploy/backup.sh" ]] && bash "$INSTALL_DIR/deploy/backup.sh" || true

  log "2/4 同步代码 $SRC_DIR -> $INSTALL_DIR"
  rsync -a \
    --exclude='/config.yaml' --exclude='/data' --exclude='/.venv' \
    --exclude='/.cloudflared' --exclude='.git' --exclude='__pycache__' \
    --exclude='deploy/' --exclude='已停用启动项/' --exclude='NVIDIA Corporation/' \
    "$SRC_DIR"/ "$INSTALL_DIR"/
else
  log "1-2/4 已在 $INSTALL_DIR 内运行，跳过同步（仅备份 + 重启）"
  [[ -x "$INSTALL_DIR/deploy/backup.sh" ]] && bash "$INSTALL_DIR/deploy/backup.sh" || true
fi

log "3/4 安装/更新依赖"
[[ -x "$INSTALL_DIR/.venv/bin/python" ]] || die "虚拟环境不存在，先跑 install.sh"
REQ="$INSTALL_DIR/deploy/requirements.txt"
[[ -f "$REQ" ]] || REQ="$SRC_DIR/deploy/requirements.txt"
"$INSTALL_DIR/.venv/bin/python" -m pip install -q -r "$REQ"

chown -R "$APP_USER:$APP_USER" "$INSTALL_DIR"
chmod 0600 "$INSTALL_DIR/config.yaml" 2>/dev/null || true

log "4/4 重启服务"
systemctl restart inforadar.service
sleep 4
systemctl --no-pager --lines=8 status inforadar.service || true
echo
curl -sS --max-time 10 http://127.0.0.1:7100/api/status | head -c 400 || true
echo
log "完成"
