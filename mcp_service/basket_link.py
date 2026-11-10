def build_basket_link(site_url: str, items: list[tuple[str, int]]) -> str | None:
    """The site's basket page with the items already in it: <site>/basket?items=<barcode>:<qty>,... The site
    imports them into a new basket. None when the site's address is not configured (no broken links)."""
    if not site_url:
        return None
    return f"{site_url.rstrip('/')}/basket?items=" + ",".join(f"{barcode}:{qty}" for barcode, qty in items)
