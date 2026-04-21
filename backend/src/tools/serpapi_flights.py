import os
import httpx
from datetime import datetime
from urllib.parse import quote, urlencode

import logging
logger = logging.getLogger(__name__)

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

# Common city -> IATA airport code mapping (Southeast Asia focus + major hubs)
_IATA_MAP: dict[str, str] = {
    "singapore": "SIN",
    "tokyo": "TYO", "osaka": "KIX", "kyoto": "KIX", "nagoya": "NGO",
    "fukuoka": "FUK", "sapporo": "CTS", "naha": "OKA", "okinawa": "OKA",
    "bangkok": "BKK", "chiang mai": "CNX", "phuket": "HKT", "krabi": "KBV",
    "kuala lumpur": "KUL", "penang": "PEN", "langkawi": "LGK", "kota kinabalu": "BKI",
    "jakarta": "CGK", "bali": "DPS", "denpasar": "DPS", "yogyakarta": "JOG",
    "surabaya": "SUB",
    "manila": "MNL", "cebu": "CEB",
    "ho chi minh city": "SGN", "hanoi": "HAN", "da nang": "DAD",
    "hong kong": "HKG", "macau": "MFM",
    "taipei": "TPE", "kaohsiung": "KHH",
    "seoul": "ICN", "busan": "PUS", "jeju": "CJU",
    "beijing": "PEK", "shanghai": "PVG", "guangzhou": "CAN", "shenzhen": "SZX",
    "chengdu": "CTU", "chongqing": "CKG", "kunming": "KMG", "xi'an": "XIY",
    "xian": "XIY", "hangzhou": "HGH", "nanjing": "NKG", "wuhan": "WUH",
    "lijiang": "LJG", "dali": "DLU", "guilin": "KWL", "zhangjiajie": "DYG",
    "sydney": "SYD", "melbourne": "MEL", "brisbane": "BNE", "perth": "PER",
    "auckland": "AKL", "queenstown": "ZQN",
    "london": "LHR", "paris": "CDG", "rome": "FCO", "barcelona": "BCN",
    "amsterdam": "AMS", "berlin": "BER", "munich": "MUC", "zurich": "ZRH",
    "vienna": "VIE", "prague": "PRG", "istanbul": "IST", "dubai": "DXB",
    "new york": "JFK", "los angeles": "LAX", "san francisco": "SFO",
    "mumbai": "BOM", "delhi": "DEL", "new delhi": "DEL",
    "colombo": "CMB", "kathmandu": "KTM", "yangon": "RGN",
    "phnom penh": "PNH", "siem reap": "REP", "vientiane": "VTE",
}


def get_iata_code(city: str) -> str | None:
    """
    Look up IATA code for a city name. Returns None if not found.
    """
    return _IATA_MAP.get(city.lower().strip())


def _google_flights_url(origin_city: str, dest_city: str, date: str) -> str:
    """
    Build a working Google Flights search URL using city names.

    Google Flights reliably parses natural-language queries like:
      flights from Singapore to Tokyo on 2026-05-01
    IATA codes in the query string do NOT work — always use city names.
    """
    query = f"flights from {origin_city} to {dest_city}"
    if date:
        query += f" on {date}"
    return f"https://www.google.com/travel/flights?q={quote(query)}"


async def search_flights(
    origin_code: str,
    dest_code: str,
    date: str,
    max_results: int = 5,
    origin_city: str = "",
    dest_city: str = "",
) -> list[dict] | None:
    """
    Search one-way flights via SerpAPI Google Flights.

    Args:
        origin_code: IATA code (e.g. "SIN")
        dest_code: IATA code (e.g. "KMG")
        date: departure date YYYY-MM-DD
        max_results: max flights to return
        origin_city: human-readable city name for booking URL (e.g. "Singapore")
        dest_city: human-readable city name for booking URL (e.g. "Kunming")

    Returns:
        List of FlightOption-compatible dicts, or None on failure.
    """
    if not SERPAPI_KEY:
        return None

    params = {
        "engine": "google_flights",
        "departure_id": origin_code,
        "arrival_id": dest_code,
        "outbound_date": date,
        "type": "2",  # one-way
        "currency": "SGD",
        "hl": "en",
        "api_key": SERPAPI_KEY,
    }

    url = f"https://serpapi.com/search?{urlencode(params)}"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("SerpAPI flight search failed: %s", e)
        return None

    if "error" in data:
        logger.warning("SerpAPI returned error: %s", data["error"])
        return None

    # Parse best_flights first (Google's own ranking), then other_flights
    # Do NOT re-sort — Google Flights already ranks best_flights by value
    results: list[dict] = []
    for flight_group in (data.get("best_flights") or []) + (data.get("other_flights") or []):
        if len(results) >= max_results:
            break

        legs = flight_group.get("flights", [])
        if not legs:
            continue

        price = flight_group.get("price")
        total_duration = flight_group.get("total_duration", 0)  # minutes

        # Use first leg for primary airline info
        first_leg = legs[0]
        last_leg = legs[-1]

        airline = first_leg.get("airline", "Unknown")
        flight_number = first_leg.get("flight_number", "")

        dep_airport = first_leg.get("departure_airport", {})
        arr_airport = last_leg.get("arrival_airport", {})

        dep_time = dep_airport.get("time", "")  # "2026-04-07 02:30"
        arr_time = arr_airport.get("time", "")

        # Convert SerpAPI time format to ISO 8601
        dep_iso = _to_iso(dep_time)
        arr_iso = _to_iso(arr_time)

        # Duration to ISO 8601
        dur_iso = None
        if total_duration:
            hours, mins = divmod(total_duration, 60)
            dur_iso = f"PT{hours}H{mins}M" if hours else f"PT{mins}M"

        stops = len(legs) - 1

        # Build Google Flights search link using city names (IATA codes don't work in ?q=)
        # Fall back to IATA codes only if city names weren't provided
        _origin_label = origin_city or origin_code
        _dest_label = dest_city or dest_code
        booking_link = _google_flights_url(_origin_label, _dest_label, date)

        # Airline logo from SerpAPI
        image_url = first_leg.get("airline_logo")

        results.append({
            "airline": airline,
            "price_sgd": float(price) if price else 0.0,
            "departure_time": dep_iso,
            "arrival_time": arr_iso,
            "stops": stops,
            "duration": dur_iso,
            "cabin_class": "economy",
            "carrier_code": first_leg.get("airline", "")[:2].upper(),
            "flight_number": flight_number,
            "source": "serpapi_google_flights",
            "verified": True,
            "booking_link": booking_link,
            "image_url": image_url,
        })

    if results:
        logger.info("SerpAPI: found %d flights %s->%s on %s", len(results), origin_code, dest_code, date)
    return results if results else None


def _to_iso(serpapi_time: str) -> str:
    """
    Convert SerpAPI time '2026-04-07 02:30' to ISO 8601 '2026-04-07T02:30:00'.
    """
    if not serpapi_time:
        return ""

    try:
        # SerpAPI format: "2026-04-07 02:30" or similar
        dt = datetime.strptime(serpapi_time.strip(), "%Y-%m-%d %H:%M")
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    except ValueError:
        # Already ISO or unknown format — pass through
        return serpapi_time
