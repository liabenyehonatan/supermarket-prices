# app/scraper/victory_scraper.py

import logging
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

DUMPS_FOLDER = Path(__file__).parent.parent.parent / "dumps"

# Victory's dedicated portal
VICTORY_PORTAL_URL = "https://laibcatalog.co.il/victory/index.html"
VICTORY_CHAIN_ID = "7290696200003"
VICTORY_CHAIN_NAME = "ויקטורי"


def get_victory_files(max_pages: int = 1, file_type: str = "price") -> list:
    """
    Use Playwright to scrape Victory's dedicated portal.
    Keeps browser open across all pages to maintain state.
    """
    all_files = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Navigate once — keep browser open for all pages
        logger.info("Opening Victory portal...")
        page.goto(
            VICTORY_PORTAL_URL,
            wait_until="networkidle",
            timeout=30000,
        )
        logger.info("Portal loaded!")

        for page_num in range(1, max_pages + 1):
            logger.info(f"Scraping page {page_num}/{max_pages}")

            # Wait for table to be visible
            page.wait_for_timeout(1500)

            # Get all download links on current page
            links = page.query_selector_all("a")
            page_files = 0

            for link in links:
                href = link.get_attribute("href") or ""

                if ".gz" not in href.lower():
                    continue

                filename = href.split("/")[-1]
                filename_lower = filename.lower()

                # Filter by file type
                if file_type == "price":
                    if "promo" in filename_lower:
                        continue
                    if "price" not in filename_lower:
                        continue

                # Get store name from the row
                try:
                    row_text = link.evaluate(
                        "el => el.closest('tr') ? el.closest('tr').innerText : ''"
                    )
                    # Row: "N filename storeId storeName type ext size date הורד"
                    parts = [p.strip() for p in row_text.split('\t') if p.strip()]
                    # Store name is usually in position 3
                    store_name = parts[3] if len(parts) > 3 else "Victory"
                except:
                    store_name = "Victory"

                # Avoid duplicates
                if not any(f["filename"] == filename for f in all_files):
                    all_files.append({
                        "url": href,
                        "filename": filename,
                        "store_name": store_name,
                    })
                    page_files += 1

            logger.info(f"Page {page_num}: found {page_files} new price files")

            # Don't click next on the last page
            if page_num >= max_pages:
                break

            # Click ▶ to go to next page
            buttons = page.query_selector_all("button")
            next_button = None
            for btn in buttons:
                if btn.inner_text().strip() == "▶":
                    next_button = btn
                    break

            if next_button:
                next_button.click()
                # Wait for new content to load
                page.wait_for_timeout(2000)
            else:
                logger.warning("No ▶ button found, stopping pagination")
                break

        browser.close()

    logger.info(f"Total Victory files found: {len(all_files)}")
    return all_files

def download_file(url: str, destination: Path) -> bool:
    """Download a single GZ file."""
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        with open(destination, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"✅ Downloaded: {destination.name}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed: {destination.name}: {e}")
        return False


def run_victory_scraper(max_pages: int = 1, limit: int = 10):
    """
    Download Victory price files.

    Parameters:
    -----------
    max_pages : int
        Pages to scrape from portal (10 files per page)
    limit : int
        Max files to actually download
    """
    victory_folder = DUMPS_FOLDER / "Victory"
    victory_folder.mkdir(parents=True, exist_ok=True)

    logger.info("🚀 Starting Victory scraper...")
    logger.info(f"Max pages: {max_pages}, Max downloads: {limit}")

    files = get_victory_files(max_pages=max_pages, file_type="price")

    if not files:
        logger.error("No Victory files found!")
        return

    # Apply limit
    files_to_download = files[:limit]
    logger.info(f"Will download {len(files_to_download)} files")

    downloaded = 0
    skipped = 0
    failed = 0

    for file_info in files_to_download:
        filename = file_info["filename"]
        destination = victory_folder / filename

        if destination.exists():
            logger.info(f"⏭️  Already exists: {filename}")
            skipped += 1
            continue

        logger.info(
            f"⬇️  Downloading: {filename} "
            f"({file_info['store_name']})"
        )

        success = download_file(file_info["url"], destination)
        if success:
            downloaded += 1
        else:
            failed += 1

    logger.info("\n" + "="*50)
    logger.info("📊 VICTORY SCRAPING SUMMARY")
    logger.info(f"  ✅ Downloaded: {downloaded}")
    logger.info(f"  ⏭️  Skipped: {skipped}")
    logger.info(f"  ❌ Failed: {failed}")
    logger.info("="*50)


if __name__ == "__main__":
    run_victory_scraper(
        max_pages=2,   # 2 pages = up to 20 files
        limit=10,      # Download max 10 for testing
    )