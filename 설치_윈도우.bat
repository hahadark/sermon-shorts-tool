@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PY=python
where py >nul 2>nul && set PY=py -3
echo 설교 쇼츠 도구에 필요한 프로그램을 설치합니다...
%PY% -m pip install --upgrade pillow imageio-ffmpeg yt-dlp
if errorlevel 1 (
  echo.
  echo [문제] 설치에 실패했습니다. Python을 설치할 때 "Add python.exe to PATH"에 체크했는지 확인해 주세요.
  pause
  exit /b 1
)
echo.
%PY% shorts.py 점검
echo.
pause
