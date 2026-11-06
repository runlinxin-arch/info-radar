#!/usr/bin/env bash
# ============================================================================
# InfoRadar 云服务器一键安装脚本
#
# 适用：全新 Ubuntu 22.04 / 24.04（Debian 12 亦可）云服务器
# 作用：装依赖 → 建用户 → 部署到 /opt/inforadar → 起 systemd 服务
#       → 装 cloudflared → 起隧道 → 本机自检
#
# 用法（在服务器上，解包后的目录里执行）：
#   sudo bash install.sh
#
# 幂等：可以重复执行，会保留已有 data/radar.db 与 config.yaml
# ============================================================================
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/inforadar}"
APP_USER="${APP_USER:-inforadar}"
TUNNEL_ID="6dcf1767-00f2-48fc-90d0-a329db4f9f14"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log()  { printf '\033[1;36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "请用 root 运行：sudo bash install.sh"
[[ -f "$SRC_DIR/run.py" ]] || die "找不到 run.py，请在解包后的项目目录里运行本脚本（当前 SRC_DIR=$SRC_DIR）"

log "源目录: $SRC_DIR"
log "安装目录: $INSTALL_DIR"

# ---------------------------------------------------------------- 1. 系统依赖
log "步骤 1/8 安装系统依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  python3 python3-venv python3-pip \
  ca-certificates curl gnupg tzdata sqlite3 rsync \
  >/dev/null

PY_VER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
log "系统 Python: $PY_VER"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
  || die "需要 Python >= 3.10，当前 $PY_VER"

# ------------------------------------------------------------ 2. cloudflared
if ! command -v cloudflared >/dev/null 2>&1; then
  log "步骤 2/8 安装 cloudflared"
  ARCH="$(dpkg --print-architecture)"   # amd64 / arm64
  CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}"
  if ! curl -fsSL --retry 3 --connect-timeout 15 -o /usr/local/bin/cloudflared "$CF_URL"; then
    warn "GitHub 直连失败，改用 Cloudflare 官方源 pkg.cloudflare.com"
    mkdir -p /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
      -o /usr/share/keyrings/cloudflare-main.gpg
    echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
      > /etc/apt/sources.list.d/cloudflared.list
    apt-get update -qq && apt-get install -y -qq cloudflared >/dev/null
  fi
  [[ -f /usr/local/bin/cloudflared ]] && chmod 0755 /usr/local/bin/cloudflared
else
  log "步骤 2/8 cloudflared 已存在，跳过安装"
fi
command -v cloudflared >/dev/null || [[ -x /usr/local/bin/cloudflared ]] \
  || die "cloudflared 安装失败"
cloudflared --version || true

# ------------------------------------------------------------------ 3. 建用户
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  log "步骤 3/8 创建系统用户 $APP_USER"
  useradd --system --create-home --home-dir "/home/$APP_USER" --shell /usr/sbin/nologin "$APP_USER"
else
  log "步骤 3/8 用户 $APP_USER 已存在"
fi
getent group cloudflared >/dev/null || groupadd --system cloudflared
id -u cloudflared >/dev/null 2>&1 || \
  useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin cloudflared

# --------------------------------------------------------------- 4. 同步代码
log "步骤 4/8 同步代码到 $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
# 保留服务器上已有的 config.yaml / data/，不被覆盖
# 注意：排除模式要用前导 / 锚定到顶层，否则 `data` 会连带排除 app/data/（习语词典）
PRESERVE=()
[[ -f "$INSTALL_DIR/config.yaml" ]] && PRESERVE+=(--exclude=/config.yaml)
[[ -d "$INSTALL_DIR/data" ]]        && PRESERVE+=(--exclude=/data)
[[ -d "$INSTALL_DIR/.venv" ]]       && PRESERVE+=(--exclude=/.venv)
[[ -d "$INSTALL_DIR/.cloudflared" ]] && PRESERVE+=(--exclude=/.cloudflared)
rsync -a "${PRESERVE[@]}" \
  --exclude='.git' --exclude='__pycache__' --exclude='deploy/' \
  --exclude='已停用启动项/' --exclude='NVIDIA Corporation/' \
  "$SRC_DIR"/ "$INSTALL_DIR"/

# 凭据目录
mkdir -p "$INSTALL_DIR/.cloudflared"
CRED_SRC=""
for cand in "$SRC_DIR/.cloudflared/$TUNNEL_ID.json" \
            "$SRC_DIR/deploy/cloudflared/$TUNNEL_ID.json" \
            "/root/$TUNNEL_ID.json"; do
  [[ -f "$cand" ]] && CRED_SRC="$cand" && break
done
if [[ -n "$CRED_SRC" ]]; then
  install -m 0600 -o cloudflared -g cloudflared \
    "$CRED_SRC" "$INSTALL_DIR/.cloudflared/$TUNNEL_ID.json"
  log "已安装隧道凭据: $CRED_SRC"
elif [[ -f "$INSTALL_DIR/.cloudflared/$TUNNEL_ID.json" ]]; then
  chown cloudflared:cloudflared "$INSTALL_DIR/.cloudflared/$TUNNEL_ID.json"
  chmod 0600 "$INSTALL_DIR/.cloudflared/$TUNNEL_ID.json"
  log "服务器上已有隧道凭据，保留"
else
  warn "未找到隧道凭据 $TUNNEL_ID.json —— 隧道无法启动！"
  warn "请把本机的 6dcf1767-....json 上传到 $INSTALL_DIR/.cloudflared/ 后执行："
  warn "  systemctl restart cloudflared-inforadar"
