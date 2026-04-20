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
    "%%~P" "%BASH_SCRIPT%" %*
    exit /b %ERRORLEVEL%
  )
)

REM 2) Fallback: any bash on PATH
where bash >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  bash "%BASH_SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

echo codenook.cmd: no bash.exe found. Install Git for Windows or add bash to PATH. 1>&2
exit /b 127
