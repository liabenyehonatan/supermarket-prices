# Deployment (single Israeli VPS)

One host runs everything: PostgreSQL, the read-only API, the ingestion worker,
a nightly backup job and nginx. Several chains (12 of them) only answer Israeli
IP addresses, which is why the host must be in Israel.

```
chains' portals ──► worker ──► db ◄── api ◄── nginx ◄── users
                  (scrape→parse→delete)  (read-only role)   (cache, rate limit)
                                  └──► backup (nightly pg_dump)
```

## 1. Pick and verify the server

Any VPS with an Israeli IP, ~4 GB RAM, 40+ GB SSD (the working set is the
database plus one batch of downloaded XML; the 75 GB dump archive is not needed).

Before building anything on it, prove it can reach the chains:

```bash
git clone <repo> && cd supermarket-prices
python3 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/python -m app.scraper.preflight
```

Every line must say `OK`. A datacenter address is not the same as a home
connection: a chain can accept one and refuse the other, so do not skip this.
(`SKIP`/`not in installed library` for a name is harmless; it means the pinned
library version does not know that chain.)

Outbound FTP (port 21) must be open; some hosts block it.

## 2. First start

On a fresh Debian/Ubuntu server, one script does steps 1 and 2 (installs Docker, creates `.env`
with random passwords, builds, runs the preflight and **stops if a chain is unreachable**, then
starts everything):

```bash
bash deploy/setup-server.sh
```

By hand:

```bash
cp .env.example .env
# set POSTGRES_PASSWORD and API_DB_PASSWORD to two different long random values
docker compose up -d --build
docker compose ps          # migrate exits 0; the rest are running/healthy
docker compose logs -f worker
```

The worker runs a cycle immediately (the database starts empty) and then twice a day at
`RUN_AT` (06:00 and 18:00 Israel time). Each cycle downloads only the *full* price files published
since the previous one (delta files are not used) and loads only the newest one per store; a failed or partial cycle is retried
up to twice, two hours apart. The first cycle downloads everything the portals still list
(some list over a month of full files per store) and takes hours; later cycles are far smaller.
Chains that publish in the afternoon (e.g. Rami Levy around 12:15) are picked up by the 18:00 cycle. Watch progress with:

```bash
docker compose exec db psql -U supermarket supermarket_prices -c \
  "select phase, chain, status, files_ok, files_failed, rows_applied, started_at, finished_at
     from ingest_runs order by id desc limit 20;"
```

Run a single chain by hand (stops being necessary once the schedule is running):

```bash
docker compose exec worker python -m app.worker --once --chains RAMI_LEVY
```

If another cycle holds the lock, this exits with code 2 instead of overlapping.

### Oracle Cloud Always Free (what we plan to use)

Create the instance as **Ampere A1, 2 OCPU, 6 GB RAM, 100 GB boot volume** in `il-jerusalem-1`.
Why these numbers:
- The free allowance is 2 OCPU, 12 GB RAM and 200 GB of block storage in total (Oracle's
  [Always Free page](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm)).
  The stack peaks around 35 GB of disk during the first load, so 100 GB is ample.
- Oracle may **reclaim "idle" instances**: CPU (95th percentile), network *and* (A1 only) memory
  all below 20% for 7 days. Our worker runs about an hour a day in total, so CPU and network will be
  low. With 6 GB allocated, the stack's roughly 2-3 GB keeps memory above 20%, so the instance
  should not count as idle. How Oracle measures memory is not documented; watch it (below).
- Oracle's page does not say what a reclaimed instance becomes, or whether upgrading to Pay As You
  Go exempts it. So: **copy backups off the server from day one** (`deploy/offsite-backup.sh`).
- The home region is fixed at sign-up; choose Jerusalem then. Do not *stop* the instance (restart
  is fine): a stopped A1 may not find capacity to start again.
- If "Out of host capacity" appears while creating, that is a temporary shortage at creation time;
  retry later or try another availability domain.

## 3. What to monitor

| Signal | How |
|---|---|
| API alive and DB reachable | `GET /health` (200/503) |
| Data is fresh | `GET /health/data` is 503 once the last good cycle is older than `MAX_DATA_AGE_HOURS` (default 36: one run a day plus the retry window). Point an uptime monitor (UptimeRobot, Better Stack) at it. |
| Worker ran | set `HEALTHCHECK_URL` to a healthchecks.io check: the worker pings `/start`, success, `/fail`. A missed ping alerts you if the worker itself dies. |
| Backups ran | set `HEALTHCHECK_BACKUP_URL` the same way |
| Per-chain problems | `ingest_runs` (above) and `ingested_files where status <> 'done'` |

A file that fails three times lands in `dumps/_quarantine/<Chain>/` inside the
worker's volume and is never retried; look at its `last_error` in `ingested_files`.

## 4. Backups and restore

`backup` writes `/backups/supermarket_prices-<stamp>.dump` daily (UTC hour
`BACKUP_HOUR_UTC`) and keeps `BACKUP_KEEP_DAYS` of them. **They sit on the same
disk as the database, so copy them off the host** (rclone/rsync to object
storage from the host's cron). Test a restore before you need one:

```bash
docker compose exec db createdb -U supermarket restore_test
docker compose exec -T backup cat /backups/<file>.dump | \
  docker compose exec -T db pg_restore -U supermarket -d restore_test
docker compose exec db psql -U supermarket restore_test -c "select count(*) from prices"
docker compose exec db dropdb -U supermarket restore_test
```

Losing the database is recoverable (re-run the worker with the backup restored,
or from scratch). Losing the `dumps` volume is cheap but not free: the scraper's
memory of what it downloaded (`dumps/status`) goes with it and everything is
fetched once more.

## 5. Updating

```bash
git pull
docker compose up -d --build        # migrate runs first, then api and worker restart
```

`docker stop`/restart lets the worker finish the file it is loading (3 minute
grace period); an interrupted file is simply loaded again next cycle.

### The scraper library

`requirements.txt` pins `il-supermarket-scraper` and `il-supermarket-parser` to the
versions this was tested with. Chains change their sites often, so expect to bump
them. Do it deliberately:

```bash
venv/bin/pip install -U il-supermarket-scraper il-supermarket-parser
venv/bin/python -m app.scraper.preflight   # still all OK?
venv/bin/pytest                            # parsing still behaves?
```

then update the pins.

## 6. Existing database (not created by this compose file)

```bash
docker compose exec -e API_DB_PASSWORD=... db sh /docker-entrypoint-initdb.d/01-roles.sh
docker compose run --rm migrate      # applies migrations and the API role's grants
```

The migration closes duplicate "current" prices (newest kept) before it builds
the unique index, replaces four generic indexes on `prices` with two partial ones,
and is reversible (`python -m alembic downgrade -1`). It briefly locks writes to
`prices` while the indexes build (seconds per million rows); run it when the
worker is idle (`docker compose stop worker` first).

## 7. TLS

nginx here speaks plain HTTP on port 80. Put Cloudflare in front (free, also gives
CDN caching and DDoS protection) or terminate TLS with Caddy/certbot. The cache
and rate limits are at the nginx layer and work either way.

## Settings reference

See `.env.example` and `app/settings.py` for every variable and its default.
