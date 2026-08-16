# fuel_api/urls.py
from django.urls import path
from fuel_api.views import RouteView, FuelStationsView

urlpatterns = [
    path('api/route/', RouteView.as_view(), name='route'),
    path('api/debug/stations/', FuelStationsView.as_view(), name='fuel-stations'),
]