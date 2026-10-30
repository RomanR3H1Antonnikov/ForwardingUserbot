import asyncio
import os
import random
import yaml
from telethon import events
from telethon.errors import FloodWaitError, FileReferenceExpiredError
from telethon.tl.types import MessageMediaWebPage


def load_config():
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _matches_media(msg, media_filter: str = "all") -> bool:
    if media_filter == "all":
        return True
    if media_filter == "photo":
        return bool(msg.photo) and not isinstance(msg.media, MessageMediaWebPage)
    if media_filter == "video":
        return (bool(msg.video) and not msg.video_note and not msg.gif
                and not isinstance(msg.media, MessageMediaWebPage))
    raise ValueError(f"Unknown media filter: {media_filter}")


def _in_topic(message, topic_id: int) -> bool:
    """Return True if message belongs to the given forum topic."""
    r = message.reply_to
    if r is None:
        return False
    top = getattr(r, "reply_to_top_id", None)
    msg = getattr(r, "reply_to_msg_id", None)
    return top == topic_id or msg == topic_id


def _matches_source(msg, mirror: dict) -> bool:
    """Return True if msg belongs to the mirror's configured source."""
    source_type = mirror.get("source_type", "topic")
    if source_type == "topic":
        return _in_topic(msg, mirror["source_topic"])
    elif source_type == "group":
        # Capture only top-level group messages, not messages inside topics
        return not msg.reply_to
    else:  # channel
        return True


async def _send_safe(client, coro_factory, name: str):
    """Run coro_factory() retrying on FloodWait."""
    while True:
        try:
            return await coro_factory()
        except FloodWaitError as e:
            print(f"[{name}] FloodWait {e.seconds}s — waiting...")
            await asyncio.sleep(e.seconds + 1)


async def _copy_single(client, msg, dest_chat, dest_topic, name: str, media_filter: str = "all"):
    """Copy one non-album message."""
    if not _matches_media(msg, media_filter):
        return 0
    is_web_preview = isinstance(msg.media, MessageMediaWebPage)

    if not msg.media or is_web_preview:
        text = (msg.text or "").strip()
        if not text:
            print(f"[{name}] Skipping empty/service message {msg.id}")
            return 0
        await _send_safe(
            client,
            lambda: client.send_message(dest_chat, text, reply_to=dest_topic),
            name,
        )
        return 1

    kwargs = dict(
        file=msg.media,
        caption=msg.text,
        reply_to=dest_topic,
        voice_note=getattr(msg, "voice", False),
        video_note=getattr(msg, "video_note", False),
    )
    try:
        await _send_safe(client, lambda: client.send_file(dest_chat, **kwargs), name)
    except FileReferenceExpiredError:
        # File reference expired (can happen for old history) — download and re-upload
        print(f"[{name}] FileReferenceExpiredError — downloading and re-uploading msg {msg.id}")
        path = await client.download_media(msg)
        kwargs["file"] = path
        await _send_safe(client, lambda: client.send_file(dest_chat, **kwargs), name)
    return 1


async def _copy_album(client, messages: list, dest_chat, dest_topic, name: str, media_filter: str = "all"):
    """Copy a media album (grouped messages)."""
    caption = next((m.text for m in messages if m.text), None)
    messages = [m for m in messages if _matches_media(m, media_filter)]
    if not messages:
        return 0
    files = [m.media for m in messages]
    try:
        await _send_safe(
            client,
            lambda: client.send_file(dest_chat, file=files, caption=caption, reply_to=dest_topic),
            name,
        )
    except FileReferenceExpiredError:
        print(f"[{name}] FileReferenceExpiredError on album — re-uploading")
        paths = [await client.download_media(m) for m in messages]
        await _send_safe(
            client,
            lambda: client.send_file(dest_chat, file=paths, caption=caption, reply_to=dest_topic),
            name,
        )
    return len(messages)


def _safe(name: str) -> str:
    return name.replace(" ", "_").replace("/", "_")


def _progress_file(name: str) -> str:
    return os.path.join("session", f"progress_{_safe(name)}.txt")


def _pause_flag_file(name: str) -> str:
    return os.path.join("session", f"pause_{_safe(name)}.txt")


def _count_file(name: str) -> str:
    return os.path.join("session", f"count_{_safe(name)}.txt")


def _done_file(name: str) -> str:
    return os.path.join("session", f"done_{_safe(name)}.txt")


def _load_progress(name: str, default_id: int) -> int:
    path = _progress_file(name)
    if os.path.exists(path):
        try:
            with open(path) as f:
                saved = int(f.read().strip())
            print(f"[{name}] Resuming from saved progress: message ID {saved}")
            return saved
        except (ValueError, OSError):
            pass
    return default_id


