"""DB + in-process station lookups for a given route. No external HTTP
calls happen anywhere in this module — station coordinates come entirely
from the DB (already geocoded offline by `geocode_stations`).

Orchestrates: bounding-box (indexed) DB query -> KD-tree nearest-point
lookup per candidate -> corridor-distance filter -> mile-marker assignment
-> hand off to the pure greedy selector in algorithm.py, retrying with a
wider corridor if a window comes up empty (spec's sparse-coverage
fallback).
"""

import math

import numpy as np
from django.conf import settings
from django.db.models import Avg
from scipy.spatial import cKDTree

from routing.algorithm import (
    NoStationsInRangeError,
    SelectionResult,
    StationCandidate,
    select_fuel_stops,
)
from stations.models import FuelStation

EARTH_RADIUS_MILES = 3958.8
MAX_ROUTE_POINTS = 3000


def haversine_miles(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(math.radians, (lat1, lng1, lat2, lng2))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def _route_points_and_mile_markers(geometry: dict, total_distance_miles: float):
    """GeoJSON LineString coordinates are [lng, lat]; flip to (lat, lng),
    decimate if very dense, and build a cumulative-mile array scaled so the
    last point equals OSRM's own total_distance_miles."""
    coords = geometry["coordinates"]
    if len(coords) > MAX_ROUTE_POINTS:
        step = math.ceil(len(coords) / MAX_ROUTE_POINTS)
        coords = coords[::step] + [coords[-1]]

    route_points = [(lat, lng) for lng, lat in coords]

    cumulative = [0.0]
    for i in range(1, len(route_points)):
        prev_lat, prev_lng = route_points[i - 1]
        lat, lng = route_points[i]
        cumulative.append(cumulative[-1] + haversine_miles(prev_lat, prev_lng, lat, lng))

    raw_total = cumulative[-1]
    if raw_total > 0:
        scale = total_distance_miles / raw_total
        cumulative = [d * scale for d in cumulative]

    return route_points, cumulative


def _bounding_box(route_points, padding_degrees):
    lats = [p[0] for p in route_points]
    lngs = [p[1] for p in route_points]
    return (
        min(lats) - padding_degrees,
        max(lats) + padding_degrees,
        min(lngs) - padding_degrees,
        max(lngs) + padding_degrees,
    )


def _fetch_stations_in_bbox(min_lat, max_lat, min_lng, max_lng):
    """The one indexed DB query per request for station candidates —
    reused across all corridor-widening attempts, never re-queried."""
    return list(
        FuelStation.objects.filter(
            lat__isnull=False,
            lat__gte=min_lat,
            lat__lte=max_lat,
            lng__gte=min_lng,
            lng__lte=max_lng,
        ).values("id", "name", "address", "city", "state", "price", "lat", "lng")
    )


def _assign_mile_markers(stations, tree, route_points, cumulative_miles, corridor_threshold):
    """KD-tree nearest-point lookup (approximate, on lat/lng degrees) to
    narrow down, then a precise haversine check against that point for the
    actual corridor distance in miles."""
    if not stations:
        return []

    query_points = np.array([[s["lat"], s["lng"]] for s in stations])
    _, indices = tree.query(query_points)

    candidates = []
    for station, idx in zip(stations, indices):
        corridor_miles, mile_marker = _project_onto_route(
            station["lat"], station["lng"], int(idx), route_points, cumulative_miles
        )
        if corridor_miles <= corridor_threshold:
            candidates.append(
                StationCandidate(
                    id=station["id"],
                    name=station["name"],
                    address=station["address"],
                    city=station["city"],
                    state=station["state"],
                    price=float(station["price"]),
                    mile_marker=mile_marker,
                )
            )
    return candidates


def _project_onto_route(lat, lng, nearest_vertex_idx, route_points, cumulative_miles):
    """The KD-tree only finds the nearest route *vertex*. On straight
    stretches where OSRM's shape points are sparse, the true closest point
    on the route is somewhere along a *segment*, not at a vertex — so
    project onto the (up to) two segments adjacent to the nearest vertex
    and take whichever is closer. Uses a local equirectangular flat-plane
    approximation (accurate at corridor-threshold scales of a few tens of
    miles) rather than full spherical projection, which would be overkill
    here.
    """
    ref_lat_rad = math.radians(lat)
    lat_miles_per_deg = 69.0
    lng_miles_per_deg = 69.0 * math.cos(ref_lat_rad)

    def to_xy(pt_lat, pt_lng):
        return (
            (pt_lat - lat) * lat_miles_per_deg,
            (pt_lng - lng) * lng_miles_per_deg,
        )

    station_xy = (0.0, 0.0)  # station is the origin of its own local frame

    best_distance = None
    best_mile_marker = None

    segment_indices = [
        i
        for i in (nearest_vertex_idx - 1, nearest_vertex_idx)
        if 0 <= i < len(route_points) - 1
    ]
    if not segment_indices:
        # route has only one point (degenerate route)
        return (
            haversine_miles(lat, lng, *route_points[nearest_vertex_idx]),
            cumulative_miles[nearest_vertex_idx],
        )

    for i in segment_indices:
        a_xy = to_xy(*route_points[i])
        b_xy = to_xy(*route_points[i + 1])
        ax, ay = a_xy
        bx, by = b_xy
        seg_dx, seg_dy = bx - ax, by - ay
        seg_len_sq = seg_dx**2 + seg_dy**2

        if seg_len_sq == 0:
            t = 0.0
        else:
            t = ((station_xy[0] - ax) * seg_dx + (station_xy[1] - ay) * seg_dy) / seg_len_sq
            t = max(0.0, min(1.0, t))

        proj_x = ax + t * seg_dx
        proj_y = ay + t * seg_dy
        distance = math.hypot(station_xy[0] - proj_x, station_xy[1] - proj_y)
        mile_marker = cumulative_miles[i] + t * (cumulative_miles[i + 1] - cumulative_miles[i])

        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_mile_marker = mile_marker

    return best_distance, best_mile_marker


def _default_price_near(lat, lng, stations, radius_miles):
    nearby_prices = [
        float(s["price"])
        for s in stations
        if haversine_miles(lat, lng, s["lat"], s["lng"]) <= radius_miles
    ]
    if nearby_prices:
        return min(nearby_prices)

    avg = FuelStation.objects.filter(lat__isnull=False).aggregate(avg=Avg("price"))["avg"]
    return float(avg) if avg is not None else 0.0


def select_stops_for_route(
    geometry: dict,
    total_distance_miles: float,
    start_coords: tuple[float, float],
) -> SelectionResult:
    route_points, cumulative_miles = _route_points_and_mile_markers(geometry, total_distance_miles)
    min_lat, max_lat, min_lng, max_lng = _bounding_box(route_points, settings.BBOX_PADDING_DEGREES)
    stations = _fetch_stations_in_bbox(min_lat, max_lat, min_lng, max_lng)

    default_price = _default_price_near(
        start_coords[0], start_coords[1], stations, settings.DEFAULT_PRICE_SEARCH_RADIUS_MILES
    )

    if total_distance_miles <= settings.VEHICLE_RANGE_MILES:
        return select_fuel_stops(total_distance_miles, [], default_price)

    tree = cKDTree(np.array(route_points))

    last_error = None
    for threshold in settings.CORRIDOR_WIDEN_STEPS_MILES:
        candidates = _assign_mile_markers(stations, tree, route_points, cumulative_miles, threshold)
        try:
            return select_fuel_stops(total_distance_miles, candidates, default_price)
        except NoStationsInRangeError as exc:
            last_error = exc
            continue

    raise last_error
