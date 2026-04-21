@echo off
REM codenook — Windows shim. Forwards to the python CLI entry point.
REM Installed by install.py into <workspace>\.codenook\bin\codenook.cmd.

setlocal
set "BIN_DIR=%~dp0"
set "KERNEL=%BIN_DIR%..\codenook-core"
set "ENTRY=%KERNEL%\_lib\cli\__main__.py"
for %%I in ("%BIN_DIR%..\..") do set "WS_ROOT=%%~fI"

if not exist "%ENTRY%" (
  echo codenook.cmd: kernel entry missing: %ENTRY% 1>&2
  echo           re-run: python install.py --target "%WS_ROOT%" 1>&2
  exit /b 1
)

REM 1) Pick a python interpreter:
REM    a) The interpreter that ran install.py (baked in at install time).
REM    b) python on PATH.
REM    c) py -3 launcher.
set "PY_EXE="
set "PY_EXE_RECORDED={{PY_EXE}}"
if exist "%PY_EXE_RECORDED%" set PY_EXE="%PY_EXE_RECORDED%"
if not defined PY_EXE (
  where python >nul 2>&1 && set "PY_EXE=python"
)
if not defined PY_EXE (
  where py >nul 2>&1 && set "PY_EXE=py -3"
)
if not defined PY_EXE (
  echo codenook.cmd: no python interpreter found 1>&2
  echo           tried: "%PY_EXE_RECORDED%", python on PATH, py -3 1>&2
  echo           install Python 3 from https://www.python.org/downloads/ 1>&2
  exit /b 127
)

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "CODENOOK_WORKSPACE=%WS_ROOT%"

%PY_EXE% "%ENTRY%" %*
exit /b %ERRORLEVEL%
