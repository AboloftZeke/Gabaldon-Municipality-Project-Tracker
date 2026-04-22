#!/bin/bash
# Setup script for Municipality Project Tracker

echo "=== Municipality Project Tracker Setup ==="
echo ""

# Create virtual environment
echo "1. Creating virtual environment..."
python -m venv venv

# Activate virtual environment
echo "2. Activating virtual environment..."
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "Error: Could not activate virtual environment"
    exit 1
fi

# Install dependencies
echo "3. Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Run migrations
echo "4. Running database migrations..."
python manage.py migrate

# Create superuser
echo "5. Creating superuser account..."
python manage.py createsuperuser

# Collect static files (optional for development)
# echo "6. Collecting static files..."
# python manage.py collectstatic --noinput

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "To start the development server, run:"
echo "  python manage.py runserver"
echo ""
echo "Access the application at: http://localhost:8000"
echo "Admin panel: http://localhost:8000/admin"
echo ""
