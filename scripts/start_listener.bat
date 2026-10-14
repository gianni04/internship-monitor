@echo off
rem Lance le listener Telegram en arrière-plan (sans fenêtre).
cd /d "%~dp0.."
start "" pythonw "scripts\telegram_listener.py"
