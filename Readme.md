# README.md
# Fuel Route Optimizer API

## Overview
An API that calculates optimal fuel stops along a route based on fuel prices and vehicle range.

## Features
- Geocoding of US locations
- Route calculation using OSRM
- Fuel station optimization based on price and location
- Caching for performance
- REST API with JSON responses

## Setup Instructions

1. Clone the repository
2. Create virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate

3. Install dependencies:
    ```bash
    pip install -r requirements.txt

4. Create .env file with your API keys:
    ```bash
    DJANGO_SECRET_KEY=your-secret-key
    OPENCAGE_API_KEY=your-opencage-api-key

5. Run migrations:
    ```bash
    python manage.py makemigrations
    python manage.py migrate

6. Import fuel station data:
    ```bash
    python manage.py import_fuel_data path/to/fuel_prices.csv

7. Start the server:
    ```bash
    python manage.py runserver