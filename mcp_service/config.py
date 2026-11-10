"""Environment and the limits the MCP tools enforce. One place, so the numbers in the tool texts match the code."""

import os

API_URL = os.getenv("API_URL", "http://api:8000").rstrip("/")
# The site's public address (the same SITE_URL the API uses); empty means "do not hand out basket links".
SITE_URL = os.getenv("SITE_URL", "").strip().rstrip("/")

MAX_BASKET_ITEMS = 40          # items in one compare_basket call
MAX_QUERIES = 10               # searches in one search_products call
MAX_SEARCH_LIMIT = 5           # results per search
MAX_DEALS = 10
MAX_CITIES = 10
MAX_QTY = 99                   # the API refuses a basket line above this
MAX_QUERY_LEN = 100            # the API refuses a longer search text
MAX_TEXT_LEN = 120             # product names and promotion text from the API are cut to this
API_TIMEOUT_SECONDS = 10.0
SLOT_WAIT_SECONDS = 5.0        # waiting longer than this for a free API slot is answered "busy", not queued
MAX_CONCURRENT_API_CALLS = 4   # the MCP reaches the API directly, past nginx's limits: it limits itself
