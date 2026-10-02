"""Small shared normalization and validation boundary."""
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from urllib.parse import urljoin, urldefrag, urlsplit


def clean(value: str | None) -> str:
    return " ".join((value or "").split())


def absolute_url(base: str, link: str) -> str:
    url = urldefrag(urljoin(base, clean(link)))[0]
    if urlsplit(url).scheme not in {"http", "https"} or not urlsplit(url).netloc:
        raise ValueError("invalid source URL")
    return url


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Record:
    source: str
    source_url: str
    external_id: str
    title: str
    category: str
    numeric_value: float | None
    availability: str | None
    rating: int | None
    author: str | None
    tags: list[str]
    collected_at: str
    content_hash: str

    def data(self) -> dict:
        return asdict(self)


def normalize(raw: dict, collected_at: str) -> Record:
    source = raw.get("source")
    if source not in {"books", "quotes"}:
        raise ValueError("unknown source")
    title = clean(raw.get("title"))
    if not title:
        raise ValueError("missing title/text")
    source_url = absolute_url(raw.get("page_url", ""), raw.get("source_url", ""))
    author = clean(raw.get("author")) or None
    tags = sorted(set(filter(None, (clean(t) for t in raw.get("tags", [])))))
    if source == "books":
        if not clean(raw.get("source_url")):
            raise ValueError("missing book identity")
        price_text = clean(raw.get("price"))
        if not re.fullmatch(r"£\d+\.\d{2}", price_text):
            raise ValueError("invalid book price")
        try:
            price = Decimal(price_text[1:])
        except InvalidOperation as exc:
            raise ValueError("invalid book price") from exc
        numeric_value = float(price)
        external_id = source_url
        rating = raw.get("rating")
        if rating is not None and (not isinstance(rating, int) or rating not in range(1, 6)):
            raise ValueError("invalid rating")
        availability = clean(raw.get("availability")) or None
        if not availability:
            raise ValueError("missing availability")
    else:
        if not author:
            raise ValueError("missing quote author/identity")
        external_id = digest([author, title])
        numeric_value = None
        rating = None
        availability = None
    category = "book" if source == "books" else "quote"
    meaningful = dict(title=title, category=category, numeric_value=numeric_value,
                      availability=availability, rating=rating, author=author, tags=tags)
    return Record(source, source_url, external_id, title, category, numeric_value,
                  availability, rating, author, tags, collected_at, digest(meaningful))
