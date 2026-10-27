@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM Chiron — masaüstü penceresi (3D arayüz, WebView2). Bkz. desktop.py
REM Arayüz derlenmemişse bir kereye mahsus derler; sonraki açılışlar doğrudan başlar.

if not exist "frontend\out\index.html" (
    echo Arayuz ilk kez derleniyor, bu bir defaya mahsus birkac dakika surebilir...
    pushd frontend
    if not exist "node_modules" call npm install
    call npm run build
    popd
)

if not exist "frontend\out\index.html" (
    echo.
    echo HATA: Arayuz derlenemedi. Yukaridaki npm ciktisina bak.
    pause
    exit /b 1
)

REM pythonw = konsol penceresi acilmaz; uygulama tek bir pencere olarak gorunur.
if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" desktop.py
) else (
    start "" pythonw desktop.py
)
