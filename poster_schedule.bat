@echo off
chcp 65001 > nul
cd /d "C:\Users\이희원\marketing-agent"

set PYTHONIOENCODING=utf-8
set LOG_FILE=logs\poster_schedule_%date:~0,4%%date:~5,2%%date:~8,2%.log

if not exist logs mkdir logs

echo [%date% %time%] 포스팅 스케줄 시작 >> %LOG_FILE%
"C:\Users\이희원\marketing-agent\venv\Scripts\python.exe" poster_schedule.py >> %LOG_FILE% 2>&1
echo [%date% %time%] 포스팅 스케줄 종료 >> %LOG_FILE%
