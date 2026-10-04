"""Projection interface; coordinates in local planar kilometres."""
import math
import numpy as np


def haversine(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, [*a, *b])
    value = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(value)))


def project(coordinates, config):
    points = np.asarray(coordinates, dtype=float).reshape((-1, 2))
    origin = points.mean(axis=0) if len(points) else np.zeros(2)
    result = (points-origin) * [math.cos(math.radians(origin[1])) * config['km_per_lon_degree'], config['km_per_lat_degree']]
    seen = {}
    for i, point in enumerate(points):
        key = tuple(point)
        count = seen.get(key, 0)
        result[i, 0] += count * config['duplicate_epsilon_km']
        seen[key] = count+1
    return result, origin.tolist()
