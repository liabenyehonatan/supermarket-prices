# app/scraper/scraper_service.py

import logging
import gzip
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Where downloaded files will be saved
DUMPS_FOLDER = Path(__file__).parent.parent.parent / "dumps"

# Shufersal's base URL
BASE_URL = "https://prices.shufersal.co.il"

# Category IDs on their portal
# We discovered these by looking at the navigation links
CATEGORIES = {
    "price_full": 2,   # Full price snapshots
    "promo_full": 3,   # Full promotion snapshots
    "stores":     5,   # Store list
}


def get_file_links_from_page(page, category_id: int, max_pages: int = 1) -> list:
    """
    Use Playwright to visit Shufersal's portal and collect
    all download links for a given category.

    Parameters:
    -----------
    page : playwright Page object
        The browser tab to use
    category_id : int
        Which category to scrape (2=prices, 3=promos, 5=stores)
    max_pages : int
        How many pages of results to go through.
        Each page has 10 files. Start with 1 for testing.

    Returns:
    --------
    list of dicts, each containing:
        - url: the full download URL
        - filename: the GZ filename
        - store_name: the branch name in Hebrew
        - file_size: size string like "338.32 KB"
        - updated_at: timestamp string
    """
    all_files = []

    for page_num in range(1, max_pages + 1):
        url = (
            f"{BASE_URL}/FileObject/UpdateCategory"
            f"?catID={category_id}"
            f"&storeId=0"
            f"&sort=Time"
            f"&sortdir=DESC"
            f"&page={page_num}"
            f"&pagesize=10"
        )

        logger.info(f"Visiting page {page_num}: {url}")

        page.goto(url, wait_until="networkidle", timeout=30000)

        # From our test we know:
        # - Download links have text "לחץ להורדה"
        # - They point to Azure Blob Storage URLs
        # - Table rows contain: download link, date, size, type, category, store, filename
        rows = page.query_selector_all("tr")

        # Skip header row (row 0) and pagination row (row 1)
        data_rows = rows[2:] if len(rows) > 2 else []

        logger.info(f"Found {len(data_rows)} file rows on page {page_num}")

        for row in data_rows:
            try:
                # Get all cells in this row
                cells = row.query_selector_all("td")

                if len(cells) < 6:
                    # Skip rows that don't have enough columns
                    continue

                # Cell 0: download link
                link_element = cells[0].query_selector("a")
                if not link_element:
                    continue

                download_url = link_element.get_attribute("href")
                if not download_url:
                    continue

                # Cell 1: update time e.g. "5/6/2026 3:40:00 AM"
                updated_at = cells[1].inner_text().strip()

                # Cell 2: file size e.g. "338.32 KB"
                file_size = cells[2].inner_text().strip()

                # Cell 4: store name e.g. "357 - דיל צורן קדימה"
                store_name = cells[4].inner_text().strip()

                # Cell 5: filename without extension
                # e.g. "PriceFull7290027600007-001-357-20260506-034000"
                filename = cells[5].inner_text().strip() + ".gz"

                all_files.append({
                    "url": download_url,
                    "filename": filename,
                    "store_name": store_name,
                    "file_size": file_size,
                    "updated_at": updated_at,
                })

            except Exception as e:
                logger.warning(f"Could not parse row: {e}")
                continue

    return all_files


def download_file(url: str, destination: Path) -> bool:
    """
    Download a single GZ file from a URL and save it to disk.

    Parameters:
    -----------
    url : str
        The Azure Blob Storage URL to download from
    destination : Path
        Where to save the file on disk

    Returns:
    --------
    bool: True if download succeeded, False if it failed
    """
    try:
        # stream=True means download in chunks instead of loading
        # the entire file into RAM at once.
        # This is important for large files (some are 5MB+)
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        # Write the file in binary mode ("wb")
        # We write in chunks of 8KB to keep memory usage low
        with open(destination, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"✅ Downloaded: {destination.name}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to download {destination.name}: {e}")
        return False


def run_scraper(
    categories: list = None,
    max_pages: int = 1,
    limit: int = 3,
):
    """
    Main scraper function. Uses Playwright to get file links,
    then downloads the GZ files to the dumps folder.

    Parameters:
    -----------
    categories : list
        Which categories to scrape. Defaults to price_full and stores.
    max_pages : int
        How many pages of results to scrape per category.
        Each page = 10 files. Keep at 1 for development.
    limit : int
        Max files to download per category. Keep small for testing.
    """

    if categories is None:
        categories = ["price_full", "stores"]

    # Create a subfolder for Shufersal inside dumps
    shufersal_folder = DUMPS_FOLDER / "Shufersal"
    shufersal_folder.mkdir(parents=True, exist_ok=True)

    logger.info("🚀 Starting Shufersal scraper with Playwright...")
    logger.info(f"Categories: {categories}")
    logger.info(f"Max pages per category: {max_pages}")
    logger.info(f"Max files to download: {limit}")

    # Track results
    total_downloaded = 0
    total_skipped = 0
    total_failed = 0

    with sync_playwright() as p:
        # Launch browser — headless=True for production
        # Change to False if you want to watch it work!
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for category_name in categories:
            category_id = CATEGORIES.get(category_name)
            if not category_id:
                logger.warning(f"Unknown category: {category_name}, skipping")
                continue

            logger.info(f"\n📂 Scraping category: {category_name} (ID={category_id})")

            # Get the list of files available for this category
            files = get_file_links_from_page(
                page=page,
                category_id=category_id,
                max_pages=max_pages,
            )

            logger.info(f"Found {len(files)} files, will download up to {limit}")

            # Apply limit
            files_to_download = files[:limit]

            for file_info in files_to_download:
                filename = file_info["filename"]
                destination = shufersal_folder / filename

                # Skip if already downloaded
                # This is our deduplication — no need to re-download
                if destination.exists():
                    logger.info(f"⏭️  Already exists, skipping: {filename}")
                    total_skipped += 1
                    continue

                logger.info(
                    f"⬇️  Downloading: {filename} "
                    f"({file_info['file_size']}) "
                    f"- {file_info['store_name']}"
                )

                success = download_file(file_info["url"], destination)
                if success:
                    total_downloaded += 1
                else:
                    total_failed += 1

        browser.close()

    # Summary
    logger.info("\n" + "="*50)
    logger.info("📊 SCRAPING SUMMARY")
    logger.info(f"  ✅ Downloaded: {total_downloaded} files")
    logger.info(f"  ⏭️  Skipped (already existed): {total_skipped} files")
    logger.info(f"  ❌ Failed: {total_failed} files")
    logger.info("="*50)

    return {
        "downloaded": total_downloaded,
        "skipped": total_skipped,
        "failed": total_failed,
    }


if __name__ == "__main__":
    run_scraper(
        categories=["price_full", "stores"],
        max_pages=1,  # 1 page = 10 files per category
        limit=3,      # Download max 3 files per category for testing
    )