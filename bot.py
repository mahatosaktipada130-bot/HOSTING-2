#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simran Hosting Bot — Total Free Edition
Auto-install missing modules on crash.
Multi-source bot token config.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─── AUTO INSTALL ────────────────────────────────────────────────
_REQ = [
    ("telebot", "pyTelegramBotAPI"),
    ("requests", "requests"),
    ("cryptography.fernet", "cryptography"),
    ("flask", "flask"),
]
_missing = []
for _m, _p in _REQ:
    try:
        __import__(_m)
    except ImportError:
        _missing.append(_p)
if _missing:
    print(f"[setup] installing: {', '.join(_missing)}")
    for cmd in (
        [sys.executable, "-m", "pip", "install", "--quiet", *_missing],
        [sys.executable, "-m", "pip", "install", "--quiet",
         "--break-system-packages", *_missing],
    ):
        try:
            subprocess.run(cmd, check=True)
            break
        except Exception:
            continue

import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException
from cryptography.fernet import Fernet
from flask import Flask, jsonify


# ═════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═════════════════════════════════════════════════════════════════
BASE_DIR = Path(__file__).resolve().parent

BOT_TOKEN_HARDCODED = "8600557449:AAHFBV2PNaBSgwTJ179pTM2PEHytsLjJHiA"
OWNER_ID_HARDCODED  = 8662511212


def _load_json_cfg() -> Dict[str, Any]:
    cfg_path = BASE_DIR / "config.json"
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


_CFG = _load_json_cfg()


def _resolve_token() -> str:
    t = (os.environ.get("BOT_TOKEN") or "").strip()
    if t:
        return t
    t = str(_CFG.get("bot_token", "")).strip()
    if t:
        return t
    tf = BASE_DIR / "bot_token.txt"
    if tf.exists():
        try:
            t = tf.read_text(encoding="utf-8").strip()
            if t:
                return t
        except Exception:
            pass
    if BOT_TOKEN_HARDCODED.strip():
        return BOT_TOKEN_HARDCODED.strip()
    return ""


def _resolve_owner() -> int:
    v = os.environ.get("OWNER_ID", "").strip()
    if v.isdigit():
        return int(v)
    v = str(_CFG.get("owner_id", "")).strip()
    if v.isdigit():
        return int(v)
    of = BASE_DIR / "owner_id.txt"
    if of.exists():
        try:
            v = of.read_text(encoding="utf-8").strip()
            if v.isdigit():
                return int(v)
        except Exception:
            pass
    return int(OWNER_ID_HARDCODED or 0)


TOKEN = _resolve_token()

if not TOKEN:
    if sys.stdin.isatty():
        print("=" * 60)
        print("  BOT TOKEN not configured.")
        print("=" * 60)
        try:
            entered = input("Paste your bot token now (or Enter to exit): ").strip()
        except (EOFError, KeyboardInterrupt):
            entered = ""
        if entered:
            (BASE_DIR / "bot_token.txt").write_text(entered, encoding="utf-8")
            TOKEN = entered
            print("[setup] token saved to bot_token.txt")
    if not TOKEN:
        sys.exit("[x] BOT_TOKEN not set.")

OWNER_ID = _resolve_owner()

try:
    KEEPALIVE_PORT = int(os.environ.get("PORT", "8080"))
except (TypeError, ValueError):
    KEEPALIVE_PORT = 8080

MAX_UPLOAD = 75 * 1024 * 1024
LOG_RING = 500
AUTO_RESTART_DELAY = 5
MAX_RESTART_ATTEMPTS = 5
AUTO_INSTALL_TIMEOUT = 300


# ─── PATHS ───────────────────────────────────────────────────────
STORAGE = BASE_DIR / "storage"
ENCFILES = STORAGE / "encfiles"
SANDBOX = BASE_DIR / "sandbox"
DATA = STORAGE / "data"
for _d in (STORAGE, ENCFILES, SANDBOX, DATA):
    _d.mkdir(parents=True, exist_ok=True)

DB_FILE = DATA / "db.json"
KEY_FILE = DATA / "keys.json"
SALT_FILE = DATA / ".master_salt"

BRAND = "ꜱᴍ"
FOOTER = f"\n\n<blockquote>{BRAND}</blockquote>"

ENTRY_PY = ("bot.py", "main.py", "app.py", "run.py")
ENTRY_JS = ("index.js", "bot.js", "main.js", "app.js")

SECRET_ENV = {
    "BOT_TOKEN", "OWNER_ID", "ERROR_BOT_TOKEN",
    "MONGO_URL", "GITHUB_TOKEN", "GITHUB_REPO",
    "DATABASE_URL", "OPENAI_API_KEY",
}


# ─── SMALL-CAPS ──────────────────────────────────────────────────
_SC_MAP = {
    'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ',
    'g': 'ɢ', 'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ',
    'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ',
    's': 'ꜱ', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x',
    'y': 'ʏ', 'z': 'ᴢ',
}


def sc(t: Any) -> str:
    return ''.join(_SC_MAP.get(c.lower(), c) for c in str(t))


def esc(s: Any = "") -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def bullet(label: str, value: Any) -> str:
    return f"•  <b>{esc(label)}</b>: <code>{esc(value)}</code>"


# ─── STYLED REPLY KEYBOARD BUILDER ──────────────────────────────
def rbtn(text: str, style: Optional[str] = None,
         **kw) -> types.KeyboardButton:
    """Reply-keyboard button with optional color style (falls back gracefully)."""
    kw2 = dict(kw)
    if style:
        try:
            return types.KeyboardButton(text, **kw2, style=style)
        except TypeError:
            pass
    b = types.KeyboardButton(text, **kw2)
    if style:
        try:
            b.style = style
        except Exception:
            pass
    return b


