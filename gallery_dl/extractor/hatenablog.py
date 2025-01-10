# -*- coding: utf-8 -*-

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Extractors for https://hatenablog.com"""

import re
from .common import Extractor, Message
from .. import text


BASE_PATTERN = (
    r"(?:hatenablog:https?://([^/]+)|(?:https?://)?"
    r"([\w-]+\.(?:hatenablog\.com|hatenablog\.jp"
    r"|hatenadiary\.com|hateblo\.jp)))"
)
QUERY_RE = r"(?:\?([^#]*))?(?:#.*)?$"


class HatenaBlogExtractor(Extractor):
    """Base class for HatenaBlog extractors"""
    category = "hatenablog"
    directory_fmt = ("{category}", "{domain}")
    filename_fmt = "{category}_{domain}_{entry}_{num:>02}.{extension}"
    archive_fmt = "{filename}"

    def __init__(self, match):
        Extractor.__init__(self, match)

        self.domain = match.group(1) or match.group(2)
        self._find_img = re.compile(r'<img +(.+?) */?>').finditer
        self._is_image = re.compile(
            r'(?: |^)class="hatena-fotolife"(?: |$)').search
        self._find_img_src = re.compile(r'(?: |^)src="(.+?)"(?: |$)').search

    def _handle_article(self, article: str):
        extr = text.extract_from(article)
        date = text.parse_datetime(extr('<time datetime="', '"'))
        entry_link = text.unescape(extr(
            '<a href="', '" class="entry-title-link bookmark">'))
        entry = entry_link.partition("/entry/")[2]
        title = extr('', '</a>')
        content = extr(
            '<div class="entry-content hatenablog-entry">', '</div>')

        images = []
        for i in self._find_img(content):
            attributes = i.group(1)
            if not self._is_image(attributes):
                continue
            image = text.unescape(self._find_img_src(attributes).group(1))
            images.append(image)

        data = {
            "domain": self.domain,
            "date": date,
            "entry": text.nameext_from_url(entry_link)[0],
            "title": title,
            "count": len(images),
        }
        yield Message.Directory, data
        for data["num"], url in enumerate(images, 1):
            yield Message.Url, url, text.nameext_from_url(url, data)


class HatenaBlogEntriesExtractor(HatenaBlogExtractor):
    """Base class for a list of entries"""
    allowed_parameters = ()

    def __init__(self, match):
        HatenaBlogExtractor.__init__(self, match)
        self.path = match.group(3)
        self.query = {key: value for key, value in text.parse_query(
            match.group(4)).items() if self._acceptable_query(key)}
        self._find_pager_url = re.compile(
            r'<span class="pager-next">\s*<a href="(.+?)"').search

    def items(self):
        url = "https://" + self.domain + self.path
        query = self.query

        while url:
            page = self.request(url, params=query).text

            extr = text.extract_from(page)
            attributes = extr('<body ', '>')
            if "page-archive" in attributes:
                yield from self._handle_partial_articles(extr)
            else:
                yield from self._handle_full_articles(extr)

            match = self._find_pager_url(page)
            url = text.unescape(match.group(1)) if match else None
            query = None

    def _handle_partial_articles(self, extr):
        while True:
            section = extr('<section class="archive-entry', '</section>')
            if not section:
                break

            url = "hatenablog:" + text.unescape(text.extr(
                section, '<a class="entry-title-link" href="', '"'))
            data = {"_extractor": HatenaBlogEntryExtractor}
            yield Message.Queue, url, data

    def _handle_full_articles(self, extr):
        while True:
            attributes = extr('<article ', '>')
            if not attributes:
                break
            if "no-entry" in attributes:
                continue

            article = extr('', '</article>')
            yield from self._handle_article(article)

    def _acceptable_query(self, key: str) -> bool:
        return key == "page" or key in self.allowed_parameters


class HatenaBlogEntryExtractor(HatenaBlogExtractor):
    """Extractor for a single entry URL"""
    subcategory = "entry"
    pattern = BASE_PATTERN + r"/entry/([^?#]+)" + QUERY_RE
    example = "https://BLOG.hatenablog.com/entry/PATH"

    def __init__(self, match):
        HatenaBlogExtractor.__init__(self, match)
        self.path = match.group(3)

    def items(self):
        url = "https://" + self.domain + "/entry/" + self.path
        page = self.request(url).text

        extr = text.extract_from(page)
        while True:
            attributes = extr('<article ', '>')
            if "no-entry" in attributes:
                continue
            article = extr('', '</article>')
            return self._handle_article(article)


class HatenaBlogHomeExtractor(HatenaBlogEntriesExtractor):
    """Extractor for a blog's home page"""
    subcategory = "home"
    pattern = BASE_PATTERN + r"(/?)" + QUERY_RE
    example = "https://BLOG.hatenablog.com"


class HatenaBlogArchiveExtractor(HatenaBlogEntriesExtractor):
    """Extractor for a blog's archive page"""
    subcategory = "archive"
    pattern = BASE_PATTERN + r"(/archive(?:/\d+(?:/\d+(?:/\d+)?)?" + \
        r"|/category/[^?#]+)?)" + QUERY_RE
    example = "https://BLOG.hatenablog.com/archive/2024"


class HatenaBlogSearchExtractor(HatenaBlogEntriesExtractor):
    """Extractor for a blog's search results"""
    subcategory = "search"
    pattern = BASE_PATTERN + r"(/search)" + QUERY_RE
    example = "https://BLOG.hatenablog.com/search?q=QUERY"
    allowed_parameters = ("q",)
