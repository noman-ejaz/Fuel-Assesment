from django.db import models

class FuelStation(models.Model):
    opis_truckstop_id = models.IntegerField(unique=True)
    truckstop_name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    rack_id = models.IntegerField()
    retail_price = models.DecimalField(max_digits=10, decimal_places=8)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['state']),
            models.Index(fields=['retail_price']),
        ]
    
    def __str__(self):
        return f"{self.truckstop_name} - {self.city}, {self.state}"