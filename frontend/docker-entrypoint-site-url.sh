#!/bin/sh
# Social previews need the site's full address, which is only known when the container starts
# (SITE_URL=https://example.com in .env). Without a usable value those tags are dropped.
set -e
page=/usr/share/nginx/html/index.html
url=$(printf '%s' "${SITE_URL:-}" | sed 's:/*$::')
if printf '%s' "$url" | grep -Eq '^https?://[A-Za-z0-9._~:/%-]+$'; then
  sed -i "s|__SITE_URL__|$url|g" "$page"
else
  [ -n "${SITE_URL:-}" ] && echo "SITE_URL is not a plain http(s) address; link-preview tags left out" >&2
  # the image-size tags only mean something next to the image tag, so they go with it
  sed -i -e '/__SITE_URL__/d' -e '/og:image:width/d' -e '/og:image:height/d' "$page"
fi

# Google Analytics 4: the measurement ID (G-XXXXXXXXXX) is set at start-up. Without a valid one the tag is removed
# and the site loads nothing from Google.
ga=$(printf '%s' "${GA_MEASUREMENT_ID:-}" | tr -d ' ')
if printf '%s' "$ga" | grep -Eq '^G-[A-Z0-9]{4,16}$'; then
  sed -i "s|__GA_MEASUREMENT_ID__|$ga|g" "$page"
else
  [ -n "${GA_MEASUREMENT_ID:-}" ] && echo "GA_MEASUREMENT_ID is not like G-XXXXXXXXXX; Google Analytics left off" >&2
  sed -i '/__GA_MEASUREMENT_ID__/d' "$page"
fi
