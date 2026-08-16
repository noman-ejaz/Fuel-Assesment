from django.urls import path
from fuel_api.views import RouteView

urlpatterns = [
    path('api/route/', RouteView.as_view(), name='route'),
]