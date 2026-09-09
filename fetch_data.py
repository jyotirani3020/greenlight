"""
Pulls real film data (budget, revenue, genre, release date, etc.) from TMDb,
synthesizes a plausible regional revenue / marketing / social split on top
(TMDb doesn't expose per-region box office), and loads both into ClickHouse.

Run schema.sql against your ClickHouse service BEFORE running this — it only
inserts, it doesn't create tables.

Requires in your environment (.env): TMDB_API_KEY, CLICKHOUSE_HOST,
CLICKHOUSE_PORT, CLICKHOUSE_USER, CLICKHOUSE_PASSWORD, CLICKHOUSE_SECURE
"""
import os
import random
import time
from datetime import date

import clickhouse_connect
import requests
from dotenv import load_dotenv

load_dotenv()

TMDB_API_KEY = os.environ["TMDB_API_KEY"]
TMDB_BASE = "https://api.themoviedb.org/3"

REGIONS = ["North America", "EMEA", "APAC", "LATAM"]
# Rough real-world-ish split of worldwide revenue by region — tune these if you
# want, they're deliberately approximate since this part is synthetic.
REGION_SHARE = {"North America": 0.38, "EMEA": 0.30, "APAC": 0.22, "LATAM": 0.10}
# ClickHouse Date32 range — classic box-office titles can predate 1970.
MIN_RELEASE_DATE = date(1900, 1, 1)
MAX_RELEASE_DATE = date(2299, 12, 31)
# Legacy ClickHouse Date type only supports 1970-01-01 onward.
LEGACY_DATE_MIN = date(1970, 1, 1)


def quarter_of(date_str: str) -> str:
    month = int(date_str.split("-")[1])
    return f"Q{(month - 1) // 3 + 1}"


def fetch_candidate_films(pages: int = 20) -> list[dict]:
    """Pull films across a spread of years so genre/season comparisons have
    enough density. discover/movie sorted by revenue gives us films that
    actually have budget/revenue data populated (a lot of TMDb entries don't)."""
    films = []
    for page in range(1, pages + 1):
        resp = requests.get(
            f"{TMDB_BASE}/discover/movie",
            params={
                "api_key": TMDB_API_KEY,
                "sort_by": "revenue.desc",
                "page": page,
                "vote_count.gte": 50,
            },
            timeout=15,
        )
        resp.raise_for_status()
        films.extend(resp.json().get("results", []))
        time.sleep(0.25)  # be polite to the free tier rate limit
    return films