fi

sed "s#<INSTALL_DIR>#$INSTALL_DIR#g" \
  "$SRC_DIR/deploy/cloudflared/config.yml" > "$INSTALL_DIR/.cloudflared/config.yml"
chown -R cloudflared:cloudflared "$INSTALL_DIR/.cloudflared"
chmod 0644 "$INSTALL_DIR/.cloudflared/config.yml"
[[ -f "$INSTALL_DIR/.cloudflared/$TUNNEL_ID.json" ]] && \
  chmod 0600 "$INSTALL_DIR/.cloudflared/$TUNNEL_ID.json"
chmod 0700 "$INSTALL_DIR/.cloudflared"

# config.yaml 兜底
if [[ ! -f "$INSTALL_DIR/config.yaml" ]]; then
  [[ -f "$SRC_DIR/config.yaml" ]] || die "缺少 config.yaml（含 Tavily key），无法启动"
  cp "$SRC_DIR/config.yaml" "$INSTALL_DIR/config.yaml"
  warn "从包内复制了 config.yaml —— 请确认其中的 tavily.api_key 是你打算在服务器上用的那把"
fi
chmod 0600 "$INSTALL_DIR/config.yaml"

mkdir -p "$INSTALL_DIR/data"
for extra in run.py update.py app static docs; do
  [[ -e "$INSTALL_DIR/$extra" ]] || warn "缺少 $extra"
done

# deploy/ 下面有 requirements.txt 和运维脚本，服务器上要留一份
mkdir -p "$INSTALL_DIR/deploy"
cp -a "$SRC_DIR/deploy/." "$INSTALL_DIR/deploy/"
chmod +x "$INSTALL_DIR/deploy/"*.sh 2>/dev/null || true
REQ="$INSTALL_DIR/deploy/requirements.txt"
[[ -f "$REQ" ]] || REQ="$SRC_DIR/deploy/requirements.txt"
[[ -f "$REQ" ]] || die "找不到 requirements.txt"

# ------------------------------------------------------- 5. 虚拟环境与依赖
log "步骤 5/8 创建虚拟环境并安装 Python 依赖（约 1-3 分钟）"
if [[ ! -x "$INSTALL_DIR/.venv/bin/python" ]]; then
  python3 -m venv "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip wheel >/dev/null
"$INSTALL_DIR/.venv/bin/python" -m pip install -r "$REQ"

chown -R "$APP_USER:$APP_USER" "$INSTALL_DIR"
chmod 0600 "$INSTALL_DIR/config.yaml"   # chown -R 不会改权限，再确认一次
chmod 0700 "$INSTALL_DIR/.cloudflared" 2>/dev/null || true

# ------------------------------------------------------------ 6. systemd 单元
log "步骤 6/8 安装 systemd 服务"
install -m 0644 "$SRC_DIR/deploy/systemd/inforadar.service" \
  /etc/systemd/system/inforadar.service
install -m 0644 "$SRC_DIR/deploy/systemd/cloudflared-inforadar.service" \
  /etc/systemd/system/cloudflared-inforadar.service
systemctl daemon-reload
systemctl enable inforadar.service cloudflared-inforadar.service >/dev/null

# ------------------------------------------------------------------ 7. 启动
log "步骤 7/8 启动服务"
systemctl restart inforadar.service
# 等应用监听 7100
for i in $(seq 1 30); do
  if curl -fsS --max-time 3 http://127.0.0.1:7100/ -o /dev/null 2>/dev/null; then
    log "应用已在 127.0.0.1:7100 就绪（等待 ${i}s）"
    break
  fi
  [[ $i -eq 30 ]] && warn "30 秒内未就绪，下面会打印日志"
  sleep 1
done
systemctl restart cloudflared-inforadar.service
sleep 5

# ------------------------------------------------------------------ 8. 自检
log "步骤 8/8 自检"
echo
echo "──── inforadar.service ────"
systemctl --no-pager --lines=10 status inforadar.service || true
echo
echo "──── cloudflared-inforadar.service ────"
systemctl --no-pager --lines=10 status cloudflared-inforadar.service || true
echo
echo "──── 隧道连接器 ────"
cloudflared tunnel info "$TUNNEL_ID" 2>/dev/null || \
  warn "tunnel info 失败（可能需要 cert.pem，不影响隧道运行）"
echo
echo "──── 本机 API ────"
curl -sS --max-time 10 http://127.0.0.1:7100/api/status | head -c 600 || warn "本机 API 未响应"
echo; echo
echo "──── 公网域名 ────"
curl -sS -o /dev/null -w 'HTTP %{http_code}  耗时 %{time_total}s\n' \
  --max-time 25 https://inforadar.xin/ || warn "公网访问失败，见 迁移指南.md 排错章节"

cat <<EOF

============================================================================
安装完成。日常运维命令：

  查看应用日志    journalctl -u inforadar -f
  查看隧道日志    journalctl -u cloudflared-inforadar -f
  重启应用        systemctl restart inforadar
  手动触发抓取    curl -X POST http://127.0.0.1:7100/api/update
  数据库备份      bash $INSTALL_DIR/deploy/backup.sh

别忘了：现在去把 Windows 笔记本上的旧隧道停掉（见 迁移指南.md 第 6 步），
否则两台机器会用同一个隧道 ID 抢占连接。
============================================================================
EOF
