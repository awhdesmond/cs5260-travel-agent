
import os
import httpx

USE_GOOGLE_PLACES: bool = os.getenv("USE_GOOGLE_PLACES", "true").lower() == "true"
GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")


async def enrich_with_places_api(activity_name: str, city: str) -> dict:
    """
    Enrich an activity with lat/lng + formatted address.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # text search first, just to grab the place_id
            text_search_resp = await client.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers={
                    "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
                    "X-Goog-FieldMask": "places.id",
                },
                json={"textQuery": f"{activity_name} {city}"},
            )
            text_search_resp.raise_for_status()
            places = text_search_resp.json().get("places", [])
            if not places:
                return {}

            place_id = places[0]["id"]

            # then fetch address + lat/lng
            detail_resp = await client.get(
                f"https://places.googleapis.com/v1/places/{place_id}",
                headers={
                    "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
                    "X-Goog-FieldMask": "formattedAddress,location",
                },
            )
            detail_resp.raise_for_status()
            detail = detail_resp.json()
            return {
                "place_id": place_id,
                "address": detail.get("formattedAddress"),
                "lat": detail.get("location", {}).get("latitude"),
                "lng": detail.get("location", {}).get("longitude"),
            }
    except Exception:
        return {}


async def get_place_photo_url(place_id: str, max_width: int = 400) -> str | None:
    """
    Fetch a photo url for a place.
    """
    if not USE_GOOGLE_PLACES or not GOOGLE_MAPS_API_KEY:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # grab the photo resource name from place details
            detail_resp = await client.get(
                f"https://places.googleapis.com/v1/places/{place_id}",
                headers={
                    "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
                    "X-Goog-FieldMask": "photos",
                },
            )
            detail_resp.raise_for_status()
            photos = detail_resp.json().get("photos", [])
            if not photos:
                return None

            photo_name = photos[0]["name"]

            # then resolve it to a direct uri (no redirect)
            media_resp = await client.get(
                f"https://places.googleapis.com/v1/{photo_name}/media",
                params={
                    "maxWidthPx": max_width,
                    "skipHttpRedirect": "true",
                    "key": GOOGLE_MAPS_API_KEY,
                },
            )
            media_resp.raise_for_status()
            return media_resp.json().get("photoUri")

    except Exception:
        return None
