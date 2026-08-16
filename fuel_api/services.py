import requests
import json
import math
from typing import List, Dict, Tuple, Optional
from decimal import Decimal
from django.core.cache import cache
from django.conf import settings
from fuel_api.models import FuelStation

class RouteService:
    """Service for handling route calculations and optimization"""
    
    def __init__(self):
        self.osrm_url = settings.OSRM_API_URL
        self.vehicle_range = 500  # miles
        self.mpg = 10  # miles per gallon
    
    def geocode_location(self, location: str) -> Tuple[float, float]:
        """Geocode a location using OpenCage Geocoder"""
        cache_key = f"geocode_{location}"
        cached = cache.get(cache_key)
        
        if cached:
            return cached
        
        try:
            # Using OpenCage Geocoder API
            url = f"https://api.opencagedata.com/geocode/v1/json"
            params = {
                'q': f"{location}, USA",
                'key': settings.OPENCAGE_API_KEY,
                'limit': 1
            }
            
            response = requests.get(url, params=params)
            data = response.json()
            
            if data['results']:
                lat = data['results'][0]['geometry']['lat']
                lng = data['results'][0]['geometry']['lng']
                result = (lat, lng)
                cache.set(cache_key, result, 3600 * 24)  # Cache for 24 hours
                return result
            else:
                # Fallback to OSM/Nominatim
                url = "https://nominatim.openstreetmap.org/search"
                params = {
                    'q': f"{location}, USA",
                    'format': 'json',
                    'limit': 1
                }
                response = requests.get(url, params=params)
                data = response.json()
                
                if data:
                    lat = float(data[0]['lat'])
                    lng = float(data[0]['lon'])
                    result = (lat, lng)
                    cache.set(cache_key, result, 3600 * 24)
                    return result
                
        except Exception as e:
            raise Exception(f"Error geocoding location: {e}")
    
    def get_route(self, start: str, finish: str) -> Dict:
        """Get route information from OSRM"""
        # Geocode locations
        start_coords = self.geocode_location(start)
        finish_coords = self.geocode_location(finish)
        
        # Get route from OSRM
        cache_key = f"route_{start_coords}_{finish_coords}"
        cached = cache.get(cache_key)
        
        if cached:
            return cached
        
        url = f"{self.osrm_url}/route/v1/driving/{start_coords[1]},{start_coords[0]};{finish_coords[1]},{finish_coords[0]}"
        params = {
            'overview': 'full',
            'geometries': 'geojson',
            'steps': 'true'
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        if data['code'] != 'Ok':
            raise Exception(f"OSRM API error: {data.get('message', 'Unknown error')}")
        
        # Calculate total distance in miles
        distance_meters = data['routes'][0]['distance']
        distance_miles = distance_meters * 0.000621371
        
        route_data = {
            'start_coords': start_coords,
            'finish_coords': finish_coords,
            'distance_miles': distance_miles,
            'geometry': data['routes'][0]['geometry'],
            'steps': data['routes'][0]['legs'][0]['steps']
        }
        
        cache.set(cache_key, route_data, 3600 * 24)  # Cache for 24 hours
        return route_data
    
    def find_nearby_stations(self, lat: float, lng: float, radius_miles: float = 10) -> List[FuelStation]:
        """Find fuel stations within a radius of a point"""
        # Approximate conversion: 1 degree latitude ≈ 69 miles
        lat_delta = radius_miles / 69.0
        lng_delta = radius_miles / (69.0 * math.cos(math.radians(lat)))
        
        stations = FuelStation.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False,
            latitude__gte=lat - lat_delta,
            latitude__lte=lat + lat_delta,
            longitude__gte=lng - lng_delta,
            longitude__lte=lng + lng_delta
        ).order_by('retail_price')
        
        # Sort by actual distance and price
        stations_with_distance = []
        for station in stations:
            distance = self.calculate_distance(
                lat, lng,
                float(station.latitude), float(station.longitude)
            )
            if distance <= radius_miles:
                stations_with_distance.append((station, distance))
        
        # Sort by price then distance
        stations_with_distance.sort(key=lambda x: (float(x[0].retail_price), x[1]))
        
        return [s[0] for s in stations_with_distance[:5]]  # Top 5 cheapest nearby
    
    def calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate distance between two points in miles"""
        # Haversine formula
        R = 3959.87433  # Earth's radius in miles
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        
        a = (math.sin(dlat/2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * 
             math.sin(dlng/2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def optimize_fuel_stops(self, route_data: Dict) -> Tuple[List[FuelStation], float]:
        """Optimize fuel stops along the route"""
        distance = route_data['distance_miles']
        start_coords = route_data['start_coords']
        
        # If total distance is less than vehicle range, no stops needed
        if distance <= self.vehicle_range:
            return [], 0
        
        # Get waypoints along the route
        waypoints = self.get_route_waypoints(route_data)
        
        fuel_stops = []
        current_position = start_coords
        remaining_range = self.vehicle_range
        total_cost = 0
        
        # Iterate through waypoints to find optimal fuel stops
        for i, waypoint in enumerate(waypoints):
            distance_to_next = self.calculate_distance(
                current_position[0], current_position[1],
                waypoint[0], waypoint[1]
            )
            
            # Calculate distance to finish from this waypoint
            distance_to_finish = self.calculate_distance(
                waypoint[0], waypoint[1],
                route_data['finish_coords'][0], route_data['finish_coords'][1]
            )
            
            # If we can reach finish with current fuel, stop looking for more stops
            if remaining_range >= distance_to_finish:
                break
            
            # If we need to refuel soon, find a station at this waypoint
            if remaining_range - distance_to_next <= 100:  # Refuel when range is low
                stations = self.find_nearby_stations(waypoint[0], waypoint[1])
                
                if stations:
                    best_station = stations[0]  # Cheapest station
                    fuel_needed = self.vehicle_range  # Fill up to full tank
                    gallons_needed = fuel_needed / self.mpg
                    cost = float(best_station.retail_price) * gallons_needed
                    
                    fuel_stops.append(best_station)
                    total_cost += cost
                    remaining_range = self.vehicle_range
                    current_position = waypoint
                else:
                    # If no station found, continue to next waypoint
                    remaining_range -= distance_to_next
                    current_position = waypoint
            else:
                remaining_range -= distance_to_next
                current_position = waypoint
        
        # Add final leg cost if fuel was used
        if fuel_stops:
            # Estimate fuel used on final leg
            final_leg_distance = self.calculate_distance(
                current_position[0], current_position[1],
                route_data['finish_coords'][0], route_data['finish_coords'][1]
            )
            final_gallons = final_leg_distance / self.mpg
            # Use the last fuel stop's price for final leg
            final_cost = float(fuel_stops[-1].retail_price) * final_gallons
            total_cost += final_cost
        
        return fuel_stops, total_cost
    
    def get_route_waypoints(self, route_data: Dict, num_points: int = 20) -> List[Tuple[float, float]]:
        """Extract waypoints from route geometry"""
        if 'geometry' in route_data:
            # Get coordinates from GeoJSON geometry
            coords = route_data['geometry']['coordinates']
            
            # Sample points evenly along the route
            if len(coords) <= num_points:
                return [(c[1], c[0]) for c in coords]
            else:
                step = len(coords) // num_points
                sampled = [coords[i] for i in range(0, len(coords), step)]
                return [(c[1], c[0]) for c in sampled]
        else:
            # Fallback: create waypoints based on steps
            steps = route_data.get('steps', [])
            waypoints = []
            
            for step in steps:
                if 'way_points' in step:
                    for wp in step['way_points']:
                        if 'location' in wp:
                            waypoints.append((wp['location'][0], wp['location'][1]))
            
            return waypoints