@echo off
setlocal
.venv\Scripts\python.exe scripts\generate_data.py --rows 600 --days 42 --seed 27 %*