def _rkb(rows: List[List[Tuple[str, Optional[str]]]]) -> types.ReplyKeyboardMarkup:
    """Build a reply keyboard from rows of (label, style) tuples."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2,
                                    is_persistent=True)
    for row in rows:
        btns = [rbtn(text, style=style) for text, style in row]
        kb.add(*btns)
    return kb


# ─── REPLY KEYBOARD BUTTON LABELS ───────────────────────────────
RB_MY_BOTS = "📂  " + sc("My Bots")
RB_UPLOAD  = "⊕  " + sc("Upload")
RB_HELP    = "?  " + sc("Help")
RB_REFRESH = "↻  " + sc("Refresh")
RB_BACK    = "↲  " + sc("Back")
RB_MAIN    = "↲  " + sc("Main Menu")
RB_START   = "▶  " + sc("Start")
RB_STOP    = "■  " + sc("Stop")
RB_RESTART = "↻  " + sc("Restart")
RB_LOGS    = "▸  " + sc("Live Logs")
RB_ENV     = "✎  " + sc("Env Vars")
RB_DELETE  = "✖  " + sc("Delete")
RB_YES_DEL = "✖  " + sc("Yes, Delete")
RB_CANCEL  = "↲  " + sc("Cancel")
RB_ADD_VAR = "⊕  " + sc("Add Variable")


def _main_rkb() -> types.ReplyKeyboardMarkup:
    return _rkb([
        [(RB_MY_BOTS, "primary"), (RB_UPLOAD, "primary")],
        [(RB_HELP, "success"), (RB_REFRESH, "success")],
    ])


# ─── UTIL ────────────────────────────────────────────────────────
def ts_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fmt_bytes(n: float) -> str:
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_dur(ms: int) -> str:
    if not ms or ms < 0:
        return "—"
    s = ms // 1000
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def safe_name(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", s or "").strip("_")
    return (s or "bot")[:48]


def rmrf(p) -> None:
    try:
        shutil.rmtree(str(p), ignore_errors=True)
    except Exception:
        pass


def safe_join(root: Path, *parts: str) -> Path:
    final = (root / Path(*parts)).resolve()
    rootp = root.resolve()
    if rootp not in final.parents and final != rootp:
        raise ValueError("path traversal")
    return final


# ─── DB ──────────────────────────────────────────────────────────
_db_lock = threading.RLock()


def db_load() -> Dict[str, Any]:
    with _db_lock:
        if not DB_FILE.exists():
            return {"bots": {}}
        try:
            d = json.loads(DB_FILE.read_text(encoding="utf-8"))
            d.setdefault("bots", {})
            return d
        except Exception:
            return {"bots": {}}


def db_save(d: Dict[str, Any]) -> None:
    with _db_lock:
        tmp = DB_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")
        tmp.replace(DB_FILE)


def get_bot(bot_id: str) -> Optional[Dict[str, Any]]:
    return db_load()["bots"].get(bot_id)


def save_bot(bot: Dict[str, Any]) -> None:
    d = db_load()
    d["bots"][bot["_id"]] = bot
    db_save(d)


def delete_bot_doc(bot_id: str) -> None:
    d = db_load()
    d["bots"].pop(bot_id, None)
    db_save(d)


def list_user_bots(uid: int) -> List[Dict[str, Any]]:
    return [b for b in db_load()["bots"].values() if b.get("owner") == uid]


# ─── CRYPTO ──────────────────────────────────────────────────────
_key_lock = threading.Lock()


def _master_key() -> bytes:
    with _key_lock:
        if not SALT_FILE.exists():
            SALT_FILE.parent.mkdir(parents=True, exist_ok=True)
            SALT_FILE.write_bytes(secrets.token_bytes(32))
        salt = SALT_FILE.read_bytes()
    return base64.urlsafe_b64encode(hashlib.sha256(salt).digest())


def _keys_load() -> Dict[str, str]:
    with _key_lock:
        if not KEY_FILE.exists():
            return {}
        try:
            f = Fernet(_master_key())
            return json.loads(f.decrypt(KEY_FILE.read_bytes()).decode("utf-8"))
        except Exception:
            return {}


def _keys_save(keys: Dict[str, str]) -> None:
    with _key_lock:
        f = Fernet(_master_key())
        KEY_FILE.write_bytes(f.encrypt(json.dumps(keys).encode("utf-8")))


def store_key(key_id: str, key: bytes) -> None:
    keys = _keys_load()
    keys[key_id] = key.decode()
    _keys_save(keys)


def load_key(key_id: str) -> Optional[bytes]:
    v = _keys_load().get(key_id)
    return v.encode() if v else None


def wipe_key(key_id: str) -> None:
    keys = _keys_load()
    if key_id in keys:
        del keys[key_id]
        _keys_save(keys)


def encrypt_and_store(owner_id: int, filename: str, plain: bytes) -> Dict[str, Any]:
    key = Fernet.generate_key()
    cipher = Fernet(key).encrypt(plain)
    key_id = secrets.token_urlsafe(16)
    stamp = int(time.time() * 1000)
    rel = f"{owner_id}/{stamp}_{safe_name(filename)}.enc"
    out = ENCFILES / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(cipher)
    store_key(key_id, key)
    return {
        "key_id": key_id,
        "enc_path": str(out),
        "filename": filename,
        "size": len(plain),
    }


def decrypt_file(enc_path: str, key_id: str) -> bytes:
    key = load_key(key_id)
    if not key:
        raise RuntimeError(f"key {key_id} missing")
    return Fernet(key).decrypt(Path(enc_path).read_bytes())


# ═════════════════════════════════════════════════════════════════
#  AUTO-INSTALL MISSING MODULES
# ═════════════════════════════════════════════════════════════════
PYPI_ALIAS: Dict[str, str] = {
    "telebot":      "pyTelegramBotAPI",
    "telegram":     "python-telegram-bot",
    "PIL":          "Pillow",
    "cv2":          "opencv-python",
    "bs4":          "beautifulsoup4",
    "yaml":         "PyYAML",
    "dotenv":       "python-dotenv",
    "Crypto":       "pycryptodome",
    "Cryptodome":   "pycryptodomex",
    "dateutil":     "python-dateutil",
    "sklearn":      "scikit-learn",
    "skimage":      "scikit-image",
    "psycopg2":     "psycopg2-binary",
    "MySQLdb":      "mysqlclient",
    "serial":       "pyserial",
    "discord":      "discord.py",
    "tgcrypto":     "TgCrypto",
    "pyrogram":     "Pyrogram",
    "telethon":     "Telethon",
    "nacl":         "PyNaCl",
    "git":          "GitPython",
    "jose":         "python-jose",
    "ujson":        "ujson",
    "aiohttp":      "aiohttp",
    "aiogram":      "aiogram",
    "fastapi":      "fastapi",
    "starlette":    "starlette",
    "redis":        "redis",
    "pymongo":      "pymongo",
    "motor":        "motor",
    "psutil":       "psutil",
    "schedule":     "schedule",
    "apscheduler":  "APScheduler",
    "github":       "PyGithub",
    "lxml":         "lxml",
    "chardet":      "chardet",
    "openai":       "openai",
    "google.generativeai": "google-generativeai",
}

_MISSING_PAT_PY = re.compile(
    r"ModuleNotFoundError:\s*No module named\s+'([^']+)'")
_MISSING_PAT_JS = re.compile(
    r"Cannot find module\s+'([^']+)'")


def _extract_missing(log_lines: List[str], kind: str) -> List[str]:
    pattern = _MISSING_PAT_PY if kind == "python" else _MISSING_PAT_JS
    found: List[str] = []
    seen: set = set()
    for line in log_lines[-40:]:
        m = pattern.search(line)
        if m:
            mod = m.group(1).strip().split(".")[0]
            if mod and mod not in seen:
                seen.add(mod)
                found.append(mod)
    return found


def _pip_install_into_deps(bot_dir: Path, packages: List[str]) -> Tuple[bool, str]:
    deps = bot_dir / ".deps"
    deps.mkdir(exist_ok=True)
    env = {**os.environ,
           "PIP_DISABLE_PIP_VERSION_CHECK": "1",
           "PIP_NO_INPUT": "1"}
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "--target", str(deps), "--upgrade", "--no-input",
             "--disable-pip-version-check", *packages],
            capture_output=True, text=True, timeout=AUTO_INSTALL_TIMEOUT,
            env=env,
        )
        return (r.returncode == 0,
                (r.stdout or "") + "\n" + (r.stderr or ""))
    except subprocess.TimeoutExpired:
        return (False, f"pip timeout after {AUTO_INSTALL_TIMEOUT}s")
    except Exception as e:
        return (False, str(e))


def _npm_install_into_dir(bot_dir: Path, packages: List[str]) -> Tuple[bool, str]:
    try:
        r = subprocess.run(
            ["npm", "install", "--no-audit", "--no-fund", *packages],
            cwd=str(bot_dir),
            capture_output=True, text=True, timeout=AUTO_INSTALL_TIMEOUT,
        )
        return (r.returncode == 0,
                (r.stdout or "") + "\n" + (r.stderr or ""))
    except subprocess.TimeoutExpired:
        return (False, f"npm timeout after {AUTO_INSTALL_TIMEOUT}s")
    except FileNotFoundError:
        return (False, "npm not installed on server")
    except Exception as e:
        return (False, str(e))


def _try_auto_install(b: Dict[str, Any], kind: str,
                      log: List[str]) -> bool:
    missing = _extract_missing(log, kind)
    if not missing:
        return False

    log.append(f"[📦] detected missing: {', '.join(missing)}")
    already = set(b.get("auto_installed", []))
    to_install: List[str] = []
    pkg_map: Dict[str, str] = {}

    for mod in missing:
        pkg = PYPI_ALIAS.get(mod, mod) if kind == "python" else mod
        pkg_map[mod] = pkg
        if pkg in already:
            log.append(f"[!] '{pkg}' was already tried — skipping")
            continue
        to_install.append(pkg)
        already.add(pkg)

    if not to_install:
        log.append("[!] all missing modules were already tried — giving up")
        return False

    b["auto_installed"] = sorted(already)
    save_bot(b)

    log.append(f"[📦] installing: {', '.join(to_install)} (this may take a minute)")
    bot_dir = Path(b["dir"])
    if kind == "python":
        ok, out = _pip_install_into_deps(bot_dir, to_install)
    else:
        ok, out = _npm_install_into_dir(bot_dir, to_install)

    log.append(f"[{'✓' if ok else '✗'}] auto-install finished")
    for line in out.splitlines()[-6:]:
        if line.strip():
            log.append(f"  {line}")

    return ok


# ─── RUNNER ──────────────────────────────────────────────────────
RUNNING: Dict[str, Dict[str, Any]] = {}
_runner_lock = threading.Lock()


def safe_env(bot_dir: Path, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    env["HOME"] = str(bot_dir)
    env["TMPDIR"] = str(bot_dir / ".tmp")
    env["PATH"] = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")
    (bot_dir / ".tmp").mkdir(exist_ok=True)
    deps = bot_dir / ".deps"
    if deps.exists():
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{deps}:{existing}" if existing else str(deps)
    if extra:
        for k, v in extra.items():
            if k in SECRET_ENV:
                continue
            env[str(k)] = str(v)
    return env


def detect_entry(bot_dir: Path) -> Tuple[Optional[str], Optional[str]]:
    for n in ENTRY_PY:
        if (bot_dir / n).exists():
            return ("python", n)
    for n in ENTRY_JS:
        if (bot_dir / n).exists():
            return ("node", n)
    for p in bot_dir.rglob("*.py"):
        if ".deps" in p.parts or "node_modules" in p.parts or "venv" in p.parts:
            continue
        return ("python", str(p.relative_to(bot_dir)))
    for p in bot_dir.rglob("*.js"):
        if "node_modules" in p.parts:
            continue
        return ("node", str(p.relative_to(bot_dir)))
    return (None, None)


def materialize_files(bot: Dict[str, Any]) -> None:
    bot_dir = Path(bot["dir"])
    bot_dir.mkdir(parents=True, exist_ok=True)
    for f in bot.get("enc_files", []):
        try:
            plain = decrypt_file(f["enc_path"], f["key_id"])
        except Exception as e:
            raise RuntimeError(f"decrypt {f.get('filename')}: {e}")
        rel = (f.get("rel_path") or f["filename"]).lstrip("/")
        try:
            tgt = safe_join(bot_dir, rel)
        except ValueError:
            continue
        tgt.parent.mkdir(parents=True, exist_ok=True)
        tgt.write_bytes(plain)


def install_deps_from_requirements(bot_dir: Path, kind: str,
                                   log: List[str]) -> None:
    marker = bot_dir / ".deps_installed"
    if marker.exists():
        log.append("[deps] cached")
        return
    try:
        if kind == "python":
            deps = bot_dir / ".deps"
            deps.mkdir(exist_ok=True)
            req = bot_dir / "requirements.txt"
            if req.exists():
                log.append("── pip install requirements.txt ──")
                r = subprocess.run(
                    [sys.executable, "-m", "pip", "install",
                     "--target", str(deps), "--upgrade", "--no-input",
                     "--disable-pip-version-check", "-r", str(req)],
                    cwd=str(bot_dir), timeout=600,
                    capture_output=True, text=True,
                )
                for line in (r.stdout or "").splitlines()[-10:]:
                    log.append(line)
                log.append(f"[pip rc={r.returncode}]")
        elif kind == "node":
            pkg = bot_dir / "package.json"
            if pkg.exists() and not (bot_dir / "node_modules").exists():
                log.append("── npm install ──")
                r = subprocess.run(
                    ["npm", "install", "--omit=dev", "--no-audit", "--no-fund"],
                    cwd=str(bot_dir), timeout=300,
                    capture_output=True, text=True,
                )
                for line in (r.stdout or "").splitlines()[-10:]:
                    log.append(line)
                log.append(f"[npm rc={r.returncode}]")
        marker.write_text("1")
    except subprocess.TimeoutExpired:
        log.append("[!] dependency install timeout")
    except FileNotFoundError as e:
        log.append(f"[!] tool not found: {e}")
    except Exception as e:
        log.append(f"[!] install error: {e}")


def _drain_proc(bot_id: str, proc: subprocess.Popen, log: List[str],
                kind: str) -> None:
    try:
        if proc.stdout:
            for line in iter(proc.stdout.readline, b""):
                try:
                    txt = line.decode("utf-8", "replace").rstrip()
                except Exception:
                    txt = repr(line)
                log.append(txt)
                if len(log) > LOG_RING:
                    del log[: len(log) - LOG_RING]
    except Exception:
        pass

    try:
        rc = proc.wait()
        log.append(f"── exited rc={rc} ──")
        with _runner_lock:
            info = RUNNING.get(bot_id)
            manual = bool(info.get("manual_stop")) if info else True
            if info and info.get("proc") is proc:
                RUNNING.pop(bot_id, None)
        if manual:
            return
        if rc == 0:
            return

        b = get_bot(bot_id)
        if not b:
            return

        installed_any = _try_auto_install(b, kind, log)

        if installed_any:
            attempts = 1
            delay = 1
            log.append("[↻] retry after installing new packages")
        else:
            attempts = int(b.get("restart_attempts", 0)) + 1
            delay = AUTO_RESTART_DELAY
            log.append(f"[↻] auto-restart in {delay}s "
                       f"(attempt {attempts}/{MAX_RESTART_ATTEMPTS})")

        b["restart_attempts"] = attempts
        b["last_exit_code"] = int(rc) if rc is not None else None
        b["last_exit_at"] = ts_iso()
        b["last_error"] = "\n".join(log[-10:])[:1200]
        save_bot(b)

        if attempts > MAX_RESTART_ATTEMPTS:
            log.append(f"[!] max restart attempts reached — giving up")
            b["status"] = "crashed"
            save_bot(b)
            return

        time.sleep(delay)
        with _runner_lock:
            info2 = RUNNING.get(bot_id)
            if info2 and info2.get("manual_stop"):
                return
        start_bot(bot_id)
    except Exception:
        traceback.print_exc()


def start_bot(bot_id: str) -> Dict[str, Any]:
    with _runner_lock:
        existing = RUNNING.get(bot_id)
        if existing and existing["proc"].poll() is None:
            return {"ok": False, "error": "already running"}
    b = get_bot(bot_id)
    if not b:
        return {"ok": False, "error": "bot not found"}
    bot_dir = Path(b["dir"])
    if not bot_dir.exists():
        return {"ok": False, "error": "sandbox missing"}

    try:
        materialize_files(b)
    except Exception as e:
        return {"ok": False, "error": f"decrypt: {e}"}

    kind, entry = detect_entry(bot_dir)
    if not kind:
        return {"ok": False, "error": "no entry file (bot.py / index.js)"}

    log: List[str] = [f"── START {ts_iso()} ──"]
    install_deps_from_requirements(bot_dir, kind, log)

    cmd = [sys.executable, "-u", entry] if kind == "python" else ["node", entry]
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(bot_dir), env=safe_env(bot_dir, b.get("env") or {}),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            preexec_fn=os.setsid if os.name == "posix" else None,
        )
    except Exception as e:
        return {"ok": False, "error": f"spawn: {e}"}

    start_token = secrets.token_hex(8)
    info = {
        "proc": proc,
        "kind": kind,
        "started": time.time() * 1000,
        "log": log,
        "manual_stop": False,
        "token": start_token,
    }
    with _runner_lock:
        RUNNING[bot_id] = info

    b["status"] = "running"
    b["last_started"] = ts_iso()
    b["last_error"] = ""
    save_bot(b)

    threading.Thread(target=_drain_proc,
                     args=(bot_id, proc, log, kind),
                     daemon=True).start()

    return {"ok": True, "pid": proc.pid, "kind": kind}


def stop_bot(bot_id: str, manual: bool = True) -> Dict[str, Any]:
    with _runner_lock:
        info = RUNNING.get(bot_id)
        if info:
            info["manual_stop"] = manual
    if not info:
        b = get_bot(bot_id)
        if b:
            b["status"] = "stopped"
            save_bot(b)
        return {"ok": True}

    proc = info["proc"]
    try:
        if os.name == "posix":
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
        else:
            proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                proc.kill()
            try:
                proc.wait(timeout=2)
            except Exception:
                pass
    except Exception as e:
        print(f"[stop_bot] {e}", file=sys.stderr)

    with _runner_lock:
        RUNNING.pop(bot_id, None)

    b = get_bot(bot_id)
    if b:
        b["status"] = "stopped"
        save_bot(b)
    return {"ok": True}


def restart_bot(bot_id: str) -> Dict[str, Any]:
    stop_bot(bot_id, manual=False)
    time.sleep(1)
    return start_bot(bot_id)


def tail_log(bot_id: str, n: int = 40) -> str:
    info = RUNNING.get(bot_id)
    if not info:
        b = get_bot(bot_id)
        if b and b.get("last_error"):
            return b["last_error"]
        return "(no logs yet)"
    log = info["log"]
    return "\n".join(log[-n:]) if log else "(no output yet)"


# ─── BOT ─────────────────────────────────────────────────────────
bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True, num_threads=4)

# State machine per user:
#   {"view": "main"}                          → main menu
#   {"view": "bots", "bot_map": {...}}        → bot list
#   {"view": "bot", "bot_id": "..."}          → bot actions
#   {"view": "logs", "bot_id": "..."}         → logs viewer
#   {"view": "env",  "bot_id": "...", "env_delete_map": {...}}
#   {"view": "delete_confirm", "bot_id": "..."}
#   {"view": "await_env_kv", "bot_id": "...", "prev": "env"}
USER_STATES: Dict[int, Dict[str, Any]] = {}


# ═════════════════════════════════════════════════════════════════
#  VIEW RENDERERS (all use reply keyboards)
# ═════════════════════════════════════════════════════════════════
def view_main(chat_id: int, intro: Optional[str] = None) -> None:
    USER_STATES[chat_id] = {"view": "main"}
    bots = list_user_bots(chat_id)
    running = sum(1 for b in bots if b["_id"] in RUNNING
                  and RUNNING[b["_id"]]["proc"].poll() is None)
    intro_block = f"{intro}\n" if intro else ""
    text = (
        f"<b>{esc(BRAND)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{intro_block}"
        f"{sc('Welcome')}!\n"
        f"{bullet('Bots', len(bots))}\n"
        f"{bullet('Running', running)}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{sc('Choose an option below')}.{FOOTER}"
    )
    try:
        bot.send_message(chat_id, text, reply_markup=_main_rkb())
    except Exception as e:
        print(f"[view_main] {e}", file=sys.stderr)


def view_bots(chat_id: int) -> None:
    bots = list_user_bots(chat_id)
    bot_map: Dict[str, str] = {}
    rows: List[List[Tuple[str, Optional[str]]]] = []

    if bots:
        for b in sorted(bots, key=lambda x: x.get("name", "")):
            running = (b["_id"] in RUNNING
                       and RUNNING[b["_id"]]["proc"].poll() is None)
            mark = "▶" if running else "■"
            label = f"{mark}  {sc(b['name'])[:30]}"
            if label in bot_map:
                label = f"{mark}  {sc(b['name'])[:25]}_{b['_id'][:4]}"
            bot_map[label] = b["_id"]
            rows.append([(label, "success" if running else "primary")])
    rows.append([(RB_MAIN, "primary")])

    USER_STATES[chat_id] = {"view": "bots", "bot_map": bot_map}

    if not bots:
        text = (
            f"<b>▸ {sc('My Bots')}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<i>{sc('No bots yet')}.</i>\n"
            f"{sc('Tap Upload to begin')}.{FOOTER}"
        )
    else:
        text = (
            f"<b>▸ {sc('My Bots')}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{bullet('Total', len(bots))}\n"
            f"{sc('Tap a bot to manage')}.{FOOTER}"
        )
    try:
        bot.send_message(chat_id, text, reply_markup=_rkb(rows))
    except Exception as e:
        print(f"[view_bots] {e}", file=sys.stderr)


def view_upload(chat_id: int) -> None:
    USER_STATES[chat_id] = {"view": "main"}
    text = (
        f"<b>⊕ {sc('Upload Bot')}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{sc('Send your bot file as a document')}:\n"
        f"• <code>.py</code>  — {sc('Python bot')}\n"
        f"• <code>.js</code>  — {sc('Node bot')}\n"
        f"• <code>.zip</code> — {sc('Whole project')}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{sc('Entry detection')}: <code>bot.py</code>, "
        f"<code>main.py</code>, <code>index.js</code>.\n"
        f"{sc('Files are encrypted at rest')}.\n"
        f"{sc('Missing modules install automatically on crash')}.\n"
        f"{sc('Bot will auto-start after upload')}.{FOOTER}"
    )
    try:
        bot.send_message(chat_id, text, reply_markup=_main_rkb())
    except Exception as e:
        print(f"[view_upload] {e}", file=sys.stderr)


def view_help(chat_id: int) -> None:
    USER_STATES[chat_id] = {"view": "main"}
    text = (
        f"<b>? {sc('Help')}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{bullet('Upload', 'Send .py / .js / .zip')}\n"
        f"{bullet('Run', 'My Bots → tap bot → Start')}\n"
        f"{bullet('Logs', 'My Bots → tap bot → Live Logs')}\n"
        f"{bullet('Env', 'My Bots → tap bot → Env Vars')}\n"
        f"{bullet('Delete', 'My Bots → tap bot → Delete')}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{sc('Auto-restart')}: {sc('crashed bots restart automatically')}\n"
        f"{sc('Auto-install')}: {sc('missing pip/npm modules install on crash')}\n"
        f"{sc('Per-bot env vars')}: {sc('set BOT_TOKEN per bot')}.\n"
        f"{sc('Everything is 100% free')}.{FOOTER}"
    )
    try:
        bot.send_message(chat_id, text, reply_markup=_main_rkb())
    except Exception as e:
        print(f"[view_help] {e}", file=sys.stderr)


def view_bot(chat_id: int, bot_id: str) -> None:
    b = get_bot(bot_id)
    if not b:
        view_bots(chat_id); return
    USER_STATES[chat_id] = {"view": "bot", "bot_id": bot_id}

    info = RUNNING.get(bot_id)
    running = bool(info and info["proc"].poll() is None)
    crashed = b.get("last_exit_code") not in (None, 0)
    status = "▶ Running" if running else ("💥 Crashed" if crashed else "■ Stopped")
    uptime = fmt_dur(int(time.time() * 1000 - info["started"])) if running else "—"

    total = 0
    bot_dir = Path(b["dir"])
    if bot_dir.exists():
        for root, _, files in os.walk(bot_dir):
            for f in files:
                try:
                    total += (Path(root) / f).stat().st_size
                except OSError:
                    pass

    text = (
        f"<b>{sc('Bot')}: {esc(b['name'])}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{bullet('Status', status)}\n"
        f"{bullet('Uptime', uptime)}\n"
        f"{bullet('Files', len(b.get('enc_files', [])))}\n"
        f"{bullet('Size', fmt_bytes(total))}\n"
    )
    auto = b.get("auto_installed") or []
    if auto:
        text += f"{bullet('Auto-installed', ', '.join(auto[:4]))}\n"
    if not running and b.get("last_error"):
        text += (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>Last error:</b>\n"
            f"<pre>{esc(b['last_error'][:600])}</pre>"
        )
    text += FOOTER

    rows: List[List[Tuple[str, Optional[str]]]] = []
    if running:
        rows.append([(RB_STOP, "danger"), (RB_RESTART, "primary")])
    else:
        rows.append([(RB_START, "success"), (RB_RESTART, "primary")])
    rows.append([(RB_LOGS, "primary"), (RB_ENV, "primary")])
    rows.append([(RB_DELETE, "danger")])
    rows.append([(RB_MY_BOTS, "primary"), (RB_MAIN, "primary")])

    try:
        bot.send_message(chat_id, text, reply_markup=_rkb(rows))
    except Exception as e:
        print(f"[view_bot] {e}", file=sys.stderr)


def view_env(chat_id: int, bot_id: str) -> None:
    b = get_bot(bot_id)
    if not b:
        view_bots(chat_id); return

    env = b.get("env") or {}
    env_delete_map: Dict[str, str] = {}

    USER_STATES[chat_id] = {
        "view": "env",
        "bot_id": bot_id,
        "env_delete_map": env_delete_map,
    }

    rows_text = "\n".join(
        f"• <code>{esc(k)}</code> = <code>{esc(str(v)[:40])}</code>"
        for k, v in env.items()
    ) or f"<i>{sc('No vars yet')}</i>"

    text = (
        f"<b>✎ {sc('Env Vars')}</b> — {esc(b['name'])}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{rows_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{sc('Tap Add Variable to create one')}.\n"
        f"{sc('Tap a ✖ button to delete a var')}.\n"
        f"{sc('Restart bot after changes')}.{FOOTER}"
    )

    rows: List[List[Tuple[str, Optional[str]]]] = [[(RB_ADD_VAR, "success")]]
    for k in env:
        label = f"✖  {k}"
        env_delete_map[label] = k
        rows.append([(label, "danger")])
    rows.append([(RB_BACK, "primary")])

    try:
        bot.send_message(chat_id, text, reply_markup=_rkb(rows))
    except Exception as e:
        print(f"[view_env] {e}", file=sys.stderr)


def view_logs(chat_id: int, bot_id: str) -> None:
    b = get_bot(bot_id)
    if not b:
        view_bots(chat_id); return
    USER_STATES[chat_id] = {"view": "logs", "bot_id": bot_id}
    logs = tail_log(bot_id, n=60)
    text = (
        f"<b>▸ {sc('Live Logs')}</b> — {esc(b['name'])}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<pre>{esc(logs[-3500:])}</pre>"
        f"━━━━━━━━━━━━━━━━━━{FOOTER}"
    )
    rows = [[(RB_REFRESH, "primary"), (RB_BACK, "success")]]
    try:
        bot.send_message(chat_id, text, reply_markup=_rkb(rows))
    except Exception as e:
        print(f"[view_logs] {e}", file=sys.stderr)


def view_delete_confirm(chat_id: int, bot_id: str) -> None:
    b = get_bot(bot_id)
    if not b:
        view_bots(chat_id); return
    USER_STATES[chat_id] = {"view": "delete_confirm", "bot_id": bot_id}
    text = (
        f"⚠ {sc('Confirm delete')}: <b>{esc(b['name'])}</b>?\n"
        f"{sc('This cannot be undone')}.{FOOTER}"
    )
    rows = [[(RB_YES_DEL, "danger"), (RB_CANCEL, "success")]]
    try:
        bot.send_message(chat_id, text, reply_markup=_rkb(rows))
    except Exception as e:
        print(f"[view_delete_confirm] {e}", file=sys.stderr)


# ─── OWNER AUTO-CLAIM ────────────────────────────────────────────
def _claim_owner(uid: int) -> None:
    global OWNER_ID
    if OWNER_ID == 0:
        OWNER_ID = uid
        try:
            (BASE_DIR / "owner_id.txt").write_text(str(uid), encoding="utf-8")
        except Exception:
            pass
        print(f"[owner] auto-claimed by {uid}", flush=True)


# ═════════════════════════════════════════════════════════════════
#  HANDLERS
# ═════════════════════════════════════════════════════════════════
@bot.message_handler(commands=["start", "menu"])
def cmd_start(m: types.Message) -> None:
    if m.chat.type != "private":
        return
    _claim_owner(m.from_user.id)
    view_main(m.chat.id,
              intro=f"Hello, <b>{esc(m.from_user.first_name or 'friend')}</b>!")


@bot.message_handler(commands=["help"])
def cmd_help(m: types.Message) -> None:
    if m.chat.type != "private":
        return
    view_help(m.chat.id)


@bot.message_handler(commands=["cancel"])
def cmd_cancel(m: types.Message) -> None:
    if m.chat.type != "private":
        return
    st = USER_STATES.get(m.from_user.id) or {}
    if st.get("view") == "await_env_kv":
        bot_id = st.get("bot_id")
        if bot_id and get_bot(bot_id):
            view_env(m.chat.id, bot_id); return
    view_main(m.chat.id)


@bot.message_handler(content_types=["document"])
def on_doc(m: types.Message) -> None:
    if m.chat.type != "private":
        return
    doc = m.document
    fname = doc.file_name or ""
    ext = Path(fname).suffix.lower()
    if ext not in (".py", ".js", ".zip"):
        bot.reply_to(m, f"✖ {sc('Only .py, .js, .zip allowed')}")
        return
    if doc.file_size and doc.file_size > MAX_UPLOAD:
        bot.reply_to(m, f"✖ {sc('Too big')} (>{MAX_UPLOAD // (1024 * 1024)} MB)")
        return
    status = bot.reply_to(m, f"⏳ {sc('Downloading')} {esc(fname)}…")
    try:
        file_info = bot.get_file(doc.file_id)
        raw = bot.download_file(file_info.file_path)
    except Exception as e:
        try:
            bot.edit_message_text(f"✖ {sc('Download failed')}: <code>{esc(e)}</code>",
                                   m.chat.id, status.message_id)
        except Exception:
            pass
        return

    bot_id = secrets.token_hex(8)
    bot_dir = SANDBOX / f"{m.from_user.id}_{bot_id}"
    bot_dir.mkdir(parents=True, exist_ok=True)
    name = safe_name(Path(fname).stem)
    doc_db = {
        "_id": bot_id,
        "owner": m.from_user.id,
        "name": name,
        "dir": str(bot_dir),
        "created": ts_iso(),
        "enc_files": [],
        "env": {},
        "status": "stopped",
        "auto_installed": [],
    }

    files: List[Tuple[str, bytes]] = []
    if ext == ".zip":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                extracted_size = 0
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    rel = member.filename.replace("\\", "/")
                    if rel.startswith("/") or ".." in rel.split("/"):
                        continue
                    if member.file_size and member.file_size > MAX_UPLOAD:
                        continue
                    try:
                        safe_join(bot_dir, rel)
                    except ValueError:
                        continue
                    content = zf.read(member)
                    extracted_size += len(content)
                    if extracted_size > MAX_UPLOAD * 3:
                        raise ValueError("zip too large when extracted")
                    files.append((rel, content))
        except (zipfile.BadZipFile, ValueError) as e:
            rmrf(bot_dir)
            try:
                bot.edit_message_text(f"✖ {sc('Invalid zip')}: <code>{esc(e)}</code>",
                                       m.chat.id, status.message_id)
            except Exception:
                pass
            return
    else:
        files.append((fname, raw))

    if not files:
        rmrf(bot_dir)
        try:
            bot.edit_message_text(f"✖ {sc('No files in upload')}",
                                   m.chat.id, status.message_id)
        except Exception:
            pass
        return

    total = 0
    try:
        for rel, content in files:
            meta = encrypt_and_store(m.from_user.id, rel, content)
            meta["rel_path"] = rel
            doc_db["enc_files"].append(meta)
            total += len(content)
    except Exception as e:
        rmrf(bot_dir)
        try:
            bot.edit_message_text(f"✖ {sc('Encrypt failed')}: <code>{esc(e)}</code>",
                                   m.chat.id, status.message_id)
        except Exception:
            pass
        return

    save_bot(doc_db)
    try:
        bot.edit_message_text(
            f"✓ {sc('Bot stored')}: {esc(name)}\n"
            f"{bullet('Files', len(files))}\n"
            f"{bullet('Size', fmt_bytes(total))}\n"
            f"⏳ {sc('Starting')}…",
            m.chat.id, status.message_id,
        )
    except Exception:
        pass

    def _start():
        time.sleep(1)
        res = start_bot(bot_id)
        if res.get("ok"):
            view_bot(m.chat.id, bot_id)
        else:
            view_main(m.chat.id)
            try:
                bot.send_message(
                    m.chat.id,
                    f"⚠ {sc('Stored but failed to start')}:\n"
                    f"<code>{esc(res.get('error', '?'))}</code>",
                )
            except Exception:
                pass
    threading.Thread(target=_start, daemon=True).start()


@bot.message_handler(content_types=["text"])
def on_text(m: types.Message) -> None:
    if m.chat.type != "private":
        return
    uid = m.from_user.id
    text = (m.text or "").strip()

    # Ignore slash commands (handled above)
    if text.startswith("/"):
        return

    st = USER_STATES.get(uid) or {}
    view = st.get("view", "main")

    # ─── Env var input flow (highest priority) ─────────────
    if view == "await_env_kv":
        bot_id = st.get("bot_id", "")
        if text == RB_CANCEL:
            if bot_id and get_bot(bot_id):
                view_env(uid, bot_id)
            else:
                view_main(uid)
            return
        if "=" not in text:
            bot.send_message(uid,
                             f"✖ {sc('Format')}: <code>KEY=VALUE</code>",
                             reply_markup=_rkb([[(RB_CANCEL, "danger")]]))
            return
        k, v = text.split("=", 1)
        k, v = k.strip(), v.strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k):
            bot.send_message(uid, f"✖ {sc('Invalid key')}",
                             reply_markup=_rkb([[(RB_CANCEL, "danger")]]))
            return
        b = get_bot(bot_id)
        if not b:
            view_main(uid); return
        env = b.get("env") or {}
        env[k] = v
        b["env"] = env
        save_bot(b)
        view_env(uid, bot_id)
        return

    # ─── Global navigation (any view) ──────────────────────
    if text == RB_MAIN:
        view_main(uid); return
    if text == RB_MY_BOTS:
        view_bots(uid); return
    if text == RB_UPLOAD:
        view_upload(uid); return
    if text == RB_HELP:
        view_help(uid); return

    # ─── View-specific routing ─────────────────────────────
    if view == "main":
        if text == RB_REFRESH:
            view_main(uid); return

    elif view == "bots":
        bot_map = st.get("bot_map") or {}
        if text in bot_map:
            view_bot(uid, bot_map[text]); return

    elif view == "bot":
        bot_id = st.get("bot_id", "")
        if not bot_id or not get_bot(bot_id):
            view_bots(uid); return
        if text == RB_START:
            try:
                bot.send_message(uid, f"⏳ {sc('Starting')}…")
                start_bot(bot_id)
            finally:
                view_bot(uid, bot_id)
            return
        if text == RB_STOP:
            try:
                bot.send_message(uid, f"⏳ {sc('Stopping')}…")
                stop_bot(bot_id, manual=True)
            finally:
                view_bot(uid, bot_id)
            return
        if text == RB_RESTART:
            try:
                bot.send_message(uid, f"⏳ {sc('Restarting')}…")
                restart_bot(bot_id)
            finally:
                view_bot(uid, bot_id)
            return
        if text == RB_LOGS:
            view_logs(uid, bot_id); return
        if text == RB_ENV:
            view_env(uid, bot_id); return
        if text == RB_DELETE:
            view_delete_confirm(uid, bot_id); return

    elif view == "logs":
        bot_id = st.get("bot_id", "")
        if not bot_id or not get_bot(bot_id):
            view_bots(uid); return
        if text == RB_REFRESH:
            view_logs(uid, bot_id); return
        if text == RB_BACK:
            view_bot(uid, bot_id); return

    elif view == "env":
        bot_id = st.get("bot_id", "")
        if not bot_id or not get_bot(bot_id):
            view_bots(uid); return
        if text == RB_ADD_VAR:
            USER_STATES[uid] = {
                "view": "await_env_kv",
                "bot_id": bot_id,
                "prev": "env",
            }
            bot.send_message(
                uid,
                f"✎ {sc('Send env var')}: <code>KEY=VALUE</code>\n"
                f"{sc('Tap Cancel to abort')}.",
                reply_markup=_rkb([[(RB_CANCEL, "danger")]]),
            )
            return
        if text == RB_BACK:
            view_bot(uid, bot_id); return
        delete_map = st.get("env_delete_map") or {}
        if text in delete_map:
            key = delete_map[text]
            b = get_bot(bot_id)
            if b:
                env = b.get("env") or {}
                env.pop(key, None)
                b["env"] = env
                save_bot(b)
            view_env(uid, bot_id); return

    elif view == "delete_confirm":
        bot_id = st.get("bot_id", "")
        if text == RB_YES_DEL:
            b = get_bot(bot_id)
            if b:
                stop_bot(bot_id, manual=True)
                for f in b.get("enc_files", []):
                    try:
                        Path(f["enc_path"]).unlink(missing_ok=True)
                    except Exception:
                        pass
                    wipe_key(f["key_id"])
                rmrf(b.get("dir", ""))
                delete_bot_doc(bot_id)
            view_bots(uid); return
        if text == RB_CANCEL:
            if bot_id and get_bot(bot_id):
                view_bot(uid, bot_id)
            else:
                view_bots(uid)
            return

    # Fallback — unknown text, show main menu
    view_main(uid)


# ─── LEGACY CALLBACK HANDLER (old inline buttons) ──────────────
@bot.callback_query_handler(func=lambda c: True)
def on_legacy_cb(call: types.CallbackQuery) -> None:
    """Old inline buttons from previous deployments — guide user to reply keyboard."""
    try:
        bot.answer_callback_query(
            call.id,
            "Use the reply keyboard buttons below 👇",
            show_alert=True,
        )
    except Exception:
        pass


# ─── KEEPALIVE ───────────────────────────────────────────────────
app = Flask(__name__)


@app.route("/")
def home():
    return jsonify({"ok": True, "brand": BRAND, "bots": len(RUNNING)})


@app.route("/health")
def health():
    return jsonify({"status": "alive"})


def start_keepalive() -> None:
    def _run():
        try:
            app.run(host="0.0.0.0", port=KEEPALIVE_PORT,
                    debug=False, use_reloader=False)
        except Exception as e:
            print(f"[keepalive] {e}", file=sys.stderr)
    threading.Thread(target=_run, daemon=True).start()


# ─── MAIN ────────────────────────────────────────────────────────
def main() -> int:
    print("=" * 60)
    print(f"   {BRAND} — Free Edition")
    print(f"   port:   {KEEPALIVE_PORT}")
    print(f"   owner:  {OWNER_ID or '(auto-claim on /start)'}")
    print(f"   token:  ...{TOKEN[-6:] if len(TOKEN) > 6 else '?'}")
    print("=" * 60)

    start_keepalive()

    try:
        bot.remove_webhook()
        try:
            bot.delete_webhook(drop_pending_updates=True)
        except Exception:
            pass
    except Exception:
        pass

    try:
        bot.set_my_commands([
            types.BotCommand("start", "open main menu"),
            types.BotCommand("menu", "main menu"),
            types.BotCommand("help", "help"),
            types.BotCommand("cancel", "cancel current action"),
        ])
    except Exception:
        pass

    try:
        me = bot.get_me()
        print(f"[bot] @{me.username} ready", flush=True)
    except Exception:
        pass

    for b in db_load()["bots"].values():
        if b.get("status") == "running":
            threading.Thread(target=start_bot, args=(b["_id"],),
                             daemon=True).start()

    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID,
                             f"✓ <b>{esc(BRAND)}</b> online — {sc('free edition')}")
        except Exception:
            pass

    print("[bot] polling…", flush=True)
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30,
                                 long_polling_timeout=25)
        except KeyboardInterrupt:
            print("\n[bot] stopping…", flush=True)
            for bid in list(RUNNING.keys()):
                stop_bot(bid, manual=False)
            return 0
        except Exception as e:
            print(f"[bot] poll error: {e}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
