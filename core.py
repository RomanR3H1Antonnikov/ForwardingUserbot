import os
import importlib
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
PHONE = os.environ["TG_PHONE"]

SESSION_PATH = Path("session") / "userbot"


async def run():
    SESSION_PATH.parent.mkdir(exist_ok=True)

    client = TelegramClient(str(SESSION_PATH), API_ID, API_HASH)
    await client.start(phone=PHONE)

    for module_file in sorted(Path("modules").glob("*.py")):
        if module_file.name == "__init__.py":
            continue
        module = importlib.import_module(f"modules.{module_file.stem}")
        if hasattr(module, "setup"):
            await module.setup(client)

    print("[core] Userbot running. Ctrl+C to stop.")
    await client.run_until_disconnected()
