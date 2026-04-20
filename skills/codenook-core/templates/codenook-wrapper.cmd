@echo off
REM codenook — Windows shim that forwards to the bash wrapper.
REM
REM Installed by `bash install.sh` into <workspace>\.codenook\bin\codenook.cmd
REM so PowerShell / cmd users can invoke `.codenook\bin\codenook ...` directly
REM without Windows popping the "Open with…" dialog for the extension-less
REM bash script next to it.
REM
REM Resolution: prefer Git-Bash bundled with Git for Windows, then fall back
REM to plain `bash` on PATH (WSL or msys2).

setlocal

set "SCRIPT_DIR=%~dp0"
set "BASH_SCRIPT=%SCRIPT_DIR%codenook"

if not exist "%BASH_SCRIPT%" (
  echo codenook.cmd: bash wrapper missing: %BASH_SCRIPT% 1>&2
  exit /b 1
)

REM 1) Common Git-for-Windows install locations
for %%P in (
  "%ProgramFiles%\Git\bin\bash.exe"
  "%ProgramFiles(x86)%\Git\bin\bash.exe"
  "%LOCALAPPDATA%\Programs\Git\bin\bash.exe"
) do (
  if exist %%~P (
    set "BASH_EXE=%%~P"
    goto :have_bash
  )
)

REM 2) Fallback: any bash on PATH
where bash >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  set "BASH_EXE=bash"
  goto :have_bash
)

echo codenook.cmd: no bash.exe found. Install Git for Windows or add bash to PATH. 1>&2
exit /b 127

:have_bash
REM 3) Locate a usable Windows-side Python and prepend its dir to PATH so the
REM    bash wrapper (which calls `python3` / `python`) finds it. Git-Bash does
REM    not ship its own Python.
set "PY_DIR="
for %%D in (
  "%LOCALAPPDATA%\Programs\Python\Python313"
  "%LOCALAPPDATA%\Programs\Python\Python312"
  "%LOCALAPPDATA%\Programs\Python\Python311"
  "%LOCALAPPDATA%\Programs\Python\Python310"
  "%ProgramFiles%\Python313"
  "%ProgramFiles%\Python312"
  "%ProgramFiles%\Python311"
  "%ProgramFiles%\Python310"
  "%ProgramFiles(x86)%\Python313"
  "%ProgramFiles(x86)%\Python312"
  "%ProgramFiles(x86)%\Python311"
  "%ProgramFiles(x86)%\Python310"
) do (
  if exist "%%~D\python.exe" (
    set "PY_DIR=%%~D"
    goto :have_python
  )
)

REM 3b) Fallback: ask `where` (covers winget / Microsoft Store / custom installs)
for /f "delims=" %%P in ('where python 2^>nul') do (
  if exist "%%~P" (
    for %%I in ("%%~P") do set "PY_DIR=%%~dpI"
    goto :have_python
  )
)

REM 3c) `py` launcher fallback
for /f "delims=" %%P in ('where py 2^>nul') do (
  if exist "%%~P" (
    for %%I in ("%%~P") do set "PY_DIR=%%~dpI"
    goto :have_python
  )
)

:have_python
if defined PY_DIR (
  set "PATH=%PY_DIR%;%PATH%"
)

"%BASH_EXE%" "%BASH_SCRIPT%" %*
exit /b %ERRORLEVEL%
