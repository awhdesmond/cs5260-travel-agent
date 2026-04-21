import os
import json
import logging

from typing import Any

logger = logging.getLogger(__name__)

_pool = None
_pool_init_failed = False

def _serialize_record(record: dict) -> dict:
    for key, value in record.items():
        if hasattr(value, "isoformat"):
            record[key] = value.isoformat()
        elif isinstance(value, (dict, list)):
            pass
        elif hasattr(value, "__str__") and not isinstance(
            value, (str, int, float, bool, type(None))
        ):
            record[key] = str(value)
    return record


def get_db_pool():
    """
    Lazy singleton connection pool.
    Returns None if DATABASE_URL is not set.
    """
    global _pool, _pool_init_failed
    if _pool_init_failed:
        return None
    if _pool is None:
        import psycopg_pool

        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.warning("DATABASE_URL not set — DB features disabled")
            _pool_init_failed = True
            return None
        try:
            _pool = psycopg_pool.ConnectionPool(
                database_url, min_size=1, max_size=5,
                timeout=5,          # fail fast if DB unreachable
                reconnect_timeout=0,
            )
        except Exception as e:
            logger.warning("DB pool creation failed (non-fatal): %s", e)
            _pool_init_failed = True
            return None
    return _pool

def insert_run(data: dict[str, Any]) -> None:
    pool = get_db_pool()
    if pool is None:
        return

    travel_dates = data.get("travel_dates")
    if isinstance(travel_dates, dict):
        travel_dates = json.dumps(travel_dates)

    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO runs (
                        user_id, architecture, booking_mode,
                        latency_ms, total_tokens, estimated_cost_sgd,
                        llm_call_count, conflicts_detected,
                        destination, travel_dates, cache_hit,
                        retry_count, success, traveler_count, trip_days, num_cities
                    ) VALUES (
                        %(user_id)s, %(architecture)s, %(booking_mode)s,
                        %(latency_ms)s, %(total_tokens)s, %(estimated_cost_sgd)s,
                        %(llm_call_count)s, %(conflicts_detected)s,
                        %(destination)s, %(travel_dates)s, %(cache_hit)s,
                        %(retry_count)s, %(success)s, %(traveler_count)s, %(trip_days)s, %(num_cities)s
                    )
                    """,
                    {
                        "user_id": data.get("user_id"),
                        "architecture": data["architecture"],
                        "booking_mode": data["booking_mode"],
                        "latency_ms": data.get("latency_ms"),
                        "total_tokens": data.get("total_tokens"),
                        "estimated_cost_sgd": data.get("estimated_cost_sgd"),
                        "llm_call_count": data.get("llm_call_count"),
                        "conflicts_detected": data.get("conflicts_detected", 0),
                        "destination": data.get("destination"),
                        "travel_dates": travel_dates,
                        "cache_hit": data.get("cache_hit", False),
                        "retry_count": data.get("retry_count", 0),
                        "success": data.get("success", False),
                        "traveler_count": data.get("traveler_count"),
                        "trip_days": data.get("trip_days"),
                        "num_cities": data.get("num_cities"),
                    },
                )
            conn.commit()
    except Exception as e:
        logger.warning("insert_run DB error (non-fatal): %s", e)


def get_runs() -> list[dict[str, Any]]:
    pool = get_db_pool()
    if pool is None:
        return []
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM runs ORDER BY created_at DESC"
                )
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
    except Exception as e:
        logger.warning("get_runs DB error: %s", e)
        return []

    return [_serialize_record(dict(zip(columns, row))) for row in rows]


def save_itinerary(
    user_id: str,
    destination: str,
    travel_dates: dict | None,
    architecture: str,
    itinerary: dict,
) -> str | None:
    pool = get_db_pool()
    if pool is None:
        return None
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO itineraries (user_id, destination, travel_dates, architecture, itinerary) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (
                        user_id,
                        destination,
                        json.dumps(travel_dates) if travel_dates else None,
                        architecture,
                        json.dumps(itinerary),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return str(row[0]) if row else None
    except Exception as e:
        logger.warning("save_itinerary DB error: %s", e)
        return None


def get_user_itineraries(user_id: str) -> list[dict]:
    """
    Fetch all itineraries for a user sorted by created_at DESC. Omits itinerary JSONB blob.
    """
    pool = get_db_pool()
    if pool is None:
        return []
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, destination, travel_dates, architecture, status, created_at "
                    "FROM itineraries WHERE user_id = %s AND status IN ('confirmed', 'sandbox_confirmed') "
                    "ORDER BY created_at DESC",
                    (user_id,),
                )
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
    except Exception as e:
        logger.warning("get_user_itineraries DB error: %s", e)
        return []

    return [_serialize_record(dict(zip(columns, row))) for row in rows]


def cache_lookup(city: str, trip_style: str, activity_intensity: str) -> dict | None:
    pool = get_db_pool()
    if pool is None:
        return None
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT itinerary, preferences, similarity(destination, %s) AS sim
                    FROM itinerary_cache
                    WHERE similarity(destination, %s) >= 0.60
                      AND expires_at > NOW()
                    ORDER BY sim DESC
                    LIMIT 10
                    """,
                    (city, city),
                )
                rows = cur.fetchall()
    except Exception as e:
        logger.warning("cache_lookup DB error: %s", e)
        return None

    for itinerary_data, preferences, _sim in rows:
        if not isinstance(preferences, dict):
            try:
                preferences = json.loads(preferences) if isinstance(preferences, str) else {}
            except (json.JSONDecodeError, TypeError):
                continue
        stored_style = preferences.get("trip_style", "")
        stored_intensity = preferences.get("activity_intensity", "")
        # No preference = lenient (accept any cached entry);
        # with preference = strict (exact match only)
        style_ok = not trip_style or stored_style == trip_style
        intensity_ok = not activity_intensity or stored_intensity == activity_intensity
        if style_ok and intensity_ok:
            return itinerary_data
    return None


