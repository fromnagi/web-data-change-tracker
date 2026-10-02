"""The two approved demo sources. Fetching is separate from HTML parsing."""
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

BOOKS_URL = "https://books.toscrape.com/"
QUOTES_URL = "https://quotes.toscrape.com/js/"
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def require_approved_url(url: str, hostname: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != hostname or parsed.port not in (None, 443):
        raise ValueError(f"pagination URL outside approved source: {hostname}")


def handle_quote_route(route) -> None:
    if not route.request.is_navigation_request():
        route.continue_()
        return
    try:
        require_approved_url(route.request.url, "quotes.toscrape.com")
    except ValueError:
        route.abort()
        return
    # Playwright's normal navigation follows redirects before page.url can be checked.
    # Fetch one response without following redirects, then let the page render it.
    response = route.fetch(max_redirects=0)
    if 300 <= response.status < 400:
        route.abort()
    else:
        route.fulfill(response=response)


def parse_books(html: str, page_url: str) -> tuple[list[dict], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("article.product_pod")
    if not cards:
        raise ValueError("book page contains no product cards")
    if len(soup.select("ol.row > li")) != len(cards):
        raise ValueError("book listing/card count mismatch; markup may have changed")
    rows = []
    for card in cards:
        link = card.select_one("h3 a")
        rating = card.select_one("p.star-rating")
        rows.append(dict(source="books", page_url=page_url,
                         source_url=link.get("href", "") if link else "",
                         title=link.get("title", "") if link else "",
                         price=card.select_one("p.price_color").get_text() if card.select_one("p.price_color") else "",
                         availability=card.select_one("p.instock.availability").get_text(" ") if card.select_one("p.instock.availability") else "",
                         rating=next((RATINGS[c] for c in rating.get("class", []) if c in RATINGS), None) if rating else None))
    next_link = soup.select_one("li.next a")
    return rows, urljoin(page_url, next_link["href"]) if next_link else None


def parse_quotes(html: str, page_url: str) -> tuple[list[dict], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.quote")
    if not cards:
        raise ValueError("rendered quote page contains no quote cards")
    if len(soup.select("span.text")) > len(cards):
        raise ValueError("quote text/card count mismatch; markup may have changed")
    rows = []
    for card in cards:
        text = card.select_one("span.text")
        author = card.select_one("small.author")
        rows.append(dict(source="quotes", page_url=page_url, source_url=page_url,
                         title=text.get_text() if text else "",
                         author=author.get_text() if author else "",
                         tags=[tag.get_text() for tag in card.select("a.tag")]))
    next_link = soup.select_one("li.next a")
    return rows, urljoin(page_url, next_link["href"]) if next_link else None


def collect_books(max_pages: int, on_page) -> list[dict]:
    rows = []
    seen = set()
    url = BOOKS_URL
    with httpx.Client(timeout=20, follow_redirects=False, headers={"User-Agent": "PortfolioDemoPipeline/0.1"}) as client:
        while url and len(seen) < max_pages:
            require_approved_url(url, "books.toscrape.com")
            if url in seen:
                raise ValueError("book pagination loop")
            seen.add(url)
            response = client.get(url)
            response.raise_for_status()
            require_approved_url(str(response.url), "books.toscrape.com")
            page_rows, url = parse_books(response.text, str(response.url))
            rows.extend(page_rows)
            on_page("books")
    return rows


def collect_quotes(max_pages: int, on_page) -> list[dict]:
    # JavaScript populates .quote. page.content() is the actual rendered DOM.
    from playwright.sync_api import sync_playwright

    rows = []
    seen = set()
    url = QUOTES_URL
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route("**/*", handle_quote_route)
            while url and len(seen) < max_pages:
                require_approved_url(url, "quotes.toscrape.com")
                if url in seen:
                    raise ValueError("quote pagination loop")
                seen.add(url)
                response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if response is None or not response.ok:
                    raise ValueError(f"quote HTTP status: {response.status if response else 'no response'}")
                require_approved_url(page.url, "quotes.toscrape.com")
                page.locator("div.quote").first.wait_for(timeout=15000)
                page_rows, url = parse_quotes(page.content(), page.url)
                rows.extend(page_rows)
                on_page("quotes")
        finally:
            browser.close()
    return rows
