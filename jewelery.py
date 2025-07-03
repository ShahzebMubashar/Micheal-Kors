import asyncio
import json
from playwright.async_api import async_playwright

from dotenv import load_dotenv

load_dotenv()

URL = "https://www.michaelkors.com/women/jewelry/"


async def scrape_michael_kors():
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
        print("Navigated to jewelry page.")

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
        with open("jewelry.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"Saved {len(results)} items to jewelry.json.")
        await browser.close()


async def main():
    await scrape_michael_kors()


if __name__ == "__main__":
    asyncio.run(main())