def _save_progress(name: str, msg_id: int):
    path = _progress_file(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(str(msg_id))


def _clear_progress(name: str):
    path = _progress_file(name)
    if os.path.exists(path):
        os.remove(path)


def _load_count(name: str) -> int:
    path = _count_file(name)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return int(f.read().strip())
        except (ValueError, OSError):
            pass
    return 0


def _save_count(name: str, count: int):
    path = _count_file(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(str(count))


def _write_done(name: str, count: int):
    path = _done_file(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(str(count))


async def _dump_history(client, mirror: dict):
    source_chat = mirror["source_chat"]
    source_topic = mirror.get("source_topic")
    source_type = mirror.get("source_type", "topic")
    dest_chat = mirror["dest_chat"]
    dest_topic = mirror.get("dest_topic")
    name = mirror["name"]
    media_filter = mirror.get("media_filter", "all")
    config_start_id = mirror.get("start_from_message_id", 1)
    direction = mirror.get("direction", "older")
    if direction not in {"older", "newer"}:
        raise ValueError(f"Unknown direction: {direction}")

    saved_id = _load_progress(name, 0)
    start_id = saved_id or config_start_id
    count = _load_count(name)
    print(f"[{name}] Dumping from message ID {start_id} ({direction}), already done: {count}...")

    # For topic source, filter iter_messages by topic; for group/channel, iterate all
    if direction == "newer":
        iter_kwargs = {"min_id": start_id, "reverse": True}
    else:
        # Fresh backwards runs include the selected message; resumes exclude the checkpoint.
        iter_kwargs = {"max_id": start_id if saved_id else start_id + 1}
    if source_type == "topic" and source_topic is not None:
        iter_kwargs["reply_to"] = source_topic

    pause_flag = _pause_flag_file(name)
    pending_group: list = []  # [grouped_id, [messages]]

    async for msg in client.iter_messages(source_chat, **iter_kwargs):
        if msg.grouped_id:
            if pending_group and pending_group[0] != msg.grouped_id:
                sent = await _copy_album(client, pending_group[1], dest_chat, dest_topic, name, media_filter)
                last_id = pending_group[1][-1].id
                count += sent
                _save_progress(name, last_id)
                _save_count(name, count)
                pending_group = []
                if os.path.exists(pause_flag):
                    print(f"[{name}] Paused at {last_id}, total dumped: {count}")
                    return
                if sent:
                    await asyncio.sleep(random.uniform(5, 10))
            if not pending_group:
                pending_group = [msg.grouped_id, []]
            pending_group[1].append(msg)
        else:
            if pending_group:
                sent = await _copy_album(client, pending_group[1], dest_chat, dest_topic, name, media_filter)
                last_id = pending_group[1][-1].id
                count += sent
                _save_progress(name, last_id)
                _save_count(name, count)
                pending_group = []
                if os.path.exists(pause_flag):
                    print(f"[{name}] Paused at {last_id}, total dumped: {count}")
                    return
                if sent:
                    await asyncio.sleep(random.uniform(5, 10))
            sent = await _copy_single(client, msg, dest_chat, dest_topic, name, media_filter)
            count += sent
            _save_progress(name, msg.id)
            _save_count(name, count)
            if os.path.exists(pause_flag):
                print(f"[{name}] Paused at {msg.id}, total dumped: {count}")
                return
            if sent:
                await asyncio.sleep(random.uniform(5, 10))

    if pending_group:
        count += await _copy_album(client, pending_group[1], dest_chat, dest_topic, name, media_filter)
        _save_count(name, count)

    _clear_progress(name)
    _write_done(name, count)
    print(f"[{name}] Done! Total messages dumped: {count}")


async def setup(client):
    config = load_config()
    mirrors = config.get("mirrors", [])
    if not mirrors:
        print("[mirror] No mirrors configured.")
        return

    # album_buf: grouped_id -> {"mirror": ..., "messages": [...], "task": Task}
    album_buf: dict = {}

    source_chats = list({m["source_chat"] for m in mirrors})

    @client.on(events.NewMessage(chats=source_chats))
    async def on_new_message(event):
        msg = event.message

        mirror = next(
            (m for m in mirrors if event.chat_id == m["source_chat"] and _matches_source(msg, m)),
            None,
        )
        if not mirror:
            return

        dest_chat = mirror["dest_chat"]
        dest_topic = mirror.get("dest_topic")
        name = mirror["name"]

        if msg.grouped_id:
            gid = msg.grouped_id
            if gid not in album_buf:
                album_buf[gid] = {"mirror": mirror, "messages": []}
            album_buf[gid]["messages"].append(msg)

            # Cancel previous flush task and schedule a new one
            if "task" in album_buf[gid]:
                album_buf[gid]["task"].cancel()

            async def flush(gid=gid):
                await asyncio.sleep(0.8)
                entry = album_buf.pop(gid, None)
                if entry:
                    await _copy_album(
                        client,
                        entry["messages"],
                        entry["mirror"]["dest_chat"],
                        entry["mirror"].get("dest_topic"),
                        entry["mirror"]["name"],
                        entry["mirror"].get("media_filter", "all"),
                    )

            album_buf[gid]["task"] = asyncio.create_task(flush())
        else:
            await _copy_single(client, msg, dest_chat, dest_topic, name, mirror.get("media_filter", "all"))

    # Run history dumps sequentially
    for mirror in mirrors:
        if mirror.get("dump_history", False):
            await _dump_history(client, mirror)

    print("[mirror] Live mirroring active.")
