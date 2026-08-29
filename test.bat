@echo off
setlocal
.venv\Scripts\pytest.exe tests_public -q %*
