@echo off
setlocal
if not defined EVAL_PYTHON set "EVAL_PYTHON=python"
"%EVAL_PYTHON%" -B -m unittest discover -s tests -v
exit /b %errorlevel%
