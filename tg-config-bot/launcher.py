import os
import subprocess
from datetime import datetime
from pathlib import Path

import yaml

_HERE = Path(__file__).parent


# ── Launch ────────────────────────────────────────────────────────────────────

_PID_FILE = "session/run.pid"


def launch_userbot(
    source_chat: int,
    source_topic: int,
    source_from_msg: int,
    dest_chat: int,
    dest_topic: int,
    userbot_dir: str,
    name: str | None = None,
) -> subprocess.Popen:
    userbot_path = (_HERE / userbot_dir).resolve()

    # Kill any previously launched userbot to avoid session lock
    _kill_from_pid_file(userbot_path)

    if name is None:
        name = f"Mirror {datetime.now():%Y-%m-%d %H:%M}"

    config = {
        "mirrors": [{
            "name": name,
            "source_chat": source_chat,
            "source_topic": source_topic,
            "dest_chat": dest_chat,
            "dest_topic": dest_topic,
            "dump_history": True,
            "start_from_message_id": source_from_msg,
        }]
    }
    (userbot_path / "config.yaml").write_text(
        yaml.dump(config, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )

    log_path = userbot_path / "session" / f"run_{datetime.now():%Y%m%d_%H%M%S}.log"
    log_path.parent.mkdir(exist_ok=True)
    log_file = open(log_path, "w", encoding="utf-8")

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    process = subprocess.Popen(
        [_python(userbot_path), "main.py"],
        cwd=str(userbot_path),
        stdout=log_file,
        stderr=log_file,
        env=env,
    )
    _write_pid_file(userbot_path, process.pid)
    return process


def _pid_file_path(userbot_path: Path) -> Path:
    return userbot_path / _PID_FILE


def _write_pid_file(userbot_path: Path, pid: int):
    path = _pid_file_path(userbot_path)
    path.parent.mkdir(exist_ok=True)
    path.write_text(str(pid))


def _kill_from_pid_file(userbot_path: Path):
    path = _pid_file_path(userbot_path)
    if not path.exists():
        return
    try:
        pid = int(path.read_text().strip())
        stop_process(pid)
    except (ValueError, OSError):
        pass
    finally:
        path.unlink(missing_ok=True)


def _python(userbot_path: Path) -> str:
    for candidate in (
        userbot_path / ".venv" / "Scripts" / "python.exe",
        userbot_path / ".venv" / "bin" / "python",
    ):
        if candidate.exists():
            return str(candidate)
    return os.getenv("USERBOT_PYTHON", "python")


# ── Process control ───────────────────────────────────────────────────────────

def is_process_alive(pid: int) -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True,
        )
        return str(pid) in result.stdout
    except Exception:
        return False


def stop_process(pid: int):
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    except Exception:
        pass


# ── Pause flag ────────────────────────────────────────────────────────────────

def _safe(name: str) -> str:
    return name.replace(" ", "_").replace("/", "_")


def _session_file(userbot_dir: str, filename: str) -> Path:
    return (_HERE / userbot_dir).resolve() / "session" / filename


def create_pause_flag(userbot_dir: str, name: str):
    path = _session_file(userbot_dir, f"pause_{_safe(name)}.txt")
    path.parent.mkdir(exist_ok=True)
    path.touch()


def remove_pause_flag(userbot_dir: str, name: str):
    path = _session_file(userbot_dir, f"pause_{_safe(name)}.txt")
    path.unlink(missing_ok=True)


# ── Status ────────────────────────────────────────────────────────────────────

def status_info(userbot_dir: str, name: str) -> dict:
    safe = _safe(name)

    def _read_int(filename: str) -> int | None:
        path = _session_file(userbot_dir, filename)
        if path.exists():
            try:
                return int(path.read_text().strip())
            except (ValueError, OSError):
                pass
        return None

    done_count = _read_int(f"done_{safe}.txt")
    count = _read_int(f"count_{safe}.txt") or 0
    current_id = _read_int(f"progress_{safe}.txt")
    is_paused = _session_file(userbot_dir, f"pause_{safe}.txt").exists()

    return {
        "done": done_count is not None,
        "count": done_count if done_count is not None else count,
        "current_id": current_id,
        "is_paused": is_paused,
    }
