#!/usr/bin/env python3
"""Generate feed.xml from the article list in index.html."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "index.html"
FEED_PATH = ROOT / "feed.xml"
SITE_URL = "https://brianlui.dog/"
FEED_URL = urljoin(SITE_URL, "feed.xml")
CHANNEL_TITLE = "Brian Lui's blog"
CHANNEL_DESCRIPTION = (
    "Essays by Brian Lui about habits, decision-making, learning, communities, and life."
)
DATE_FORMAT = "%B %d, %Y"


@dataclass(frozen=True)
class Post:
    title: str
    date_text: str
    url: str
    description: str

    @property
    def published_at(self) -> datetime:
        return datetime.strptime(self.date_text, DATE_FORMAT).replace(tzinfo=timezone.utc)

    @property
    def rss_date(self) -> str:
        return format_datetime(self.published_at)


def has_class(attrs: dict[str, str | None], class_name: str) -> bool:
    return class_name in (attrs.get("class") or "").split()


def normalize_text(parts: Iterable[str]) -> str:
    return " ".join("".join(parts).split())


class ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.posts: list[Post] = []
        self.current: dict[str, list[str] | str | None] | None = None
        self.capture_field: str | None = None
        self.capture_depth = 0

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs_list)

        if tag == "article" and self.current is None:
            self.current = {
                "title": [],
                "date": [],
                "description": [],
                "href": None,
            }
            return

        if self.current is None:
            return

        if self.capture_field is not None:
            self.capture_depth += 1

        if tag == "h2" and has_class(attrs, "article-title"):
            self.capture_field = "title"
            self.capture_depth = 1
            return

        if tag == "div" and has_class(attrs, "article-date"):
            self.capture_field = "date"
            self.capture_depth = 1
            return

        if tag == "div" and has_class(attrs, "article-content"):
            self.capture_field = "description"
            self.capture_depth = 1
            return

        if (
            tag == "a"
            and self.capture_field == "description"
            and self.current.get("href") is None
        ):
            self.current["href"] = attrs.get("href")

    def handle_data(self, data: str) -> None:
        if self.current is None or self.capture_field is None:
            return

        value = self.current[self.capture_field]
        if not isinstance(value, list):
            raise TypeError(f"Expected {self.capture_field} to collect text")
        value.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.current is None:
            return

        if self.capture_field is not None:
            self.capture_depth -= 1
            if self.capture_depth == 0:
                self.capture_field = None

        if tag != "article":
            return

        title = normalize_text(self.current["title"])  # type: ignore[arg-type]
        date_text = normalize_text(self.current["date"])  # type: ignore[arg-type]
        description = normalize_text(self.current["description"])  # type: ignore[arg-type]
        href = self.current["href"]
        self.current = None

        if not isinstance(href, str):
            raise ValueError(f"Missing article link for {title or 'untitled post'}")
        if not title or not date_text or not description:
            raise ValueError(f"Incomplete article metadata for {href}")

        self.posts.append(
            Post(
                title=title,
                date_text=date_text,
                url=urljoin(SITE_URL, href),
                description=description,
            )
        )


def parse_posts(index_html: str) -> list[Post]:
    parser = ArticleParser()
    parser.feed(index_html)
    parser.close()

    if not parser.posts:
        raise ValueError("No posts found in index.html")

    return parser.posts


def xml_text(value: str) -> str:
    return escape(value, {'"': "&quot;", "'": "&apos;"})


def render_feed(posts: list[Post]) -> str:
    latest_post_date = max(post.published_at for post in posts)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "  <channel>",
        f"    <title>{xml_text(CHANNEL_TITLE)}</title>",
        f"    <link>{xml_text(SITE_URL)}</link>",
        f"    <description>{xml_text(CHANNEL_DESCRIPTION)}</description>",
        "    <language>en</language>",
        f"    <lastBuildDate>{format_datetime(latest_post_date)}</lastBuildDate>",
        f'    <atom:link href="{xml_text(FEED_URL)}" rel="self" type="application/rss+xml" />',
        "    <ttl>1440</ttl>",
        "    <!-- Generated by scripts/generate_feed.py from index.html. -->",
        "",
    ]

    for post in posts:
        lines.extend(
            [
                "    <item>",
                f"      <title>{xml_text(post.title)}</title>",
                f"      <link>{xml_text(post.url)}</link>",
                f'      <guid isPermaLink="true">{xml_text(post.url)}</guid>',
                f"      <pubDate>{post.rss_date}</pubDate>",
                f"      <description>{xml_text(post.description)}</description>",
                "    </item>",
                "",
            ]
        )

    lines.extend(["  </channel>", "</rss>", ""])
    return "\n".join(lines)


def main() -> None:
    posts = parse_posts(INDEX_PATH.read_text(encoding="utf-8"))
    FEED_PATH.write_text(render_feed(posts), encoding="utf-8", newline="\n")
    print(f"Wrote {FEED_PATH.relative_to(ROOT)} with {len(posts)} posts")


if __name__ == "__main__":
    main()
