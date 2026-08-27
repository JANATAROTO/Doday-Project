def favorites(request):
    """RF17: expose the current session's favorite count to every template
    (used for the "Favorites (N)" link in the header)."""
    return {"favorite_count": len(request.session.get("favorite_ids", []))}
