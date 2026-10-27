@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto nopython
python -c "import streamlit" 2>nul
if errorlevel 1 goto nostreamlit
python -m streamlit run app.py
echo.
echo 프로그램이 종료되었습니다. 위 메시지를 확인하세요.
pause
exit /b 0

:nopython
echo [오류] Python을 찾을 수 없습니다. 설치.bat 안내를 따라 Python을 설치하세요.
pause
exit /b 1

:nostreamlit
echo [오류] streamlit이 설치되지 않았습니다. 설치.bat 을 먼저 실행하세요.
pause
exit /b 1
