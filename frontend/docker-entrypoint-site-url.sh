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
