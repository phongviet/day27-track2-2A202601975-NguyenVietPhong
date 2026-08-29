@echo off
setlocal
.venv\Scripts\python.exe scripts\sync_dbt_seeds.py
.venv\Scripts\dbt.exe build --project-dir dbt_project --profiles-dir dbt_project %*
