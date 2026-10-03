@echo off
rem Deletes what was done on the test copy and starts again from the demo data. Double-click it; see GUIA-DE-TESTE.md.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\teste.ps1" repor
