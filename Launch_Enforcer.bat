@echo off
setlocal EnableDelayedExpansion
title PnL Enforcer Beta -- Launcher
cd /d "%~dp0"

:: 0. Fast-path launch when enforcer.py is already installed (skips console checks unless a pending update boot failed)
if exist "enforcer.py" if not exist ".enforcer_boot_pending.json" if /i not "%~1"=="--console" (
    for /f "delims=" %%i in ('where pythonw 2^>nul') do (
        echo "%%i" | find /i "WindowsApps\pythonw.exe" >nul
        if !errorlevel! neq 0 (
            start "" "%%i" enforcer.py
            exit /b 0
        )
    )
    set "FAST_PYW="
    for /d %%D in ("%LocalAppData%\Programs\Python\Python3*" "%LocalAppData%\Python\pythoncore-3*" "C:\Python3*" "C:\Program Files\Python3*") do (
        if exist "%%~fD\pythonw.exe" set "FAST_PYW=%%~fD\pythonw.exe"
    )
    if defined FAST_PYW (
        start "" "!FAST_PYW!" enforcer.py
        exit /b 0
    )
)

echo ========================================================
echo          PnL ENFORCER BETA -- STARTUP CHECK
echo ========================================================

set "PY_CMD="

:: 1. Check if real Python is on PATH (ignoring the blank Windows Store stub)
for /f "delims=" %%i in ('where python 2^>nul') do (
    echo "%%i" | find /i "WindowsApps\python.exe" >nul
    if !errorlevel! neq 0 (
        "%%i" --version >nul 2>&1
        if !errorlevel! equ 0 (
            if not defined PY_CMD set "PY_CMD=%%i"
        )
    )
)

:: 2. If not on PATH, auto-search standard Windows Python install folders
if not defined PY_CMD (
    for /d %%D in ("%LocalAppData%\Programs\Python\Python3*" "%LocalAppData%\Python\pythoncore-3*" "C:\Python3*" "C:\Program Files\Python3*") do (
        if exist "%%~fD\python.exe" (
            set "PY_CMD=%%~fD\python.exe"
        )
    )
)

:: 3. If still not found, auto-install Python 3.12 + PATH via Windows winget
if not defined PY_CMD (
    echo [NOTICE] Python was not found on your system.
    echo Automatically installing Python 3.12 and adding it to PATH...
    echo ^(If a Windows permission prompt appears, click Yes^)
    echo.
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --override "/passive PrependPath=1 Include_test=0"
    
    for /d %%D in ("%LocalAppData%\Programs\Python\Python3*" "C:\Program Files\Python3*") do (
        if exist "%%~fD\python.exe" (
            set "PY_CMD=%%~fD\python.exe"
        )
    )
)

if not defined PY_CMD (
    echo [ERROR] Could not locate or auto-install Python!
    echo Please install Python 3.12 from https://www.python.org/downloads/
    echo and check the box "Add python.exe to PATH".
    pause
    exit /b
)

echo Using Python: "!PY_CMD!"
echo Checking required broker libraries (Schwab ^& Webull)...

"!PY_CMD!" -c "import schwab" >nul 2>&1
if !errorlevel! neq 0 (
    echo Installing schwab-py...
    "!PY_CMD!" -m pip install --upgrade "schwab-py==1.5.1" "authlib==1.8.0" "httpx==0.28.1"
)

"!PY_CMD!" -c "import six, jmespath, requests, urllib3, certifi, cryptography, cachetools; from webull.core.client import ApiClient; from webull.trade.trade_client import TradeClient" >nul 2>&1
if !errorlevel! neq 0 (
    echo Installing Webull OpenAPI SDK and dependencies...
    "!PY_CMD!" -m pip install --upgrade six jmespath protobuf paho-mqtt requests urllib3 certifi cryptography cachetools
    "!PY_CMD!" -m pip install --upgrade --no-deps --ignore-requires-python "webull-openapi-python-sdk==3.0.4"
)

