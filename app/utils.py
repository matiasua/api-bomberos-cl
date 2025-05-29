from geopy.distance import geodesic

def filter_bomberos(data, **kwargs):
    results = data
    for key, value in kwargs.items():
        if value:
            results = [item for item in results if str(item.get(key, '')).lower() == str(value).lower()]
    return results

def filter_by_coords(data, lat, lon, radio_km):
    center = (lat, lon)
    return [
        item for item in data
        if 'latitud' in item and 'longitud' in item and
        geodesic(center, (item['latitud'], item['longitud'])).km <= radio_km
    ]
