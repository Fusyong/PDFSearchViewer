@echo off
REM Build PDFSearchViewer.exe (wrapper for build_exe.ps1)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_exe.ps1" %*
if errorlevel 1 exit /b %errorlevel%
