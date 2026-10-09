@echo off
setlocal
cd /d "%~dp0"
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cd frontend
npm install
cd ..
if not exist .env copy .env.example .env
echo.
echo Setup complete. Open two terminals and run run_backend.bat and run_frontend.bat.
pause
