# app/seo.py
#
# Search-engine and link-preview support. The site is a single-page app whose HTML is empty until its
# JavaScript runs, so the edge nginx sends page requests here: the built page shell is fetched from the
# frontend container and each page's own title, description, canonical link, structured data (JSON-LD) and
# a plain-text summary are put into it. Unknown addresses get a real 404. Also robots.txt and the sitemaps.

import html
import json
import math
import re
import time
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.api.routes import _not_wholesale
from app.chains import display_chain_name_sql
from app.db.database import get_db
from app.db.models import Chain, IngestRun, Price, Product, Store
from app.images import is_allowed_image_url

router = APIRouter()

SITE_NAME = "סלי"
SHELL_TTL = 30            # seconds; short, so a new frontend build's file names are picked up quickly
SITEMAP_TTL = 3600
SITEMAP_PAGE = 40000      # urls per product sitemap (the protocol allows 50,000)
MIN_STORES_FOR_SITEMAP = 2   # a product sold in one store has nothing to compare: not worth a search result
BARCODE_RE = re.compile(r"^[0-9A-Za-z_-]{1,30}$")

# Pages every visitor sees the same. `index=False` pages are for using the site, not for search results.
PAGES = {
    "": {
        "title": "סלי — השוואת מחירי סופרמרקט בישראל | איפה הכי זול",
        "description": "השוואת מחירי סופרמרקט בין כל הרשתות בישראל: חפשו מוצר או סל קניות וראו איפה הכי זול, "
                       "עם מחירים שמתעדכנים פעמיים ביום.",
        "h1": "השוואת מחירי סופרמרקט בישראל",
        "intro": "חפשו מוצר או בנו סל קניות, וראו באיזו רשת ובאיזה סניף הכי זול. המחירים מגיעים מקבצי המחירים "
                 "הציבוריים שהרשתות מפרסמות לפי חוק, ומתעדכנים פעמיים ביום.",
        "index": True, "freq": "daily", "priority": "1.0",
    },
    "promotions": {
        "title": "מבצעים בסופרמרקטים — הכי משתלם מול השוק | סלי",
        "description": "המבצעים המשתלמים ביותר בסופרמרקטים בישראל, מושווים למחיר הזול ביותר בשוק. "
                       "סינון לפי רשת ועיר.",
        "h1": "מבצעים בסופרמרקטים",
        "intro": "מבצעים של רשתות השיווק בישראל, מדורגים לפי החיסכון לעומת המחיר הזול ביותר של אותם מוצרים בשוק.",
        "index": True, "freq": "daily", "priority": "0.8",
    },
    "about": {
        "title": "אודות והבהרות | סלי",
        "description": "מה זה סלי, מאיפה המחירים, פרטיות והבהרות משפטיות על אתר השוואת מחירי הסופרמרקט.",
        "h1": "אודות והבהרות",
        "intro": "סלי משווה מחירי סופרמרקט בין רשתות בישראל. המחירים להמחשה והשוואה בלבד.",
        "index": True, "freq": "monthly", "priority": "0.3",
    },
    "basket": {
        "title": "הסל שלי | סלי",
        "description": "השוואת מחיר הסל שלכם בין הרשתות.",
        "h1": "הסל שלי", "intro": "", "index": False,
    },
    "scan": {
        "title": "סריקת ברקוד | סלי",
        "description": "סרקו ברקוד של מוצר וראו איפה הוא הכי זול.",
        "h1": "סריקת ברקוד", "intro": "", "index": False,
    },
}
REDIRECTS = {"search": "/", "index.html": "/"}


# ── Addresses ────────────────────────────────────────────────────────────────

def base_url(request: Request) -> str:
    return settings.SITE_URL or str(request.base_url).rstrip("/")


# ── The page shell ───────────────────────────────────────────────────────────

_shell_cache: Optional[tuple[float, str]] = None


async def _fetch_shell() -> str:
    async with httpx.AsyncClient(timeout=3) as client:
        r = await client.get(settings.SEO_SHELL_URL)
        r.raise_for_status()
        return r.text


async def get_shell() -> str:
    """The built index.html, kept for SHELL_TTL seconds; an older copy is used when the frontend does not answer."""
    global _shell_cache
    now = time.monotonic()
    if _shell_cache and now - _shell_cache[0] < SHELL_TTL:
        return _shell_cache[1]
    try:
        shell = await _fetch_shell()
    except Exception:
        if _shell_cache:
            return _shell_cache[1]
        raise HTTPException(status_code=503, detail="page shell unavailable")   # nginx then serves the plain app
    _shell_cache = (now, shell)
    return shell