def cache_save(city: str,trip_style: str,activity_intensity: str,activities_plan: dict,) -> None:
    pool = get_db_pool()
    if pool is None:
        return
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO itinerary_cache
                        (destination, preferences, itinerary)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        city,
                        json.dumps({"trip_style": trip_style, "activity_intensity": activity_intensity}),
                        json.dumps(activities_plan),
                    ),
                )
            conn.commit()
    except Exception as e:
        logger.warning("cache_save DB error: %s", e)


def meal_cache_lookup(city: str, meal_type: str, meal_preferences: str) -> list[dict]:
    """
    Look up cached meal options using city matching + meal_type.

    Returns a list of {meal_option, lat, lng} dicts. Scoring is done in Python by the caller.
    Fails open on DB error.
    """
    pool = get_db_pool()
    if pool is None:
        return []

    # No preference / default = lenient (accept any cached meal for this city)
    is_lenient = meal_preferences in ("", "local cuisine")
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                if is_lenient:
                    cur.execute(
                        """
                        SELECT meal_option, lat, lng, similarity(city, %s) AS sim
                        FROM meal_cache
                        WHERE similarity(city, %s) >= 0.60
                          AND meal_type = %s
                          AND expires_at > NOW()
                        ORDER BY sim DESC
                        LIMIT 50
                        """,
                        (city, city, meal_type),
                    )
                else:
                    cur.execute(
                        """
                        SELECT meal_option, lat, lng, similarity(city, %s) AS sim
                        FROM meal_cache
                        WHERE similarity(city, %s) >= 0.60
                          AND meal_type = %s
                          AND meal_preferences = %s
                          AND expires_at > NOW()
                        ORDER BY sim DESC
                        LIMIT 50
                        """,
                        (city, city, meal_type, meal_preferences),
                    )
                rows = cur.fetchall()
    except Exception as e:
        logger.warning("meal_cache_lookup DB error: %s", e)
        return []

    results = []
    for meal_option, lat, lng, _sim in rows:
        if not isinstance(meal_option, dict):
            try:
                meal_option = json.loads(meal_option) if isinstance(meal_option, str) else {}
            except (json.JSONDecodeError, TypeError):
                continue
        results.append({"meal_option": meal_option, "lat": lat, "lng": lng})
    return results


