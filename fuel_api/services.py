# fuel_api/services.py
import requests
import json
import math
import csv
import os
from typing import List, Dict, Tuple, Optional
from django.core.cache import cache
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class RouteService:
    """Service for handling route calculations and optimization"""
    
    def __init__(self):
        self.osrm_url = settings.OSRM_API_URL
        self.vehicle_range = 500  # miles
        self.mpg = 10  # miles per gallon
        self.city_coords_cache = self._load_city_coordinates()
        self.fuel_stations = self._load_fuel_stations()
        logger.info(f"Loaded {len(self.fuel_stations)} fuel stations")
        logger.info(f"Loaded {len(self.city_coords_cache)} city coordinates")
    
    def _load_city_coordinates(self) -> Dict[str, Tuple[float, float]]:
        """Pre-load coordinates for common cities to avoid geocoding"""
        # Common cities along major highways
        cities = {
            # Northeast
            "New York,NY": (40.7128, -74.0060),
            "Boston,MA": (42.3588, -71.0578),
            "Philadelphia,PA": (39.9526, -75.1652),
            "Baltimore,MD": (39.2904, -76.6122),
            "Washington,DC": (38.9072, -77.0369),
            "Pittsburgh,PA": (40.4406, -79.9959),
            "Buffalo,NY": (42.8864, -78.8784),
            "Hartford,CT": (41.7637, -72.6851),
            "Providence,RI": (41.8236, -71.4222),
            
            # Midwest
            "Chicago,IL": (41.8781, -87.6298),
            "Detroit,MI": (42.3314, -83.0458),
            "Cleveland,OH": (41.4993, -81.6944),
            "Columbus,OH": (39.9612, -82.9988),
            "Indianapolis,IN": (39.7684, -86.1581),
            "Milwaukee,WI": (43.0389, -87.9065),
            "Minneapolis,MN": (44.9778, -93.2650),
            "St Louis,MO": (38.6270, -90.1994),
            "Kansas City,MO": (39.0997, -94.5786),
            "Omaha,NE": (41.2565, -95.9345),
            "Des Moines,IA": (41.5868, -93.6250),
            
            # South
            "Atlanta,GA": (33.7490, -84.3880),
            "Charlotte,NC": (35.2271, -80.8431),
            "Nashville,TN": (36.1627, -86.7816),
            "Memphis,TN": (35.1495, -90.0490),
            "New Orleans,LA": (29.9511, -90.0715),
            "Houston,TX": (29.7604, -95.3698),
            "Dallas,TX": (32.7767, -96.7970),
            "Austin,TX": (30.2672, -97.7431),
            "San Antonio,TX": (29.4241, -98.4936),
            "Oklahoma City,OK": (35.4676, -97.5164),
            "Tulsa,OK": (36.1540, -95.9928),
            
            # West
            "Denver,CO": (39.7392, -104.9903),
            "Salt Lake City,UT": (40.7608, -111.8910),
            "Phoenix,AZ": (33.4484, -112.0740),
            "Las Vegas,NV": (36.1699, -115.1398),
            "Los Angeles,CA": (34.0522, -118.2437),
            "San Francisco,CA": (37.7749, -122.4194),
            "San Diego,CA": (32.7157, -117.1611),
            "Sacramento,CA": (38.5816, -121.4944),
            "Portland,OR": (45.5051, -122.6750),
            "Seattle,WA": (47.6062, -122.3321),
            
            # Southwest
            "Albuquerque,NM": (35.0853, -106.6056),
            "Tucson,AZ": (32.2226, -110.9747),
            "El Paso,TX": (31.7619, -106.4850),
            
            # Small cities from the CSV
            "Big Cabin,OK": (36.5389, -95.2214),
            "Tomah,WI": (43.9785, -90.5040),
            "Gila Bend,AZ": (32.9478, -112.7168),
            "Fort Smith,AR": (35.3859, -94.3985),
            "Mount Jackson,VA": (38.7459, -78.6422),
            "Jarrell,TX": (30.8227, -97.6006),
        }
        
        # Load pre-computed coordinates for all cities in the fuel price CSV.
        # This file is generated offline so the request path makes no
        # per-request geocoding calls (keeps the API fast).
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        coords_file = os.path.join(base_dir, 'data', 'city_coordinates.json')
        if os.path.exists(coords_file):
            try:
                with open(coords_file, 'r', encoding='utf-8') as f:
                    for city_key, coords in json.load(f).items():
                        cities.setdefault(city_key.strip(), (float(coords[0]), float(coords[1])))
            except Exception as e:
                logger.error(f"Error loading city coordinates file: {e}")
        
        return cities
    
    def _get_city_coordinates(self, city: str, state: str) -> Tuple[float, float]:
        """Get coordinates for a city/state from the pre-loaded cache"""
        key = "{} {}".format(city, state).strip()
        clean_key = ",".join(part.strip() for part in key.split(",")) if "," in key else key
        
        # Check cache (also allow "City, State" style keys)
        if key in self.city_coords_cache:
            return self.city_coords_cache[key]
        if clean_key in self.city_coords_cache:
            return self.city_coords_cache[clean_key]
        if f"{city},{state}" in self.city_coords_cache:
            return self.city_coords_cache[f"{city},{state}"]
        if f"{city}, {state}" in self.city_coords_cache:
            return self.city_coords_cache[f"{city}, {state}"]
        
        # Fallback: return center of state (no network call on the request path)
        state_centers = {
            'OK': (35.4676, -97.5164),
            'WI': (44.5000, -89.5000),
            'AZ': (34.0489, -111.0937),
            'AR': (34.9697, -92.3731),
            'VA': (37.4316, -78.6569),
            'TX': (31.9686, -99.9018),
            'CA': (36.7783, -119.4179),
            'NY': (43.2994, -74.2179),
            'IL': (40.6331, -89.3985),
            'PA': (41.2033, -77.1945),
            'OH': (40.4173, -82.9071),
            'MI': (44.3148, -85.6024),
            'IN': (40.2672, -86.1349),
            'KY': (37.8393, -84.2700),
            'TN': (35.5175, -86.5804),
            'GA': (32.1656, -82.9001),
            'FL': (27.6648, -81.5158),
            'NC': (35.7596, -79.0193),
            'SC': (33.8361, -81.1637),
            'AL': (32.3182, -86.9023),
            'MS': (32.3547, -89.3985),
            'LA': (30.9843, -91.9623),
            'MO': (38.5739, -92.6038),
            'IA': (42.0329, -93.5815),
            'MN': (46.7296, -94.6859),
            'KS': (39.0119, -98.4842),
            'NE': (41.4925, -99.9018),
            'SD': (44.2998, -99.4388),
            'ND': (47.5515, -101.0020),
            'MT': (46.8797, -110.3626),
            'WY': (43.0759, -107.2903),
            'CO': (39.5501, -105.7821),
            'NM': (34.5199, -105.8701),
            'NV': (39.8760, -117.2241),
            'UT': (39.3210, -111.0937),
            'ID': (44.0682, -114.7420),
            'OR': (44.5720, -122.0709),
            'WA': (47.7511, -120.7401),
            'MA': (42.4072, -71.3824),
            'CT': (41.6032, -73.0877),
            'RI': (41.5801, -71.4774),
            'NH': (43.1939, -71.5724),
            'VT': (44.5588, -72.5778),
            'ME': (45.2538, -69.4455),
            'DE': (38.9108, -75.5277),
            'MD': (39.0458, -76.6413),
            'NJ': (40.0583, -74.4057),
            'WV': (38.5976, -80.4549),
        }
        
        return state_centers.get(state, (39.8283, -98.5795))
    
    def _geocode_city_state(self, city: str, state: str) -> Optional[Tuple[float, float]]:
        """Geocode a city and state (used only for cities not in cache)"""
        location = f"{city}, {state}, USA"
        
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': location,
                'format': 'json',
                'limit': 1
            }
            headers = {
                'User-Agent': 'FuelRouteOptimizer/1.0'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=3)
            
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return (float(data[0]['lat']), float(data[0]['lon']))
        except Exception as e:
            logger.debug(f"Geocoding error for {location}: {e}")
        
        return None
    
    def _load_fuel_stations(self) -> List[Dict]:
        """Load fuel stations from CSV file in the data folder"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, 'data')
        
        if not os.path.exists(data_dir):
            logger.error(f"Data directory not found: {data_dir}")
            return []
        
        csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
        
        if not csv_files:
            logger.error(f"No CSV files found in {data_dir}")
            return []
        
        csv_path = os.path.join(data_dir, csv_files[0])
        logger.info(f"Loading fuel data from: {csv_path}")
        
        stations = []
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as file:
                sample = file.read(1024)
                file.seek(0)
                
                if '\t' in sample:
                    delimiter = '\t'
                elif ';' in sample:
                    delimiter = ';'
                else:
                    delimiter = ','
                
                reader = csv.DictReader(file, delimiter=delimiter)
                
                for row in reader:
                    try:
                        station = {
                            'opis_truckstop_id': int(row.get('OPIS Truckstop ID', 0)),
                            'truckstop_name': row.get('Truckstop Name', '').strip(),
                            'address': row.get('Address', '').strip(),
                            'city': row.get('City', '').strip(),
                            'state': row.get('State', '').strip(),
                            'rack_id': int(row.get('Rack ID', 0)),
                            'retail_price': float(row.get('Retail Price', 0)),
                            'latitude': None,
                            'longitude': None
                        }
                        
                        if station['opis_truckstop_id'] and station['truckstop_name']:
                            # Get coordinates from cache
                            coords = self._get_city_coordinates(station['city'], station['state'])
                            station['latitude'] = coords[0]
                            station['longitude'] = coords[1]
                            stations.append(station)
                                
                    except Exception as e:
                        logger.warning(f"Error parsing row: {e}")
                        continue
                
                logger.info(f"Loaded {len(stations)} fuel stations from CSV")
                
        except Exception as e:
            logger.error(f"Error loading CSV: {e}")
            
            # Try to load from database
            try:
                from fuel_api.models import FuelStation
                db_stations = FuelStation.objects.filter(latitude__isnull=False, longitude__isnull=False)
                for station in db_stations:
                    stations.append({
                        'opis_truckstop_id': station.opis_truckstop_id,
                        'truckstop_name': station.truckstop_name,
                        'address': station.address,
                        'city': station.city,
                        'state': station.state,
                        'rack_id': station.rack_id,
                        'retail_price': float(station.retail_price),
                        'latitude': float(station.latitude),
                        'longitude': float(station.longitude)
                    })
                logger.info(f"Loaded {len(stations)} fuel stations from database")
            except:
                pass
        
        return stations
    
    def geocode_location(self, location: str) -> Tuple[float, float]:
        """Geocode a location using multiple free geocoding services"""
        clean_location = location.replace(' ', '_').replace(',', '')
        cache_key = f"geocode_{clean_location}"
        
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        # Try multiple geocoding services
        geocoders = [
            self._geocode_nominatim,
            self._geocode_opencage,
            self._geocode_arcgis,
            self._geocode_mapquest
        ]
        
        for geocoder in geocoders:
            try:
                result = geocoder(f"{location}, USA")
                if result:
                    cache.set(cache_key, result, 3600 * 24)
                    return result
            except Exception as e:
                continue
        
        raise Exception(f"Could not geocode location: {location}")
    
    def _geocode_nominatim(self, location: str) -> Optional[Tuple[float, float]]:
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {'q': location, 'format': 'json', 'limit': 1}
            headers = {'User-Agent': 'FuelRouteOptimizer/1.0'}
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return (float(data[0]['lat']), float(data[0]['lon']))
        except:
            pass
        return None
    
    def _geocode_opencage(self, location: str) -> Optional[Tuple[float, float]]:
        if not settings.OPENCAGE_API_KEY:
            return None
        try:
            url = "https://api.opencagedata.com/geocode/v1/json"
            params = {'q': location, 'key': settings.OPENCAGE_API_KEY, 'limit': 1}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('results') and len(data['results']) > 0:
                    lat = data['results'][0]['geometry']['lat']
                    lng = data['results'][0]['geometry']['lng']
                    return (lat, lng)
        except:
            pass
        return None
    
    def _geocode_arcgis(self, location: str) -> Optional[Tuple[float, float]]:
        try:
            url = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/find"
            params = {'text': location, 'f': 'json', 'maxLocations': 1}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('locations') and len(data['locations']) > 0:
                    loc = data['locations'][0]['feature']['geometry']
                    return (loc['y'], loc['x'])
        except:
            pass
        return None
    
    def _geocode_mapquest(self, location: str) -> Optional[Tuple[float, float]]:
        try:
            url = "https://open.mapquestapi.com/geocoding/v1/address"
            params = {'location': location, 'maxResults': 1}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if (data.get('results') and len(data['results']) > 0 and 
                    data['results'][0].get('locations') and len(data['results'][0]['locations']) > 0):
                    loc = data['results'][0]['locations'][0]['latLng']
                    return (loc['lat'], loc['lng'])
        except:
            pass
        return None
    
    def get_route(self, start: str, finish: str) -> Dict:
        """Get route information from OSRM"""
        start_coords = self.geocode_location(start)
        finish_coords = self.geocode_location(finish)
        
        cache_key = f"route_{start_coords[0]}_{start_coords[1]}_{finish_coords[0]}_{finish_coords[1]}"
        cached = cache.get(cache_key)
        
        if cached:
            return cached
        
        url = f"{self.osrm_url}/route/v1/driving/{start_coords[1]},{start_coords[0]};{finish_coords[1]},{finish_coords[0]}"
        params = {
            'overview': 'full',
            'geometries': 'geojson',
            'steps': 'true'
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code != 200:
                raise Exception(f"OSRM API returned status {response.status_code}")
            
            data = response.json()
            
            if data['code'] != 'Ok':
                raise Exception(f"OSRM API error: {data.get('message', 'Unknown error')}")
            
            distance_meters = data['routes'][0]['distance']
            distance_miles = distance_meters * 0.000621371
            
            route_data = {
                'start_coords': start_coords,
                'finish_coords': finish_coords,
                'distance_miles': distance_miles,
                'geometry': data['routes'][0]['geometry'],
                'steps': data['routes'][0]['legs'][0]['steps']
            }
            
            cache.set(cache_key, route_data, 3600 * 24)
            return route_data
            
        except Exception as e:
            raise Exception(f"Route calculation failed: {str(e)}")
    
    def find_nearby_stations(self, lat: float, lng: float, radius_miles: float = 100) -> List[Dict]:
        """Find fuel stations near a point"""
        if not self.fuel_stations:
            return []
        
        nearby = []
        
        for station in self.fuel_stations:
            if station['latitude'] is None or station['longitude'] is None:
                continue
            
            distance = self.calculate_distance(
                lat, lng,
                station['latitude'], station['longitude']
            )
            
            if distance <= radius_miles:
                nearby.append((station, distance))
        
        nearby.sort(key=lambda x: (float(x[0]['retail_price']), x[1]))
        
        return [s[0] for s in nearby[:10]]
    
    def calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        R = 3959.87433
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        
        a = (math.sin(dlat/2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * 
             math.sin(dlng/2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def find_cheapest_station(self, lat: float, lng: float, radius_miles: float = 100) -> Optional[Dict]:
        """Find the cheapest fuel station near a point"""
        stations = self.find_nearby_stations(lat, lng, radius_miles)
        return stations[0] if stations else None

    def min_station_price(self) -> float:
        """Return the cheapest fuel price across all stations"""
        prices = [float(s['retail_price']) for s in self.fuel_stations if s.get('retail_price')]
        return min(prices) if prices else 3.0

    def optimize_fuel_stops(self, route_data: Dict) -> Tuple[List[Dict], float]:
        """Optimize fuel stops along the route.

        Model: the vehicle buys exactly the fuel it needs for each leg of the
        trip (total gallons = total_distance / mpg). A full tank covers up to
        ``vehicle_range`` miles, so a refuel stop is planned roughly every
        ``vehicle_range`` miles. At each refuel point the cheapest station
        within 100 miles is selected, which keeps the total spend low.
        """
        distance = route_data['distance_miles']
        start_coords = route_data['start_coords']
        finish_coords = route_data['finish_coords']

        if distance <= 0:
            return [], 0.0

        # Get waypoints along the route
        waypoints = self.get_route_waypoints(route_data, num_points=100)
        logger.info(f"Checking {len(waypoints)} waypoints for fuel stations")

        # Price used for the very first leg (buy fuel before leaving)
        start_station = self.find_cheapest_station(start_coords[0], start_coords[1])
        anchor_price = float(start_station['retail_price']) if start_station else self.min_station_price()

        points = list(waypoints) + [(finish_coords[0], finish_coords[1])]
        fuel_stops = []
        total_cost = 0.0
        last_anchor = start_coords
        prev_point = start_coords

        for waypoint in points:
            distance_from_anchor = self.calculate_distance(
                last_anchor[0], last_anchor[1], waypoint[0], waypoint[1]
            )

            if distance_from_anchor > self.vehicle_range:
                # Cannot reach this waypoint on the current tank: buy fuel at
                # the last waypoint that was still in range.
                leg_miles = self.calculate_distance(
                    last_anchor[0], last_anchor[1], prev_point[0], prev_point[1]
                )
                total_cost += (leg_miles / self.mpg) * anchor_price

                station = self.find_cheapest_station(prev_point[0], prev_point[1])
                if station:
                    fuel_stops.append(station)
                    anchor_price = float(station['retail_price'])
                    logger.info(
                        f"Fuel stop {len(fuel_stops)}: {station['truckstop_name']} in "
                        f"{station['city']}, {station['state']} - ${station['retail_price']:.2f}/gal"
                    )
                last_anchor = prev_point

            prev_point = waypoint

        # Final leg from the last refuel point to the destination
        final_leg_miles = self.calculate_distance(
            last_anchor[0], last_anchor[1], finish_coords[0], finish_coords[1]
        )
        total_cost += (final_leg_miles / self.mpg) * anchor_price

        if not fuel_stops:
            logger.info(f"Distance {distance:.1f} miles within range {self.vehicle_range}, no fuel stops needed")
            logger.info(f"Total cost (no stops): ${total_cost:.2f}")
            return [], round(total_cost, 2)

        logger.info(f"Total fuel stops: {len(fuel_stops)}, Total cost: ${total_cost:.2f}")
        return fuel_stops, round(total_cost, 2)
    
    def get_route_waypoints(self, route_data: Dict, num_points: int = 100) -> List[Tuple[float, float]]:
        """Extract waypoints from route geometry"""
        try:
            if 'geometry' in route_data and route_data['geometry']:
                coords = route_data['geometry']['coordinates']
                
                if len(coords) <= num_points:
                    return [(c[1], c[0]) for c in coords if len(c) >= 2]
                else:
                    step = len(coords) // num_points
                    sampled = [coords[i] for i in range(0, len(coords), step)]
                    return [(c[1], c[0]) for c in sampled if len(c) >= 2]
        except Exception as e:
            logger.error(f"Error extracting waypoints: {e}")
        
        return [
            (route_data['start_coords'][0], route_data['start_coords'][1]),
            (route_data['finish_coords'][0], route_data['finish_coords'][1])
        ]