# Tags the shell carries for the home page; replaced by the page's own.
_REPLACED_TAGS = re.compile(
    r'\s*<title>.*?</title>'
    r'|\s*<meta\s+(?:name="(?:description|robots|twitter:[^"]*)"|property="(?:og|article):[^"]*")[^>]*>'
    r'|\s*<link\s+rel="(?:canonical|alternate)"[^>]*>',
    re.S,
)


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _jsonld(data: dict) -> str:
    # "<" is escaped so no text in the data can close the script tag
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return f'<script type="application/ld+json">{payload}</script>'


def render_page(shell: str, *, base: str, path: str, title: str, description: str, index: bool,
                image: Optional[str] = None, jsonld: Optional[list[dict]] = None, body: str = "",
                og_type: str = "website") -> str:
    url = f"{base}{path}"
    image = image or f"{base}/og-image.jpg"
    robots = "index,follow,max-image-preview:large,max-snippet:-1" if index else "noindex,follow"
    head = [
        f"<title>{_esc(title)}</title>",
        f'<meta name="description" content="{_esc(description)}" />',
        f'<meta name="robots" content="{robots}" />',
    ]
    if index:
        head += [
            f'<link rel="canonical" href="{_esc(url)}" />',
            f'<link rel="alternate" hreflang="he-IL" href="{_esc(url)}" />',
            f'<link rel="alternate" hreflang="x-default" href="{_esc(url)}" />',
        ]
    head += [
        f'<meta property="og:type" content="{og_type}" />',
        f'<meta property="og:site_name" content="{SITE_NAME}" />',
        '<meta property="og:locale" content="he_IL" />',
        f'<meta property="og:title" content="{_esc(title)}" />',
        f'<meta property="og:description" content="{_esc(description)}" />',
        f'<meta property="og:url" content="{_esc(url)}" />',
        f'<meta property="og:image" content="{_esc(image)}" />',
        '<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:title" content="{_esc(title)}" />',
        f'<meta name="twitter:description" content="{_esc(description)}" />',
        f'<meta name="twitter:image" content="{_esc(image)}" />',
    ]
    head += [_jsonld(block) for block in (jsonld or [])]
    page = _REPLACED_TAGS.sub("", shell)
    page = page.replace("</head>", "\n    " + "\n    ".join(head) + "\n  </head>", 1)
    if body:
        # The app replaces this when its script runs; until then (and for crawlers that do not run it) it is the page.
        page = page.replace('<div id="root"></div>', f'<div id="root"><main class="seo-content">{body}</main></div>', 1)
    return page


def _html_response(content: str, status: int, index: bool) -> HTMLResponse:
    headers = {
        "Cache-Control": "no-cache",                            # browsers always ask; nginx keeps its own copy
        "X-Accel-Expires": "300" if status == 200 else "60",
    }
    if not index:
        headers["X-Robots-Tag"] = "noindex"
    return HTMLResponse(content, status_code=status, headers=headers)


_NAV = (
    '<nav><a href="/">חיפוש מוצר</a> · <a href="/promotions">מבצעים</a> · <a href="/basket">הסל שלי</a>'
    ' · <a href="/about">אודות</a></nav>'
)


def _organization(base: str) -> dict:
    return {"@type": "Organization", "@id": f"{base}/#org", "name": SITE_NAME, "url": f"{base}/",
            "logo": f"{base}/icon-512.png"}


# ── Pages ────────────────────────────────────────────────────────────────────

async def _chain_names(db: AsyncSession) -> list[str]:
    rows = (await db.execute(
        select(display_chain_name_sql()).select_from(Store).join(Chain, Chain.id == Store.chain_id).distinct()
    )).scalars().all()
    return sorted(set(rows))


async def _static_page(key: str, request: Request, db: AsyncSession) -> Response:
    page = PAGES[key]
    base = base_url(request)
    path = f"/{key}"
    body = f'<h1>{_esc(page["h1"])}</h1>' + (f'<p>{_esc(page["intro"])}</p>' if page["intro"] else "") + _NAV
    graph: list[dict] = []
    if key == "":
        try:
            chains = await _chain_names(db)
        except Exception:
            chains = []
        if chains:
            body += f'<p>הרשתות שאנחנו משווים: {_esc(", ".join(chains))}.</p>'
        graph = [
            {"@context": "https://schema.org", "@type": "WebSite", "@id": f"{base}/#site", "name": SITE_NAME,
             "url": f"{base}/", "inLanguage": "he-IL", "publisher": {"@id": f"{base}/#org"},
             "potentialAction": {"@type": "SearchAction",
                                 "target": {"@type": "EntryPoint", "urlTemplate": f"{base}/?q={{search_term_string}}"},
                                 "query-input": "required name=search_term_string"}},
            {"@context": "https://schema.org", **_organization(base)},
        ]
    elif page["index"]:
        kind = "AboutPage" if key == "about" else "CollectionPage"
        graph = [{"@context": "https://schema.org", "@type": kind, "name": page["title"], "url": f"{base}{path}",
                  "description": page["description"], "inLanguage": "he-IL", "isPartOf": {"@id": f"{base}/#site"}}]
    shell = await get_shell()
    content = render_page(shell, base=base, path="/" if key == "" else path, title=page["title"],
                          description=page["description"], index=page["index"], jsonld=graph, body=body)
    return _html_response(content, 200, page["index"])


