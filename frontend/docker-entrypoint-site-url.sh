#!/bin/sh
# Social previews and the canonical link need the site's full address, which is only known when the
# container starts (SITE_URL=https://example.com in .env). Without it those tags are dropped.
set -e
page=/usr/share/nginx/html/index.html
if [ -n "${SITE_URL:-}" ]; then
  url=$(printf '%s' "$SITE_URL" | sed 's:/*$::; s/[&|\\]//g')
  sed -i "s|__SITE_URL__|$url|g" "$page"
else
  # the image-size tags only mean something next to the image tag, so they go with it
  sed -i -e '/__SITE_URL__/d' -e '/og:image:width/d' -e '/og:image:height/d' "$page"
fi
