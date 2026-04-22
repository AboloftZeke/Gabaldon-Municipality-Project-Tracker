@echo off
REM Setup script for Municipality Project Tracker (Windows)

echo === Municipality Project Tracker Setup ===
echo.

REM Create virtual environment
echo 1. Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo Error: Could not create virtual environment
    exit /b 1
)

REM Activate virtual environment
echo 2. Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo Error: Could not activate virtual environment
    exit /b 1
)

REM Install dependencies
echo 3. Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

REM Run migrations
echo 4. Running database migrations...
python manage.py migrate

REM Create superuser
echo 5. Creating superuser account...
python manage.py createsuperuser

REM Optional: Collect static files
REM echo 6. Collecting static files...
REM python manage.py collectstatic --noinput

echo.
echo === Setup Complete! ===
echo.
echo To start the development server, run:
echo   python manage.py runserver
echo.
echo Access the application at: http://localhost:8000
echo Admin panel: http://localhost:8000/admin
echo.
pause
