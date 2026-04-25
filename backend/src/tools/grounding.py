def get_search_grounding_tool() -> dict:
    return {"google_search": {}}


def get_maps_grounding_tool() -> dict:
    """
    Use for activities, meals, and other place-based searches.
    Cannot be combined with google_search in the same request.
    """
    return {"google_maps": {}}
