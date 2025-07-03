import asyncio
import json
from playwright.async_api import async_playwright

from crawl4ai import AsyncWebCrawler
from dotenv import load_dotenv

from config import BASE_URL, CSS_SELECTOR, REQUIRED_KEYS
from utils.data_utils import (
    save_venues_to_csv,
)
from utils.scraper_utils import (
    fetch_and_process_page,
    get_browser_config,
    get_llm_strategy,
)

load_dotenv()

URL = "https://www.michaelkors.com/women/handbags/"


async def scrape_michael_kors():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
            }
        )
        page = await context.new_page()
        await asyncio.sleep(2)
        await page.goto(URL)
        print("Page loaded.")

        # Handle cookie consent
        try:
            accept_btn = await page.wait_for_selector('button:has-text("Accept All")', timeout=5000)
            await accept_btn.click()
            print("Accepted cookies.")
            await asyncio.sleep(1)
        except Exception:
            print("No cookie popup found.")

        # Ensure you are on the correct URL
        await page.goto(URL)
        print("Navigated to Handbags page.")

        # Wait for product cards to load
        await page.wait_for_selector('div.col-6.col-md-3.product-tile-wrapper')

        # Run JavaScript scroll and load more script inside the page
        print("Starting JS scroll and Load More script...")

        await page.evaluate("""
        (async () => {
            let scrollCount = 0;
            let maxScrolls = 100;
            let loadMoreSelector = 'button.more.desktop-load-more';

            function sleep(ms) {
                return new Promise(resolve => setTimeout(resolve, ms));
            }

            while (scrollCount < maxScrolls) {
                let loadMoreBtn = document.querySelector(loadMoreSelector);

                if (loadMoreBtn && !loadMoreBtn.disabled) {
                    console.log('Clicking Load More button...');
                    loadMoreBtn.click();
                    await sleep(3000);
                } else {
                    console.log('Scrolling... Count:', scrollCount + 1);
                    window.scrollBy(0, 5000);
                    await sleep(1000);
                    scrollCount++;
                }
            }

            console.log('Reached maximum scrolls or no more Load More button.');
        })();
    """)

        # Wait extra time to make sure all products are loaded
        await asyncio.sleep(10)
        print("Finished scrolling and loading more. Starting data extraction...")

        # Extract product details
        items = await page.query_selector_all('div.col-6.col-md-3.product-tile-wrapper')
        print(f"Found {len(items)} items.")

        results = []
        for item in items:
            try:
                tile_body = await item.query_selector('.tile-body')
                # Get all name elements
                name_els = await tile_body.query_selector_all('a.link.back-to-product-anchor-js') if tile_body else []
                name = ""
                link = ""
                for name_el in name_els:
                    text = (await name_el.inner_text()).strip()
                    # Check if the text is not all uppercase
                    if any(c.islower() for c in text):
                        name = text
                        link = await name_el.get_attribute("href")
                        break

                price_el = await tile_body.query_selector('.value') if tile_body else None
                price = (await price_el.inner_text()) if price_el else ""

                results.append({
                    "name": name,
                    "price": price.strip(),
                    "product_url": f"https://www.michaelkors.com{link}" if link else ""
                })
            except Exception as e:
                print("Error extracting item:", e)

        # Save to JSON
        with open("handbags.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"Saved {len(results)} items to handbags.json.")
        await browser.close()


async def scrape_handbag_details():
    # Load URLs from handbags.json
    with open("handbags.json", "r", encoding="utf-8") as f:
        products = json.load(f)

    results = []
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
            }
        )
        page = await context.new_page()

        for idx, product in enumerate(products):
            url = product.get("product_url")
            if not url:
                continue
            print(f"[{idx+1}/{len(products)}] Scraping: {url}")
            try:
                await page.goto(url, timeout=60000)
                # Handle cookie/region popups if present
                try:
                    accept_btn = await page.wait_for_selector('button:has-text("Accept All")', timeout=5000)
                    await accept_btn.click()
                    print("Accepted cookies on product page.")
                    await asyncio.sleep(1)
                except Exception:
                    pass

                # Take a debug screenshot before extracting data
                await page.screenshot(path=f"debug_product_{idx+1}.png", full_page=True)

                # Wait for product name to appear
                await page.wait_for_selector('.product-name.overflow-hidden', timeout=15000)
                name = await page.locator('.product-name.overflow-hidden').inner_text()
                price = await page.locator('.value').first.inner_text()
                img_el = await page.query_selector('img.zoom-image.d-block.img-fluid.mouseFocusUnActive')
                image_url = await img_el.get_attribute('src') if img_el else ""
                # Click the Product Details button
                try:
                    details_btn = await page.query_selector('button.product-details--js')
                    if details_btn:
                        await details_btn.click()
                        await asyncio.sleep(1)
                except Exception:
                    pass
                desc = ""
                try:
                    desc_el = await page.query_selector('.product-details-tabs__item p')
                    desc = await desc_el.inner_text() if desc_el else ""
                except Exception:
                    pass

                results.append({
                    "name": name.strip(),
                    "price": price.strip(),
                    "image_url": image_url,
                    "description": desc.strip(),
                    "product_url": url
                })
            except Exception as e:
                print(f"Error scraping {url}: {e}")

        await browser.close()

    # Save results
    with open("handbags_detailed.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(results)} detailed items to handbags_detailed.json.")


async def crawl_venues():
    browser_config = get_browser_config()
    llm_strategy = get_llm_strategy()
    session_id = "venue_crawl_session"

    page_number = 2
    all_venues = []
    seen_names = set()

    async with AsyncWebCrawler(config=browser_config) as crawler:
        while True:
            venues, no_results_found = await fetch_and_process_page(
                crawler,
                page_number,
                BASE_URL,
                CSS_SELECTOR,
                llm_strategy,
                session_id,
                REQUIRED_KEYS,
                seen_names,
            )

            if no_results_found:
                print("No more venues found. Ending crawl.")
                break

            if not venues:
                print(f"No venues extracted from page {page_number}.")
                break

            all_venues.extend(venues)
            page_number += 1

            await asyncio.sleep(2)

    if all_venues:
        save_venues_to_csv(all_venues, "complete_venues.csv")
        print(f"Saved {len(all_venues)} venues to 'complete_venues.csv'.")
    else:
        print("No venues were found during the crawl.")

    llm_strategy.show_usage()


async def main():
    # await scrape_michael_kors()  # Commented out, as handbags.json is already generated
    await scrape_handbag_details()
    # await crawl_venues()  # Optional if you want to run venue crawling


if __name__ == "__main__":
    asyncio.run(main())
