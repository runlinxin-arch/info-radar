@echo off
REM ===========================================================================
REM 生成用来登录云服务器的 SSH 密钥（只需运行一次）
REM 运行后把  deploy\id_ed25519_pub.txt  的内容整段贴到
REM 阿里云/腾讯云创建实例时的「密钥对」里。
REM ===========================================================================
setlocal
set KEYDIR=D:\KimiData\kimi\workspace\info-radar\deploy
set KEY=%KEYDIR%\id_ed25519
set PUB=%KEYDIR%\id_ed25519_pub.txt

if exist "%KEY%" (
  echo [跳过] 私钥已存在：%KEY%
) else (
  echo 正在生成 SSH 密钥（ed25519，无口令）...
  ssh-keygen -t ed25519 -f "%KEY%" -N "" -C "inforadar-deploy"
  if errorlevel 1 (
    echo [失败] ssh-keygen 执行失败
    pause
    exit /b 1
  )
  ssh-keygen -y -f "%KEY%" > "%PUB%"
)

if not exist "%PUB%" ssh-keygen -y -f "%KEY%" > "%PUB%"

echo.
echo ===============================================================
echo  下面这段是【公钥】，创建云服务器时整段贴进去：
echo ===============================================================
type "%PUB%"
echo ===============================================================
echo.
echo 私钥（不要外传）：%KEY%
echo 公钥：%PUB%
echo.
echo 以后连服务器：
echo   ssh -i "%KEY%" root@^<服务器公网IP^>
echo ===============================================================
pause
