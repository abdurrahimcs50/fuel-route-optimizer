import logging
import time
import uuid

from rest_framework.response import Response
from rest_framework.views import APIView

from routing.algorithm import NoStationsInRangeError
from routing.candidates import select_stops_for_route
from routing.exceptions import (
    GeocodeFailedError,
    NoStationsInRangeAPIError,
    RouteNotFoundAPIError,
)
from routing.serializers import RouteRequestSerializer
from routing.services import GeocodeError, RouteNotFoundError, geocode_location, get_route

logger = logging.getLogger("routing")


class RouteView(APIView):
    def post(self, request):
        request_id = uuid.uuid4().hex[:12]
        serializer = RouteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        start_text = serializer.validated_data["start_location"]
        finish_text = serializer.validated_data["finish_location"]

        external_start = time.perf_counter()
        try:
            start_coords = geocode_location(start_text, request_id)
        except GeocodeError as exc:
            raise GeocodeFailedError(f"Could not geocode start_location: {start_text!r}") from exc

        try:
            finish_coords = geocode_location(finish_text, request_id)
        except GeocodeError as exc:
            raise GeocodeFailedError(f"Could not geocode finish_location: {finish_text!r}") from exc

        try:
            geometry, total_distance_miles = get_route(start_coords, finish_coords, request_id)
        except RouteNotFoundError as exc:
            raise RouteNotFoundAPIError(str(exc)) from exc
        external_elapsed_ms = (time.perf_counter() - external_start) * 1000

        internal_start = time.perf_counter()
        try:
            result = select_stops_for_route(geometry, total_distance_miles, start_coords)
        except NoStationsInRangeError as exc:
            raise NoStationsInRangeAPIError(str(exc)) from exc
        internal_elapsed_ms = (time.perf_counter() - internal_start) * 1000

        logger.info(
            "request_complete request_id=%s distance_miles=%.1f stops=%d total_cost=%.2f "
            "external_ms=%.0f internal_ms=%.0f",
            request_id, total_distance_miles, len(result.fuel_stops), result.total_fuel_cost,
            external_elapsed_ms, internal_elapsed_ms,
        )

        return Response(
            {
                "route": geometry,
                "total_distance_miles": round(total_distance_miles, 1),
                "fuel_stops": [
                    {
                        "name": stop.name,
                        "address": stop.address,
                        "city": stop.city,
                        "state": stop.state,
                        "price_per_gallon": stop.price_per_gallon,
                        "mile_marker": stop.mile_marker,
                        "gallons_purchased": stop.gallons_purchased,
                    }
                    for stop in result.fuel_stops
                ],
                "total_fuel_cost": result.total_fuel_cost,
            }
        )
