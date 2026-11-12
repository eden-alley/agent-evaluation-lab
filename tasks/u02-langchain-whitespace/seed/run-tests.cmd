@echo off
"%~dp0..\runtime\Scripts\python.exe" -B -I -m unittest discover -s "%~dp0tests" -v
exit /b %errorlevel%
