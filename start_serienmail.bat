@echo off
cd /d "%~dp0"
python Serienmail.py
if errorlevel 1 pause
