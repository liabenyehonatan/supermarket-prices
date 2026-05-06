# test_playwright.py

from playwright.sync_api import sync_playwright

def test_shufersal_listing():
    with sync_playwright() as p:

        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("Opening Shufersal price portal...")
        page.goto(
            "https://prices.shufersal.co.il/FileObject/UpdateCategory"
            "?catID=2&storeId=0&sort=Time&sortdir=DESC&page=1&pagesize=10",
            wait_until="networkidle",
            timeout=30000,
        )

        print("Page loaded! Analyzing structure...")

        # Strategy 1: Find ALL links on the page and print them
        # This gives us a complete picture of what's available
        all_links = page.query_selector_all("a")
        print(f"\nALL links found on page ({len(all_links)} total):")
        for link in all_links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            # Only print links that look like file downloads
            if any(x in href.lower() for x in ["download", "file", ".gz", ".xml", ".zip"]):
                print(f"  DOWNLOAD LINK → text='{text}' href='{href}'")

        # Strategy 2: Print ALL table rows — files are probably in a table
        print("\nTable rows found:")
        rows = page.query_selector_all("tr")
        print(f"Found {len(rows)} table rows")
        for i, row in enumerate(rows[:5]):  # Print first 5 rows only
            print(f"\nRow {i+1}:")
            print(row.inner_text().strip())

        # Strategy 3: Save the full page HTML to a file
        # Open this file in your browser to visually inspect the structure
        html = page.content()
        with open("shufersal_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("\n✅ Full page HTML saved to shufersal_page.html")
        print("Open that file in your browser to inspect the structure!")

        # Keep browser open for 10 seconds so you can look at it
        print("\nBrowser staying open for 10 seconds...")
        page.wait_for_timeout(10000)

        browser.close()

if __name__ == "__main__":
    test_shufersal_listing()