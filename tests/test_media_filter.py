import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telethon.tl.types import MessageMediaWebPage

from modules import mirror

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tg-config-bot"))
import launcher
from keyboards import media_filter_keyboard


def message(kind, msg_id=1, grouped_id=None, text=None):
    return SimpleNamespace(
        id=msg_id, grouped_id=grouped_id, text=text, reply_to=None,
        photo=kind == "photo", video=kind in {"video", "gif", "round"},
        gif=kind == "gif", video_note=kind == "round", voice=False,
        media=None if kind == "text" else object(),
    )


class MediaTests(unittest.IsolatedAsyncioTestCase):
    async def test_direction_and_resume_boundaries(self):
        for direction, saved, expected in [
            ("older", 0, {"max_id": 11}),
            ("older", 7, {"max_id": 7}),
            ("newer", 0, {"min_id": 10, "reverse": True}),
            ("newer", 12, {"min_id": 12, "reverse": True}),
        ]:
            for source_type in ("channel", "group", "topic"):
                with self.subTest(direction=direction, saved=saved, source_type=source_type):
                    calls = []

                    async def history(chat, **kwargs):
                        calls.append((chat, kwargs))
                        if False:
                            yield

                    client = SimpleNamespace(iter_messages=history)
                    config = dict(source_chat=1, source_topic=42, source_type=source_type,
                                  dest_chat=2, name="test", start_from_message_id=10, direction=direction)
                    with patch.object(mirror, "_load_progress", return_value=saved), \
                            patch.object(mirror, "_load_count", return_value=0), \
                            patch.object(mirror, "_clear_progress"), patch.object(mirror, "_write_done"):
                        await mirror._dump_history(client, config)
                    kwargs = dict(expected)
                    if source_type == "topic":
                        kwargs["reply_to"] = 42
                    self.assertEqual(calls, [(1, kwargs)])

    async def test_newer_history_is_ordered_filtered_and_resumes_without_repeat(self):
        items = [message("photo", 10), message("video", 11, 100), message("photo", 12, 100),
                 message("video", 13), message("video", 14)]
        calls = []

        async def history(chat, **kwargs):
            calls.append(kwargs)
            for msg in items:
                if msg.id > kwargs["min_id"]:
                    yield msg

        client = SimpleNamespace(iter_messages=history, send_file=AsyncMock(), send_message=AsyncMock())
        config = dict(source_chat=1, source_type="channel", dest_chat=2, name="test",
                      start_from_message_id=10, media_filter="video", direction="newer")
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(mirror, "_progress_file", return_value=str(Path(tmp) / "progress")), \
                patch.object(mirror, "_count_file", return_value=str(Path(tmp) / "count")), \
                patch.object(mirror, "_done_file", return_value=str(Path(tmp) / "done")), \
                patch.object(mirror, "_pause_flag_file", return_value=str(Path(tmp) / "pause")), \
                patch.object(mirror.asyncio, "sleep", new_callable=AsyncMock):
            Path(tmp, "pause").touch()
            await mirror._dump_history(client, config)
            self.assertEqual(Path(tmp, "progress").read_text(), "12")
            self.assertEqual(Path(tmp, "count").read_text(), "1")
            Path(tmp, "pause").unlink()
            await mirror._dump_history(client, config)
            self.assertEqual(Path(tmp, "done").read_text(), "3")
            self.assertEqual(calls, [{"min_id": 10, "reverse": True}, {"min_id": 12, "reverse": True}])
            files = [call.kwargs["file"] for call in client.send_file.await_args_list]
            self.assertEqual(files, [[items[1].media], items[3].media, items[4].media])

    async def test_single_modes(self):
        for mode, accepted in [("all", {"photo", "video", "gif", "round", "text", "document"}),
                               ("photo", {"photo"}), ("video", {"video"})]:
            for kind in ["photo", "video", "gif", "round", "text", "document"]:
                with self.subTest(mode=mode, kind=kind):
                    client = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
                    result = await mirror._copy_single(client, message(kind, text="caption"), 2, None, "test", mode)
                    self.assertEqual(result, int(kind in accepted))
                    self.assertEqual(client.send_file.await_count + client.send_message.await_count, result)

    async def test_web_preview_is_not_photo_or_video(self):
        msg = message("photo")
        msg.media = MessageMediaWebPage(webpage=None)
        self.assertFalse(mirror._matches_media(msg, "photo"))
        msg.video = True
        self.assertFalse(mirror._matches_media(msg, "video"))

    async def test_mixed_album_preserves_caption_and_filters_each_item(self):
        photo = message("photo", text="Shared caption")
        video = message("video")
        for mode, expected in [("all", [photo.media, video.media]),
                               ("photo", [photo.media]), ("video", [video.media])]:
            client = SimpleNamespace(send_file=AsyncMock())
            count = await mirror._copy_album(client, [photo, video], 2, 42, "test", mode)
            self.assertEqual(count, len(expected))
            client.send_file.assert_awaited_once_with(2, file=expected, caption="Shared caption", reply_to=42)
        client = SimpleNamespace(send_file=AsyncMock())
        self.assertEqual(await mirror._copy_album(client, [photo], 2, None, "test", "video"), 0)
        client.send_file.assert_not_awaited()

    async def test_history_counts_only_selected_and_checkpoints_skipped(self):
        messages = [message("photo", 6, 100, "caption"), message("video", 5, 100),
                    message("text", 4, text="skip"), message("video", 3), message("photo", 2)]

        async def history(*args, **kwargs):
            for msg in messages:
                yield msg

        client = SimpleNamespace(iter_messages=history, send_file=AsyncMock(), send_message=AsyncMock())
        config = dict(source_chat=1, source_type="channel", dest_chat=2, name="test",
                      start_from_message_id=6, media_filter="video")
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(mirror, "_progress_file", return_value=str(Path(tmp) / "progress")), \
                patch.object(mirror, "_count_file", return_value=str(Path(tmp) / "count")), \
                patch.object(mirror, "_done_file", return_value=str(Path(tmp) / "done")), \
                patch.object(mirror, "_pause_flag_file", return_value=str(Path(tmp) / "pause")), \
                patch.object(mirror.asyncio, "sleep", new_callable=AsyncMock), \
                patch.object(mirror, "_save_progress", wraps=mirror._save_progress) as progress:
            await mirror._dump_history(client, config)
            self.assertEqual(Path(tmp, "done").read_text(), "2")
            self.assertEqual(progress.call_args.args, ("test", 2))
            self.assertEqual(client.send_file.await_count, 2)
            client.send_message.assert_not_awaited()


class ConfigTests(unittest.TestCase):
    def test_filter_is_written_by_launcher(self):
        for mode in ("all", "photo", "video"):
            with tempfile.TemporaryDirectory() as tmp, \
                    patch.object(launcher, "_kill_from_pid_file"), \
                    patch.object(launcher.subprocess, "Popen", return_value=SimpleNamespace(pid=123)), \
                    patch("builtins.open", unittest.mock.mock_open()):
                launcher.launch_userbot(1, None, "group", 100, 2, None, "group", tmp, media_filter=mode, direction="newer")
                config = launcher.yaml.safe_load(Path(tmp, "config.yaml").read_text(encoding="utf-8"))
                self.assertEqual(config["mirrors"][0]["media_filter"], mode)
                self.assertEqual(config["mirrors"][0]["direction"], "newer")

    def test_keyboard_choices(self):
        choices = {button.callback_data for row in media_filter_keyboard().inline_keyboard for button in row}
        self.assertEqual(choices, {"media:all", "media:photo", "media:video", "back"})


if __name__ == "__main__":
    unittest.main()
