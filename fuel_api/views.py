# fuel_api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
from fuel_api.services import RouteService
from fuel_api.serializers import RouteRequestSerializer
import logging
import re

logger = logging.getLogger(__name__)

class RouteView(APIView):
    """API endpoint for route planning with fuel optimization"""
    
    def post(self, request):
        # Validate input
        serializer = RouteRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        start = serializer.validated_data['start']
        finish = serializer.validated_data['finish']
        
        try:
            # Create clean cache key
            clean_start = re.sub(r'[^a-zA-Z0-9_]', '_', start)
            clean_finish = re.sub(r'[^a-zA-Z0-9_]', '_', finish)
            cache_key = f"route_response_{clean_start}_{clean_finish}"
            
            cached_response = cache.get(cache_key)
            if cached_response:
                return Response(cached_response, status=status.HTTP_200_OK)
            
            # Initialize route service
            route_service = RouteService()
            
            # Get route information
            route_data = route_service.get_route(start, finish)
            
            # Optimize fuel stops
            fuel_stops, total_cost = route_service.optimize_fuel_stops(route_data)
            
            # Prepare response
            response_data = {
                'start_location': {
                    'address': start,
                    'coordinates': {
                        'latitude': route_data['start_coords'][0],
                        'longitude': route_data['start_coords'][1]
                    }
                },
                'finish_location': {
                    'address': finish,
                    'coordinates': {
                        'latitude': route_data['finish_coords'][0],
                        'longitude': route_data['finish_coords'][1]
                    }
                },
                'total_distance_miles': round(route_data['distance_miles'], 2),
                'fuel_stops': [
                    {
                        'name': station['truckstop_name'],
                        'address': f"{station['address']}, {station['city']}, {station['state']}",
                        'price_per_gallon': round(float(station['retail_price']), 2),
                        'coordinates': {
                            'latitude': float(station['latitude']),
                            'longitude': float(station['longitude'])
                        }
                    } for station in fuel_stops
                ],
                'total_fuel_cost': round(total_cost, 2),
                'map_data': {
                    'geometry': route_data['geometry'],
                    'center': [
                        (route_data['start_coords'][0] + route_data['finish_coords'][0]) / 2,
                        (route_data['start_coords'][1] + route_data['finish_coords'][1]) / 2
                    ]
                },
                'statistics': {
                    'vehicle_range_miles': route_service.vehicle_range,
                    'miles_per_gallon': route_service.mpg,
                    'estimated_gallons_needed': round(route_data['distance_miles'] / route_service.mpg, 2),
                    'number_of_fuel_stops': len(fuel_stops),
                    'total_fuel_stations_loaded': len(route_service.fuel_stations)  # Add this to debug
                }
            }
            
            # Cache response for 24 hours
            cache.set(cache_key, response_data, 3600 * 24)
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Route calculation error: {str(e)}")
            return Response(
                {'error': f'Failed to calculate route: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# Add a debug endpoint to check fuel stations
class FuelStationsView(APIView):
    """Debug endpoint to check loaded fuel stations"""
    
    def get(self, request):
        route_service = RouteService()
        return Response({
            'total_stations': len(route_service.fuel_stations),
            'sample_stations': route_service.fuel_stations[:5] if route_service.fuel_stations else [],
            'csv_path': 'data folder (check logs for details)'
        })