def _short(text_: str, limit: int) -> str:
    text_ = " ".join(text_.split())
    return text_ if len(text_) <= limit else text_[: limit - 1].rstrip() + "…"


def _gtin_key(barcode: str) -> Optional[str]:
    if barcode.isdigit() and len(barcode) in (8, 12, 13, 14):
        return f"gtin{len(barcode)}"
    return None


async def _product_page(barcode: str, request: Request, db: AsyncSession) -> Response:
    base = base_url(request)
    product = None
    if BARCODE_RE.match(barcode) and len(barcode) >= 7:
        product = (await db.execute(select(Product).where(Product.barcode == barcode))).scalar_one_or_none()
    stats = None
    top = []
    if product:
        where = (Price.product_id == product.id, Price.is_current, Price.price > 0, _not_wholesale())
        joined = Price.__table__.join(Store.__table__, Price.store_id == Store.id).join(Chain.__table__, Store.chain_id == Chain.id)
        stats = (await db.execute(
            select(func.count(), func.min(Price.price), func.max(Price.price)).select_from(joined).where(*where)
        )).one()
        if stats[0]:
            top = (await db.execute(
                select(Price.price, Store.name, Store.city, display_chain_name_sql())
                .select_from(joined).where(*where).order_by(Price.price.asc()).limit(10)
            )).all()
    shell = await get_shell()
    if not product or not stats or not stats[0]:
        content = render_page(
            shell, base=base, path=f"/product/{barcode}", index=False,
            title="המוצר לא נמצא | סלי", description="לא מצאנו מחירים למוצר הזה. אפשר לחפש מוצר אחר.",
            body='<h1>המוצר לא נמצא</h1><p>לא מצאנו מחירים למוצר הזה.</p>' + _NAV,
        )
        return _html_response(content, 404, False)

    count, low, high = stats
    name = " ".join(product.name.split())
    title = f"{_short(name, 70)} — השוואת מחירים | סלי"
    if low == high:
        price_text = f"{low:.2f} ₪"
    else:
        price_text = f"{low:.2f} ₪ עד {high:.2f} ₪"
    description = _short(f"השוואת מחירים ל{name}: {price_text} ב-{count} סניפים בכל הרשתות. ראו איפה הכי זול.", 160)
    image = product.image_url if product.image_url and is_allowed_image_url(product.image_url) else None
    url = f"{base}/product/{barcode}"
    product_ld: dict = {
        "@type": "Product", "@id": f"{url}#product", "name": name, "url": url, "sku": barcode,
        "offers": {"@type": "AggregateOffer", "priceCurrency": "ILS", "lowPrice": f"{low:.2f}",
                   "highPrice": f"{high:.2f}", "offerCount": count, "url": url},
    }
    if _gtin_key(barcode):
        product_ld[_gtin_key(barcode)] = barcode
    if product.brand:
        product_ld["brand"] = {"@type": "Brand", "name": product.brand}
    if image:
        product_ld["image"] = [image]
    crumbs = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": f"{base}/"},
        {"@type": "ListItem", "position": 2, "name": name, "item": url},
    ]}
    rows = "".join(
        f"<li>{_esc(chain)}{' — ' + _esc(store) if store else ''}{' (' + _esc(city) + ')' if city else ''}: {price:.2f} ₪</li>"
        for price, store, city, chain in top
    )
    body = (f"<h1>{_esc(name)}</h1><p>{_esc(f'מחיר {price_text} ב-{count} סניפים.')}</p>"
            f"<h2>הסניפים הזולים ביותר</h2><ul>{rows}</ul>" + _NAV)
    content = render_page(shell, base=base, path=f"/product/{barcode}", title=title, description=description,
                          index=True, image=image, og_type="product", body=body,
                          jsonld=[{"@context": "https://schema.org", **product_ld},
                                  {"@context": "https://schema.org", **crumbs}])
    return _html_response(content, 200, True)


