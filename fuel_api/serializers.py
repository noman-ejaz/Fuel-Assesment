from rest_framework import serializers
from fuel_api.models import FuelStation

class FuelStationSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelStation
        fields = ['opis_truckstop_id', 'truckstop_name', 'address', 
                  'city', 'state', 'retail_price', 'latitude', 'longitude']
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Format price to 2 decimal places for display
        data['retail_price'] = f"${float(instance.retail_price):.2f}"
        return data

class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(max_length=255)
    finish = serializers.CharField(max_length=255)
    
    def validate(self, data):
        # Basic validation for US locations
        if not data['start'] or not data['finish']:
            raise serializers.ValidationError("Both start and finish locations are required")
        return data

class RouteResponseSerializer(serializers.Serializer):
    start_location = serializers.DictField()
    finish_location = serializers.DictField()
    total_distance_miles = serializers.FloatField()
    fuel_stops = FuelStationSerializer(many=True)
    total_fuel_cost = serializers.FloatField()
    map_data = serializers.DictField()