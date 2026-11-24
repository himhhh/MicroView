@echo off
setlocal EnableExtensions
title MicroView Windows Builder
chcp 65001 >nul

echo.
echo ========================================
echo   MicroView Windows Build
echo ========================================
echo.

rem Building directly on a macOS shared folder is not reliable. Keep the old
rem proven behavior: copy UNC sources to Windows first.
set "SOURCE_DIR=%~dp0"
rem %~dp0 always ends with a backslash. Remove it because robocopy can treat
rem the closing quote after a trailing backslash as part of the source path.
set "SOURCE_DIR=%SOURCE_DIR:~0,-1%"
set "LOCAL_BUILD_DIR=%TEMP%\MicroView-Windows-Build"
set "OUTPUT_DIR=%USERPROFILE%\Desktop\MicroView_Windows"

echo Source: %SOURCE_DIR%
if "%SOURCE_DIR:~0,2%"=="\\" (
    echo UNC shared folder detected. Copying source to Windows...
    if exist "%LOCAL_BUILD_DIR%" rmdir /s /q "%LOCAL_BUILD_DIR%"
    mkdir "%LOCAL_BUILD_DIR%"
    if errorlevel 1 goto :source_failed

    robocopy "%SOURCE_DIR%" "%LOCAL_BUILD_DIR%" /E /XD .git venv .venv-win build dist __pycache__ /XF .DS_Store /R:2 /W:1 /NFL /NDL /NJH /NJS /NP
    if errorlevel 8 goto :source_failed
    pushd "%LOCAL_BUILD_DIR%"
) else (
    pushd "%SOURCE_DIR%"
)
if errorlevel 1 goto :source_failed

echo Working: %CD%
echo.

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3.12"

if not defined PYTHON_CMD (
    if exist "C:\Program Files\Python312\python.exe" set PYTHON_CMD="C:\Program Files\Python312\python.exe"
)

if not defined PYTHON_CMD (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PYTHON_CMD="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)

if not defined PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo [ERROR] Python was not found.
    echo Please install Python 3.12 from https://www.python.org/downloads/windows/
    echo During installation, enable "Add Python to PATH".
    echo.
    pause
    popd
    exit /b 1
)

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] MicroView requires Python 3.12.
    echo Install Python 3.12, then run build.bat again.
    echo.
    pause
    popd
    exit /b 1
)

echo [1/2] Checking MicroView dependencies...
%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto :build_failed

echo [2/2] Building MicroView.exe...
%PYTHON_CMD% -m PyInstaller --noconfirm --clean build-windows.spec
if errorlevel 1 goto :build_failed

if not exist "dist\MicroView\MicroView.exe" (
    echo [ERROR] Build finished, but MicroView.exe was not found.
    echo.
    pause
    popd
    exit /b 1
)

echo Copying finished application to the Desktop...
if exist "%OUTPUT_DIR%" rmdir /s /q "%OUTPUT_DIR%"
xcopy /e /i /q "dist\MicroView" "%OUTPUT_DIR%"
if errorlevel 1 goto :build_failed

if not exist "%OUTPUT_DIR%\MicroView.exe" (
    echo [ERROR] MicroView.exe could not be copied to the Desktop.
    echo.
    pause
    popd
    exit /b 1
)

echo.
echo ========================================
echo   Build completed successfully.
echo   Output: %OUTPUT_DIR%\MicroView.exe
echo ========================================
echo.

start "" explorer.exe "%OUTPUT_DIR%"
pause
popd
exit /b 0

:source_failed
echo.
echo [ERROR] The project could not be copied to the Windows build directory.
echo.
pause
exit /b 1

:build_failed
echo.
echo [ERROR] Build failed. Review the messages above for details.
echo.
pause
popd
exit /b 1
