@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto nopython
for /f %%a in ('python -c "import sysconfig;print(sysconfig.get_platform())"') do set ARCH=%%a
echo Python 종류: %ARCH%
if /i "%ARCH%"=="win-arm64" goto arm
python -m pip install --upgrade pip
python -m pip install -r requirements-local.txt > install_log.txt 2>&1
if errorlevel 1 goto pipfail
python -m playwright install chromium
if not exist .env copy .env.example .env
echo.
echo 설치 완료. .env 파일에 API 키를 입력한 뒤 실행.bat 을 더블클릭하세요.
pause
exit /b 0

:nopython
echo [오류] Python을 찾을 수 없습니다. python.org 에서 Windows installer 64-bit 를 설치하고 Add python.exe to PATH 를 체크하세요.
pause
exit /b 1

:arm
echo [오류] 지금 잡힌 Python이 ARM64 버전입니다.
echo Streamlit에 필요한 pyarrow가 ARM64 Windows를 지원하지 않습니다.
echo python.org 에서 Windows installer 64-bit 를 설치하고, cmd에서 where python 으로 경로를 확인하세요.
pause
exit /b 1

:pipfail
echo [오류] 패키지 설치 실패. install_log.txt 내용을 확인하세요.
pause
exit /b 1
