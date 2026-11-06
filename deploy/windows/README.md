# Windows 计划任务托管（应用 + 隧道）

用 Windows 计划任务代替「启动文件夹快捷方式」和「会话内 `Start-Process`」，让 InfoRadar 在**会话重启、进程崩溃**后自动恢复。

---

## 为什么换掉旧方式

| 旧方式 | 问题 |
|---|---|
| 启动文件夹快捷方式 | 实测失效：2026-11-06 开机后两个进程都没启动（公网 1033） |
| 在 AI 会话里 `Start-Process` | 进程是本会话的子进程，会话一重启就被连带杀掉（2026-11-06 14:13，中断 17 分钟） |

计划任务由 **Task Scheduler 服务**启动，不挂在任何终端会话上，因此会话重启不会影响它。

---

## 安装 / 卸载

```powershell
# 安装（不需要管理员权限）
powershell -ExecutionPolicy Bypass -File deploy\windows\install_tasks.ps1

# 卸载
powershell -ExecutionPolicy Bypass -File deploy\windows\uninstall_tasks.ps1
```

安装后会注册两个任务：

| 任务名 | 作用 |
|---|---|
| `InfoRadar-App` | `pythonw run.py`（FastAPI，127.0.0.1:7100） |
| `InfoRadar-Tunnel` | `cloudflared tunnel run inforadar` |

---

## 自愈机制（关键）

**两个触发器 + 单实例策略 = 看门狗**

```
TimeTrigger   每 1 分钟触发一次（无限重复）
LogonTrigger  登录时立即启动
MultipleInstancesPolicy = IgnoreNew   ← 已在跑就忽略
```

含义：*没在跑就拉起来，正在跑就不管*。所以进程被杀后，最多 1 分钟自动恢复。

> **实测**（2026-11-06）：
> - 强杀应用 → **25 秒**恢复
> - 强杀隧道 → **42 秒**恢复，连接器重新注册，公网恢复 200

### 两个踩过的坑（不要重犯）

1. **`<RestartOnFailure>` 单独使用无效**
   强杀交互式任务后，任务结果是 `0xFFFFFFFF`，等了 85 秒也没有重启。

2. **`<Repetition>` 挂在 `LogonTrigger` 上不触发**
   注册后 `Repetition.Duration` 是空值，心跳从不发生。
   必须用 `TimeTrigger` + `Repetition`（这也是 `schtasks /sc minute` 生成的标准形态）。

脚本里保留了 `RestartOnFailure` 作为次要提示，但**真正起作用的是 TimeTrigger 的 1 分钟心跳**。

---

## 日志

计划任务没有控制台，所以日志改为写文件（`run.py` 里的 `RotatingFileHandler`）：

```
docs/audit/app.log            当前日志（5 MB 轮转，保留 3 份）
docs/audit/app.log.1 …        历史轮转
```

由于 `uvicorn.run(..., log_config=None)`，**访问日志现在也带时间戳**了：

```
2026-11-06 20:06:24,401 INFO uvicorn.access: 180.156.130.242:0 - "GET / HTTP/1.1" 200
```

（旧方案下 access log 没有时间列，事后排查「几点开始挂的」很困难。）

---

## 排障

```powershell
# 任务状态
Get-ScheduledTask -TaskName 'InfoRadar-App','InfoRadar-Tunnel' |
  Get-ScheduledTaskInfo | Select TaskName,LastRunTime,LastTaskResult

# 立即重启
schtasks /run /tn "InfoRadar-App"

# 看日志
Get-Content docs\audit\app.log -Tail 50 -Wait

# 手工验证看门狗：杀掉进程，等 60-90 秒，应自动出现新进程
Get-Process pythonw | Stop-Process -Force
Start-Sleep 90; Get-Process pythonw
```

`LastTaskResult = 267009`（0x41301）表示「任务正在运行」，是正常值。

---

## 已知限制

**`LogonTrigger` 要求「有人登录桌面」。** 如果机器开机后停在登录界面没人登录，任务不会启动。

- 无管理员权限时这无法根除（需要 SYSTEM 账户 + `BootTrigger`，或装成 Windows 服务）
- 彻底解法是迁移到云服务器：见仓库根目录的 `迁移指南.md`

---

## 注意：脚本只能用 ASCII

`install_tasks.ps1` / `uninstall_tasks.ps1` 里**没有任何中文字符**，这是故意的：

> Windows PowerShell 5.1 会把**无 BOM 的 UTF-8** `.ps1` 按 ANSI(GBK) 解析，
> 中文会变成乱码，进而破坏字符串引号，直接导致语法错误。

2026-11-06 就因此踩了两次坑。若将来要加中文注释，**必须把文件保存为 UTF-8 with BOM**。
中文说明放在本 README（`.md` 不受此影响）。
