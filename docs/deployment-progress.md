# InfoRadar 常驻域名部署 — 进度交接（2026-09-09 午更新）

> 给下一次会话的 AI：用户说"继续 InfoRadar 部署"时，读本文件继续。项目在 `D:\KimiData\kimi\workspace\info-radar`，本地服务端口 7100（`python run.py` 启动，已设开机自启）。

## 目标
把 InfoRadar（本地 FastAPI 资讯站，端口 7100）通过 **Cloudflare Tunnel** 暴露为公网站点 `https://inforadar.xin`，无登录、面向大众免费访问。

## 已完成
1. 应用改造：API 限流（`app/api.py` RateLimitMiddleware：搜索 10/分+50/天/IP+全站 300/天；/api/update 30 分钟 1 次；/api/word 30/分）
2. 周期自动更新（`run.py` `_update_loop`：启动时 >2h 未更新立即更新；常驻期间每 30 分钟检查、>4h 自动刷新）
3. 开机自启：Startup 文件夹 `InfoRadar.lnk`（pythonw 无窗口运行 run.py）
4. 修复历史问题：量子位源被 WAF 拦截已换成极客公园（config.yaml）；db.py init_db 启动时清理中断的 running 日志
5. cloudflared 2026.8.3 已通过 winget 安装（`C:\Program Files (x86)\cloudflared\cloudflared.exe`）
6. 域名 `inforadar.xin` 已购于阿里云，已添加进 Cloudflare（Free 计划），CF 分配的 NS：`arturo.ns.cloudflare.com` / `vita.ns.cloudflare.com`，用户已在阿里云提交 NS 替换
7. **2026-09-09 12:58 完成 cloudflared 授权**：`C:\Users\xinru\.cloudflared\cert.pem` 已生成（浏览器授权页是中文界面，用 pyautogui 屏幕点击完成：先点域名行 (1455,567)，再点弹出的「授权」按钮 (2066,379)）
8. **隧道已创建**：`inforadar`，ID `6dcf1767-00f2-48fc-90d0-a329db4f9f14`，凭据 `C:\Users\xinru\.cloudflared\6dcf1767-00f2-48fc-90d0-a329db4f9f14.json`
9. **配置文件已写好**：`C:\Users\xinru\.cloudflared\config.yml`（ingress: inforadar.xin → http://localhost:7100）
10. **DNS 路由已绑定**：`cloudflared tunnel route dns` 成功，CNAME inforadar.xin → 隧道
11. **常驻方案已落地**：`cloudflared service install` 因无管理员权限失败，改用 Startup 文件夹 `CloudflareTunnel.lnk`（`cloudflared tunnel run inforadar`，最小化窗口）
12. **隧道当前正在运行**并已连接 4 个 CF 边缘节点（`cloudflared tunnel info inforadar` 可见 CONNECTOR）

## 🎉 部署完成（2026-09-09 14:10）
- **https://inforadar.xin 已上线，公网访问 HTTPS 200**，页面内容验证正常（"InfoRadar · 个人资讯雷达"）
- Cloudflare 区域已激活，A 记录已生效（CF 边缘 IP 172.67.137.134 / 104.21.78.211）
- 已处理版权风险：config.yaml `fetch_full_content: false`（只展示摘要+原文链接），服务已重启生效
- 自动监控 cron 已在上线确认后删除

## 运维速查
- 本地服务：`python run.py`（开机自启 InfoRadar.lnk），隧道：`cloudflared tunnel run inforadar`（开机自启 CloudflareTunnel.lnk）
- 隧道状态检查：`cloudflared tunnel info inforadar`
- 注意本机宿舍网劫持 53 端口 DNS，本机查域名/验证要用 DoH（`--doh-url https://doh.pub/dns-query` 或 doh.pub JSON API）；公网访客不受影响

## 历史待办（已全部完成）
1. **等 Cloudflare 区域激活**（自动，最长 24 小时，通常 1-2 小时内）
2. 激活后 `https://inforadar.xin` 公网可访问即全部完成（cron 会自动验证）
3. 提醒用户决定：`config.yaml` 的 `fetch_full_content: true` 公开站有版权风险，建议改 false

## 环境备忘
- 用户：Rain（大学生，中文交流），Windows，Git Bash 在 `D:\git\git\Git\bin\bash.exe`
- Windows 命令注意：schtasks 需 `MSYS_NO_PATHCONV=1` 前缀；iconv 不可用；控制台输出 GBK 中文会乱码（不影响功能）
- 打开浏览器链接用 `powershell -NoProfile -Command "Start-Process '<url>'"`（cmd start 对带 & 的 URL 会解析失败）
- 屏幕 2560x1440，PIL ImageGrab + pyautogui 可做 GUI 自动化（用户已授权全权操控电脑）
- GitHub 直连下载慢，优先用 winget 安装软件
