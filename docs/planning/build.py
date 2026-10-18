#!/usr/bin/env python3
"""Builds the six planning documents (HTML -> PDF through headless Chrome).

    python3 docs/planning/build.py

Plain English, written for readers who do not code. Describes the product as it works; only the map view is marked "coming next".
Sources land in docs/planning/html/, the PDFs in docs/planning/.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_HTML = HERE / "html"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DATE = "19 Oct 2026"
TOTAL = 6

STATUS = {"built": "", "review": "", "planned": "COMING NEXT"}


# ── building blocks ───────────────────────────────────────────────────────────

def C(s):
    return f'<span class="code">{s}</span>'


def stt(kind):
    return f'<span class="stt {kind}">{STATUS[kind]}</span>' if STATUS[kind] else ""


def sec(num, title, lead=""):
    h = f'<h2><b>{num:02d}</b> {title}</h2>'
    return h + (f'<p class="lead">{lead}</p>' if lead else "")


def minute(points):
    li = "".join(f"<li>{p}</li>" for p in points)
    return f'<div class="minute"><div class="mt">IN ONE MINUTE</div><ul>{li}</ul></div>'


def legend():
    return ""


def card(n, title, sub, body, done, without, status="built"):
    cls = "" if status == "built" else status
    return f'''<div class="card {cls}"><div class="top"><h3><span class="n">{n}</span>{title}{stt(status)}</h3>
<div class="sub">{sub}</div><p>{body}</p></div>
<div class="two"><div><span class="lab">DONE WHEN</span><p>{done}</p></div>
<div><span class="lab">WITHOUT IT</span><p>{without}</p></div></div></div>'''


def table(heads, rows, widths=None):
    cg = ""
    if widths:
        cg = "<colgroup>" + "".join(f'<col style="width:{w}%">' for w in widths) + "</colgroup>"
    th = "".join(f"<th>{h}</th>" for h in heads)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table>{cg}<tr>{th}</tr>{tr}</table>"


def callout(text, kind=""):
    return f'<div class="callout {kind}">{text}</div>'


def flow(steps, title=""):
    tight = len(steps) > 7
    parts = []
    for i, (cls, head, small) in enumerate(steps):
        if i:
            parts.append('<div class="ar">→</div>')
        parts.append(f'<div class="st {cls}"><b>{head}</b><small>{small}</small></div>')
    t = f'<div class="flowt">{title}</div>' if title else ""
    return t + f'<div class="flow{" tight" if tight else ""}">{"".join(parts)}</div>'


def minis(items, cols=3):
    cells = "".join(f'<div class="mini"><div class="ic">{i}</div><h4>{h}</h4><p>{p}</p></div>' for i, h, p in items)
    return f'<div class="grid{cols}">{cells}</div>'


def kpi(items):
    return '<div class="kpi">' + "".join(f"<div><b>{a}</b><span>{b}</span></div>" for a, b in items) + "</div>"


AUTHOR = "Lia Ben Yehonatan"
GITHUB = "https://github.com/liabenyehonatan/supermarket-prices"
SITE = "https://sali.one"


def byline():
    return (f'<div class="by"><div><b>{AUTHOR}</b><br>Planning documents for the Sali app</div>'
            f'<div class="lnk"><a href="{GITHUB}">GitHub: supermarket-prices</a><a href="{SITE}">Live site: sali.one</a></div></div>')


def phones(items, sm=False):
    cells = "".join(f'<div class="ph"><img src="../img/{f}.png"><b>{t}</b>{d}</div>' for f, t, d in items)
    return f'<div class="phones{" sm" if sm else ""}">{cells}</div>'


def page(n, title, tagline, kicker, body):
    chips = (f"Updated {DATE}", "Live at sali.one")
    meta = "".join(f"<span>{c}</span>" for c in chips)
    return f'''<!doctype html><html lang="en" dir="ltr"><head><meta charset="utf-8">
<title>Sali · {title}</title><link rel="stylesheet" href="../style.css"><style>@page{{@bottom-left{{content:"SALI · {title.upper()} · {DATE.upper()}"}}}}</style></head><body>
<div class="brandbar"><div class="logo"><i></i>Sali</div><div class="docno">Document {n} of {TOTAL}</div></div>
<div class="hero"><div class="kick">{kicker}</div><h1>{title}</h1><p>{tagline}</p><div class="meta">{meta}</div></div>
{byline()}
{body}
</body></html>'''


docs = {}


def tag(label, kind="built"):
    return f'<span class="stt {kind}" style="margin-left:0">{label}</span>'


# ══════════════════════════════════════════════════════════════════════════════
# 1. PRODUCT REQUIREMENTS
# ══════════════════════════════════════════════════════════════════════════════
b = minute([
    "<b>Sali</b> compares supermarket prices across 29 Israeli chains and more than 2,000 stores: search a product or build a <b>basket</b> and see where it is cheapest.",
    "A <b>Deals</b> section shows only promotions that really are cheaper than the shelf price.",
    "Prices come from the public files the chains must publish by law, refreshed twice a day. Over 240,000 products, no accounts.",
])
b += phones([("home", "Home", "Search, banner, quick search"), ("product", "Product", "Every store, cheapest first"), ("deals", "Deals", "Only real bargains"), ("basket", "Basket", "Total at each store")])
b += sec(1, "The problem and who it is for", "The same basket costs a different amount at every chain, and there is no quick and comfortable way to see where it is cheapest. Comparison sites exist (CHP, MySupermarket, Pricez); comparing a <b>whole basket</b>, promotions included, is what they handle least well.")
b += minis([
    ("🛒", "The weekly shopper", "Builds a regular basket and wants the cheapest chain for all of it."),
    ("📱", "The in-store checker", "Scans a barcode at the shelf to see if it is cheaper elsewhere."),
    ("📍", "The nearby shopper", "Wants the cheapest price close to home."),
])

b += sec(2, "The features", "What each one does, and what counts as finished.")
b += table(["Feature", "What it does", "Done when"], [
    ["Home and search", "A greeting, search with a scan button, a three-slide banner, “quick search” with ten product photos, the user’s baskets and a Deals strip with fresh picks every day. Words in any order, spelling mistakes forgiven. Photo cards show where it is cheapest and the price per 100 g or litre.", "A new visitor starts a search in one tap."],
    ["Product page", "The price at every store, cheapest first. Filter by city (the chain list follows the city) and chain, or “near me” (15 km, closer first at equal prices). Address, Waze or Google Maps, delivery link, the chain’s own promotion, and a warning on an old price.", "The cheapest store, the saving and the freshness are clear at a glance."],
    ["Basket", "The total at every store, cheapest first, stores missing an item ranked lower and flagged. Promotions are applied (“2 for ₪10”, also across several products) and shown per line. Several named baskets, swipe to remove, move items, undo, and a quiet price-change check.", "A basket of up to 100 items compares in about a second, and a store dearer on the shelf can win once its deal applies."],
    ["Deals", "Every promotion is compared with the cheapest shelf price found; only those 10% to 60% cheaper are shown, searchable, filterable by chain and sortable, with the list loading as the user scrolls and pictured deals first. A group deal lets the user pick a product; adding puts exactly the right number of units in the basket.", "Deals shows real bargains only, and going back returns to the same card."],
    ["Barcode scan", "The camera reads a barcode and opens the product. A barcode can also be typed.", "A real product opens in seconds; the picture never leaves the phone."],
    ["Pictures, trust and small print", "Pictures from Shufersal’s catalogue, used only when they are that exact product. Every page has its own title, description and link preview for search engines and sharing. An About page: where prices come from, “for illustration and comparison only”, privacy, credits, contact. A short first-visit tour.", "No wrong pictures; the disclaimer is one tap away on every page."],
    [f"Map view {stt('planned')}", "After building a basket, open a map like Airbnb’s: each supermarket is a pin with <b>your whole basket’s price</b> there, the cheapest highlighted, the list moving with the map. Store positions and basket totals already exist.", "A Map toggle on the basket page shows correct pins and navigation."],
], widths=[17, 55, 28])

b += sec(3, "Rules the product follows")
b += table(["Rule", "Why"], [
    ["Always cheapest first", "It is what the user came to see, in both the store list and the basket."],
    ["Prices under 10 agorot, wholesale stores and short item codes are ignored", "Fake prices, shops not for shoppers, and chain-internal numbers that mean different products elsewhere."],
    ["A promotion changes a total only when it is safe", "Clear “N for X” deals with promotion data under 7 days old. Anything unclear stays at the shelf price, so a saving is never overstated."],
    ["Baskets and location stay with the user", "No accounts. Baskets live in the browser; location is rounded to about 1 km and never stored."],
], widths=[40, 60])
b += "<p class='small'><b>Not included, on purpose:</b> accounts, ordering and payment, club prices and coupons in totals, price alerts and a history chart (tried, then removed to keep the product page simple).</p>"
docs[1] = page(1, "Product Requirements", "What the site does, feature by feature: who uses it and what counts as finished.", "01 · PRODUCT REQUIREMENTS", b)

# ══════════════════════════════════════════════════════════════════════════════
# 2. TECHNICAL REQUIREMENTS
# ══════════════════════════════════════════════════════════════════════════════
b = minute([
    "A <b>Worker</b> collects prices twice a day; a <b>website and API</b> show them. They meet in one <b>database</b>.",
    "Everything runs on <b>one server in Israel</b>, because 12 chains only answer Israeli addresses.",
    "The public side can only <b>read</b> the database, so it cannot change prices.",
])
b += sec(1, "The architecture on one page", "Solid boxes are live; the dashed box is coming next.")
b += '<div class="arch">'
b += '<div class="lane">WHAT THE USER TOUCHES</div>' + flow([("o", "Phone or browser", "the shopper"), ("", "Caddy + nginx", "HTTPS, cache, rate limit"), ("", "Website", "React pages"), ("", "API", "FastAPI, read-only")])
b += '<div class="lane">WHERE THE DATA LIVES</div>' + flow([("", "API", "reads"), ("s", "Database", "PostgreSQL"), ("", "Worker", "writes, twice a day"), ("", "Backup", "nightly copy")])
b += '<div class="lane">THE OUTSIDE WORLD</div>' + flow([("o", "Chain websites", "price and promotion files"), ("m", "Shufersal catalogue", "product pictures"), ("m", "OpenStreetMap", "store positions"), ("p", "Map source", "coming next")])
b += '</div>'
b += "<p>The Worker does all the slow work in the background, so no visitor waits for a download. The API only reads what is already stored.</p>"

b += sec(2, "What it is built with")
b += table(["Part", "Tool", "In plain words"], [
    ["Website", "React, TypeScript, Vite", "Fast single-page site in Hebrew, right to left. Barcodes are read in the browser (ZXing)."],
    ["API", "Python 3.12, FastAPI", "14 endpoints: search, compare, basket, deals, cities, chains, pictures and more."],
    ["Database", "PostgreSQL 16, pg_trgm", "Open-source database; the add-on makes Hebrew search forgive spelling mistakes."],
    ["Price collection", "Open-source scraper and parser", "Community libraries that download and read every chain’s files, pinned to a tested version."],
    ["Running it", "Docker Compose, Caddy, nginx", "Every part in its own box. Caddy gives sali.one its HTTPS certificate; nginx caches answers, limits 20 requests a second per visitor and adds security headers."],
    ["Search visibility", "Server-built page headers", "The server gives each page its own title, description and structured data, real 404s, and a sitemap that lists every priced product."],
    ["Quality and release", "About 270 tests, GitHub Actions", "Every change is tested against a temporary database; once it passes on main it is deployed to the server automatically."],
], widths=[17, 27, 56])

b += sec(3, "Where it runs, and what it depends on")
b += table(["Part", "Job", "If it is down"], [
    ["Caddy, nginx, website, API", "The only public side: serves sali.one over HTTPS and answers questions, read-only.", "Site unavailable"],
    ["Worker", "At 06:00 and 18:00 Israel time: downloads and loads prices and promotions, refreshes the pre-worked tables, fills in pictures and positions (2 to 3 hours).", "Data gets stale; an alert fires"],
    ["Database and backup", "All data; a nightly copy kept 7 days, also copied off the server.", "Restore from backup"],
    ["Chain websites", "The source of every price and promotion.", "That chain stops updating; the rest carry on"],
    ["Shufersal catalogue, OpenStreetMap", "Product pictures; finding where each store is.", "Placeholder picture; store left out of “near me”"],
    ["Waze, Google Maps, healthchecks.io", "Navigation links; alerts if the Worker or backup stops.", "Link fails; no alert, site unaffected"],
], widths=[24, 52, 24])

b += sec(4, "Safety and decisions already made")
b += table(["Topic", "What was decided, and why"], [
    ["Read-only public side", "The API connects as a database user that can only read (and set a picture link). A flaw in the site cannot change prices."],
    ["Limits", "Rate limits, caps on search length and basket size (100 items), and security headers."],
    ["One server in Israel", "Instead of managed cloud services: size limits, network delay, and Israeli-only chains."],
    ["Load 500 rows at a time", "One row at a time took 30 s where batches take 3.4 s for the same files."],
    ["Full price files only", "A full file corrects itself; a changes-only file can miss something."],
    ["Monitoring", "A health address fails if data is older than 36 hours, or a single chain is silent for 5 days, and an alert is sent."],
], widths=[28, 72])
docs[2] = page(2, "Technical Requirements", "What the site is built with, where it runs, and what it depends on.", "02 · TECHNICAL REQUIREMENTS", b)

# ══════════════════════════════════════════════════════════════════════════════
# 3. APP FLOW
# ══════════════════════════════════════════════════════════════════════════════
b = minute([
    "Six screens: <b>Home, Product, Scan, Basket, Deals, About</b>, each with its own plain address. A floating bottom bar has Home, Scan (raised) and Basket.",
    "The usual path: <b>search → product → add to basket → compare the basket</b>. Deals is a second way in.",
    "Nothing dead-ends: every failure shows a plain message.",
])
b += sec(1, "Screen map")
b += phones([("search", "Search results", "Photo cards, sort, scroll"), ("filter", "Filter stores", "City, chain, near me"), ("deals_pick", "Group deal", "Choose which product")], sm=True)
b += "<p class='small'>Addresses on sali.one: <code class='code'>/</code> Home, <code class='code'>/product/&lt;barcode&gt;</code>, <code class='code'>/basket</code>, <code class='code'>/promotions</code> Deals, <code class='code'>/scan</code>, <code class='code'>/about</code>. An unknown address shows a “page not found” page with links back to search and Deals.</p>"

b += sec(2, "The main journeys")
b += flow([("o", "Home", "type “milk” or tap a photo"), ("", "Results", "photo cards, cheapest shown"), ("", "Product page", "stores, cheapest first"), ("m", "Add to basket", "the item flies to the basket"), ("s", "Basket page", "total at each store")], "A · A shopper builds a weekly basket")
b += flow([("o", "In the store", "tap “Scan”"), ("", "Camera", "point at the barcode"), ("", "Check", "server confirms the product"), ("m", "Product page", "opens by itself")], "B · Checking a price at the shelf")
b += flow([("o", "Home", "Deals strip or banner"), ("", "Deals page", "search, filter, scroll"), ("", "Deal card", "tap to add, or choose a product"), ("m", "Basket page", "the deal is in the total")], "C · Picking up a real bargain")
b += flow([("o", "Product page", "tap “Near me”"), ("", "Phone asks", "permission for location"), ("", "Distance", "worked out on the phone"), ("m", "Nearby stores", "within 15 km, closest first")], "D · Finding a store close by")
b += flow([("p", "Basket result", "tap “Map”"), ("p", "Map", "pins show basket totals"), ("p", "Tap a pin", "store card appears"), ("p", "Navigate", "Waze or Google Maps")], "E · Seeing the basket on a map  (coming next)")

b += sec(3, "What happens on a tap, and when it goes wrong")
b += table(["The tap", "What happens", "If it goes wrong"], [
    ["Search", "Results appear and keep loading as the user scrolls; sort by relevance or cheapest.", "“No products found”, or “Could not load, try again”"],
    ["+ add to basket", "The item flies to the basket icon and joins the active basket (the first add of a visit asks which, if there are several).", "Adding the same item raises its quantity"],
    ["Filter or Near me", "The list narrows and the choice is remembered; “near me” shows stores within 15 km with distances.", "None match or no permission: all stores shown, with a note"],
    ["Deals page", "A search box finds deals by product or chain; the list keeps loading as the user scrolls, deals with a picture first.", "No match: a message and a button to clear the search"],
    ["Deal card", "Opens the product; the button adds exactly the units the deal needs; a group deal opens a list to choose from.", "A finished deal is simply not listed"],
    ["Compare basket", "Totals at each store with deals applied and shown per line.", "Empty basket message; “N items missing”; a note when we lack fresh deal data for a branch"],
    ["Scan", "The camera reads the code and the product opens.", "Clear message with no permission or camera; unknown code offers typing"],
    ["Back from a product", "Same results or same card, same scroll position.", "If cleared from memory, the list loads again"],
], widths=[17, 50, 33])
b += "<p class='small'>Failures never leave a blank screen: an unexpected error shows “Something went wrong” and a way home, a late answer never overwrites a newer one, pages fade in without flashing, and blocked browser storage only means the basket is not kept.</p>"

b += sec(4, "The journey nobody sees: the twice-daily refresh", "At 06:00 and 18:00 Israel time; each run takes 2 to 3 hours.")
b += flow([("o", "Start", "one run at a time"), ("", "Download", "chain by chain, with time limits"), ("", "Check", "a cut-off file is rejected"), ("s", "Save", "prices, then promotions"), ("m", "Tidy up", "delete the file; refresh the pre-worked tables")])
b += callout("<b>Golden rule.</b> A file counts as loaded only once its data is safely saved, and is deleted only after that. A chain that fails is recorded and the others carry on; a failed run retries two hours later.", "ok")
docs[3] = page(3, "App Flow", "What happens when someone taps, when something goes wrong, and what the system does by itself.", "03 · APP FLOW", b)

# ══════════════════════════════════════════════════════════════════════════════
# 4. DESIGN BRIEF
# ══════════════════════════════════════════════════════════════════════════════
def sw(color, name, hexv, use, border=False):
    bd = "border-bottom:1px solid var(--line);" if border else ""
    return f'<div class="sw"><div class="c" style="background:{color};{bd}"></div><div class="t"><b>{name}</b>{C(hexv)}<br>{use}</div></div>'


b = minute([
    "A <b>fresh, clean and colourful</b> look: a white page, borderless cards on soft shadows, big product photos, round store logos.",
    "<b>One green</b> for every action, soft green for “cheapest”, orange for deals. Small, quiet type.",
    "Right to left, phone first. The same part looks the same on every page.",
])
b += '<div class="crops"><div class="cr"><img src="../img/cr_banner.png"><b>Banner</b> bright photo, calm green panel, white button</div><div class="cr"><img src="../img/cr_quick.png"><b>Quick search</b> square product photos</div><div class="cr"><img src="../img/cr_store.png"><b>Store row</b> round logo, cheapest on pale green</div><div class="cr"><img src="../img/cr_bar.png"><b>Bottom bar</b> floating capsule, raised scan button</div></div>'
b += sec(1, "Colours", "Taken from the live site’s style file.")
b += '<div class="grid3" style="margin-bottom:4mm">' + "".join([
    sw("#14A044", "Sali green", "#14A044", "The + buttons, main button, active tab."),
    sw("#118438", "Deep green", "#118438", "Text and icons on light green."),
    sw("#F1FAF4", "Pale green", "#F1FAF4", "The “cheapest” row and highlights.", True),
    sw("#3E8C4F", "Banner green", "#3E8C4F", "The calm panel behind banner text."),
    sw("#F97316", "Orange", "#F97316", "Deal accents and savings."),
    sw("#FFF4E8", "Pale orange", "#FFF4E8", "The saving tile.", True),
    sw("#1B1B1B", "Ink", "#1B1B1B", "Main text."),
    sw("#F4F5F4", "Soft grey", "#F4F5F4", "Flat search fields.", True),
    sw("#C0382F", "Red", "#C0382F", "Errors only."),
]) + "</div>"

b += sec(2, "Type, layout and the main pieces")
b += table(["Element", "Rule"], [
    ["Type", "Rubik, small and quiet: 11 to 14 px does most of the work; text fields are 16 px so phones never zoom. Right to left. Prices always ₪ with two digits."],
    ["Cards and spacing", "White, no outline, soft shadow, corners 10 to 20 px, spacing in steps of 4 px. Touch targets at least 44 px; the notch and home indicator are respected."],
    ["Header and bottom bar", "A flat white header (logo, city chip, basket pill, a search icon once the page’s search box scrolls away). A floating white capsule with Home, a raised green Scan circle, and Basket."],
    ["Banner and quick search", "Three slides (compare, scan, deals) with a bright photo, a calm green panel, white text and button. Ten square product photos for quick search."],
    ["Product and deal cards", "A big photo, name, “cheapest at” with the chain’s round logo, price per 100 g or litre when useful, a green add button. Deal cards add a saving pill (for example -40%)."],
    ["Store row", "The same on the product and basket pages: round logo, branch, price, gap from cheapest; the cheapest on pale green with a tag; promotion line and “old price” warning."],
    ["Feel", "Items fly to the basket icon, loading is a calm shimmer, pages fade in. Keyboard focus rings and labels on every icon button."],
], widths=[20, 80])

b += sec(3, "Coming next: the map view")
b += table(["Part", "Intention"], [
    ["Pins", "A rounded label with the <b>basket total</b>; the cheapest is pale green with the tag; stores missing items are grey. Clusters when zoomed out."],
    ["Phone layout", "The map fills the screen and the store list is a sheet sliding up, with a clear Map / List toggle. Stores without a position are listed under the map."],
], widths=[20, 80])
docs[4] = page(4, "Design Brief", "How every screen should look: colours, type, the main pieces, and the rules that keep it consistent.", "04 · DESIGN BRIEF", b)

# ══════════════════════════════════════════════════════════════════════════════
# 5. DATABASE
# ══════════════════════════════════════════════════════════════════════════════
b = minute([
    "Think of a spreadsheet with <b>tabs</b>: Chains, Stores, Products, Prices, Promotions, plus two work-log tabs.",
    "<b>Prices</b> link a product to a store. History is kept, but only one price per product and store is “current”.",
    "No personal data is kept at all. The public side can only <b>read</b>.",
])
b += kpi([("29", "chains"), ("2,000+", "stores"), ("240,000+", "products"), ("2×", "refreshed daily")])
b += sec(1, "The tables")
b += '''<div class="erd">
<div class="ent"><div class="h">Chains<small>chains</small></div><ul><li>Name (Shufersal, Rami Levy…)</li><li>Official company ID</li></ul></div>
<div class="ent"><div class="h">Stores<small>stores</small></div><ul><li>Which chain, branch number</li><li>Name, city, address</li><li>Map position and its accuracy</li><li>When prices and promotions were last confirmed</li></ul></div>
<div class="ent"><div class="h">Products<small>products</small></div><ul><li>Barcode (one ID everywhere)</li><li>Name, brand, unit</li><li>Picture</li></ul></div>
<div class="ent s"><div class="h">Prices<small>prices</small></div><ul><li>Which product, at which store</li><li>The price, exact to the agora</li><li>Current or history</li></ul></div>
<div class="ent o"><div class="h">Promotions<small>promotions</small></div><ul><li>The chain’s promotion text</li><li>One row per product it covers</li><li>Quantity, price, dates</li><li>Whether it can be applied in a basket</li></ul></div>
<div class="ent o"><div class="h">Work logs<small>ingest_*</small></div><ul><li>Every file loaded and its state</li><li>Every refresh run, per chain</li></ul></div>
</div>
<div class="rel">A chain has many stores · a store has many prices · a product is priced at many stores · a price = product + store + amount</div>'''
b += "<p class='small'>Two pre-worked tables are refreshed after every run: per product its store count and lowest and highest price, and per promotion its price per unit and saving against the cheapest shelf price. Search ordering, the home-page examples and Deals read from them, so they are fast.</p>"

b += sec(2, "The data rules that matter", "Each is enforced in the code and by the database itself.")
b += table(["Rule", "How it works", "What it prevents"], [
    ["One current price per product per store", "A changed price marks the old row as history and adds a new one; the database refuses two current rows.", "Two prices at one store, or lost history"],
    ["Prices exact to the agora", "Stored as exact decimals, never floating-point numbers.", "Totals like 9.7999"],
    ["A store is chain + branch number", "Branch “001” exists in many chains, so the pair is the identity and is unique.", "One chain’s prices landing in another’s store"],
    ["The first product name stays", "If another chain names the product differently, the stored name is kept.", "Names flipping between refreshes"],
    ["A file is “loaded” only once its data is saved", "The log is written in the same step as the data; a file that fails three times is put aside.", "Double loads, or “loaded” files with no data"],
], widths=[28, 46, 26])
b += callout("<b>Why unchanged prices are not rewritten.</b> About 11 million prices are checked daily and most do not change, so only one field on the store (“last confirmed”) is updated. Rewriting every row kept the database saturated for hours.", "info")

b += sec(3, "Who may see and change what", "No personal data is held, but permissions still matter.")
b += table(["Who", "Allowed", "Not allowed"], [
    ["A visitor", "Search, compare, build a basket. No login.", "No direct database access"],
    ["The API (read-only user)", "Read every table; set a product’s picture link.", "Change prices or names, delete, alter tables (tested)"],
    ["The Worker (owner)", "Load data and change structure.", "Not reachable from the internet"],
], widths=[26, 42, 32])
b += "<p class='small'>Baskets and chosen filters live only in the user’s browser. The user’s location is never kept: a rounded point may be sent once to suggest a city, then discarded. Every structure change is one of 20 recorded, reversible migrations, and nothing in price history is deleted.</p>"
docs[5] = page(5, "Database Schema", "Where the information is kept, how the pieces relate, and who may see and change what.", "05 · DATABASE SCHEMA", b)

# ══════════════════════════════════════════════════════════════════════════════
# 6. IMPLEMENTATION PLAN
# ══════════════════════════════════════════════════════════════════════════════
b = minute([
    "Sali is live at sali.one. It was built in ten stages, each ending with something you can see and approve; eight are done.",
    "<b>Next:</b> the map view of the basket. Then later ideas, chosen by what users ask for.",
])
b += kpi([("8 of 10", "stages done"), ("29", "chains"), ("2,000+", "stores"), ("270", "automated tests")])
b += flow([("m", "1", "Collect"), ("m", "2", "Database"), ("m", "3", "Website"), ("m", "4", "Server"), ("m", "5", "Polish"), ("m", "6", "Live"), ("m", "7", "Promos"), ("m", "8", "New look"), ("o", "9", "Map"), ("p", "10", "Later")])
b += sec(1, "The stages")
D = tag("DONE")
b += table(["Stage", "What it delivered", "Sign-off point"], [
    [f"1 · Collect<br>{D}", "Downloading and reading the first chains’ price files; exact decimals, batch loading.", "One chain (about 1.5 million Shufersal rows) loaded"],
    [f"2 · Database and API<br>{D}", "The tables, Hebrew search that forgives spelling mistakes, product and basket comparison.", "A basket total at each store is correct"],
    [f"3 · Website<br>{D}", "Search, product page, baskets, scan, filters, “near me”: Hebrew, right to left, for phones.", "Search, add and compare work at phone width"],
    [f"4 · Server and refresh<br>{D}", "A Worker refreshing the chains twice a day, a log of loaded files, read-only public side, backups, health checks, positions and pictures filled in the background.", "426 Shufersal files in 243 s; a crash midway equals a clean load"],
    [f"5 · Quality and polish<br>{D}", "Fake-price filtering, input limits, security headers, About page, faster loading, error page, accessibility.", "All tests pass; merged to main"],
    [f"6 · Going live<br>{D}", "One server in Israel behind sali.one with HTTPS; all 29 chains load; alerts and the off-server backup connected; every merged change is deployed automatically; search-engine page headers and a sitemap.", "Data is fresh and the health check is healthy"],
    [f"7 · Promotions and Deals<br>{D}", "Promotions loaded for every chain; shown on the product page and applied in the basket (single products and groups); the Deals section with search and endless scrolling; duplicate, test and coupon promotions filtered out.", "A dearer-on-the-shelf store can win a basket, and Deals shows no duplicates"],
    [f"8 · A fresh look<br>{D}", "A full redesign with the same features: photos, soft cards, banner, floating bar, animations, a first-visit tour.", "Every page uses the new look"],
    [f"9 · Map view<br>{tag('NEXT', 'review')}", "See the basket’s total at each nearby store on a map (steps below).", "A Map toggle shows correct pins; navigation works"],
    [f"10 · Later<br>{tag('LATER', 'planned')}", "Colour-contrast check and screen tests; fuller privacy text; more deal types; price alerts; sending a basket to a chain’s site.", "Chosen by what users ask for"],
], widths=[22, 48, 30])

b += sec(2, "Stage 9 in detail: the map view")
b += "<ol class='steps'><li><b>Two quick checks.</b> How many stores really have a position (about 86% did), and a trial cut of the Israel map to see its size and whether Hebrew labels look right.</li><li><b>Choose the map source.</b> Recommended: host the map file on our own server, so there are no usage limits, no outside dependency and no change to the privacy text.</li><li><b>Pins with totals,</b> cheapest highlighted, clusters when zoomed out, stores missing items in grey.</li><li><b>List and map together:</b> moving the map updates the list; a pin opens the store with navigation. The map loads only when asked for.</li><li><b>Test on phones</b> with 100 stores, with and without location permission.</li></ol>"

b += sec(3, "What could go wrong")
b += table(["Risk", "What we do"], [
    ["A chain changes its site and the download fails (often)", "That chain fails alone; the library is pinned and upgraded on purpose; an alert fires after 5 silent days."],
    ["Promotion files make runs long or fill the disk", "A run takes 2 to 3 hours and the disk has room; promotions can be limited to some chains or switched off with one setting."],
    ["Wrong prices or stale promotions in chain files", "Fake prices are filtered; promotions count only when fresh and clearly safe; deals must beat the shelf price."],
    ["One server is a single point of failure", "Accepted for now: nightly backups copied off the server, and recovery = restore + re-run the Worker."],
    ["Missing or approximate store positions (for the map)", "An accuracy flag, and stores without a position are listed under the map."],
], widths=[38, 62])
docs[6] = page(6, "Implementation Plan", "How Sali was built in stages, what each stage delivered, and what comes next.", "06 · IMPLEMENTATION PLAN", b)

# ── write + render ────────────────────────────────────────────────────────────
NAMES = {
    1: "01-product-requirements",
    2: "02-technical-requirements",
    3: "03-app-flow",
    4: "04-design-brief",
    5: "05-database-schema",
    6: "06-implementation-plan",
}


def main():
    OUT_HTML.mkdir(exist_ok=True)
    for old in list(HERE.glob("0*.pdf")) + list(OUT_HTML.glob("0*.html")):
        old.unlink()
    for n, html in docs.items():
        src = OUT_HTML / f"{NAMES[n]}.html"
        src.write_text(html, encoding="utf-8")
        pdf = HERE / f"{NAMES[n]}.pdf"
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", src.as_uri()],
                       check=True, capture_output=True, timeout=120)
        print("built", pdf.name)
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