def fetch_detail(movie_id: int) -> dict:
    resp = requests.get(
        f"{TMDB_BASE}/movie/{movie_id}",
        params={"api_key": TMDB_API_KEY},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def build_rows(pages: int = 20):
    films_rows = []
    regional_rows = []
    seen_ids = set()

    candidates = fetch_candidate_films(pages=pages)
    for c in candidates:
        movie_id = c["id"]
        if movie_id in seen_ids:
            continue
        seen_ids.add(movie_id)

        detail = fetch_detail(movie_id)
        budget = detail.get("budget") or 0
        revenue = detail.get("revenue") or 0
        release_date_str = detail.get("release_date") or ""
        if budget <= 0 or revenue <= 0 or not release_date_str:
            continue  # TMDb has a lot of incomplete financial data — skip it

        release_date = date.fromisoformat(release_date_str)
        if not (MIN_RELEASE_DATE <= release_date <= MAX_RELEASE_DATE):
            continue  # outside ClickHouse Date32 range

        genres = detail.get("genres") or []
        primary_genre = genres[0]["name"] if genres else "Unknown"
        rq = quarter_of(release_date_str)

        films_rows.append(
            {
                "film_id": movie_id,
                "title": detail.get("title", ""),
                "primary_genre": primary_genre,
                "budget_usd": float(budget),
                "worldwide_revenue_usd": float(revenue),
                "release_date": release_date,
                "release_quarter": rq,
                "runtime_minutes": detail.get("runtime") or 0,
                "vote_average": detail.get("vote_average") or 0.0,
                "popularity": detail.get("popularity") or 0.0,
                "overview": (detail.get("overview") or "")[:500],
            }
        )

        # --- synthetic layer: regional split + marketing + social ---
        vote = detail.get("vote_average") or 5.0
        for region in REGIONS:
            share = REGION_SHARE[region] * random.uniform(0.85, 1.15)
            total_regional = revenue * share
            opening = total_regional * random.uniform(0.28, 0.42)
            marketing = budget * random.uniform(0.35, 0.65) * random.uniform(0.9, 1.1) * REGION_SHARE[region] / 0.25
            social = max(0.0, min(100.0, (vote * 8) + random.uniform(-15, 15)))

            regional_rows.append(
                {
                    "film_id": movie_id,
                    "region": region,
                    "opening_weekend_revenue_usd": round(opening, 2),
                    "total_regional_revenue_usd": round(total_regional, 2),
                    "marketing_spend_usd": round(marketing, 2),
                    "social_engagement_score": round(social, 1),
                    "release_window": rq,
                }
            )

        time.sleep(0.15)

    return films_rows, regional_rows


def release_date_column_type(client) -> str | None:
    result = client.query(
        """
        SELECT type FROM system.columns
        WHERE database = currentDatabase() AND table = 'films' AND name = 'release_date'
        """
    )
    return result.result_rows[0][0] if result.result_rows else None


def ensure_release_date_column(client) -> str:
    """Upgrade Date -> Date32 so pre-1970 TMDb titles can load."""
    col_type = release_date_column_type(client)
    if col_type == "Date":
        client.command("ALTER TABLE films MODIFY COLUMN release_date Date32")
        print("Upgraded films.release_date from Date to Date32.")
        return "Date32"
    return col_type or "Date32"


def drop_pre_legacy_date_rows(films_rows, regional_rows):
    """Fallback when the table still uses Date (1970+ only)."""
    skipped_ids = {r["film_id"] for r in films_rows if r["release_date"] < LEGACY_DATE_MIN}
    if not skipped_ids:
        return films_rows, regional_rows
    films_rows = [r for r in films_rows if r["film_id"] not in skipped_ids]
    regional_rows = [r for r in regional_rows if r["film_id"] not in skipped_ids]
    print(
        f"Skipped {len(skipped_ids)} pre-1970 films "
        f"(films.release_date is still Date — run schema.sql or allow auto-upgrade)."
    )
    return films_rows, regional_rows


def main():
    client = clickhouse_connect.get_client(
        host=os.environ["CLICKHOUSE_HOST"],
        port=int(os.environ.get("CLICKHOUSE_PORT", 8443)),
        username=os.environ.get("CLICKHOUSE_USER", "default"),
        password=os.environ["CLICKHOUSE_PASSWORD"],
        secure=os.environ.get("CLICKHOUSE_SECURE", "true").lower() == "true",
    )

    print("Checking ClickHouse schema...")
    try:
        col_type = ensure_release_date_column(client)
    except Exception as exc:
        print(f"Warning: could not upgrade release_date column: {exc}")
        col_type = release_date_column_type(client)

    print("Fetching films from TMDb (this takes a few minutes)...")
    films_rows, regional_rows = build_rows(pages=20)
    print(f"Got {len(films_rows)} films with usable budget/revenue data, "
          f"{len(regional_rows)} regional rows.")

    if col_type == "Date":
        films_rows, regional_rows = drop_pre_legacy_date_rows(films_rows, regional_rows)
        print(f"Inserting {len(films_rows)} films, {len(regional_rows)} regional rows.")

    if films_rows:
        client.insert(
            "films",
            [list(r.values()) for r in films_rows],
            column_names=list(films_rows[0].keys()),
        )
    if regional_rows:
        client.insert(
            "regional_performance",
            [list(r.values()) for r in regional_rows],
            column_names=list(regional_rows[0].keys()),
        )

    print("Loaded into ClickHouse. Sanity check with:")
    print("  SELECT count() FROM films;")
    print("  SELECT count() FROM regional_performance;")


if __name__ == "__main__":
    main()
