@echo off
REM ===================================================================
REM  claude-ask.bat - launcher for the Claude subscription CLI (Windows)
REM  Add this folder to your PATH, then run from anywhere, e.g.:
REM      claude-ask "summarize this: ..."
REM      claude-ask --attach data.txt "turn into JSON" --format json
REM      claude-ask --check
REM  (Comments kept ASCII-only: cmd.exe misparses non-ASCII .bat files.)
REM ===================================================================
setlocal
set "PYTHONUTF8=1"
python "%~dp0claude_subscription.py" %*
exit /b %ERRORLEVEL%
