import csv
import os
from django.core.management.base import BaseCommand
from fuel_api.models import FuelStation
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import time
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Import fuel station data from CSV file'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--csv_file', 
            type=str, 
            default='data/fuel-prices-for-be-assessment.csv',
            help='Path to CSV file (default: data/fuel-prices-for-be-assessment.csv)'
        )
        parser.add_argument(
            '--skip-geocode',
            action='store_true',
            help='Skip geocoding and use default coordinates'
        )
    
    def handle(self, *args, **options):
        csv_file = options.get('csv_file')
        skip_geocode = options.get('skip_geocode')
        
        # Check if file exists
        if not os.path.exists(csv_file):
            self.stdout.write(self.style.ERROR(f"File not found: {csv_file}"))
            self.stdout.write("Please ensure the file exists at: data/fuel-prices-for-be-assessment.csv")
            return
        
        # Initialize geocoder if needed
        geolocator = None
        if not skip_geocode:
            try:
                geolocator = Nominatim(user_agent="fuel_assessment")
                geocode = RateLimiter(geolocator.geocode, min_delay_seconds=0.5)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Geocoding not available: {e}"))
                self.stdout.write("Will use default coordinates for stations")
                skip_geocode = True
        
        count = 0
        error_count = 0
        station_data = []
        
        self.stdout.write(f"Starting import from {csv_file}...")
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as file:
                # Skip BOM if present
                content = file.read()
                if content.startswith('\ufeff'):
                    content = content[1:]
                
                reader = csv.DictReader(content.splitlines())
                
                # Check if CSV has expected columns
                expected_columns = ['OPIS Truckstop ID', 'Truckstop Name', 'Address', 
                                   'City', 'State', 'Rack ID', 'Retail Price']
                actual_columns = reader.fieldnames if reader.fieldnames else []
                
                self.stdout.write(f"CSV Columns found: {actual_columns}")
                
                # Map columns if different
                column_map = {}
                for col in expected_columns:
                    for actual in actual_columns:
                        if col.lower() in actual.lower() or actual.lower() in col.lower():
                            column_map[col] = actual
                            break
                
                if not column_map:
                    self.stdout.write(self.style.ERROR("Could not match CSV columns. Expected columns:"))
                    self.stdout.write(str(expected_columns))
                    return
                
                self.stdout.write(f"Column mapping: {column_map}")
                
                for row in reader:
                    try:
                        # Extract data using mapped columns
                        opis_id = int(row.get(column_map.get('OPIS Truckstop ID', 'OPIS Truckstop ID'), 0))
                        name = row.get(column_map.get('Truckstop Name', 'Truckstop Name'), '').strip()
                        address = row.get(column_map.get('Address', 'Address'), '').strip()
                        city = row.get(column_map.get('City', 'City'), '').strip()
                        state = row.get(column_map.get('State', 'State'), '').strip()
                        rack_id = int(row.get(column_map.get('Rack ID', 'Rack ID'), 0))
                        price = float(row.get(column_map.get('Retail Price', 'Retail Price'), 0))
                        
                        if not opis_id or not name:
                            self.stdout.write(f"Warning: Skipping row with missing data: {row}")
                            error_count += 1
                            continue
                        
                        # Geocode address
                        lat = None
                        lng = None
                        
                        if not skip_geocode and geolocator:
                            try:
                                full_address = f"{address}, {city}, {state}, USA"
                                self.stdout.write(f"Geocoding: {full_address}")
                                
                                # Try with delay
                                time.sleep(0.5)
                                location = geocode(full_address)
                                
                                if location:
                                    lat = location.latitude
                                    lng = location.longitude
                                    self.stdout.write(f"  ✓ Found: {lat}, {lng}")
                                else:
                                    # Try with just city and state
                                    city_state = f"{city}, {state}, USA"
                                    location = geocode(city_state)
                                    if location:
                                        lat = location.latitude
                                        lng = location.longitude
                                        self.stdout.write(f"  ✓ Found (city only): {lat}, {lng}")
                                    else:
                                        self.stdout.write(f"  ✗ Could not geocode")
                                        # Set default coordinates based on state
                                        lat, lng = self.get_default_coordinates(state)
                            except Exception as e:
                                self.stdout.write(f"  ✗ Error: {e}")
                                lat, lng = self.get_default_coordinates(state)
                        else:
                            # Set default coordinates
                            lat, lng = self.get_default_coordinates(state)
                        
                        # Store station data
                        station_data.append({
                            'opis_truckstop_id': opis_id,
                            'truckstop_name': name,
                            'address': address,
                            'city': city,
                            'state': state,
                            'rack_id': rack_id,
                            'retail_price': price,
                            'latitude': lat,
                            'longitude': lng,
                        })
                        
                        count += 1
                        
                        if count % 10 == 0:
                            self.stdout.write(f"Processed {count} stations...")
                            
                    except Exception as e:
                        self.stdout.write(f"Error processing row: {e}")
                        error_count += 1
                        continue
                
            # Bulk insert
            self.stdout.write(f"\nBulk inserting {len(station_data)} stations...")
            FuelStation.objects.all().delete()  # Clear existing data
            
            bulk_data = []
            for data in station_data:
                bulk_data.append(FuelStation(**data))
            
            FuelStation.objects.bulk_create(bulk_data, batch_size=100)
            
            self.stdout.write(self.style.SUCCESS(
                f"\n✅ Successfully imported {count} fuel stations"
            ))
            if error_count > 0:
                self.stdout.write(self.style.WARNING(f"⚠️ {error_count} records had errors"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Fatal error: {e}"))
            import traceback
            traceback.print_exc()
    
    def get_default_coordinates(self, state):
        """Return default coordinates for US states"""
        state_coords = {
            'CA': (36.7783, -119.4179),
            'TX': (31.9686, -99.9018),
            'NY': (40.7128, -74.0060),
            'FL': (27.6648, -81.5158),
            'IL': (40.6331, -89.3985),
            'PA': (41.2033, -77.1945),
            'OH': (40.4173, -82.9071),
            'GA': (32.1656, -82.9001),
            'NC': (35.7596, -79.0193),
            'MI': (44.3148, -85.6024),
            'NJ': (40.0583, -74.4057),
            'VA': (37.4316, -78.6569),
            'WA': (47.7511, -120.7401),
            'AZ': (34.0489, -111.0937),
            'MA': (42.4072, -71.3824),
            'TN': (35.5175, -86.5804),
            'IN': (40.2672, -86.1349),
            'MO': (38.5739, -92.6036),
            'MD': (39.0458, -76.6413),
            'WI': (43.7844, -88.7879),
            'CO': (39.5501, -105.7821),
            'MN': (46.7296, -94.6859),
            'SC': (33.8361, -81.1637),
            'AL': (32.3182, -86.9023),
            'LA': (30.9843, -91.9623),
            'OK': (35.0078, -97.0929),
            'OR': (44.5720, -122.0709),
            'CT': (41.6032, -73.0877),
            'IA': (41.8780, -93.0977),
            'MS': (32.3547, -89.3985),
            'AR': (34.7465, -92.2896),
            'UT': (39.3210, -111.0937),
            'NV': (38.8026, -116.4194),
            'KS': (38.5266, -96.7265),
            'NM': (34.5199, -105.8701),
            'NE': (41.4925, -99.9018),
            'WV': (38.5976, -80.4549),
            'ID': (44.0682, -114.7420),
            'HI': (19.8968, -155.5828),
            'AK': (61.2181, -149.9003),
            'KY': (37.8393, -84.2700),
            'ND': (47.5515, -101.0020),
            'SD': (43.9695, -99.9018),
            'MT': (46.8797, -110.3626),
            'WY': (43.0759, -107.2903),
            'DE': (38.9108, -75.5277),
            'RI': (41.5801, -71.4774),
            'NH': (43.1939, -71.5724),
            'ME': (45.2538, -69.4455),
            'VT': (44.5588, -72.5778),
        }
        return state_coords.get(state.upper(), (37.0902, -95.7129))  # Default to center US