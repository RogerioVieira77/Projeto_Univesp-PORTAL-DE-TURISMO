from django.contrib import admin
from .models import Type, TouristSpot, CityType

@admin.register(Type)
class TypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(TouristSpot)
class TouristSpotAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'rating', 'place_id')
    search_fields = ('name', 'city', 'place_id')
    filter_horizontal = ('types',)

@admin.register(CityType)
class CityTypeAdmin(admin.ModelAdmin):
    list_display = ('city', 'type')
    search_fields = ('city', 'type')