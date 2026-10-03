@echo off
rem Starts the test copy of the site (demo data) and opens it in the browser. Double-click it; see GUIA-DE-TESTE.md.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\teste.ps1" iniciar
