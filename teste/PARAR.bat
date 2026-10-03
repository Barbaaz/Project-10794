@echo off
rem Stops the test copy; what was done on the site is kept. Double-click it; see GUIA-DE-TESTE.md.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\teste.ps1" parar
