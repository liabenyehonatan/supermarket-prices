#!/bin/sh
# Runs once, on first start of an empty database volume.
#
# Creates the least-privilege role the public API connects with: it can read
# everything and write exactly one thing, the cached products.image_url. The
# schema is created later by the migrate service as the owner role; default
# privileges make every table it creates readable by the API role.
#
# For a database that already exists, run the same statements by hand:
#   docker compose exec -e API_DB_PASSWORD=... db sh /docker-entrypoint-initdb.d/01-roles.sh
set -eu

: "${API_DB_PASSWORD:?API_DB_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v api_password="$API_DB_PASSWORD" -v owner="$POSTGRES_USER" -v dbname="$POSTGRES_DB" <<'SQL'
SELECT format('CREATE ROLE api_ro LOGIN PASSWORD %L', :'api_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_ro') \gexec
SELECT format('ALTER ROLE api_ro PASSWORD %L', :'api_password') \gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO api_ro', :'dbname') \gexec
GRANT USAGE ON SCHEMA public TO api_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO api_ro;
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT ON TABLES TO api_ro', :'owner') \gexec

-- The one write the API does (remember a product's image URL) is granted by the
-- Alembic migration, because the products table does not exist yet at this point.

-- Cap runaway API queries; the worker keeps the owner role's defaults.
ALTER ROLE api_ro SET statement_timeout = '15s';
ALTER ROLE api_ro SET idle_in_transaction_session_timeout = '30s';
SQL