def meal_cache_save(
    city: str,
    day_number: int,
    meal_type: str,
    meal_preferences: str,
    meal_options: list[dict],
) -> None:
    pool = get_db_pool()
    if pool is None:
        return
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                for opt in meal_options:
                    cur.execute(
                        """
                        INSERT INTO meal_cache
                            (city, day_number, meal_type, meal_preferences, meal_option, lat, lng)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            city,
                            day_number,
                            meal_type,
                            meal_preferences,
                            json.dumps(opt),
                            opt.get("lat"),
                            opt.get("lng"),
                        ),
                    )
            conn.commit()
    except Exception as e:
        logger.warning("meal_cache_save DB error: %s", e)


def update_itinerary_status(
    itinerary_id: str,
    status: str,
    booking_confirmation_id: str | None = None
) -> bool:
    pool = get_db_pool()
    if pool is None:
        return False
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE itineraries SET status = %s, booking_confirmation_id = %s WHERE id = %s",
                    (status, booking_confirmation_id, itinerary_id),
                )
            conn.commit()
        return True
    except Exception as e:
        logger.warning("update_itinerary_status DB error: %s", e)
        return False


def update_itinerary_data(itinerary_id: str, itinerary: dict) -> bool:
    pool = get_db_pool()
    if pool is None:
        return False
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE itineraries SET itinerary = %s WHERE id = %s",
                    (json.dumps(itinerary), itinerary_id),
                )
            conn.commit()
        return True
    except Exception as e:
        logger.warning("update_itinerary_data DB error: %s", e)
        return False


def save_plan_options(user_id: str, plan_state: dict) -> str | None:
    pool = get_db_pool()
    if pool is None:
        return None
    try:
        with pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO plan_options (user_id, plan_state) "
                "VALUES (%s, %s::jsonb) RETURNING id",
                (user_id, json.dumps(plan_state, default=str)),
            ).fetchone()
            conn.commit()
            return str(row[0]) if row else None
    except Exception as e:
        logger.warning("save_plan_options failed (non-fatal): %s", e)
        return None


def get_plan_options(plan_id: str, user_id: str) -> dict | None:
    pool = get_db_pool()
    if pool is None:
        return None
    try:
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT plan_state FROM plan_options "
                "WHERE id = %s AND user_id = %s AND expires_at > NOW()",
                (plan_id, user_id),
            ).fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.warning("get_plan_options failed (non-fatal): %s", e)
        return None


def save_thread_state(thread_id: str, user_id: str, plan_state: dict) -> None:
    pool = get_db_pool()
    if pool is None:
        return
    try:
        with pool.connection() as conn:
            conn.execute(
                "INSERT INTO plan_options (id, user_id, plan_state, expires_at) "
                "VALUES (%s, %s, %s::jsonb, NOW() + INTERVAL '24 hours') "
                "ON CONFLICT (id) DO UPDATE SET plan_state = EXCLUDED.plan_state, "
                "expires_at = NOW() + INTERVAL '24 hours'",
                (thread_id, user_id, json.dumps(plan_state, default=str)),
            )
            conn.commit()
    except Exception as e:
        logger.warning("save_thread_state failed (non-fatal): %s", e)


def get_itinerary_by_id(itinerary_id: str, user_id: str) -> dict | None:
    pool = get_db_pool()
    if pool is None:
        return None
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, destination, travel_dates, architecture, itinerary, "
                    "status, booking_confirmation_id, created_at "
                    "FROM itineraries WHERE id = %s AND user_id = %s",
                    (itinerary_id, user_id),
                )
                columns = [desc[0] for desc in cur.description]
                row = cur.fetchone()
    except Exception as e:
        logger.warning("get_itinerary_by_id DB error: %s", e)
        return None

    if row is None:
        return None

    return _serialize_record(dict(zip(columns, row)))
