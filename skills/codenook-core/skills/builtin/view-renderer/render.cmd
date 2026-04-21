@echo off
rem view-renderer/render.cmd — Windows shim for render.py
rem Usage: render.cmd prepare --id <entry-id> [--workspace <dir>]
python "%~dp0render.py" %*
