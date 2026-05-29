import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedLink:
    chat_id: Optional[int]   # already -100-prefixed, or None for public groups
    username: Optional[str]  # set only for public groups
    topic_id: Optional[int]
    message_id: int


def parse_tme_link(url: str) -> Optional[ParsedLink]:
    url = url.strip()

    # Private supergroup with topic: t.me/c/{id}/{topic}/{msg}
    m = re.match(r'https?://t\.me/c/(\d+)/(\d+)/(\d+)/?$', url)
    if m:
        return ParsedLink(
            chat_id=int(f"-100{m.group(1)}"),
            username=None,
            topic_id=int(m.group(2)),
            message_id=int(m.group(3)),
        )

    # Private supergroup without topic: t.me/c/{id}/{msg}
    m = re.match(r'https?://t\.me/c/(\d+)/(\d+)/?$', url)
    if m:
        return ParsedLink(
            chat_id=int(f"-100{m.group(1)}"),
            username=None,
            topic_id=None,
            message_id=int(m.group(2)),
        )

    # Public group with topic: t.me/{username}/{topic}/{msg}
    m = re.match(r'https?://t\.me/([a-zA-Z][a-zA-Z0-9_]{3,})/(\d+)/(\d+)/?$', url)
    if m:
        return ParsedLink(
            chat_id=None,
            username=m.group(1),
            topic_id=int(m.group(2)),
            message_id=int(m.group(3)),
        )

    # Public group without topic: t.me/{username}/{msg}
    m = re.match(r'https?://t\.me/([a-zA-Z][a-zA-Z0-9_]{3,})/(\d+)/?$', url)
    if m:
        return ParsedLink(
            chat_id=None,
            username=m.group(1),
            topic_id=None,
            message_id=int(m.group(2)),
        )

    return None