:: 4. Bootstrap missing files if user only downloaded Launch_Enforcer.bat, then check for updates
if not exist "enforcer.py" (
    echo Downloading PnL Enforcer Beta files...
    "!PY_CMD!" -c "import time, urllib.request; base='https://gist.githubusercontent.com/DBCodez/6442a3ab2767aeb5ba0b13940d012634/raw/'; t='?t='+str(int(time.time())); [open(f,'wb').write(urllib.request.urlopen(urllib.request.Request(base+f+t, headers={'User-Agent':'PnL-Enforcer-Updater'}), timeout=10).read()) for f in ('enforcer.py','README.md','CHANGELOG.md','LICENSE.txt')]"
)
:: 4a. Crash-safe update recovery: if a newly installed update failed before Pre-Flight opened, offer 1-click restore
if exist ".enforcer_boot_pending.json" if exist "enforcer.py.prev" "!PY_CMD!" -c "import ctypes, json, os, re, tempfile, time; bp='.enforcer_boot_pending.json'; pp='enforcer.py.prev'; ep='enforcer.py'; in_tmp=os.path.abspath('.').lower().startswith(os.path.abspath(tempfile.gettempdir()).lower()); mtx=(os.environ.get('_ENFORCER_BAT_TEST_MUTEX','') if in_tmp else '') or 'Local\\PnLEnforcerBeta_SingleInstance_Mutex'; k32=ctypes.windll.kernel32; h=k32.CreateMutexW(None, False, mtx); busy=(k32.GetLastError()==183); (k32.CloseHandle(h) if h else None); d=json.load(open(bp,'r',encoding='utf-8')) if (not busy and os.path.isfile(bp)) else None; sup=bool(isinstance(d,dict) and d.get('suppress_bat_prompt')); age=(time.time()-float(d.get('installed_at',0))) if (isinstance(d,dict) and not sup) else 0; pt=open(pp,'rb').read() if (d and not sup and age>=1.5 and os.path.isfile(pp)) else b''; ptxt=pt.decode('utf-8') if pt else ''; ok=bool(ptxt and ('def data_loop' in ptxt) and compile(ptxt,pp,'exec')); m=re.search(r'(?m)^APP_VERSION\s*=\s*.([0-9.]+).', ptxt) if ok else None; pv=(m.group(1) if m else str((d or {}).get('prev_version','previous'))); tv=str((d or {}).get('target_version','update')); msg='PnL Enforcer v'+tv+' did not finish starting on its last launch.\n\nRestore your previous working version (v'+pv+') now?\n\n(Your saved settings, tokens, and session baseline remain untouched.)'; tans=(os.environ.get('ENFORCER_TEST_RECOVERY_ANS','') if in_tmp else ''); ans=((int(tans) if tans else ctypes.windll.user32.MessageBoxW(0, msg, 'PnL Enforcer -- Startup Recovery', 0x00040034)) if ok else 0); (open(ep+'.tmp','wb').write(pt), os.replace(ep+'.tmp',ep), (open('CHANGELOG.md.tmp','wb').write(open('CHANGELOG.md.prev','rb').read()), os.replace('CHANGELOG.md.tmp','CHANGELOG.md')) if os.path.isfile('CHANGELOG.md.prev') else None, (os.remove(bp) if os.path.exists(bp) else None), print('[RECOVERY] Restored PnL Enforcer v'+pv+'.')) if ans==6 else None; (d.__setitem__('suppress_bat_prompt',True), open(bp+'.tmp','w',encoding='utf-8').write(json.dumps(d,indent=2)), os.replace(bp+'.tmp',bp)) if (ans==7 and isinstance(d,dict)) else None; cfgp=os.path.join(os.path.expanduser('~'),'enforcer_config.json'); cd=(json.load(open(cfgp,'r',encoding='utf-8')) if (ans==6 and os.path.isfile(cfgp)) else None); (cd.__setitem__('skipped_update_version',tv), open(cfgp+'.tmp','w',encoding='utf-8').write(json.dumps(cd,indent=4)), os.replace(cfgp+'.tmp',cfgp)) if isinstance(cd,dict) else None" 2>nul

findstr /c:"--check-update" enforcer.py >nul 2>&1
if !errorlevel! equ 0 (
    "!PY_CMD!" enforcer.py --check-update
) else (
    "!PY_CMD!" -c "import os, re, time, urllib.request; url='https://gist.githubusercontent.com/DBCodez/6442a3ab2767aeb5ba0b13940d012634/raw/enforcer.py?t='+str(int(time.time())); rem=urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'PnL-Enforcer-Updater'}), timeout=3).read(); txt=rem.decode('utf-8','replace'); m=re.search(r'(?m)^APP_VERSION\s*=\s*.([0-9.]+).', txt); v=m.group(1) if m else 'latest'; ans=input(f'\nNew version v{v} available. Download and install now? (Y/N): ').strip().lower(); (open('enforcer.py.tmp','wb').write(rem), os.replace('enforcer.py.tmp','enforcer.py'), print(f'[SUCCESS] Updated to v{v}.')) if ans in ('y','yes') and 'def data_loop' in txt else None" 2>nul
)

echo Launching PnL Enforcer...
if /i "%~1"=="--console" (
    "!PY_CMD!" enforcer.py --console
    if !errorlevel! neq 0 (
        echo.
        echo Application exited with an error. See messages above.
        pause
    )
    exit /b
)

set "PYW_CMD="
for %%F in ("!PY_CMD!") do (
    if exist "%%~dpFpythonw.exe" set "PYW_CMD=%%~dpFpythonw.exe"
)
if defined PYW_CMD (
    start "" "!PYW_CMD!" enforcer.py
) else (
    start "" "!PY_CMD!" enforcer.py
)
exit /b 0
