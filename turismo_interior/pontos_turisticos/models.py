from django.db import models

# Create your models here.

class Type(models.Model):
    name = models.CharField(max_length=100, unique=True)
    
    def __str__(self):
        return self.name

class TouristSpot(models.Model):
    name = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    address = models.TextField()
    rating = models.FloatField()
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    place_id = models.CharField(max_length=100, unique=True)
    types = models.ManyToManyField(Type)

    def __str__(self):
        return self.name

class CityType(models.Model):
    city = models.CharField(max_length=100)
    type = models.CharField(max_length=100)
    
    class Meta:
        unique_together = ('city', 'type')
        
    def __str__(self):
        return f"{self.city} - {self.type}"
