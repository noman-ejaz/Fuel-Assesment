#!/bin/bash
# setup.sh - Setup script

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser (optional)
python manage.py createsuperuser

# Import fuel data (replace with your CSV file path)
python manage.py import_fuel_data path/to/your/fuel_prices.csv

# Run the server
python manage.py runserver