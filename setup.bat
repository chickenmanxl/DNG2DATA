@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

rem Defaults
set "REQ=requirements.txt"
set "VENV=DNG2DATA"
set "PYCMD="

:parse
if "%~1"=="" goto run
if "%~1"=="-r" (set "REQ=%~2" & shift & shift & goto parse)
if "%~1"=="-v" (set "VENV=%~2" & shift & shift & goto parse)
if "%~1"=="-p" (set "PYCMD=%~2" & shift & shift & goto parse)
if "%~1"=="-h" (
  echo Usage: %~nx0 [-r requirements.txt] [-v .venv] [-p C:\Path\to\python.exe]
  exit /b 0
)
echo Invalid option: %~1
exit /b 1

:run
if not exist "%REQ%" (
  echo Requirements file not found: %REQ%
  exit /b 1
)

rem Choose Python
if not defined PYCMD (
  where py >nul 2>nul && (set "PYCMD=py -3") ^
  || ( where python >nul 2>nul && (set "PYCMD=python") ^
  || ( echo Python not found. Install Python 3 and try again. & exit /b 1))
)

echo Using Python:
%PYCMD% --version

echo Creating venv at: %VENV%
%PYCMD% -m venv "%VENV%" || (echo Failed to create venv & exit /b 1)

echo Upgrading pip and installing requirements...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip || exit /b 1
"%VENV%\Scripts\python.exe" -m pip install -r "%REQ%" || exit /b 1

echo(
echo ✅ Done.
echo Activate in this shell later with:
echo     call "%VENV%\Scripts\activate.bat"
endlocal