@router.api_route("/_seo/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def seo_page(path: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Every page address of the site (the edge nginx sends them here). The page's own head tags and summary are
    put into the app shell; an address that is not a page answers 404."""
    query = f"?{request.url.query}" if request.url.query else ""
    if path.endswith("/") and path != "":
        return RedirectResponse(f"/{path.rstrip('/')}{query}", status_code=301)
    if path in REDIRECTS:
        return RedirectResponse(REDIRECTS[path], status_code=301)
    if path in PAGES:
        return await _static_page(path, request, db)
    m = re.fullmatch(r"product/([^/]+)", path)
    if m:
        return await _product_page(m.group(1), request, db)
    shell = await get_shell()
    base = base_url(request)
    content = render_page(
        shell, base=base, path="/", index=False, title="הדף לא נמצא | סלי",
        description="הדף שחיפשתם לא קיים. אפשר לחפש מוצר ולהשוות מחירים.",
        body='<h1>הדף לא נמצא</h1><p>הכתובת הזאת לא קיימת באתר.</p>' + _NAV,
    )
    return _html_response(content, 404, False)


# ── robots.txt and sitemaps ──────────────────────────────────────────────────

@router.get("/robots.txt", include_in_schema=False)
async def robots_txt(request: Request):
    base = base_url(request)
    return PlainTextResponse(
        "User-agent: *\nAllow: /\nDisallow: /api/\n\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )


_sitemap_cache: dict[str, tuple[float, object]] = {}


async def _cached(key: str, make):
    hit = _sitemap_cache.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < SITEMAP_TTL:
        return hit[1]
    value = await make()
    _sitemap_cache[key] = (now, value)
    return value


_PRODUCTS_FROM = """
      FROM product_store_counts v JOIN products p ON p.id = v.product_id
     WHERE v.store_count >= :min_stores AND length(p.barcode) >= 7 AND p.barcode ~ '^[0-9A-Za-z_-]+$'
"""


async def _product_total(db: AsyncSession) -> int:
    return int((await db.execute(text("SELECT count(*) " + _PRODUCTS_FROM), {"min_stores": MIN_STORES_FOR_SITEMAP})).scalar() or 0)


async def _last_update(db: AsyncSession) -> str:
    """The day the data was last refreshed (Israel's date): the honest 'last modified' of every product page."""
    finished = (await db.execute(
        select(func.max(IngestRun.finished_at)).where(IngestRun.phase == "cycle", IngestRun.status.in_(("ok", "partial")))
    )).scalar()
    day = finished or datetime.now()
    return day.date().isoformat()


def _xml(body: str, ttl: int = SITEMAP_TTL) -> Response:
    return Response(body, media_type="application/xml", headers={"Cache-Control": f"public, max-age={ttl}"})


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap_index(request: Request, db: AsyncSession = Depends(get_db)):
    base = base_url(request)

    async def make():
        total = await _product_total(db)
        return total, await _last_update(db)

    total, last = await _cached("index", make)
    parts = [f"{base}/sitemap-pages.xml"] + [
        f"{base}/sitemap-products-{n}.xml" for n in range(1, math.ceil(total / SITEMAP_PAGE) + 1)
    ]
    items = "".join(f"  <sitemap><loc>{_esc(u)}</loc><lastmod>{last}</lastmod></sitemap>\n" for u in parts)
    return _xml('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + items + "</sitemapindex>\n")


@router.get("/sitemap-pages.xml", include_in_schema=False)
async def sitemap_pages(request: Request, db: AsyncSession = Depends(get_db)):
    base = base_url(request)
    last = (await _cached("index", lambda: _index_values(db)))[1]
    items = "".join(
        f"  <url><loc>{_esc(base + ('/' if key == '' else '/' + key))}</loc><lastmod>{last}</lastmod>"
        f"<changefreq>{p['freq']}</changefreq><priority>{p['priority']}</priority></url>\n"
        for key, p in PAGES.items() if p["index"]
    )
    return _xml('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + items + "</urlset>\n")


async def _index_values(db: AsyncSession):
    return await _product_total(db), await _last_update(db)


@router.get("/sitemap-products-{n}.xml", include_in_schema=False)
async def sitemap_products(n: int, request: Request, db: AsyncSession = Depends(get_db)):
    base = base_url(request)
    total, last = await _cached("index", lambda: _index_values(db))
    if n < 1 or n > max(1, math.ceil(total / SITEMAP_PAGE)):
        raise HTTPException(status_code=404)

    async def make():
        rows = (await db.execute(
            text("SELECT p.barcode " + _PRODUCTS_FROM + " ORDER BY v.product_id LIMIT :n OFFSET :o"),
            {"min_stores": MIN_STORES_FOR_SITEMAP, "n": SITEMAP_PAGE, "o": (n - 1) * SITEMAP_PAGE},
        )).scalars().all()
        return rows

    barcodes = await _cached(f"products-{n}", make)
    items = "".join(f"  <url><loc>{_esc(base)}/product/{_esc(b)}</loc><lastmod>{last}</lastmod></url>\n" for b in barcodes)
    return _xml('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + items + "</urlset>\n")
