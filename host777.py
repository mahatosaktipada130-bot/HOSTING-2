from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import os
import random
import re
import secrets
import shutil
import signal
import string
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import traceback
import zipfile
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

_REQUIRED_PKGS = [
    ("telebot",             "pyTelegramBotAPI"),
    ("requests",            "requests"),
    ("cryptography.fernet", "cryptography"),
    ("flask",               "flask"),
    ("psutil",              "psutil"),
]

def _auto_install_missing() -> None:
    import importlib
    missing: List[str] = []
    for mod, pip_name in _REQUIRED_PKGS:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pip_name)
    if not missing:
        return
    print(f"[setup] installing: {', '.join(missing)}")
    strategies = [
        [sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", *missing],
        [sys.executable, "-m", "pip", "install", "--upgrade", "--quiet",
         "--break-system-packages", *missing],
    ]
    for cmd in strategies:
        try:
            subprocess.run(cmd, check=True)
            return
        except Exception:
            continue
    sys.exit(f"[x] auto-install failed. Run: pip install {' '.join(missing)}")

_auto_install_missing()

import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException
import requests
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, jsonify

try:
    import psutil
except ImportError:
    psutil = None

# ═════════════════════════════════════════════════════════════════
#  CONFIG
# ═════════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).resolve().parent

DIRS: Dict[str, Path] = {
    "encfiles": BASE_DIR / "storage" / "encfiles",
    "data":     BASE_DIR / "storage" / "data",
    "sandbox":  BASE_DIR / "sandbox",
    "tickets":  BASE_DIR / "storage" / "tickets",
}
for _p in DIRS.values():
    _p.mkdir(parents=True, exist_ok=True)

DB_FILE       = DIRS["data"] / "panel_db.json"
SETTINGS_FILE = DIRS["data"] / "panel_settings.json"
AUDIT_FILE    = DIRS["data"] / "audit.log"

# ⚠️ SECURITY: Token code se hata diya gaya hai. 
# Railway ke Variables tab mein BOT_TOKEN zaroor daalein!
BOT_TOKEN_HARDCODED = "8600557449:AAHDXGopfKT0_sWFV9mTDXn5SIfugbzBHLU"
TOKEN = (
    os.environ.get("BOT_TOKEN")
    or os.environ.get("MAIN_BOT_TOKEN")
    or os.environ.get("TELEGRAM_BOT_TOKEN")
    or BOT_TOKEN_HARDCODED
    or ""
).strip()

try:
    OWNER_ID = int(os.environ.get("8662511212", "8662511212"))
except (TypeError, ValueError):
    OWNER_ID = 8662511212

if not TOKEN or TOKEN == "BOT_TOKEN":
    sys.exit("BOT_TOKEN missing. Set BOT_TOKEN env var in Railway Variables.")

# 🟢 PORT FIX: 3000 hardcoded taaki Railway ka 8080 conflict na kare
KEEPALIVE_PORT = 3000

BRAND     = "Hᴏꜱᴛɪɴɢ Bᴏᴛ"
BRAND_VER = "v3.0"
BRAND_TAG = f"{BRAND} {BRAND_VER}"

PLAN_LIMITS: Dict[str, Dict[str, Any]] = {
    "free":       {"name": "Free",       "max_bots": 1,  "ram": 128,  "auto_restart": False, "price": 0,    "days": 0},
    "starter":    {"name": "Starter",    "max_bots": 2,  "ram": 256,  "auto_restart": True,  "price": 99,   "days": 30},
    "basic":      {"name": "Basic",      "max_bots": 4,  "ram": 512,  "auto_restart": True,  "price": 199,  "days": 30},
    "pro":        {"name": "Pro",        "max_bots": 8,  "ram": 1024, "auto_restart": True,  "price": 499,  "days": 30},
    "lifetime":   {"name": "Lifetime",   "max_bots": 15, "ram": 2048, "auto_restart": True,  "price": 1999, "days": 36500},
}

PAYMENT_METHODS: Dict[str, Dict[str, Any]] = {
    "bkash":   {"name": "bKash",       "number": "01306633616",          "type": "Send Money",       "tag": "[B]"},
    "nagad":   {"name": "Nagad",       "number": "01306633616",          "type": "Send Money",       "tag": "[N]"},
    "rocket":  {"name": "Rocket",      "number": "01306633616",          "type": "Send Money",       "tag": "[R]"},
    "binance": {"name": "Binance Pay", "number": "Binance ID 758637628", "type": "USDT (BEP20/TRC20)","tag": "[BP]"},
}

SECRET_ENV_NAMES = {
    "BOT_TOKEN", "OWNER_ID", "ERROR_BOT_TOKEN",
    "MONGO_URL", "GITHUB_TOKEN", "GITHUB_REPO", "GITHUB_BRANCH",
    "OWNER_IDS", "SESSION_SECRET",
    "DATABASE_URL", "PGDATABASE", "PGHOST", "PGPORT", "PGUSER", "PGPASSWORD",
    "REPLIT_DB_URL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY",
}

ENTRY_NODE = ("index.js", "bot.js", "main.js", "app.js")
ENTRY_PY   = ("bot.py", "main.py", "app.py", "run.py")
LOG_RING   = 200
MAX_LOG_SEND = 50
MAX_UPLOAD_BYTES = 75 * 1024 * 1024

G = {
    "ok": "✓", "no": "✘", "warn": "⚠", "arrow": "→", "bullet": "•",
    "div": "━" * 16, "div_eq": "═" * 16,
    "play": "▶", "stop": "■", "refresh": "↻",
    "shield": "◇", "key": "❖", "trash": "✖",
    "diamond": "◆", "star": "★", "wallet": "◇",
    "user": "◆", "users": "◎", "ticket": "✿", "back": "↲",
    "plus": "⊕", "eye": "◉", "cog": "⚙", "lock": "▣",
    "cloud": "☁", "folder": "▸", "upload": "▴", "download": "▾",
    "bolt": "⚡", "broadcast": "⚑", "graph": "▪",
    "crown": "♔", "spark": "✦", "cog2": "⚙",
}

def sc(text: Any) -> str:
    """Small-caps a-z only."""
    _MAP = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘQʀꜱᴛᴜᴠᴡxʏᴢ")
    return str(text).translate(_MAP)

def esc(s: Any = "") -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def bullet(label: str, value: Any, glyph: str = "•") -> str:
    return f"{glyph}  <b>{esc(label)}</b>: <code>{esc(value)}</code>"

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def ts_iso() -> str:
    return now_utc().isoformat()

def safe_name(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", s or "").strip("_")
    return (s or "bot")[:48]

def fmt_bytes(n: float) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"

def fmt_dur(ms: int) -> str:
    if ms is None or ms < 0:
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

def fmt_ts(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(iso)

def rmrf(p: str | Path) -> None:
    try:
        shutil.rmtree(p, ignore_errors=True)
    except Exception:
        pass

def rand_token(n: int = 8) -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(n))

def safe_path_join(root: Path, *parts: str) -> Path:
    final = (root / Path(*parts)).resolve()
    rootp = root.resolve()
    if rootp not in final.parents and final != rootp:
        raise ValueError("path traversal detected")
    return final

# ═════════════════════════════════════════════════════════════════
#  DB (atomic writes, RLock)
# ═════════════════════════════════════════════════════════════════

_db_lock = threading.RLock()

def _atomic_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    try:
        tmp.replace(path)
    except OSError:
        shutil.copyfile(str(tmp), str(path))
        tmp.unlink(missing_ok=True)

def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        try: path.replace(path.with_suffix(".corrupt"))
        except Exception: pass
        return default

_DB_CACHE: Dict[str, Tuple[float, Any]] = {}

def _cached_load_ro(path: Path, default: Any) -> Any:
    key = str(path)
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        mtime = 0.0
    cached = _DB_CACHE.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    d = _load_json(path, default)
    _DB_CACHE[key] = (mtime, d)
    return d

def _cached_load(path: Path, default: Any) -> Any:
    return copy.deepcopy(_cached_load_ro(path, default))

def _cache_invalidate(path: Path) -> None:
    _DB_CACHE.pop(str(path), None)

_DB_DEFAULT_KEYS: Tuple[Tuple[str, Any], ...] = (
    ("users", {}),
    ("bots", {}),
    ("payments", []),
    ("admins", {}),
    ("audit", []),
    ("tickets", {}),
    ("scan_log", []),
)

def _ensure_db_defaults(d: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in _DB_DEFAULT_KEYS:
        if k not in d:
            d[k] = copy.deepcopy(v) if isinstance(v, (dict, list)) else v
    return d

def db_load() -> Dict[str, Any]:
    with _db_lock:
        d = _cached_load(DB_FILE, {})
    return _ensure_db_defaults(d)

def db_load_ro() -> Dict[str, Any]:
    with _db_lock:
        d = _cached_load_ro(DB_FILE, {})
    return _ensure_db_defaults(d)

def db_save(d: Dict[str, Any]) -> None:
    with _db_lock:
        _atomic_write(DB_FILE, d)
        _cache_invalidate(DB_FILE)

def settings_load() -> Dict[str, Any]:
    with _db_lock:
        return _cached_load(SETTINGS_FILE, {})

def settings_load_ro() -> Dict[str, Any]:
    with _db_lock:
        return _cached_load_ro(SETTINGS_FILE, {})

def settings_save(d: Dict[str, Any]) -> None:
    with _db_lock:
        _atomic_write(SETTINGS_FILE, d)
        _cache_invalidate(SETTINGS_FILE)

def get_setting(key: str, default: Any = None) -> Any:
    return settings_load_ro().get(key, default)

def set_setting(key: str, value: Any) -> None:
    s = settings_load()
    s[key] = value
    settings_save(s)

def cache_clear_all() -> None:
    with _db_lock:
        _DB_CACHE.clear()

# ═════════════════════════════════════════════════════════════════
#  PERMISSIONS
# ═════════════════════════════════════════════════════════════════

def is_owner(uid: int) -> bool:
    return int(uid) == OWNER_ID and OWNER_ID > 0

def is_admin(uid: int) -> bool:
    if is_owner(uid):
        return True
    return str(uid) in db_load_ro().get("admins", {})

def admin_role(uid: int) -> str:
    if is_owner(uid):
        return "owner"
    return db_load_ro().get("admins", {}).get(str(uid), {}).get("role", "")

def admin_can(uid: int, action: str) -> bool:
    role = admin_role(uid)
    if role == "owner":
        return True
    if role == "full-access":
        return action != "manage_admins"
    if role == "manage-users":
        return action in {"view_stats", "view_users", "find_user", "ban_user",
                          "give_plan", "approve_payment", "reply_ticket"}
    if role == "view-only":
        return action in {"view_stats", "view_users", "find_user"}
    return False

def audit(uid: int, action: str, detail: str = "") -> None:
    line = f"[{ts_iso()}] uid={uid} action={action} {detail}\n"
    try:
        with AUDIT_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    with _db_lock:
        d = db_load()
        d["audit"].append({"ts": ts_iso(), "uid": uid, "action": action, "detail": detail})
        d["audit"] = d["audit"][-500:]
        db_save(d)

# ═════════════════════════════════════════════════════════════════
#  ENCRYPTION  +  KEYRING
# ═════════════════════════════════════════════════════════════════

class KeyRing:
    def __init__(self) -> None:
        self._mem: Dict[str, bytes] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _gh_token() -> str:
        return (os.environ.get("GITHUB_TOKEN") or get_setting("github_token", "") or "").strip()

    @staticmethod
    def _gh_key_repo() -> str:
        return (os.environ.get("GITHUB_REPO") or get_setting("github_repo", "") or "").strip()

    def gh_enabled(self) -> bool:
        return bool(self._gh_token() and "/" in self._gh_key_repo())

    def _gh_request(self, method: str, path: str, **kw) -> Optional[requests.Response]:
        if not self.gh_enabled():
            return None
        url = f"https://api.github.com/repos/{self._gh_key_repo()}/{path.lstrip('/')}"
        h = kw.pop("headers", {}) or {}
        h.setdefault("Authorization", f"token {self._gh_token()}")
        h.setdefault("Accept", "application/vnd.github+json")
        h.setdefault("User-Agent", "hosting-bot/3.0")
        try:
            return requests.request(method, url, headers=h, timeout=30, **kw)
        except Exception:
            return None

    def new_key(self) -> bytes:
        return Fernet.generate_key()

    def store(self, key_id: str, key: bytes, meta: Dict[str, Any]) -> bool:
        with self._lock:
            self._mem[key_id] = key
        self._cache_local(key_id, key)
        if not self.gh_enabled():
            return True
        body = {"key": key.decode(), "meta": meta, "ts": ts_iso()}
        payload = json.dumps(body, indent=2).encode()
        gh_path = f"keys/{key_id}.json"
        sha: Optional[str] = None
        r = self._gh_request("GET", f"contents/{gh_path}")
        if r is not None and r.status_code == 200:
            try: sha = r.json().get("sha")
            except Exception: pass
        put_body: Dict[str, Any] = {
            "message": f"key {key_id} stored {ts_iso()}",
            "content": base64.b64encode(payload).decode(),
        }
        if sha: put_body["sha"] = sha
        r2 = self._gh_request("PUT", f"contents/{gh_path}", json=put_body)
        return r2 is not None and r2.status_code in (200, 201)

    def fetch(self, key_id: str) -> Optional[bytes]:
        with self._lock:
            cached = self._mem.get(key_id)
        if cached:
            return cached
        if self.gh_enabled():
            r = self._gh_request("GET", f"contents/keys/{key_id}.json")
            if r is not None and r.status_code == 200:
                try:
                    raw = base64.b64decode(r.json()["content"])
                    blob = json.loads(raw.decode())
                    key = blob["key"].encode()
                    with self._lock:
                        self._mem[key_id] = key
                    return key
                except Exception:
                    pass
        return self._uncache_local(key_id)

    def wipe(self, key_id: str) -> None:
        with self._lock:
            self._mem.pop(key_id, None)

    def _local_master(self) -> bytes:
        material = f"{TOKEN}|{OWNER_ID}".encode()
        digest = hashlib.sha256(material).digest()
        return base64.urlsafe_b64encode(digest)

    def _cache_local(self, key_id: str, key: bytes) -> None:
        try:
            d = DIRS["data"] / "keycache"
            d.mkdir(parents=True, exist_ok=True)
            f = Fernet(self._local_master())
            (d / f"{key_id}.bin").write_bytes(f.encrypt(key))
        except Exception:
            pass

    def _uncache_local(self, key_id: str) -> Optional[bytes]:
        p = DIRS["data"] / "keycache" / f"{key_id}.bin"
        if not p.exists():
            return None
        try:
            f = Fernet(self._local_master())
            key = f.decrypt(p.read_bytes())
            with self._lock:
                self._mem[key_id] = key
            return key
        except Exception:
            return None

KEYRING = KeyRing()

def encrypt_file(plain: bytes) -> Tuple[str, bytes, bytes]:
    key = KEYRING.new_key()
    f = Fernet(key)
    cipher = f.encrypt(plain)
    key_id = secrets.token_urlsafe(16)
    return key_id, key, cipher

def read_encrypted(path: Path, key: bytes) -> bytes:
    return Fernet(key).decrypt(path.read_bytes())

# ═════════════════════════════════════════════════════════════════
#  SECURITY SCANNER
# ═════════════════════════════════════════════════════════════════

_SEC_PATTERNS = {
    "🔴 Data Theft": [
        (r'os\.walk\s*\(\s*["\'][/\\](?:root|home|etc|var|proc)["\']', "Root/system directory walk"),
        (r'send_document\s*\(.*open\s*\(\s*["\'][/\\](?:root|etc|proc|sys)', "System file exfil"),
        (r'zipfile\.ZipFile.*["\']w["\'].*\bos\.walk\b.*["\'][/\\](?:root|etc|home)', "System zip"),
        (r'glob\.glob\s*\(["\'][/\\]\*', "Root glob"),
        (r'shutil\.copy.*["\'][/\\]root', "Copy from /root"),
        (r'ROOT_DIR\s*=\s*["\'][/\\]["\']', "Targets root"),
    ],
    "🔴 Backdoor": [
        (r'subprocess\s*\.\s*(?:Popen|call|run)\s*\([^\n]*shell\s*=\s*True[^\n]*(?:input|stdin)', "Shell injection"),
        (r'marshal\.loads\s*\(', "Marshalled bytecode"),
    ],
    "🟡 Obfuscation": [
        (r'base64\.b64decode\s*\(.*\)\s*[\)\s]*\bexec\b', "Base64 + exec"),
        (r'(?:\\x[0-9a-fA-F]{2}){6,}', "Long hex string"),
    ],
    "🟡 Suspicious Network": [
        (r'devil-api\.com|elementfx\.io', "Known malicious endpoint"),
        (r'open\s*\(\s*["\'][/\\](?:root|etc|proc|sys).*(?:requests|urllib).*(?:post|put)', "System file POST"),
        (r'pastebin\.com/raw', "Pastebin raw"),
    ],
    "🟠 Resource Abuse": [
        (r'multiprocessing\.Pool\s*\(\s*(?:None|\d{3,})', "Massive pool"),
        (r'fork\s*\(\s*\).*fork\s*\(', "Fork bomb"),
    ],
}

_SEC_TOKEN_RE = re.compile(r'\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b')

def _sec_static_scan(code: str) -> dict:
    results: Dict[str, List[str]] = {}
    for category, pattern_list in _SEC_PATTERNS.items():
        hits = []
        for pattern, description in pattern_list:
            if re.search(pattern, code, re.IGNORECASE | re.MULTILINE):
                hits.append(description)
        if hits:
            results[category] = hits
    tokens = _SEC_TOKEN_RE.findall(code)
    if tokens:
        results.setdefault("🔴 Exposed Credentials", [])
        results["🔴 Exposed Credentials"].append(f"Bot token: {tokens[0][:15]}...")
    return results

def _sec_ast_scan(code: str) -> List[str]:
    import ast as _ast
    findings: List[str] = []
    try:
        tree = _ast.parse(code)
    except SyntaxError as e:
        findings.append(f"Code parse failed: {e}")
        return findings
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call):
            func = node.func
            if isinstance(func, _ast.Attribute):
                if (func.attr == 'walk' and isinstance(func.value, _ast.Name)
                        and func.value.id == 'os' and node.args):
                    arg = node.args[0]
                    if isinstance(arg, _ast.Constant) and isinstance(arg.value, str):
                        if arg.value in ['/root', '/etc', '/home', '/proc']:
                            findings.append(f"os.walk('{arg.value}') — sensitive dir")
            if isinstance(func, _ast.Name) and func.id in ('eval', 'exec'):
                if node.args and isinstance(node.args[0], _ast.Call):
                    findings.append(f"Dangerous: {func.id}() dynamic exec")
            if isinstance(func, _ast.Name) and func.id == '__import__':
                if node.args and isinstance(node.args[0], _ast.Constant):
                    if node.args[0].value == 'os':
                        findings.append("Dynamic __import__('os')")
    return findings

def _sec_calculate_risk(static_findings: dict, ast_findings: List[str]) -> int:
    weights = {
        "🔴 Data Theft": 40, "🔴 Backdoor": 40, "🔴 Exposed Credentials": 10,
        "🟡 Suspicious Network": 12, "🟡 Obfuscation": 10, "🟠 Resource Abuse": 8,
    }
    score = sum(weights.get(cat, 5) * min(len(hits), 3)
                for cat, hits in static_findings.items() if hits)
    unique_ast = list(dict.fromkeys(ast_findings))
    score += min(len(unique_ast) * 5, 20)
    return min(score, 100)

def _sec_get_verdict(risk_score: int, static_findings: dict) -> Tuple[str, str]:
    has_blocking = any(static_findings.get(c) for c in ("🔴 Data Theft", "🔴 Backdoor"))
    if has_blocking and risk_score >= 70:
        return "DANGEROUS", "REJECT"
    if risk_score >= 85:
        return "DANGEROUS", "REJECT"
    if has_blocking and risk_score >= 35:
        return "SUSPICIOUS", "MANUAL_REVIEW"
    if risk_score >= 55:
        return "SUSPICIOUS", "MANUAL_REVIEW"
    return "SAFE", "APPROVE"

def _sec_scan_code(code: str, filename: str = "file.py") -> dict:
    sf = _sec_static_scan(code)
    af = _sec_ast_scan(code)
    risk = _sec_calculate_risk(sf, af)
    verdict, recommendation = _sec_get_verdict(risk, sf)
    all_threats: List[str] = [f"{c}: {h}" for c, hits in sf.items() for h in hits] + af
    if verdict == "DANGEROUS":
        summary = f"⚠️ File DANGEROUS: {len(all_threats)} threats"
    elif verdict == "SUSPICIOUS":
        summary = "🔍 File suspicious — manual review needed"
    else:
        summary = "✅ File safe"
    return {"verdict": verdict, "risk_score": risk, "findings": sf,
            "ast_findings": af, "all_threats": all_threats,
            "recommendation": recommendation, "summary": summary, "filename": filename}

def _sec_scan_archive(file_path: str) -> dict:
    tmp = tempfile.mkdtemp()
    try:
        if file_path.endswith('.zip'):
            with zipfile.ZipFile(file_path, 'r') as z:
                for name in z.namelist():
                    if name.startswith('/') or '..' in name:
                        return {"verdict": "DANGEROUS", "risk_score": 99,
                                "findings": {"🔴 Zip Slip": ["Dangerous paths"]},
                                "ast_findings": [], "recommendation": "REJECT",
                                "summary": "Zip Slip!", "all_threats": []}
                z.extractall(tmp)
        py_files = list(Path(tmp).rglob("*.py"))
        if not py_files:
            return {"verdict": "SAFE", "risk_score": 0, "findings": {},
                    "ast_findings": [], "recommendation": "APPROVE",
                    "summary": "No Python files", "all_threats": []}
        worst = None
        for py_file in py_files[:10]:
            try:
                result = _sec_scan_code(py_file.read_text(errors='ignore'), py_file.name)
                if worst is None or result['risk_score'] > worst['risk_score']:
                    worst = result
            except Exception:
                continue
        return worst or {"verdict": "SAFE", "risk_score": 0, "recommendation": "APPROVE",
                         "summary": "Safe", "all_threats": []}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def _scan_file(file_path: str) -> dict:
    filename = os.path.basename(file_path)
    try:
        if filename.lower().endswith(('.zip', '.tar.gz', '.tgz', '.tar')):
            return _sec_scan_archive(file_path)
        elif filename.lower().endswith(('.py', '.js')):
            with open(file_path, 'r', errors='ignore') as _f:
                return _sec_scan_code(_f.read(), filename)
        else:
            return {"verdict": "SUSPICIOUS", "risk_score": 30,
                    "findings": {"🟡": [f"Unknown: {filename}"]},
                    "ast_findings": [], "recommendation": "MANUAL_REVIEW",
                    "summary": f"File type '{filename}' not allowed",
                    "all_threats": [], "filename": filename}
    except Exception as _e:
        return {"verdict": "ERROR", "risk_score": 50, "findings": {},
                "ast_findings": [], "recommendation": "MANUAL_REVIEW",
                "summary": f"Scan error: {_e}", "all_threats": [], "filename": filename}

def _run_security_scan(files_added: List[Tuple[str, bytes]],
                       uploader_uid: Optional[int] = None) -> Dict[str, Any]:
    tmp_dir = Path(tempfile.mkdtemp())
    worst: Optional[Dict[str, Any]] = None
    try:
        for rel, plain in files_added[:10]:
            safe_rel = Path(rel).name or "upload.bin"
            tmp_file = tmp_dir / safe_rel
            try:
                tmp_file.write_bytes(plain)
                result = _scan_file(str(tmp_file))
                if worst is None or result.get("risk_score", 0) > worst.get("risk_score", 0):
                    worst = result
            except Exception:
                continue
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)
    if worst is None:
        return {"recommendation": "APPROVE", "verdict": "SAFE",
                "risk_score": 0, "summary": "No scannable files", "all_threats": []}
    try:
        log_entry = {
            "ts": ts_iso(), "uid": str(uploader_uid or "?"),
            "filename": worst.get("filename", "?"),
            "verdict": worst.get("verdict", "UNKNOWN"),
            "risk_score": worst.get("risk_score", 0),
            "summary": (worst.get("summary", "") or "")[:200],
        }
        d = db_load()
        d["scan_log"].append(log_entry)
        d["scan_log"] = d["scan_log"][-500:]
        db_save(d)
    except Exception:
        pass
    return worst

# ═════════════════════════════════════════════════════════════════
#  BOT INSTANCE
# ═════════════════════════════════════════════════════════════════

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True, num_threads=8)
USER_STATES: Dict[int, Dict[str, Any]] = {}
START_TS = int(time.time() * 1000)

_ka = Flask(__name__)

@_ka.route("/")
def _ka_root() -> Any:
    return jsonify({"ok": True, "brand": BRAND_TAG,
                    "uptime_ms": int(time.time() * 1000) - START_TS,
                    "running_bots": len(RUNNING)})

@_ka.route("/health")
def _ka_health() -> Any:
    return jsonify({"status": "alive"})

def _start_keepalive() -> None:
    def _run() -> None:
        try:
            _ka.run(host="0.0.0.0", port=KEEPALIVE_PORT, debug=False, use_reloader=False)
        except Exception as e:
            print(f"[keepalive] {e}")
    threading.Thread(target=_run, daemon=True).start()

# ═════════════════════════════════════════════════════════════════
#  BOT RUNNER (subprocess, sandboxed env)
# ═════════════════════════════════════════════════════════════════

RUNNING: Dict[str, Dict[str, Any]] = {}
_runner_lock = threading.Lock()
_SKIP_DIR_PARTS = {".deps", "node_modules", ".tmp_run", "__pycache__",
                   ".git", "venv", ".venv", "env"}

def _iter_user_files(bot_dir: Path, suffix: str) -> List[Path]:
    out: List[Path] = []
    for p in bot_dir.rglob(f"*{suffix}"):
        if any(part in _SKIP_DIR_PARTS for part in p.parts):
            continue
        out.append(p)
    return sorted(out, key=lambda x: (len(x.parts), str(x)))

def detect_entry(bot_dir: Path) -> Tuple[Optional[str], Optional[str]]:
    for n in ENTRY_NODE:
        p = bot_dir / n
        if p.exists():
            return ("node", n)
    for n in ENTRY_PY:
        p = bot_dir / n
        if p.exists():
            return ("python", n)
    for n in ENTRY_PY:
        for p in _iter_user_files(bot_dir, ".py"):
            if p.name == n:
                return ("python", str(p.relative_to(bot_dir)))
    for n in ENTRY_NODE:
        for p in _iter_user_files(bot_dir, ".js"):
            if p.name == n:
                return ("node", str(p.relative_to(bot_dir)))
    py_files = _iter_user_files(bot_dir, ".py")
    if py_files:
        return ("python", str(py_files[0].relative_to(bot_dir)))
    js_files = _iter_user_files(bot_dir, ".js")
    if js_files:
        return ("node", str(js_files[0].relative_to(bot_dir)))
    zip_files = [p for p in bot_dir.rglob("*.zip")
                 if not any(part in _SKIP_DIR_PARTS for part in p.parts)]
    if zip_files:
        try:
            with zipfile.ZipFile(zip_files[0], "r") as z:
                z.extractall(bot_dir)
        except Exception:
            return (None, None)
        py_files = _iter_user_files(bot_dir, ".py")
        if py_files:
            return ("python", str(py_files[0].relative_to(bot_dir)))
        js_files = _iter_user_files(bot_dir, ".js")
        if js_files:
            return ("node", str(js_files[0].relative_to(bot_dir)))
    return (None, None)

def safe_env(bot_dir: Path, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV_NAMES}
    env["HOME"] = str(bot_dir)
    env["TMPDIR"] = str(bot_dir / ".tmp_run")
    env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    env.setdefault("NODE_ENV", "production")
    deps_dir = str(bot_dir / ".deps")
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{deps_dir}:{existing_pp}" if existing_pp else deps_dir
    Path(env["TMPDIR"]).mkdir(parents=True, exist_ok=True)
    Path(deps_dir).mkdir(parents=True, exist_ok=True)
    if extra:
        for k, v in extra.items():
            if k in SECRET_ENV_NAMES:
                continue
            env[str(k)] = str(v)
    return env

_PYPI_ALIAS: Dict[str, str] = {
    "telebot": "pyTelegramBotAPI", "telegram": "python-telegram-bot",
    "telethon": "Telethon", "pyrogram": "Pyrogram", "PIL": "Pillow",
    "cv2": "opencv-python", "bs4": "beautifulsoup4", "yaml": "PyYAML",
    "dotenv": "python-dotenv", "Crypto": "pycryptodome", "dateutil": "python-dateutil",
    "sklearn": "scikit-learn", "google": "google-api-python-client",
    "psycopg2": "psycopg2-binary", "discord": "discord.py", "aiogram": "aiogram",
    "fastapi": "fastapi", "starlette": "starlette", "redis": "redis",
    "pymongo": "pymongo", "motor": "motor", "schedule": "schedule",
    "github": "PyGithub", "requests": "requests", "aiohttp": "aiohttp",
    "httpx": "httpx", "nacl": "PyNaCl", "lxml": "lxml",
}

def _scan_imports(bot_dir: Path) -> List[str]:
    import ast as _ast
    found: set = set()
    for pyfile in bot_dir.rglob("*.py"):
        if ".deps" in pyfile.parts:
            continue
        try:
            tree = _ast.parse(pyfile.read_text(errors="ignore"))
        except Exception:
            continue
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                for n in node.names:
                    if n.name:
                        found.add(n.name.split(".")[0])
            elif isinstance(node, _ast.ImportFrom):
                if node.level and node.level > 0:
                    continue
                if node.module:
                    found.add(node.module.split(".")[0])
    return sorted(found)

def _filter_third_party(modules: List[str], bot_dir: Path) -> List[str]:
    import importlib.util as _ilu
    stdlib = set(getattr(sys, "stdlib_module_names", set()))
    skip = stdlib | {"__future__", ""}
    deps_dir = bot_dir / ".deps"
    for child in bot_dir.iterdir():
        if child == deps_dir:
            continue
        if child.suffix == ".py":
            skip.add(child.stem)
        elif child.is_dir() and (child / "__init__.py").exists():
            skip.add(child.name)
    deps_str = str(deps_dir)
    deps_in_path = deps_str in sys.path
    if deps_dir.exists() and not deps_in_path:
        sys.path.insert(0, deps_str)
    out: List[str] = []
    seen: set = set()
    try:
        for m in modules:
            if not m or m in skip:
                continue
            try:
                if _ilu.find_spec(m) is not None:
                    continue
            except (ImportError, ValueError):
                pass
            pip_name = _PYPI_ALIAS.get(m, m)
            if pip_name in seen:
                continue
            seen.add(pip_name)
            out.append(pip_name)
    finally:
        if deps_dir.exists() and not deps_in_path:
            try: sys.path.remove(deps_str)
            except ValueError: pass
    return out

def _pip_env(deps_dir: Path) -> Dict[str, str]:
    env = {**os.environ,
           "PIP_DISABLE_PIP_VERSION_CHECK": "1",
           "PIP_NO_INPUT": "1",
           "PIP_ROOT_USER_ACTION": "ignore"}
    env.pop("PYTHONUSERBASE", None)
    env.pop("PIP_USER", None)
    return env

_PIP_BASE_FLAGS = ["--upgrade", "--no-input", "--no-warn-script-location",
                   "--disable-pip-version-check"]

def install_deps(bot_dir: Path, kind: str, log: List[str]) -> bool:
    try:
        if kind == "python":
            deps_dir = bot_dir / ".deps"
            deps_dir.mkdir(parents=True, exist_ok=True)
            req = bot_dir / "requirements.txt"
            pip_env = _pip_env(deps_dir)
            if req.exists():
                log.append(f"{G['div']} pip (requirements.txt) {G['div']}")
                r = subprocess.run(
                    [sys.executable, "-m", "pip", "install",
                     "--target", str(deps_dir), *_PIP_BASE_FLAGS, "-r", str(req)],
                    cwd=str(bot_dir), timeout=600, capture_output=True, text=True, env=pip_env,
                )
                for line in (r.stdout or "").splitlines()[-10:]:
                    log.append(line)
                log.append(f"[{G['ok']}] requirements done (rc={r.returncode})")
            try:
                modules = _scan_imports(bot_dir)
                third_party = _filter_third_party(modules, bot_dir)
                if third_party:
                    log.append(f"{G['div']} auto-install {G['div']}")
                    log.append(f"📦 packages: {', '.join(third_party)}")
                    r2 = subprocess.run(
                        [sys.executable, "-m", "pip", "install",
                         "--target", str(deps_dir), *_PIP_BASE_FLAGS, *third_party],
                        cwd=str(bot_dir), timeout=600, capture_output=True, text=True, env=pip_env,
                    )
                    for line in (r2.stdout or "").splitlines()[-10:]:
                        log.append(line)
                    log.append(f"[{G['ok']}] auto-install done (rc={r2.returncode})")
            except Exception as e:
                log.append(f"[{G['warn']}] auto-install error: {e}")
            return True
        if kind == "node":
            pkg = bot_dir / "package.json"
            if not pkg.exists():
                return False
            if (bot_dir / "node_modules").exists():
                log.append(f"[{G['ok']}] node_modules cached")
                return False
            log.append(f"{G['div']} npm install {G['div']}")
            r = subprocess.run(
                ["npm", "install", "--omit=dev", "--no-audit", "--no-fund"],
                cwd=str(bot_dir), timeout=300, capture_output=True, text=True,
            )
            for line in (r.stdout or "").splitlines()[-10:]:
                log.append(line)
            log.append(f"[{G['ok']}] npm done (rc={r.returncode})")
            return True
    except subprocess.TimeoutExpired:
        log.append(f"[{G['warn']}] dependency timeout")
    except FileNotFoundError as e:
        log.append(f"[{G['warn']}] tool missing: {e}")
    except Exception as e:
        log.append(f"[{G['warn']}] install error: {e}")
    return False

def _drain_proc(bot_id: str, proc: subprocess.Popen, log: List[str]) -> None:
    try:
        if not proc.stdout:
            return
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
        log.append(f"{G['div']} process exited rc={rc} {G['div']}")
        info = RUNNING.get(bot_id)
        was_manual = (info is None) or info.get("manual_stop", False)
        b_doc = find_bot(bot_id)
        if b_doc is not None:
            tail = [ln for ln in log[-15:] if ln and not ln.startswith(G["div"])]
            b_doc["last_error"] = "\n".join(tail[-8:])[:1500]
            b_doc["last_exit_code"] = int(rc) if rc is not None else None
            b_doc["last_exit_at"] = ts_iso()
            if rc not in (0, None) and not was_manual:
                b_doc["status"] = "crashed"
            try: save_bot(b_doc)
            except Exception: pass
        if not info or not b_doc:
            return
        owner = db_load()["users"].get(str(b_doc["owner"]))
        plan = (owner or {}).get("plan", "free")
        if PLAN_LIMITS.get(plan, {}).get("auto_restart") and not was_manual:
            log.append(f"[{G['refresh']}] auto-restart in 3s...")
            time.sleep(3)
            start_child(b_doc)
    except Exception:
        pass

def start_child(b: Dict[str, Any]) -> Dict[str, Any]:
    bid = b["_id"]
    if (b or {}).get("approval_status") == "pending":
        return {"ok": False, "error": "Waiting for admin approval."}
    if (b or {}).get("approval_status") == "rejected":
        return {"ok": False, "error": "Bot rejected by admin."}
    with _runner_lock:
        existing = RUNNING.get(bid)
        if existing and existing["proc"].poll() is None:
            return {"ok": False, "error": "Already running."}
    bot_dir = Path(b["dir"])
    if not bot_dir.exists():
        return {"ok": False, "error": "Bot folder missing."}
    try:
        materialize_bot_files(b)
    except Exception as e:
        return {"ok": False, "error": f"decrypt failed: {e}"}
    kind, entry = detect_entry(bot_dir)
    if not kind:
        return {"ok": False, "error": "No entry file (bot.py / index.js)."}
    log: List[str] = [f"{G['div_eq']} START {ts_iso()} {G['div_eq']}"]
    install_deps(bot_dir, kind, log)
    cmd = ["node", entry] if kind == "node" else [sys.executable, "-u", entry]
    extra_env = b.get("env") or {}
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(bot_dir), env=safe_env(bot_dir, extra_env),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            preexec_fn=os.setsid if os.name == "posix" else None,
        )
    except Exception as e:
        return {"ok": False, "error": f"spawn: {e}"}
    info = {
        "proc": proc, "kind": kind, "started": time.time() * 1000,
        "log": log, "dir": str(bot_dir), "name": b["name"],
        "owner": b["owner"], "manual_stop": False,
    }
    with _runner_lock:
        RUNNING[bid] = info
    threading.Thread(target=_drain_proc, args=(bid, proc, log), daemon=True).start()

    def _wipe_source_files(bot_path: Path, wait_sec: float = 6.0) -> None:
        time.sleep(wait_sec)
        _ext = (".py", ".js", ".ts") if kind == "node" else (".py",)
        for _f in bot_path.iterdir():
            try:
                if _f.is_file() and _f.suffix in _ext and _f.name != "__init__.py":
                    _f.write_bytes(b"# sandboxed\n")
            except Exception:
                pass
    threading.Thread(target=_wipe_source_files, args=(bot_dir,), daemon=True).start()

    b["status"] = "running"
    b["last_started"] = ts_iso()
    b["last_error"] = ""
    b["last_exit_code"] = None
    save_bot(b)
    return {"ok": True, "pid": proc.pid, "kind": kind}

def stop_child(bot_id: str, manual: bool = True) -> Dict[str, Any]:
    with _runner_lock:
        info = RUNNING.get(bot_id)
    if not info:
        b = find_bot(bot_id)
        if b and b.get("status") != "stopped":
            b["status"] = "stopped"
            save_bot(b)
        return {"ok": True}
    info["manual_stop"] = manual
    proc = info["proc"]
    child_pids: List[int] = []
    if psutil is not None:
        try:
            parent = psutil.Process(proc.pid)
            for ch in parent.children(recursive=True):
                child_pids.append(ch.pid)
        except Exception:
            pass

    def _kill(pid: int, sig: int) -> None:
        try: os.kill(pid, sig)
        except (ProcessLookupError, PermissionError): pass
        except Exception: pass
    try:
        if os.name == "posix":
            try: os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError): pass
            for pid in child_pids: _kill(pid, signal.SIGTERM)
        else:
            proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError): pass
                for pid in child_pids: _kill(pid, signal.SIGKILL)
            else:
                proc.kill()
            try: proc.wait(timeout=3)
            except Exception: pass
    except ProcessLookupError:
        pass
    except Exception as e:
        with _runner_lock:
            RUNNING.pop(bot_id, None)
        b = find_bot(bot_id)
        if b:
            b["status"] = "stopped"
            save_bot(b)
        return {"ok": False, "error": str(e)}
    with _runner_lock:
        RUNNING.pop(bot_id, None)
    b = find_bot(bot_id)
    if b:
        b["status"] = "stopped"
        save_bot(b)
    return {"ok": True}

def restart_child(b: Dict[str, Any]) -> Dict[str, Any]:
    stop_child(b["_id"], manual=False)
    time.sleep(1)
    return start_child(b)

def child_status(bot_id: str, b_doc: Dict[str, Any]) -> Dict[str, Any]:
    info = RUNNING.get(bot_id)
    running = bool(info and info["proc"].poll() is None)
    bot_dir = Path(b_doc.get("dir") or "")
    kind, _ = detect_entry(bot_dir) if bot_dir.exists() else (None, None)
    sz = 0
    try:
        for root, _, files in os.walk(bot_dir):
            for f in files:
                try: sz += (Path(root) / f).stat().st_size
                except OSError: pass
    except Exception:
        pass
    cpu = mem = 0.0
    if running and psutil is not None:
        try:
            p = psutil.Process(info["proc"].pid)
            cpu = p.cpu_percent(interval=0.05)
            mem = p.memory_info().rss
        except Exception:
            pass
    return {
        "running": running,
        "pid": info["proc"].pid if running else None,
        "kind": (info["kind"] if info else kind) or "—",
        "uptimeMs": int(time.time() * 1000 - info["started"]) if running else 0,
        "sizeBytes": sz,
        "logs": info["log"] if info else [],
        "cpuPct": cpu,
        "memBytes": mem,
    }

def tail_log(bot_id: str, lines: int = 60) -> str:
    info = RUNNING.get(bot_id)
    if not info:
        return ""
    log = info.get("log") or []
    return "\n".join(log[-lines:])

# ═════════════════════════════════════════════════════════════════
#  ENCRYPTED BOT STORAGE
# ═════════════════════════════════════════════════════════════════

def store_uploaded_file(uploader: types.User, filename: str, plain: bytes) -> Dict[str, Any]:
    safe = safe_name(filename)
    key_id, key, cipher = encrypt_file(plain)
    rel = f"{uploader.id}/{int(time.time())}_{safe}.enc"
    out = DIRS["encfiles"] / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(cipher)
    meta = {
        "filename": filename, "uploader_id": uploader.id,
        "uploader_username": uploader.username or "",
        "size": len(plain), "uploaded": ts_iso(), "stored_at": str(out),
    }
    KEYRING.store(key_id, key, meta)
    return {"key_id": key_id, "path": str(out), "size": len(plain)}

def materialize_bot_files(b: Dict[str, Any]) -> None:
    bot_dir = Path(b["dir"])
    bot_dir.mkdir(parents=True, exist_ok=True)
    files = b.get("enc_files") or []
    for f in files:
        key = KEYRING.fetch(f["key_id"])
        if not key:
            raise RuntimeError(f"missing key {f['key_id']}")
        try:
            plain = read_encrypted(Path(f["enc_path"]), key)
        except InvalidToken:
            raise RuntimeError(f"key mismatch for {f.get('filename')}")
        rel = f.get("rel_path") or f["filename"]
        rel = rel.lstrip("/")
        try:
            tgt = safe_path_join(bot_dir, rel)
        except ValueError:
            continue
        tgt.parent.mkdir(parents=True, exist_ok=True)
        tgt.write_bytes(plain)
        plain = b""
    for f in files:
        KEYRING.wipe(f["key_id"])

# ═════════════════════════════════════════════════════════════════
#  GITHUB BACKUP / RESTORE
# ═════════════════════════════════════════════════════════════════

GH = {
    "token": "", "repo": "", "branch": "main",
    "intervalMin": 360, "lastBackup": None, "lastError": None,
    "inProgress": False, "autoEnabled": True,
}

def gh_load_config() -> None:
    GH["token"] = os.environ.get("GITHUB_TOKEN") or get_setting("github_token", "") or ""
    GH["repo"] = os.environ.get("GITHUB_REPO") or get_setting("github_repo", "") or ""
    GH["branch"] = os.environ.get("GITHUB_BRANCH") or get_setting("github_branch", "main") or "main"
    try:
        ivl = int(os.environ.get("GITHUB_AUTO_INTERVAL_MIN") or get_setting("github_interval_min", 360))
    except Exception:
        ivl = 360
    GH["intervalMin"] = ivl if ivl > 0 else 360

def gh_set_config(patch: Dict[str, Any]) -> None:
    keymap = {"token": "github_token", "repo": "github_repo",
              "branch": "github_branch", "intervalMin": "github_interval_min"}
    for k, v in patch.items():
        if k not in keymap: continue
        if k == "intervalMin":
            try: v = int(v)
            except Exception: v = 360
        GH[k] = v
        set_setting(keymap[k], v)

def gh_enabled() -> bool:
    return bool(GH["token"] and GH["repo"] and "/" in GH["repo"])

def _gh(method: str, url: str, **kw) -> requests.Response:
    h = kw.pop("headers", {}) or {}
    h.setdefault("Authorization", f"token {GH['token']}")
    h.setdefault("Accept", "application/vnd.github+json")
    h.setdefault("User-Agent", "hosting-bot/3.0")
    return requests.request(method, url, headers=h, timeout=60, **kw)

def _gh_repo_url(p: str = "") -> str:
    return f"https://api.github.com/repos/{GH['repo']}/{p.lstrip('/')}"

def _gh_ensure_branch() -> bool:
    r = _gh("GET", _gh_repo_url(f"branches/{GH['branch']}"))
    if r.status_code == 200:
        return True
    if r.status_code != 404:
        return False
    info = _gh("GET", _gh_repo_url())
    if info.status_code != 200:
        return False
    default = info.json().get("default_branch", "main")
    ref = _gh("GET", _gh_repo_url(f"git/ref/heads/{default}"))
    if ref.status_code != 200:
        return False
    sha = ref.json()["object"]["sha"]
    _gh("POST", _gh_repo_url("git/refs"),
        json={"ref": f"refs/heads/{GH['branch']}", "sha": sha})
    return True

def _gh_put_file(path: str, content: bytes, message: str) -> bool:
    sha: Optional[str] = None
    g = _gh("GET", _gh_repo_url(f"contents/{path}"), params={"ref": GH["branch"]})
    if g.status_code == 200:
        sha = g.json().get("sha")
    elif g.status_code != 404:
        return False
    body: Dict[str, Any] = {
        "message": message, "branch": GH["branch"],
        "content": base64.b64encode(content).decode(),
    }
    if sha: body["sha"] = sha
    r = _gh("PUT", _gh_repo_url(f"contents/{path}"), json=body)
    return r.status_code in (200, 201)

def _make_tarball() -> Path:
    tmp = Path(tempfile.gettempdir()) / f"panel-backup-{int(time.time())}.tar.gz"
    excludes = ("node_modules", ".deps", ".tmp_run", "__pycache__")

    def _filter(ti: tarfile.TarInfo) -> Optional[tarfile.TarInfo]:
        if any(x in ti.name.split("/") for x in excludes):
            return None
        if ti.name.endswith(".log"):
            return None
        return ti

    with tarfile.open(tmp, "w:gz") as tf:
        storage_dir = BASE_DIR / "storage"
        if storage_dir.exists():
            tf.add(str(storage_dir), arcname="storage", filter=_filter)
    return tmp

def gh_backup_now() -> Dict[str, Any]:
    if not gh_enabled():
        return {"ok": False, "error": "Not configured."}
    if GH["inProgress"]:
        return {"ok": False, "error": "Backup already running."}
    GH["inProgress"] = True
    tar: Optional[Path] = None
    try:
        if not _gh_ensure_branch():
            raise RuntimeError(f"Branch {GH['branch']} unavailable")
        tar = _make_tarball()
        buf = tar.read_bytes()
        size_mb = len(buf) / 1024 / 1024
        if size_mb > 95:
            raise RuntimeError(f"Backup {size_mb:.1f} MB > 95 MB")
        ts = ts_iso().replace(":", "-").replace(".", "-")
        ok1 = _gh_put_file("backups/latest.tar.gz", buf, f"panel backup {ts}")
        if not ok1:
            raise RuntimeError("upload failed")
        GH["lastBackup"] = ts
        GH["lastError"] = None
        return {"ok": True, "sizeMB": f"{size_mb:.2f}", "ts": ts}
    except Exception as e:
        GH["lastError"] = str(e)
        return {"ok": False, "error": str(e)}
    finally:
        if tar and tar.exists():
            try: tar.unlink()
            except Exception: pass
        GH["inProgress"] = False

def gh_restore_now(overwrite: bool = True) -> Dict[str, Any]:
    if not gh_enabled():
        return {"ok": False, "error": "Not configured."}
    r = _gh("GET", _gh_repo_url("contents/backups/latest.tar.gz"),
            params={"ref": GH["branch"]})
    if r.status_code == 404:
        return {"ok": False, "error": "No backup found."}
    if r.status_code != 200:
        return {"ok": False, "error": f"GitHub HTTP {r.status_code}"}
    buf = base64.b64decode(r.json()["content"])
    tmp = Path(tempfile.gettempdir()) / f"panel-restore-{int(time.time())}.tar.gz"
    tmp.write_bytes(buf)
    try:
        if overwrite:
            d = BASE_DIR / "storage"
            if d.exists():
                for sub in d.iterdir():
                    rmrf(sub)
        with tarfile.open(tmp, "r:gz") as tf:
            tf.extractall(str(BASE_DIR))
        for _p in DIRS.values():
            _p.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "sizeBytes": len(buf)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try: tmp.unlink()
        except Exception: pass

def gh_auto_loop() -> None:
    while True:
        try:
            time.sleep(max(60, GH["intervalMin"] * 60))
            if gh_enabled() and GH["autoEnabled"]:
                res = gh_backup_now()
                if not res.get("ok"):
                    print(f"[gh_auto_loop] backup failed: {res.get('error')}", flush=True)
                else:
                    print(f"[gh_auto_loop] backup ok ({res.get('sizeMB')} MB)", flush=True)
        except Exception as e:
            print(f"[gh_auto_loop] loop error: {e}", flush=True)

def gh_auto_restore_on_boot() -> Optional[Dict[str, Any]]:
    if not gh_enabled():
        return None
    if not GH.get("autoEnabled", False):
        return None
    try:
        if DB_FILE.exists():
            data = json.loads(DB_FILE.read_text(encoding="utf-8") or "{}")
            users = data.get("users") or {}
            bots = data.get("bots") or {}
            if users or bots:
                return {"ok": False, "skip": True, "reason": "local data present"}
    except Exception:
        pass
    return gh_restore_now(overwrite=True)

# ═════════════════════════════════════════════════════════════════
#  USER MANAGEMENT
# ═════════════════════════════════════════════════════════════════

def notify_owner(html: str) -> None:
    if not OWNER_ID:
        return
    try:
        bot.send_message(OWNER_ID, html, parse_mode="HTML")
    except Exception as e:
        print(f"[notify_owner] {e}")

def get_or_create_user(u: types.User, ref: Optional[int] = None) -> Tuple[Dict[str, Any], bool]:
    db = db_load()
    key = str(u.id)
    is_new = key not in db["users"]
    if is_new:
        db["users"][key] = {
            "_id": u.id, "name": u.first_name or "", "username": u.username or "",
            "plan": "free", "plan_expires": None,
            "joined": ts_iso(), "last_seen": ts_iso(),
            "banned": False, "ban_reason": "",
            "wallet": 0,
            "stats": {"commands": 0, "bots_uploaded": 0, "logins": 1},
        }
        db_save(db)
        notify_owner(
            f"<b>{G['plus']} New user</b>\n"
            f"{bullet('Name', u.first_name)}\n"
            f"{bullet('Username', '@' + (u.username or '—'))}\n"
            f"{bullet('ID', u.id)}"
        )
    else:
        db["users"][key]["last_seen"] = ts_iso()
        db["users"][key]["stats"]["logins"] = int(
            db["users"][key]["stats"].get("logins", 0)) + 1
        db_save(db)
    return db["users"][key], is_new

def list_user_bots(uid: int) -> List[Dict[str, Any]]:
    return [copy.deepcopy(b) for b in db_load_ro()["bots"].values() if b.get("owner") == uid]

def find_bot(bot_id: str) -> Optional[Dict[str, Any]]:
    b = db_load_ro()["bots"].get(bot_id)
    return copy.deepcopy(b) if b is not None else None

def save_bot(doc: Dict[str, Any]) -> Dict[str, Any]:
    d = db_load()
    d["bots"][doc["_id"]] = doc
    db_save(d)
    return doc

def delete_bot_doc(bot_id: str) -> None:
    d = db_load()
    d["bots"].pop(bot_id, None)
    db_save(d)

def user_max_bots(u: Dict[str, Any]) -> int:
    plan = u.get("plan", "free")
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])["max_bots"]

def user_plan_active(u: Dict[str, Any]) -> bool:
    if u.get("plan") == "free":
        return True
    exp = u.get("plan_expires")
    if not exp:
        return False
    try:
        return datetime.fromisoformat(str(exp).replace("Z", "+00:00")) > now_utc()
    except Exception:
        return False

def downgrade_expired_users() -> None:
    d = db_load()
    changed = False
    for uid, u in d["users"].items():
        if u.get("plan") == "free":
            continue
        if not user_plan_active(u):
            u["plan"] = "free"
            u["plan_expires"] = None
            changed = True
            try:
                bot.send_message(int(uid),
                    f"<b>{G['warn']} Plan expired</b>\n\nDowngraded to Free.",
                    parse_mode="HTML")
            except Exception:
                pass
    if changed:
        db_save(d)

def grant_plan(uid: int, plan: str, days: Optional[int] = None) -> bool:
    d = db_load()
    key = str(uid)
    if key not in d["users"] or plan not in PLAN_LIMITS:
        return False
    u = d["users"][key]
    pl = PLAN_LIMITS[plan]
    days = days if days is not None else pl["days"]
    if plan == "free":
        u["plan"] = "free"
        u["plan_expires"] = None
    else:
        u["plan"] = plan
        try:
            cur_exp = datetime.fromisoformat(str(u.get("plan_expires") or "").replace("Z", "+00:00"))
        except Exception:
            cur_exp = now_utc()
        if cur_exp < now_utc() or u.get("plan") != plan:
            cur_exp = now_utc()
        u["plan_expires"] = (cur_exp + timedelta(days=days)).isoformat()
    db_save(d)
    try:
        bot.send_message(uid,
            f"<b>{G['ok']} Plan activated</b>\n\n"
            f"{bullet('Plan', pl['name'])}\n"
            f"{bullet('Bots', pl['max_bots'])}\n"
            f"{bullet('RAM', str(pl['ram']) + ' MB')}\n"
            f"{bullet('Until', fmt_ts(u.get('plan_expires')) if u.get('plan_expires') else 'Lifetime')}",
            parse_mode="HTML")
    except Exception:
        pass
    return True

# ═════════════════════════════════════════════════════════════════
#  MENU RENDERING (photo + caption + buttons)
# ═════════════════════════════════════════════════════════════════

def _log_err(where: str, exc: BaseException) -> None:
    try:
        print(f"[ui:{where}] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
    except Exception:
        pass

_TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)(\s[^>]*)?>")

def _html_safe_truncate(s: str, limit: int = 1024) -> str:
    if len(s) <= limit:
        return s
    cut = s[: limit - 1]
    last_lt = cut.rfind("<")
    last_gt = cut.rfind(">")
    if last_lt > last_gt:
        cut = cut[:last_lt]
    stack: List[str] = []
    for m in _TAG_RE.finditer(cut):
        closing, name = m.group(1), m.group(2).lower()
        if closing:
            if stack and stack[-1] == name:
                stack.pop()
        else:
            stack.append(name)
    closes = "".join(f"</{t}>" for t in reversed(stack))
    return cut + "…" + closes

def show_text(chat_id: int, text: str,
              kb: Optional[types.InlineKeyboardMarkup] = None,
              call: Optional[types.CallbackQuery] = None) -> None:
    text = _html_safe_truncate(text, 4096)
    if call and call.message and call.message.content_type == "text":
        try:
            bot.edit_message_text(text, chat_id=chat_id,
                                  message_id=call.message.message_id,
                                  reply_markup=kb, parse_mode="HTML",
                                  disable_web_page_preview=True)
            return
        except ApiTelegramException as e:
            if "message is not modified" in str(e).lower():
                return
            _log_err("edit_message_text", e)
        except Exception as e:
            _log_err("edit_message_text", e)
    try:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb,
                         disable_web_page_preview=True)
    except Exception as e:
        _log_err("send_message", e)
        try:
            plain = re.sub(r"<[^>]+>", "", text)
            bot.send_message(chat_id, plain or "…", reply_markup=kb,
                             disable_web_page_preview=True)
        except Exception as e2:
            _log_err("send_message(plain)", e2)

def main_menu_kb(admin: bool = False) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{G['diamond']}  My Bots", callback_data="menu_bots"),
        types.InlineKeyboardButton(f"{G['upload']}  Upload",  callback_data="menu_upload"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{G['star']}  Plans",     callback_data="menu_plans"),
        types.InlineKeyboardButton(f"{G['wallet']}  Wallet",  callback_data="menu_wallet"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{G['user']}  Profile",   callback_data="menu_profile"),
        types.InlineKeyboardButton(f"{G['ticket']}  Tickets", callback_data="menu_tickets"),
    )
    if admin:
        kb.add(types.InlineKeyboardButton(
            f"{G['shield']}  Admin Panel", callback_data="menu_admin"))
    return kb

def back_main_kb() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(f"{G['back']}  Main Menu", callback_data="menu_main"))

def back_admin_kb() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(f"{G['back']}  Admin", callback_data="menu_admin"))

def back_kb(target: str, label: str = "Back") -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(f"{G['back']}  {sc(label)}", callback_data=target))

def plans_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    for k, v in PLAN_LIMITS.items():
        price = "Free" if v["price"] == 0 else "৳" + str(v["price"])
        kb.add(types.InlineKeyboardButton(
            f"{G['star']}  {sc(v['name'])}  •  {price}",
            callback_data=f"plan_view_{k}"))
    kb.add(types.InlineKeyboardButton(
        f"{G['back']}  Main Menu", callback_data="menu_main"))
    return kb

def payments_kb(plan: Optional[str] = None) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    suffix = f"_{plan}" if plan else ""
    for k, v in PAYMENT_METHODS.items():
        kb.add(types.InlineKeyboardButton(
            f"{v['tag']}  {sc(v['name'])}", callback_data=f"pay_{k}{suffix}"))
    kb.add(types.InlineKeyboardButton(
        f"{G['back']}  Plans", callback_data="menu_plans"))
    return kb

def admin_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{G['graph']}  Stats",    callback_data="adm_stats"),
        types.InlineKeyboardButton(f"{G['users']}  Users",    callback_data="adm_users"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{G['diamond']}  All Bots", callback_data="adm_allbots"),
        types.InlineKeyboardButton(f"{G['wallet']}  Payments", callback_data="adm_payments"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{G['broadcast']}  Broadcast", callback_data="adm_broadcast"),
        types.InlineKeyboardButton(f"{G['no']}  Ban/Unban",     callback_data="adm_ban"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{G['plus']}  Give Plan",   callback_data="adm_giveplan"),
        types.InlineKeyboardButton(f"{G['ok']}  Approve Pay",   callback_data="adm_payments"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{G['ticket']}  Tickets",   callback_data="adm_tickets"),
        types.InlineKeyboardButton(f"{G['shield']}  Admins",    callback_data="adm_admins"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{G['eye']}  Audit Log",    callback_data="adm_audit"),
        types.InlineKeyboardButton(f"{G['cog']}  GitHub",       callback_data="adm_github"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{G['lock']}  Security",    callback_data="adm_security"),
        types.InlineKeyboardButton(f"{G['warn']}  Maintenance", callback_data="adm_maint"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{G['cog']}  Settings",     callback_data="adm_settings"),
        types.InlineKeyboardButton(f"{G['eye']}  Pending",      callback_data="adm_pending"),
    )
    kb.add(types.InlineKeyboardButton(
        f"{G['back']}  Main Menu", callback_data="menu_main"))
    return kb

def bot_actions_kb(bot_id: str, running: bool) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    if running:
        kb.add(
            types.InlineKeyboardButton(f"{G['stop']}  Stop", callback_data=f"bot_stop_{bot_id}"),
            types.InlineKeyboardButton(f"{G['refresh']}  Restart", callback_data=f"bot_restart_{bot_id}"),
        )
    else:
        kb.add(
            types.InlineKeyboardButton(f"{G['play']}  Start", callback_data=f"bot_start_{bot_id}"),
            types.InlineKeyboardButton(f"{G['refresh']}  Restart", callback_data=f"bot_restart_{bot_id}"),
        )
    kb.add(
        types.InlineKeyboardButton(f"{G['bolt']}  Logs", callback_data=f"bot_logs_{bot_id}"),
        types.InlineKeyboardButton(f"{G['eye']}  Info", callback_data=f"bot_info_{bot_id}"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{G['cog']}  Env Vars", callback_data=f"bot_env_{bot_id}"),
        types.InlineKeyboardButton(f"{G['cog']}  Cron", callback_data=f"bot_cron_{bot_id}"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{G['download']}  Pip Install", callback_data=f"bot_pip_{bot_id}"),
        types.InlineKeyboardButton(f"{G['plus']}  Clone", callback_data=f"bot_clone_{bot_id}"),
    )
    kb.add(types.InlineKeyboardButton(
        f"{G['arrow']}  Download", callback_data=f"bot_dl_{bot_id}"))
    kb.add(types.InlineKeyboardButton(
        f"{G['trash']}  Delete", callback_data=f"bot_delete_{bot_id}"))
    kb.add(types.InlineKeyboardButton(
        f"{G['back']}  My Bots", callback_data="menu_bots"))
    return kb

def confirm_kb(yes_cb: str, no_cb: str = "menu_main",
               yes_label: str = "Confirm", no_label: str = "Cancel") -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{G['ok']}  {sc(yes_label)}", callback_data=yes_cb),
        types.InlineKeyboardButton(f"{G['no']}  {sc(no_label)}", callback_data=no_cb),
    )
    return kb

# ═════════════════════════════════════════════════════════════════
#  RENDERERS
# ═════════════════════════════════════════════════════════════════

def render_main_menu(chat_id: int, uid: int,
                     call: Optional[types.CallbackQuery] = None,
                     intro: Optional[str] = None) -> None:
    u = db_load()["users"].get(str(uid)) or {}
    plan = PLAN_LIMITS.get(u.get("plan", "free"), PLAN_LIMITS["free"])
    bots = list_user_bots(uid)
    running = sum(1 for b in bots if b["_id"] in RUNNING and RUNNING[b["_id"]]["proc"].poll() is None)
    intro_block = f"{intro}\n{G['div']}\n" if intro else ""
    cap = (
        f"<b>{esc(BRAND_TAG)}</b>\n"
        f"{G['div_eq']}\n"
        f"{intro_block}"
        f"{sc('Welcome')}, <b>{esc(u.get('name') or 'friend')}</b>\n"
        f"{bullet('Plan', plan['name'])}\n"
        f"{bullet('Until', fmt_ts(u.get('plan_expires')) if u.get('plan_expires') else 'Forever' if plan['price'] == 0 else '—')}\n"
        f"{bullet('Bots', str(len(bots)) + ' / ' + str(user_max_bots(u)) + '  (running ' + str(running) + ')')}\n"
        f"{bullet('Wallet', '৳' + str(u.get('wallet', 0)))}\n"
        f"{G['div']}\n"
        f"Choose an option below."
    )
    show_text(chat_id, cap, main_menu_kb(is_admin(uid)), call=call)

def render_bots_menu(call: types.CallbackQuery) -> None:
    uid = call.from_user.id
    bots = list_user_bots(uid)
    u = db_load()["users"][str(uid)]
    cap = (
        f"<b>{G['diamond']} {sc('Your Bots')}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Slots', str(len(bots)) + ' / ' + str(user_max_bots(u)))}\n"
    )
    kb = types.InlineKeyboardMarkup()
    if not bots:
        cap += f"\n{sc('No bots yet. Tap Upload to begin')}."
    else:
        for b in sorted(bots, key=lambda x: x.get("name", "")):
            running = b["_id"] in RUNNING and RUNNING[b["_id"]]["proc"].poll() is None
            mark = G["play"] if running else G["stop"]
            kb.add(types.InlineKeyboardButton(
                f"{mark}  {sc(b['name'])[:30]}",
                callback_data=f"bot_view_{b['_id']}"))
    kb.add(
        types.InlineKeyboardButton(f"{G['plus']}  Upload", callback_data="menu_upload"),
        types.InlineKeyboardButton(f"{G['back']}  Main Menu", callback_data="menu_main"),
    )
    show_text(call.message.chat.id, cap, kb, call=call)

def render_upload_menu(call: types.CallbackQuery) -> None:
    uid = call.from_user.id
    u = db_load()["users"][str(uid)]
    used = len(list_user_bots(uid))
    cap = (
        f"<b>{G['upload']} {sc('Upload Bot')}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Plan', PLAN_LIMITS[u['plan']]['name'])}\n"
        f"{bullet('Slots', str(used) + ' / ' + str(user_max_bots(u)))}\n"
        f"{G['div']}\n"
        f"<b>{sc('Send your bot file as a document')}.</b>\n"
        f"Accepted: <code>.zip  .py  .js</code>\n"
        f"Entry: <code>bot.py</code>, <code>main.py</code>, <code>app.py</code>, "
        f"<code>index.js</code>, <code>bot.js</code>.\n"
        f"All files are <b>encrypted at rest</b>."
    )
    USER_STATES[uid] = {"flow": "await_upload"}
    show_text(call.message.chat.id, cap, back_main_kb(), call=call)

def render_plans_menu(call: types.CallbackQuery) -> None:
    lines = []
    for v in PLAN_LIMITS.values():
        price_txt = "Free" if v["price"] == 0 else "৳" + str(v["price"])
        detail = f"{v['max_bots']} bots • {v['ram']} MB RAM • {price_txt}"
        lines.append(bullet(v['name'], detail))
    cap = (
        f"<b>{G['star']} {sc('Plans')}</b>\n"
        f"{G['div_eq']}\n"
        + "\n".join(lines)
        + f"\n{G['div']}\nTap a plan for full details."
    )
    show_text(call.message.chat.id, cap, plans_kb(), call=call)

def render_plan_detail(call: types.CallbackQuery, plan: str) -> None:
    p = PLAN_LIMITS.get(plan)
    if not p:
        ack(call, "Unknown plan"); return
    cap = (
        f"<b>{G['star']} {esc(p['name'])} {sc('Plan')}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Max bots', p['max_bots'])}\n"
        f"{bullet('RAM per bot', str(p['ram']) + ' MB')}\n"
        f"{bullet('Auto-restart', 'Yes' if p['auto_restart'] else 'No')}\n"
        f"{bullet('Duration', 'Lifetime' if plan == 'lifetime' else str(p['days']) + ' days')}\n"
        f"{bullet('Price', 'Free' if p['price'] == 0 else '৳' + str(p['price']))}\n"
        f"{G['div']}\n"
        f"{sc('Tap buy to choose a payment method')}."
    )
    kb = types.InlineKeyboardMarkup()
    if plan != "free":
        kb.add(types.InlineKeyboardButton(
            f"{G['spark']}  {sc('Buy')} {p['name']}",
            callback_data=f"plan_buy_{plan}"))
    kb.add(types.InlineKeyboardButton(
        f"{G['back']}  {sc('Plans')}", callback_data="menu_plans"))
    show_text(call.message.chat.id, cap, kb, call=call)

def render_payment_methods_for(call: types.CallbackQuery, plan: str) -> None:
    p = PLAN_LIMITS.get(plan)
    if not p:
        ack(call, "Unknown plan"); return
    cap = (
        f"<b>{G['wallet']} {sc('Choose Payment Method')}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Plan', p['name'])}\n"
        f"{bullet('Price', '৳' + str(p['price']))}\n"
        f"{G['div']}\n"
        f"{sc('Pick the method you will pay with')}."
    )
    show_text(call.message.chat.id, cap, payments_kb(plan), call=call)

def render_payment_screen(call: types.CallbackQuery, data: str) -> None:
    parts = data.split("_")
    method = parts[1] if len(parts) > 1 else ""
    plan = parts[2] if len(parts) > 2 else None
    pm = PAYMENT_METHODS.get(method)
    if not pm:
        ack(call, "Unknown method"); return
    p = PLAN_LIMITS.get(plan or "")
    cap = (
        f"<b>{pm['tag']} {esc(pm['name'])} — {sc('Payment')}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Number', pm['number'])}\n"
        f"{bullet('Type', pm['type'])}\n"
    )
    if p:
        cap += f"{bullet('Plan', p['name'])}\n{bullet('Amount', '৳' + str(p['price']))}\n"
    cap += (
        f"{G['div']}\n"
        f"<b>{sc('How to pay')}:</b>\n"
        f"1. {sc('Send the exact amount to the number above')}.\n"
        f"2. {sc('Tap Send Proof and forward receipt screenshot')}.\n"
        f"3. {sc('Wait for admin approval')}.\n"
        f"{G['div']}"
    )
    kb = types.InlineKeyboardMarkup()
    USER_STATES[call.from_user.id] = {
        "flow": "await_payment_proof", "method": method, "plan": plan,
    }
    kb.add(types.InlineKeyboardButton(
        f"{G['plus']}  {sc('Send Proof')}", callback_data="pay_proof"))
    kb.add(types.InlineKeyboardButton(
        f"{G['back']}  {sc('Methods')}",
        callback_data=f"plan_buy_{plan}" if plan else "menu_plans"))
    show_text(call.message.chat.id, cap, kb, call=call)

def render_profile(call: types.CallbackQuery) -> None:
    uid = call.from_user.id
    u = db_load()["users"][str(uid)]
    p = PLAN_LIMITS.get(u["plan"], PLAN_LIMITS["free"])
    bots = list_user_bots(uid)
    cap = (
        f"<b>{G['user']} {sc('Profile')}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Name', u.get('name'))}\n"
        f"{bullet('Username', '@' + (u.get('username') or '—'))}\n"
        f"{bullet('User ID', uid)}\n"
        f"{bullet('Plan', p['name'])}\n"
        f"{bullet('Until', fmt_ts(u.get('plan_expires')) if u.get('plan_expires') else 'Forever' if p['price'] == 0 else '—')}\n"
        f"{bullet('Wallet', '৳' + str(u.get('wallet', 0)))}\n"
        f"{bullet('Bots', str(len(bots)) + ' / ' + str(user_max_bots(u)))}\n"
        f"{bullet('Joined', fmt_ts(u.get('joined')))}\n"
        f"{G['div']}"
    )
    show_text(call.message.chat.id, cap, back_main_kb(), call=call)

def render_wallet(call: types.CallbackQuery) -> None:
    uid = call.from_user.id
    u = db_load()["users"][str(uid)]
    cap = (
        f"<b>{G['wallet']} {sc('Wallet')}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Balance', '৳' + str(u.get('wallet', 0)))}\n"
        f"{G['div']}\n"
        f"{sc('Top up by sending payment proof. Admin will credit your wallet')}."
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        f"{G['plus']}  {sc('Top Up')}", callback_data="wallet_topup"))
    kb.add(types.InlineKeyboardButton(
        f"{G['back']}  {sc('Main Menu')}", callback_data="menu_main"))
    show_text(call.message.chat.id, cap, kb, call=call)

def render_user_tickets(call: types.CallbackQuery) -> None:
    uid = call.from_user.id
    d = db_load()["tickets"]
    mine = [t for t in d.values() if t.get("uid") == uid][-10:]
    rows = "\n".join(
        f"{G['bullet']} <code>{t['id']}</code> • {esc(t.get('status'))} • {esc(t.get('subject', ''))[:40]}"
        for t in mine
    ) or f"<i>{sc('no tickets yet')}</i>"
    cap = (
        f"<b>{G['ticket']} {sc('Your Tickets')}</b>\n"
        f"{G['div_eq']}\n{rows}\n{G['div']}"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        f"{G['plus']}  {sc('Open Ticket')}", callback_data="ticket_open"))
    for t in mine:
        kb.add(types.InlineKeyboardButton(
            f"{G['eye']}  #{t['id']}", callback_data=f"ticket_view_{t['id']}"))
    kb.add(types.InlineKeyboardButton(
        f"{G['back']}  {sc('Main Menu')}", callback_data="menu_main"))
    show_text(call.message.chat.id, cap, kb, call=call)

def render_ticket_view(call: types.CallbackQuery, tid: str) -> None:
    d = db_load()
    t = d["tickets"].get(tid)
    if not t:
        ack(call, "Not found"); return
    if t["uid"] != call.from_user.id and not is_admin(call.from_user.id):
        ack(call, "Not yours"); return
    msgs = "\n".join(
        f"<b>{esc(m['from'])}</b>: {esc(m['text'])[:200]}"
        for m in t.get("messages", [])
    )
    cap = (
        f"<b>{G['ticket']} #{t['id']}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('From', t['uid'])}\n"
        f"{bullet('Status', t['status'])}\n"
        f"{bullet('Subject', t['subject'])}\n"
        f"{G['div']}\n{msgs}\n{G['div']}"
    )
    kb = types.InlineKeyboardMarkup()
    if t["status"] == "open":
        kb.add(types.InlineKeyboardButton(
            f"{G['plus']}  {sc('Reply')}", callback_data=f"ticket_reply_{tid}"))
        kb.add(types.InlineKeyboardButton(
            f"{G['no']}  {sc('Close')}", callback_data=f"ticket_close_{tid}"))
    kb.add(types.InlineKeyboardButton(
        f"{G['back']}  {sc('Tickets')}",
        callback_data="adm_tickets" if is_admin(call.from_user.id) else "menu_tickets"))
    show_text(call.message.chat.id, cap, kb, call=call)

# ═════════════════════════════════════════════════════════════════
#  BOT VIEWS
# ═════════════════════════════════════════════════════════════════

def render_bot_view(call: types.CallbackQuery, bot_id: str) -> None:
    b = find_bot(bot_id)
    if not b:
        ack(call, "Not found"); return
    if b["owner"] != call.from_user.id and not is_admin(call.from_user.id):
        ack(call, "Not yours"); return
    st = child_status(bot_id, b)
    err_block = ""
    if not st["running"]:
        rc = b.get("last_exit_code")
        last_err = (b.get("last_error") or "").strip()
        if last_err or (rc not in (None, 0)):
            head = f"{G['no']} {sc('Last error')}"
            if rc not in (None, 0):
                head += f"  (exit {rc})"
            err_block = (
                f"\n{G['div']}\n<b>{head}</b>\n"
                f"<pre>{esc(last_err or '(no log captured)')[:900]}</pre>"
            )
    appr = (b.get("approval_status") or "").lower()
    if appr == "pending":
        status_lbl = "⏳ Pending approval"
    elif appr == "rejected":
        status_lbl = "❌ Rejected"
    elif st["running"]:
        status_lbl = "▶ Running"
    elif b.get("status") == "crashed":
        status_lbl = "💥 Crashed"
    else:
        status_lbl = "⏹ Stopped"
    cap = (
        f"<b>{G['diamond']} {esc(b['name'])}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Status', status_lbl)}\n"
        f"{bullet('Kind', st['kind'] or '—')}\n"
        f"{bullet('PID', '••••' if st['pid'] else '—')}\n"
        f"{bullet('Uptime', fmt_dur(st['uptimeMs']))}\n"
        f"{bullet('Size', fmt_bytes(st['sizeBytes']))}\n"
        f"{bullet('CPU', '{:.1f}%'.format(st['cpuPct']))}\n"
        f"{bullet('Memory', fmt_bytes(st['memBytes']))}\n"
        f"{bullet('Created', fmt_ts(b.get('created')))}"
        f"{err_block}\n"
        f"{G['div']}"
    )
    show_text(call.message.chat.id, cap,
              bot_actions_kb(bot_id, st["running"]), call=call)

def render_bot_delete_confirm(call: types.CallbackQuery, bot_id: str) -> None:
    b = find_bot(bot_id)
    if not b:
        ack(call, "Not found"); return
    if b["owner"] != call.from_user.id and not is_admin(call.from_user.id):
        ack(call, "Not yours"); return
    cap = (
        f"<b>{G['no']} {sc('Delete Bot')}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Bot', b['name'])}\n\n"
        f"{sc('Choose delete type')}:\n\n"
        f"• <b>{sc('Delete Bot Files')}</b> — removes files and keys only\n"
        f"• <b>{sc('Delete All Data')}</b> — removes files + GitHub backup\n\n"
        f"{sc('Cannot be undone')}."
    )
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(f"{G['trash']}  {sc('Delete Bot Files')}",
                                   callback_data=f"bot_delfiles_{bot_id}"),
        types.InlineKeyboardButton(f"{G['no']}  {sc('Delete All Data')}",
                                   callback_data=f"bot_delall_{bot_id}"),
        types.InlineKeyboardButton(f"{G['back']}  {sc('Cancel')}",
                                   callback_data=f"bot_view_{bot_id}"),
    )
    show_text(call.message.chat.id, cap, kb, call=call)

def render_bot_delfiles_confirm(call: types.CallbackQuery, bot_id: str) -> None:
    b = find_bot(bot_id)
    if not b:
        ack(call, "Not found"); return
    cap = (
        f"<b>{G['trash']} {sc('Delete Bot Files')} — {esc(b['name'])}</b>\n"
        f"{G['div_eq']}\n"
        f"{sc('Removes encrypted files and keys only')}.\n"
        f"{sc('GitHub backup will NOT be deleted')}.\n\n"
        f"{sc('Are you sure')}?"
    )
    show_text(call.message.chat.id, cap,
              confirm_kb(f"bot_delfilesyes_{bot_id}", f"bot_view_{bot_id}",
                         "Yes Delete", "Cancel"), call=call)

def render_bot_delall_confirm(call: types.CallbackQuery, bot_id: str) -> None:
    b = find_bot(bot_id)
    if not b:
        ack(call, "Not found"); return
    cap = (
        f"<b>{G['no']} {sc('Delete All Data')} — {esc(b['name'])}</b>\n"
        f"{G['div_eq']}\n"
        f"{sc('Removes files, keys AND GitHub backup')}.\n"
        f"{G['warn']} <b>{sc('Everything permanently gone')}.</b>\n\n"
        f"{sc('Are you sure')}?"
    )
    show_text(call.message.chat.id, cap,
              confirm_kb(f"bot_delalyes_{bot_id}", f"bot_view_{bot_id}",
                         "Yes Delete All", "Cancel"), call=call)

def render_env_menu(call: types.CallbackQuery, bot_id: str) -> None:
    b = find_bot(bot_id)
    if not b:
        ack(call, "Not found"); return
    if b["owner"] != call.from_user.id and not is_admin(call.from_user.id):
        ack(call, "Not yours"); return
    env = b.get("env") or {}
    rows = "\n".join(f"{bullet(k, v)}" for k, v in env.items()) or f"<i>{sc('no variables yet')}</i>"
    cap = (
        f"<b>{G['cog']} {sc('Env Vars')} — {esc(b['name'])}</b>\n"
        f"{G['div_eq']}\n{rows}\n{G['div']}"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        f"{G['plus']}  {sc('Add Variable')}", callback_data=f"env_add_{bot_id}"))
    for k in env:
        kb.add(types.InlineKeyboardButton(
            f"{G['no']}  {sc('Delete')} {k}",
            callback_data=f"env_del_{bot_id}_{k}"))
    kb.add(types.InlineKeyboardButton(
        f"{G['back']}  {sc('Bot')}", callback_data=f"bot_view_{bot_id}"))
    show_text(call.message.chat.id, cap, kb, call=call)

def render_cron(call: types.CallbackQuery, bot_id: str) -> None:
    b = find_bot(bot_id)
    if not b:
        ack(call, "Not found"); return
    if b["owner"] != call.from_user.id and not is_admin(call.from_user.id):
        ack(call, "Not yours"); return
    cron = b.get("cron") or {}
    cap = (
        f"<b>{G['cog']} {sc('Cron')} — {esc(b['name'])}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Restart every', cron.get('restart_hours', '—'))}\n"
        f"{bullet('Backup every', cron.get('backup_hours', '—'))}\n"
        f"{G['div']}\n"
        f"{sc('Send a message like')} <code>restart=6 backup=12</code> "
        f"{sc('to set hours')}.\n"
        f"{sc('Send')} <code>off</code> {sc('to disable cron')}."
    )
    USER_STATES[call.from_user.id] = {"flow": "await_cron", "bot_id": bot_id}
    show_text(call.message.chat.id, cap, back_kb(f"bot_view_{bot_id}", "Back"), call=call)

# ═════════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ═════════════════════════════════════════════════════════════════

def admin_only_call(call: types.CallbackQuery, action: str = "view_stats") -> bool:
    if not is_admin(call.from_user.id):
        ack(call, "Owner / admin only.")
        return False
    if not admin_can(call.from_user.id, action):
        ack(call, "Insufficient permission.")
        return False
    return True

def render_admin(call: types.CallbackQuery) -> None:
    if not admin_only_call(call, "view_stats"):
        return
    role = admin_role(call.from_user.id)
    cap = (
        f"<b>{G['shield']} {sc('Admin Panel')}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Role', role)}\n"
        f"{bullet('Users', len(db_load()['users']))}\n"
        f"{bullet('Bots', len(db_load()['bots']))}\n"
        f"{bullet('Running', sum(1 for x in RUNNING.values() if x['proc'].poll() is None))}\n"
        f"{G['div']}"
    )
    show_text(call.message.chat.id, cap, admin_kb(), call=call)

def render_adm_stats(call: types.CallbackQuery) -> None:
    d = db_load()
    users = d["users"]
    bots = d["bots"]
    pays = d["payments"]
    revenue = sum(p.get("amount", 0) for p in pays if p.get("status") == "approved")
    today_str = now_utc().strftime("%Y-%m-%d")
    new_today = sum(1 for u in users.values() if str(u.get("joined", "")).startswith(today_str))
    plan_counts: Dict[str, int] = defaultdict(int)
    for u in users.values():
        plan_counts[u.get("plan", "free")] += 1
    rss = 0
    if psutil is not None:
        try:
            rss = psutil.Process(os.getpid()).memory_info().rss
        except Exception:
            pass
    cap = (
        f"<b>{G['graph']} {sc('System Stats')}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Total users', len(users))}\n"
        f"{bullet('New today', new_today)}\n"
        f"{bullet('Total bots', len(bots))}\n"
        f"{bullet('Bots running', sum(1 for x in RUNNING.values() if x['proc'].poll() is None))}\n"
        f"{bullet('Revenue', '৳' + str(revenue))}\n"
        f"{bullet('Panel RSS', fmt_bytes(rss))}\n"
        f"{bullet('Uptime', fmt_dur(int(time.time() * 1000) - START_TS))}\n"
        f"{G['div']}\n"
        + "\n".join(f"{bullet(PLAN_LIMITS[p]['name'], n)}" for p, n in plan_counts.items())
    )
    show_text(call.message.chat.id, cap, back_admin_kb(), call=call)

def render_adm_users(call: types.CallbackQuery) -> None:
    d = db_load()["users"]
    items = sorted(d.values(), key=lambda u: u.get("joined", ""), reverse=True)[:20]
    rows = "\n".join(
        f"{G['bullet']} <code>{u['_id']}</code> — {esc(u.get('name'))} "
        f"(@{esc(u.get('username') or '—')}) • <i>{esc(PLAN_LIMITS.get(u.get('plan'), {}).get('name', u.get('plan')))}</i>"
        for u in items
    ) or f"<i>{sc('no users yet')}</i>"
    cap = (
        f"<b>{G['users']} {sc('Recent Users')} ({len(d)} {sc('total')})</b>\n"
        f"{G['div_eq']}\n{rows}\n{G['div']}\n"
        f"{sc('Send a numeric user id to look one up')}."
    )
    USER_STATES[call.from_user.id] = {"flow": "await_admin_finduser"}
    show_text(call.message.chat.id, cap, back_admin_kb(), call=call)

def render_adm_allbots(call: types.CallbackQuery) -> None:
    d = db_load()["bots"]
    items = list(d.values())[:25]
    rows = "\n".join(
        f"{G['bullet']} <code>{b['_id']}</code> — {esc(b['name'])} "
        f"• uid {b['owner']} "
        f"• {'run' if b['_id'] in RUNNING and RUNNING[b['_id']]['proc'].poll() is None else 'idle'}"
        for b in items
    ) or f"<i>{sc('no bots')}</i>"
    cap = (
        f"<b>{G['diamond']} {sc('All Bots')} ({len(d)})</b>\n"
        f"{G['div_eq']}\n{rows}\n{G['div']}"
    )
    show_text(call.message.chat.id, cap, back_admin_kb(), call=call)

def render_adm_payments(call: types.CallbackQuery) -> None:
    d = db_load()
    pays = [p for p in d["payments"] if p.get("status") == "pending"][-15:]
    rows = "\n".join(
        f"{G['bullet']} <code>{p['id']}</code> • uid {p['uid']} "
        f"• {esc(p.get('plan', '—'))} • {esc(p.get('method'))}"
        for p in pays
    ) or f"<i>{sc('no pending payments')}</i>"
    cap = (
        f"<b>{G['wallet']} {sc('Pending Payments')}</b>\n"
        f"{G['div_eq']}\n{rows}\n{G['div']}\n"
        f"{sc('Tap a payment id from the inbox notification to approve/reject')}."
    )
    show_text(call.message.chat.id, cap, back_admin_kb(), call=call)

def render_adm_broadcast(call: types.CallbackQuery) -> None:
    cap = (
        f"<b>{G['broadcast']} {sc('Broadcast')}</b>\n"
        f"{G['div_eq']}\n"
        f"{sc('Send the message text now')}.\n"
        f"<b>{sc('Optional prefix')}:</b>\n"
        f"  <code>plan:pro</code> — {sc('only pro users')}\n"
        f"  <code>plan:free</code> — {sc('only free users')}\n"
        f"  <code>at:YYYY-MM-DD HH:MM</code> — {sc('schedule')}\n"
        f"  {sc('Otherwise message goes to everyone now')}."
    )
    USER_STATES[call.from_user.id] = {"flow": "await_broadcast"}
    show_text(call.message.chat.id, cap, back_admin_kb(), call=call)

def render_adm_ban(call: types.CallbackQuery) -> None:
    cap = (
        f"<b>{G['no']} {sc('Ban / Unban')}</b>\n"
        f"{G['div_eq']}\n"
        f"{sc('Send')} <code>ban &lt;user_id&gt; &lt;reason&gt;</code>\n"
        f"{sc('Send')} <code>unban &lt;user_id&gt;</code>"
    )
    USER_STATES[call.from_user.id] = {"flow": "await_ban_cmd"}
    show_text(call.message.chat.id, cap, back_admin_kb(), call=call)

def render_adm_giveplan(call: types.CallbackQuery) -> None:
    cap = (
        f"<b>{G['plus']} {sc('Give Plan')}</b>\n"
        f"{G['div_eq']}\n"
        f"{sc('Send')} <code>&lt;user_id&gt; &lt;plan&gt; [days]</code>\n"
        f"{sc('Plans')}: {', '.join(PLAN_LIMITS.keys())}"
    )
    USER_STATES[call.from_user.id] = {"flow": "await_giveplan"}
    show_text(call.message.chat.id, cap, back_admin_kb(), call=call)

def render_adm_tickets(call: types.CallbackQuery) -> None:
    d = db_load()["tickets"]
    open_t = [t for t in d.values() if t.get("status") == "open"][-15:]
    rows = "\n".join(
        f"{G['bullet']} <code>{t['id']}</code> uid {t['uid']} — {esc(t.get('subject'))[:40]}"
        for t in open_t
    ) or f"<i>{sc('no open tickets')}</i>"
    cap = (
        f"<b>{G['ticket']} {sc('Open Tickets')}</b>\n"
        f"{G['div_eq']}\n{rows}\n{G['div']}"
    )
    kb = types.InlineKeyboardMarkup()
    for t in open_t:
        kb.add(types.InlineKeyboardButton(
            f"{G['eye']}  #{t['id']}", callback_data=f"ticket_view_{t['id']}"))
    kb.add(types.InlineKeyboardButton(
        f"{G['back']}  {sc('Admin')}", callback_data="menu_admin"))
    show_text(call.message.chat.id, cap, kb, call=call)

def render_adm_admins(call: types.CallbackQuery) -> None:
    if not is_owner(call.from_user.id):
        ack(call, "Owner only"); return
    d = db_load()["admins"]
    rows = "\n".join(
        f"{G['bullet']} <code>{uid}</code> — {esc(a.get('role'))}"
        for uid, a in d.items()
    ) or f"<i>{sc('no extra admins yet')}</i>"
    cap = (
        f"<b>{G['shield']} {sc('Admins')}</b>\n"
        f"{G['div_eq']}\n{rows}\n{G['div']}\n"
        f"{sc('Send')} <code>add &lt;uid&gt; &lt;role&gt;</code>\n"
        f"  {sc('Roles')}: <code>view-only</code>, <code>manage-users</code>, <code>full-access</code>\n"
        f"{sc('Send')} <code>del &lt;uid&gt;</code>"
    )
    USER_STATES[call.from_user.id] = {"flow": "await_admin_admins"}
    show_text(call.message.chat.id, cap, back_admin_kb(), call=call)

def render_adm_audit(call: types.CallbackQuery) -> None:
    d = db_load()["audit"][-25:]
    rows = "\n".join(
        f"{G['bullet']} {esc(a['ts'][11:19])} uid {a['uid']} → {esc(a['action'])} {esc(a.get('detail', ''))[:60]}"
        for a in reversed(d)
    ) or f"<i>{sc('no audit entries yet')}</i>"
    cap = (
        f"<b>{G['eye']} {sc('Recent Audit')}</b>\n"
        f"{G['div_eq']}\n{rows}\n{G['div']}"
    )
    show_text(call.message.chat.id, cap, back_admin_kb(), call=call)

def render_adm_github(call: types.CallbackQuery) -> None:
    enabled = gh_enabled()
    cap = (
        f"<b>{G['cog']} {sc('GitHub Backup')}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Configured', 'Yes' if enabled else 'No')}\n"
        f"{bullet('Repo', GH['repo'] or '—')}\n"
        f"{bullet('Branch', GH['branch'])}\n"
        f"{bullet('Interval', str(GH['intervalMin']) + ' min')}\n"
        f"{bullet('Auto', 'On' if GH['autoEnabled'] else 'Off')}\n"
        f"{bullet('Last', fmt_ts(GH['lastBackup']))}\n"
        f"{bullet('Last err', GH['lastError'] or '—')}\n"
        f"{G['div']}"
    )
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{G['plus']}  Backup Now", callback_data="gh_backup_now"),
        types.InlineKeyboardButton(f"{G['refresh']}  Restore Latest", callback_data="gh_restore_now"),
    )
    kb.add(types.InlineKeyboardButton(
        f"{G['rec'] if GH['autoEnabled'] else G['rec_off']}  "
        f"Auto Backup: {'ON' if GH['autoEnabled'] else 'OFF'}",
        callback_data="gh_toggle_auto"))
    kb.add(
        types.InlineKeyboardButton(f"{G['key']}  Set Token", callback_data="gh_set_token"),
        types.InlineKeyboardButton(f"{G['diamond']}  Set Repo", callback_data="gh_set_repo"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{G['arrow']}  Set Branch", callback_data="gh_set_branch"),
        types.InlineKeyboardButton(f"{G['cog']}  Interval", callback_data="gh_set_interval"),
    )
    kb.add(types.InlineKeyboardButton(f"{G['no']}  Clear", callback_data="gh_clear"))
    kb.add(types.InlineKeyboardButton(f"{G['back']}  Admin", callback_data="menu_admin"))
    show_text(call.message.chat.id, cap, kb, call=call)

def render_adm_security(call: types.CallbackQuery) -> None:
    d = db_load()
    scan_log = d.get("scan_log", [])
    blocked = sum(1 for s in scan_log if s.get("verdict") == "DANGEROUS")
    cap = (
        f"<b>{G['lock']} {sc('Security')}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Total scans', len(scan_log))}\n"
        f"{bullet('Blocked files', blocked)}\n"
        f"{bullet('Encryption', 'Fernet (AES-128-CBC) per file')}\n"
        f"{bullet('Key storage', 'GitHub' if KEYRING.gh_enabled() else 'Local cache')}\n"
        f"{bullet('Path traversal', 'blocked (safe_path_join)')}\n"
        f"{bullet('Secret env strip', 'active')}\n"
        f"{G['div']}"
    )
    show_text(call.message.chat.id, cap, back_admin_kb(), call=call)

def render_adm_maint(call: types.CallbackQuery) -> None:
    cur = bool(get_setting("maintenance", False))
    cap = (
        f"<b>{G['warn']} {sc('Maintenance Mode')}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('State', 'ON' if cur else 'OFF')}\n"
        f"{sc('When ON, only admins can use the bot')}."
    )
    kb = types.InlineKeyboardMarkup()
    label = "Turn OFF" if cur else "Turn ON"
    kb.add(types.InlineKeyboardButton(
        f"{G['refresh']}  {sc(label)}", callback_data="adm_maint_toggle"))
    kb.add(types.InlineKeyboardButton(
        f"{G['back']}  {sc('Admin')}", callback_data="menu_admin"))
    show_text(call.message.chat.id, cap, kb, call=call)

def render_adm_settings(call: types.CallbackQuery) -> None:
    running_n = sum(1 for x in RUNNING.values() if x['proc'].poll() is None)
    total_bots = len(db_load_ro()['bots'])
    cap = (
        f"<b>{G['cog']} {sc('Settings')}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Brand', BRAND_TAG)}\n"
        f"{bullet('Owner ID', OWNER_ID)}\n"
        f"{bullet('Keep-alive port', KEEPALIVE_PORT)}\n"
        f"{bullet('GitHub keys', 'GitHub' if KEYRING.gh_enabled() else 'Local cache')}\n"
        f"{bullet('GitHub backup', 'On' if gh_enabled() and GH['autoEnabled'] else 'Off')}\n"
        f"{bullet('Bots running', str(running_n) + ' / ' + str(total_bots))}\n"
        f"{G['div']}"
    )
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{G['cog']}  Edit Brand", callback_data="adm_set_brand"),
        types.InlineKeyboardButton(f"{G['shield']}  Transfer Owner", callback_data="adm_set_owner"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{G['refresh']}  Reload Caches", callback_data="adm_set_reload"),
        types.InlineKeyboardButton(f"{G['eye']}  System Info", callback_data="adm_set_sysinfo"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{G['refresh']}  Restart All Bots", callback_data="adm_set_restart_all"),
        types.InlineKeyboardButton(f"{G['no']}  Stop All Bots", callback_data="adm_set_stop_all"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{G['warn']}  Clean Orphans", callback_data="adm_set_clean_orphans"),
        types.InlineKeyboardButton(f"{G['upload']}  Export Data", callback_data="adm_set_export"),
    )
    kb.add(types.InlineKeyboardButton(f"{G['back']}  Admin", callback_data="menu_admin"))
    show_text(call.message.chat.id, cap, kb, call=call)

def render_adm_pending(call: types.CallbackQuery) -> None:
    items = pending_list()
    if not items:
        cap = (
            f"<b>{G['eye']} {sc('Pending Uploads')}</b>\n"
            f"{G['div_eq']}\n<i>{sc('Inbox is empty')}.</i>\n{G['div']}"
        )
        show_text(call.message.chat.id, cap, back_admin_kb(), call=call)
        return
    rows = []
    kb = types.InlineKeyboardMarkup(row_width=2)
    for bid, info in items[:15]:
        b = find_bot(bid)
        nm = (b or {}).get("name") or info.get("file_name") or bid
        rows.append(
            f"{G['bullet']} <code>{esc(bid)}</code> — {esc(nm)} "
            f"• uid {info.get('user_id')} "
            f"• {fmt_bytes(info.get('size', 0))}"
        )
        kb.add(
            types.InlineKeyboardButton(f"{G['ok']}  OK {esc(nm)[:18]}",
                                       callback_data=f"appr_ok_{bid}"),
            types.InlineKeyboardButton(f"{G['no']}  No {esc(nm)[:18]}",
                                       callback_data=f"appr_no_{bid}"),
        )
    kb.add(types.InlineKeyboardButton(f"{G['back']}  {sc('Admin')}", callback_data="menu_admin"))
    cap = (
        f"<b>{G['eye']} {sc('Pending Uploads')} ({len(items)})</b>\n"
        f"{G['div_eq']}\n" + "\n".join(rows) + f"\n{G['div']}"
    )
    show_text(call.message.chat.id, cap, kb, call=call)

# ═════════════════════════════════════════════════════════════════
#  APPROVAL SYSTEM
# ═════════════════════════════════════════════════════════════════

def approval_required() -> bool:
    return bool(get_setting("approval_required", True))

def set_approval_required(on: bool) -> None:
    set_setting("approval_required", bool(on))

def _pending_load() -> Dict[str, Any]:
    return dict(get_setting("pending_uploads", {}) or {})

def _pending_save(d: Dict[str, Any]) -> None:
    set_setting("pending_uploads", d)

def pending_add(bot_id: str, info: Dict[str, Any]) -> None:
    p = _pending_load()
    p[bot_id] = info
    _pending_save(p)

def pending_remove(bot_id: str) -> Optional[Dict[str, Any]]:
    p = _pending_load()
    info = p.pop(bot_id, None)
    _pending_save(p)
    return info

def pending_list() -> List[Tuple[str, Dict[str, Any]]]:
    return list(_pending_load().items())

def _send_approval_request_to_admins(b: Dict[str, Any], info: Dict[str, Any]) -> None:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{G['ok']}  {sc('Approve')}",
                                   callback_data=f"appr_ok_{b['_id']}"),
        types.InlineKeyboardButton(f"{G['no']}  {sc('Reject')}",
                                   callback_data=f"appr_no_{b['_id']}"),
    )
    txt = (
        f"<b>{G['warn']} {sc('New bot upload — awaiting approval')}</b>\n"
        f"{G['div']}\n"
        f"{bullet('User', '{} (@{})'.format(info.get('user_name') or '', info.get('user_username') or '-'))}\n"
        f"{bullet('User ID', info.get('user_id'))}\n"
        f"{bullet('Bot Name', b.get('name'))}\n"
        f"{bullet('Bot ID', b['_id'])}\n"
        f"{bullet('File', info.get('file_name'))}\n"
        f"{bullet('Files', info.get('file_count'))}\n"
        f"{bullet('Size', fmt_bytes(info.get('size', 0)))}\n"
        f"{G['div']}"
    )
    targets: List[int] = []
    if OWNER_ID:
        targets.append(OWNER_ID)
    for uid_str in (db_load().get("admins") or {}).keys():
        try:
            uid_i = int(uid_str)
            if uid_i not in targets:
                targets.append(uid_i)
        except Exception:
            pass
    for tgt in targets:
        try:
            bot.send_message(tgt, txt, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass

def approve_bot(bot_id: str, admin_uid: int) -> Dict[str, Any]:
    b = find_bot(bot_id)
    if not b:
        return {"ok": False, "error": "Bot not found."}
    pending_remove(bot_id)
    b["approval_status"] = "approved"
    b["approval_reason"] = ""
    b["status"] = "stopped"
    save_bot(b)
    audit(admin_uid, "approve_bot", f"bot={bot_id}")
    try:
        owner = b.get("owner")
        if owner:
            bot.send_message(owner,
                f"<b>{G['ok']} {sc('Your bot was approved')}</b>\n"
                f"{bullet('Bot', b.get('name'))}\n"
                f"{sc('Starting it now')}…",
                parse_mode="HTML")
    except Exception:
        pass
    def _bg() -> None:
        try:
            res = start_child(b)
            if not res.get("ok") and b.get("owner"):
                try:
                    bot.send_message(b["owner"],
                        f"<b>{G['no']} {sc('Auto-start failed after approval')}</b>\n"
                        f"{bullet('Error', esc(res.get('error', '')))}",
                        parse_mode="HTML")
                except Exception:
                    pass
        except Exception as e:
            print(f"[approve_bot bg] {e}")
    threading.Thread(target=_bg, daemon=True).start()
    return {"ok": True}

def reject_bot(bot_id: str, admin_uid: int, reason: str = "") -> Dict[str, Any]:
    b = find_bot(bot_id)
    if not b:
        return {"ok": False, "error": "Bot not found."}
    pending_remove(bot_id)
    b["approval_status"] = "rejected"
    b["approval_reason"] = reason or "rejected by admin"
    b["status"] = "rejected"
    save_bot(b)
    try:
        for f in b.get("enc_files") or []:
            try:
                Path(f.get("enc_path", "")).unlink(missing_ok=True)
            except Exception:
                pass
        rmrf(b.get("dir", ""))
    except Exception:
        pass
    try:
        db = db_load()
        db["bots"].pop(bot_id, None)
        db_save(db)
    except Exception:
        pass
    audit(admin_uid, "reject_bot", f"bot={bot_id} reason={reason}")
    try:
        owner = b.get("owner")
        if owner:
            bot.send_message(owner,
                f"<b>{G['no']} {sc('Your bot was rejected')}</b>\n"
                f"{bullet('Bot', b.get('name'))}\n"
                f"{bullet('Reason', reason or 'No reason given')}",
                parse_mode="HTML")
    except Exception:
        pass
    return {"ok": True}

# ═════════════════════════════════════════════════════════════════
#  COMMON HELPERS
# ═════════════════════════════════════════════════════════════════

def ack(call: types.CallbackQuery, text: str = "") -> None:
    try:
        bot.answer_callback_query(call.id, text=text)
    except Exception:
        pass

def maintenance_block(uid: int) -> bool:
    return get_setting("maintenance", False) and not is_admin(uid)

def banned_block(call_or_msg: Any) -> bool:
    uid = call_or_msg.from_user.id
    u = db_load_ro()["users"].get(str(uid))
    if u and u.get("banned"):
        try:
            chat = call_or_msg.message.chat.id if hasattr(call_or_msg, "message") else call_or_msg.chat.id
            bot.send_message(chat,
                f"<b>{G['no']} {sc('You are banned')}</b>\n"
                f"{bullet('Reason', u.get('ban_reason') or '—')}",
                parse_mode="HTML")
        except Exception:
            pass
        return True
    return False

class RateLimiter:
    def __init__(self, max_actions: int = 30, window_s: int = 60) -> None:
        self.max = max_actions
        self.window = window_s
        self._bucket: Dict[int, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, uid: int) -> bool:
        now = time.time()
        with self._lock:
            q = self._bucket[uid]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.max:
                return False
            q.append(now)
            return True

RATE = RateLimiter(max_actions=40, window_s=60)
UPLOAD_RATE = RateLimiter(max_actions=8, window_s=300)

def maybe_auto_ban(uid: int, reason: str) -> None:
    try:
        notify_owner(f"<b>{G['warn']} {sc('rate abuse')}</b>\nUser <code>{uid}</code> ({reason})")
    except Exception:
        pass

# ═════════════════════════════════════════════════════════════════
#  UPLOAD HANDLER
# ═════════════════════════════════════════════════════════════════

def _handle_bot_upload(m: types.Message) -> None:
    uid = m.from_user.id
    u = db_load()["users"][str(uid)]
    if len(list_user_bots(uid)) >= user_max_bots(u):
        bot.reply_to(m, f"{G['no']} {sc('You hit your bot slot limit')}. {sc('Upgrade or delete one')}.")
        return
    doc = m.document
    if not doc:
        return
    if doc.file_size and doc.file_size > MAX_UPLOAD_BYTES:
        bot.reply_to(m, f"{G['no']} {sc('File too big')} (>{MAX_UPLOAD_BYTES // (1024*1024)} Mʙ).")
        return
    fname = doc.file_name or "upload.bin"
    if not re.match(r"^[A-Za-z0-9._\-]+$", fname):
        bot.reply_to(m, f"{G['warn']} {sc('Suspicious filename, please rename')}.")
        return
    try:
        f = bot.get_file(doc.file_id)
        raw = bot.download_file(f.file_path)
    except Exception as e:
        bot.reply_to(m, f"{G['no']} {sc('download error')}: <code>{esc(e)}</code>",
                     parse_mode="HTML")
        return

    bot_id = secrets.token_hex(8)
    bot_dir = DIRS["sandbox"] / f"{uid}_{bot_id}"
    bot_dir.mkdir(parents=True, exist_ok=True)
    name = safe_name(Path(fname).stem)
    doc_db = {
        "_id": bot_id, "owner": uid, "name": name,
        "dir": str(bot_dir), "created": ts_iso(),
        "enc_files": [], "env": {}, "status": "stopped", "cron": {},
    }

    files_added: List[Tuple[str, bytes]] = []
    if fname.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    rel = member.filename.replace("\\", "/")
                    if rel.startswith("/") or ".." in rel.split("/"):
                        continue
                    try:
                        safe_path_join(bot_dir, rel)
                    except ValueError:
                        continue
                    files_added.append((rel, zf.read(member)))
        except zipfile.BadZipFile:
            bot.reply_to(m, f"{G['no']} {sc('not a valid zip')}")
            rmrf(bot_dir); return
    else:
        files_added.append((fname, raw))

    # Security scan
    scan_msg = bot.reply_to(m, f"{G['shield']} {sc('Security scan in progress...')}",
                             parse_mode="HTML")
    scan = _run_security_scan(files_added, uploader_uid=uid)
    recommend = scan.get("recommendation", "APPROVE")
    risk = scan.get("risk_score", 0)
    verdict = scan.get("verdict", "SAFE")
    summary = scan.get("summary", "")
    threats = scan.get("all_threats") or []
    try:
        bot.delete_message(m.chat.id, scan_msg.message_id)
    except Exception:
        pass

    if recommend == "REJECT":
        rmrf(bot_dir)
        threat_lines = "\n".join(f"• {esc(t)}" for t in threats[:5])
        bot.reply_to(m,
            f"<b>🚫 {sc('File Blocked — Security Threat Detected')}</b>\n"
            f"{G['div']}\n"
            f"{bullet('File', fname)}\n"
            f"{bullet('Risk Score', f'{risk}/100')}\n"
            f"{bullet('Verdict', verdict)}\n"
            f"{G['div']}\n"
            f"<b>{sc('Threats')}:</b>\n{threat_lines or sc('See admin alert')}",
            parse_mode="HTML")
        notify_owner(
            f"<b>🚨 {sc('DANGEROUS FILE BLOCKED')}</b>\n"
            f"{G['div']}\n"
            f"{bullet('User', '{} (@{})'.format(m.from_user.first_name or '', m.from_user.username or '-'))}\n"
            f"{bullet('User ID', uid)}\n"
            f"{bullet('File', fname)}\n"
            f"{bullet('Risk', f'{risk}/100')}\n"
            f"{bullet('Verdict', verdict)}\n"
            f"<b>{sc('Threats')}:</b>\n" +
            "\n".join(f"• {esc(t)}" for t in threats[:3]))
        audit(uid, "security_reject", f"file={fname} risk={risk} verdict={verdict}")
        return

    if recommend == "MANUAL_REVIEW":
        doc_db["security_scan"] = {
            "verdict": verdict, "risk_score": risk, "summary": summary,
        }

    for rel, plain in files_added:
        meta = store_uploaded_file(m.from_user, rel, plain)
        doc_db["enc_files"].append({
            "key_id": meta["key_id"], "enc_path": meta["path"],
            "filename": Path(rel).name, "rel_path": rel,
        })

    total_size = sum(len(p) for _, p in files_added)

    needs_approval = approval_required() and not is_admin(uid) and OWNER_ID > 0
    if needs_approval:
        doc_db["approval_status"] = "pending"
        doc_db["status"] = "pending_approval"
    save_bot(doc_db)
    db = db_load()
    db["users"][str(uid)]["stats"]["bots_uploaded"] = int(
        db["users"][str(uid)]["stats"].get("bots_uploaded", 0)) + 1
    db_save(db)
    USER_STATES.pop(uid, None)

    if needs_approval:
        info = {
            "user_id": uid, "user_name": m.from_user.first_name or "",
            "user_username": m.from_user.username or "",
            "chat_id": m.chat.id, "msg_id": m.message_id,
            "file_name": fname, "file_count": len(files_added),
            "size": total_size, "ts": ts_iso(),
        }
        pending_add(bot_id, info)
        try:
            _send_approval_request_to_admins(doc_db, info)
        except Exception as e:
            print(f"[approval notify] {e}")
        bot.reply_to(m,
            f"<b>{G['warn']} {sc('Pending admin approval')}</b>\n"
            f"{G['div']}\n"
            f"{bullet('Bot Name', name)}\n"
            f"{bullet('Files', len(files_added))}\n"
            f"{bullet('Size', fmt_bytes(total_size))}\n"
            f"{G['div']}\n"
            f"{sc('Your bot will start automatically once an admin approves it')}.",
            parse_mode="HTML")
        return

    notify_owner(
        f"<b>{G['upload']} ɴᴇᴡ ʙᴏᴛ ᴜᴘʟᴏᴀᴅ</b>\n"
        f"{G['div']}\n"
        f"{bullet('File', fname)}\n"
        f"{bullet('User', '{} (@{})'.format(m.from_user.first_name or '', m.from_user.username or '-'))}\n"
        f"{bullet('User ID', uid)}\n"
        f"{bullet('Bot Name', name)}\n"
        f"{bullet('Files', len(files_added))}\n"
        f"{bullet('Size', fmt_bytes(total_size))}\n"
        f"{G['div']}")

    kind, _ = detect_entry(bot_dir)

    def _make_bar(pct: int, status: str, kind_str: str = "") -> str:
        filled = int(pct / 5)
        bar = "▓" * filled + "░" * (20 - filled)
        return (
            f"<b>{G['ok']} {sc('Bot stored encrypted')}</b>\n"
            f"{bullet('Name', name)}\n"
            f"{bullet('Files', len(files_added))}\n"
            f"{bullet('Kind', kind_str or kind or 'auto-detect on start')}\n"
            f"<code>{bar} {pct}%</code>\n"
            f"{status}"
        )

    sent = bot.reply_to(m, _make_bar(0, sc("Starting...")), parse_mode="HTML")
    msg_id = sent.message_id
    cid = m.chat.id

    def _edit(pct: int, status: str, kind_str: str = "") -> None:
        try:
            bot.edit_message_text(_make_bar(pct, status, kind_str),
                                  chat_id=cid, message_id=msg_id, parse_mode="HTML")
        except Exception:
            pass

    def _bg_start(doc: Dict[str, Any]) -> None:
        try:
            _edit(10, sc("Decrypting files..."))
            time.sleep(0.8)
            _edit(30, sc("Installing dependencies..."))
            time.sleep(0.8)
            _edit(50, sc("Setting up environment..."))
            time.sleep(0.8)
            _edit(70, sc("Launching bot..."))
            res = start_child(doc)
            if res.get("ok"):
                _edit(100, f"<b>{G['play']} {sc('Bot is running!')}</b>",
                      res.get("kind", ""))
                time.sleep(1.5)
                try: bot.delete_message(cid, msg_id)
                except Exception: pass
                bots = list_user_bots(uid)
                u2 = db_load()["users"][str(uid)]
                cap = (
                    f"<b>{G['diamond']} {sc('Your Bots')}</b>\n"
                    f"{G['div_eq']}\n"
                    f"{bullet('Slots', str(len(bots)) + ' / ' + str(user_max_bots(u2)))}\n"
                )
                kb = types.InlineKeyboardMarkup()
                for b in sorted(bots, key=lambda x: x.get("name", "")):
                    running = b["_id"] in RUNNING and RUNNING[b["_id"]]["proc"].poll() is None
                    mark = G["play"] if running else G["stop"]
                    kb.add(types.InlineKeyboardButton(
                        f"{mark}  {sc(b['name'])[:30]}",
                        callback_data=f"bot_view_{b['_id']}"))
                kb.add(
                    types.InlineKeyboardButton(f"{G['plus']}  Upload", callback_data="menu_upload"),
                    types.InlineKeyboardButton(f"{G['back']}  Main Menu", callback_data="menu_main"),
                )
                bot.send_message(cid, cap, parse_mode="HTML", reply_markup=kb)
            else:
                _edit(0,
                      f"<b>{G['no']} {sc('Auto-start failed')}</b>\n"
                      f"{bullet('Error', esc(res.get('error', '')))}\n"
                      f"{sc('Open My Bots → Logs to see why')}.")
        except Exception as e:
            try:
                _edit(0, f"{G['no']} {sc('Auto-start error')}: <code>{esc(str(e))}</code>")
            except Exception:
                pass

    threading.Thread(target=_bg_start, args=(doc_db,), daemon=True).start()

# ═════════════════════════════════════════════════════════════════
#  TEXT FLOW HANDLERS
# ═════════════════════════════════════════════════════════════════

def _handle_env_kv(m: types.Message, st: Dict[str, Any]) -> None:
    text = m.text.strip()
    if "=" not in text:
        bot.reply_to(m, f"{G['no']} {sc('Use')} <code>KEY=VALUE</code>.", parse_mode="HTML"); return
    key, _, value = text.partition("=")
    key = key.strip(); value = value.strip()
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        bot.reply_to(m, f"{G['no']} {sc('Invalid key')}."); return
    if key in SECRET_ENV_NAMES:
        bot.reply_to(m, f"{G['no']} {sc('That env name is protected')}."); return
    b = find_bot(st["bot_id"])
    if not b:
        bot.reply_to(m, f"{G['no']} {sc('Bot not found')}."); return
    env = b.get("env") or {}
    env[key] = value
    b["env"] = env
    save_bot(b)
    USER_STATES.pop(m.from_user.id, None)
    bot.reply_to(m, f"{G['ok']} {sc('Saved')} <code>{esc(key)}</code>", parse_mode="HTML")

def _handle_pip_install(m: types.Message, st: Dict[str, Any]) -> None:
    text = (m.text or "").strip()
    USER_STATES.pop(m.from_user.id, None)
    if not text:
        bot.reply_to(m, f"{G['no']} {sc('Nothing to install')}."); return
    pkgs = [p for p in text.split() if p]
    bad = [p for p in pkgs if not re.match(r"^[A-Za-z0-9_\-\.\[\]=<>!~,+]+$", p) or p.startswith("-")]
    if bad:
        bot.reply_to(m,
            f"{G['no']} {sc('Invalid package spec')}: <code>{esc(' '.join(bad))}</code>",
            parse_mode="HTML"); return
    if len(pkgs) > 15:
        bot.reply_to(m, f"{G['no']} {sc('Too many packages (max 15)')}."); return
    b = find_bot(st["bot_id"])
    if not b:
        bot.reply_to(m, f"{G['no']} {sc('Bot not found')}."); return
    if b["owner"] != m.from_user.id and not is_admin(m.from_user.id):
        bot.reply_to(m, f"{G['no']} {sc('Not yours')}."); return
    bot_dir = Path(b["dir"])
    deps_dir = bot_dir / ".deps"
    deps_dir.mkdir(parents=True, exist_ok=True)
    status = bot.reply_to(m,
        f"{G['refresh']} {sc('Installing')} <code>{esc(' '.join(pkgs))}</code> ...",
        parse_mode="HTML")
    pip_env = _pip_env(deps_dir)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "--target", str(deps_dir), *_PIP_BASE_FLAGS] + pkgs,
            capture_output=True, text=True, timeout=180, env=pip_env,
        )
        ok = (proc.returncode == 0)
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        tail = "\n".join([ln for ln in out.splitlines() if ln.strip()][-10:])[:1500]
        head = f"{G['ok']} {sc('Installed')}" if ok else f"{G['no']} {sc('Install failed')}"
        try:
            bot.edit_message_text(
                f"<b>{head}</b>\n"
                f"{G['div']}\n"
                f"<b>{sc('Packages')}:</b> <code>{esc(' '.join(pkgs))}</code>\n"
                f"<pre>{esc(tail) or '(no output)'}</pre>",
                chat_id=status.chat.id, message_id=status.message_id, parse_mode="HTML")
        except Exception:
            bot.send_message(m.chat.id, f"{head}\n<pre>{esc(tail)}</pre>", parse_mode="HTML")
        audit(m.from_user.id, "pip_install",
              f"bot={b['_id']} pkgs={' '.join(pkgs)} rc={proc.returncode}")
    except subprocess.TimeoutExpired:
        bot.send_message(m.chat.id, f"{G['no']} {sc('Install timed out')}.")
    except Exception as e:
        bot.send_message(m.chat.id,
            f"{G['no']} {sc('Install error')}: <code>{esc(str(e))}</code>", parse_mode="HTML")

def _handle_cron(m: types.Message, st: Dict[str, Any]) -> None:
    text = m.text.strip().lower()
    b = find_bot(st["bot_id"])
    if not b:
        bot.reply_to(m, f"{G['no']} {sc('Bot not found')}."); return
    if text == "off":
        b["cron"] = {}; save_bot(b); USER_STATES.pop(m.from_user.id, None)
        bot.reply_to(m, f"{G['ok']} {sc('Cron disabled')}"); return
    cron = b.get("cron") or {}
    for tok in text.split():
        if "=" not in tok:
            continue
        k, v = tok.split("=", 1)
        if k not in {"restart", "backup"}:
            continue
        try:
            iv = int(v)
        except Exception:
            continue
        if iv <= 0:
            continue
        cron[f"{k}_hours"] = iv
    b["cron"] = cron
    save_bot(b)
    USER_STATES.pop(m.from_user.id, None)
    bot.reply_to(m, f"{G['ok']} {sc('Cron updated')}: <code>{esc(json.dumps(cron))}</code>",
                 parse_mode="HTML")

def _handle_admin_finduser(m: types.Message) -> None:
    if not is_admin(m.from_user.id):
        return
    USER_STATES.pop(m.from_user.id, None)
    text = m.text.strip()
    if not text.lstrip("@").lstrip("-").isdigit() and not text.startswith("@"):
        return
    d = db_load()
    target = None
    if text.startswith("@"):
        for u in d["users"].values():
            if (u.get("username") or "").lower() == text[1:].lower():
                target = u; break
    else:
        try:
            target = d["users"].get(str(int(text)))
        except Exception:
            target = None
    if not target:
        bot.reply_to(m, f"{G['no']} {sc('No such user')}."); return
    bots = list_user_bots(target["_id"])
    txt = (
        f"<b>{G['user']} {sc('User')} {target['_id']}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Name', target.get('name'))}\n"
        f"{bullet('Username', '@' + (target.get('username') or '—'))}\n"
        f"{bullet('Plan', PLAN_LIMITS.get(target.get('plan'), {}).get('name'))}\n"
        f"{bullet('Until', fmt_ts(target.get('plan_expires')))}\n"
        f"{bullet('Wallet', '৳' + str(target.get('wallet', 0)))}\n"
        f"{bullet('Banned', target.get('banned'))}\n"
        f"{bullet('Bots', len(bots))}\n"
        f"{bullet('Joined', fmt_ts(target.get('joined')))}\n"
        f"{G['div']}"
    )
    bot.reply_to(m, txt, parse_mode="HTML", reply_markup=back_admin_kb())

def _handle_ban_cmd(m: types.Message) -> None:
    if not is_admin(m.from_user.id):
        return
    if not admin_can(m.from_user.id, "ban_user"):
        bot.reply_to(m, f"{G['no']} {sc('insufficient permission')}"); return
    USER_STATES.pop(m.from_user.id, None)
    parts = m.text.split(maxsplit=2)
    if len(parts) < 2:
        bot.reply_to(m, f"{G['no']} {sc('format')}: <code>ban &lt;uid&gt; &lt;reason&gt;</code>",
                     parse_mode="HTML"); return
    op = parts[0].lower()
    try:
        uid = int(parts[1])
    except Exception:
        bot.reply_to(m, f"{G['no']} {sc('bad uid')}"); return
    reason = parts[2] if len(parts) > 2 else ""
    d = db_load()
    if str(uid) not in d["users"]:
        bot.reply_to(m, f"{G['no']} {sc('no such user')}"); return
    if op == "ban":
        d["users"][str(uid)]["banned"] = True
        d["users"][str(uid)]["ban_reason"] = reason
        db_save(d)
        audit(m.from_user.id, "ban_user", f"uid={uid} reason={reason}")
        try:
            bot.send_message(uid,
                f"<b>{G['no']} {sc('You have been banned')}</b>\n{bullet('Reason', reason)}",
                parse_mode="HTML")
        except Exception:
            pass
        bot.reply_to(m, f"{G['ok']} {sc('banned')} {uid}"); return
    if op == "unban":
        d["users"][str(uid)]["banned"] = False
        d["users"][str(uid)]["ban_reason"] = ""
        db_save(d)
        audit(m.from_user.id, "unban_user", f"uid={uid}")
        try:
            bot.send_message(uid, f"<b>{G['ok']} {sc('You have been unbanned')}</b>", parse_mode="HTML")
        except Exception:
            pass
        bot.reply_to(m, f"{G['ok']} {sc('unbanned')} {uid}"); return

def _handle_giveplan_cmd(m: types.Message) -> None:
    if not is_admin(m.from_user.id):
        return
    if not admin_can(m.from_user.id, "give_plan"):
        bot.reply_to(m, f"{G['no']} {sc('insufficient permission')}"); return
    USER_STATES.pop(m.from_user.id, None)
    parts = m.text.split()
    if len(parts) < 2:
        bot.reply_to(m, f"{G['no']} {sc('format')}: <code>uid plan [days]</code>",
                     parse_mode="HTML"); return
    try:
        uid = int(parts[0])
    except Exception:
        bot.reply_to(m, f"{G['no']} {sc('bad uid')}"); return
    plan = parts[1]
    if plan not in PLAN_LIMITS:
        bot.reply_to(m, f"{G['no']} {sc('bad plan')}"); return
    days = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
    if not grant_plan(uid, plan, days=days):
        bot.reply_to(m, f"{G['no']} {sc('failed')}"); return
    audit(m.from_user.id, "give_plan", f"uid={uid} plan={plan} days={days}")
    bot.reply_to(m, f"{G['ok']} {sc('granted')} {plan} {sc('to')} {uid}")

def _handle_broadcast(m: types.Message) -> None:
    if not is_admin(m.from_user.id):
        return
    USER_STATES.pop(m.from_user.id, None)
    text = m.text or ""
    target_plan: Optional[str] = None
    schedule_at: Optional[datetime] = None

    while True:
        head, _, rest = text.partition("\n")
        head = head.strip()
        if head.startswith("plan:"):
            target_plan = head.split(":", 1)[1].strip().lower()
            text = rest
        elif head.startswith("at:"):
            try:
                schedule_at = datetime.strptime(head[3:].strip(),
                                                "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            except Exception:
                bot.reply_to(m, f"{G['no']} {sc('bad time format, use YYYY-MM-DD HH:MM UTC')}")
                return
            text = rest
        else:
            break

    text = text.strip()
    if not text:
        bot.reply_to(m, f"{G['no']} {sc('empty broadcast')}"); return

    if schedule_at:
        d = db_load()
        d["scheduled_broadcasts"].append({
            "at": schedule_at.isoformat(), "text": text,
            "plan": target_plan, "by": m.from_user.id,
        })
        db_save(d)
        audit(m.from_user.id, "broadcast_schedule",
              f"at={schedule_at.isoformat()} plan={target_plan}")
        bot.reply_to(m, f"{G['ok']} {sc('scheduled for')} {fmt_ts(schedule_at.isoformat())}")
        return

    sent, skipped = _send_broadcast(text, target_plan)
    audit(m.from_user.id, "broadcast",
          f"sent={sent} skipped={skipped} plan={target_plan}")
    bot.reply_to(m, f"{G['ok']} {sc('broadcast done')} — Sᴇɴᴛ {sent}, Sᴋɪᴘᴘᴇᴅ {skipped}")

def _send_broadcast(text: str, target_plan: Optional[str]) -> Tuple[int, int]:
    sent = skipped = 0
    d = db_load()
    for u in d["users"].values():
        if u.get("banned"):
            skipped += 1; continue
        if target_plan and u.get("plan") != target_plan:
            skipped += 1; continue
        try:
            bot.send_message(int(u["_id"]), text, parse_mode="HTML",
                             disable_web_page_preview=True)
            sent += 1
            time.sleep(0.04)
        except Exception:
            skipped += 1
    return sent, skipped

def _handle_admin_admins(m: types.Message) -> None:
    if not is_owner(m.from_user.id):
        return
    USER_STATES.pop(m.from_user.id, None)
    parts = m.text.split()
    if len(parts) < 2:
        return
    op = parts[0].lower()
    d = db_load()
    if op == "add" and len(parts) >= 3:
        try:
            uid = int(parts[1])
        except Exception:
            bot.reply_to(m, f"{G['no']} {sc('bad uid')}"); return
        role = parts[2]
        if role not in {"view-only", "manage-users", "full-access"}:
            bot.reply_to(m, f"{G['no']} {sc('bad role')}"); return
        d["admins"][str(uid)] = {"role": role, "added": ts_iso(), "by": m.from_user.id}
        db_save(d)
        audit(m.from_user.id, "admin_add", f"uid={uid} role={role}")
        bot.reply_to(m, f"{G['ok']} {sc('added admin')} {uid} ({role})"); return
    if op == "del" and len(parts) >= 2:
        try:
            uid = int(parts[1])
        except Exception:
            bot.reply_to(m, f"{G['no']} {sc('bad uid')}"); return
        if d["admins"].pop(str(uid), None):
            db_save(d)
            audit(m.from_user.id, "admin_del", f"uid={uid}")
            bot.reply_to(m, f"{G['ok']} {sc('removed')} {uid}"); return

def _handle_ticket_subject(m: types.Message) -> None:
    USER_STATES[m.from_user.id] = {"flow": "await_ticket_body", "subject": m.text.strip()[:120]}
    bot.reply_to(m, f"{G['ticket']} {sc('Now send the ticket body')}.")

def _handle_ticket_body(m: types.Message, st: Dict[str, Any]) -> None:
    subject = st.get("subject") or "Support"
    d = db_load()
    tid = rand_token(6)
    d["tickets"][tid] = {
        "id": tid, "uid": m.from_user.id, "subject": subject, "status": "open",
        "messages": [{"from": "user", "text": m.text, "ts": ts_iso()}],
        "opened_at": ts_iso(),
    }
    db_save(d)
    USER_STATES.pop(m.from_user.id, None)
    bot.reply_to(m, f"<b>{G['ok']} {sc('Ticket opened')} #{tid}</b>", parse_mode="HTML")
    notify_owner(
        f"<b>{G['ticket']} ɴᴇᴡ ᴛɪᴄᴋᴇᴛ #{tid}</b>\n"
        f"{bullet('From', m.from_user.id)}\n"
        f"{bullet('Subject', subject)}\n"
        f"{bullet('Body', m.text[:400])}")

def _handle_ticket_reply(m: types.Message, st: Dict[str, Any]) -> None:
    tid = st.get("tid")
    d = db_load()
    t = d["tickets"].get(tid)
    if not t:
        USER_STATES.pop(m.from_user.id, None); return
    if t["uid"] != m.from_user.id and not is_admin(m.from_user.id):
        USER_STATES.pop(m.from_user.id, None); return
    who = "admin" if is_admin(m.from_user.id) and t["uid"] != m.from_user.id else "user"
    t.setdefault("messages", []).append({"from": who, "text": m.text, "ts": ts_iso()})
    db_save(d)
    USER_STATES.pop(m.from_user.id, None)
    target = OWNER_ID if who == "user" else t["uid"]
    try:
        bot.send_message(target,
            f"<b>{G['ticket']} {sc('Ticket')} #{tid}</b> — {sc(who + ' replied')}\n"
            f"{esc(m.text)[:1000]}", parse_mode="HTML")
    except Exception:
        pass
    bot.reply_to(m, f"{G['ok']} {sc('reply sent')}")

def _handle_payment_proof(m: types.Message, st: Dict[str, Any]) -> None:
    method = st.get("method") or "unknown"
    plan = st.get("plan")
    p = PLAN_LIMITS.get(plan or "")
    pid = rand_token(8)
    d = db_load()
    d["payments"].append({
        "id": pid, "uid": m.from_user.id, "method": method, "plan": plan,
        "amount": (p or {}).get("price", 0),
        "status": "pending", "ts": ts_iso(), "telegram_msg_id": m.message_id,
    })
    db_save(d)
    USER_STATES.pop(m.from_user.id, None)
    try:
        bot.forward_message(OWNER_ID, m.chat.id, m.message_id)
    except Exception:
        pass
    notify_owner(
        f"<b>{G['wallet']} ɴᴇᴡ ᴘᴀʏᴍᴇɴᴛ ᴘʀᴏᴏғ</b>\n"
        f"{bullet('ID', pid)}\n"
        f"{bullet('From', m.from_user.id)}\n"
        f"{bullet('Method', method)}\n"
        f"{bullet('Plan', plan or '—')}\n"
        f"{bullet('Amount', '৳' + str((p or {}).get('price', 0)))}\n"
        f"{sc('Tap below to approve or reject')}.")
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(f"{G['ok']}  {sc('Approve')}", callback_data=f"payapprove_{pid}"),
        types.InlineKeyboardButton(f"{G['no']}  {sc('Reject')}", callback_data=f"payreject_{pid}"),
    )
    try:
        bot.send_message(OWNER_ID, f"<b>{sc('Decide')} #{pid}</b>",
                         parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    bot.reply_to(m, f"<b>{G['ok']} {sc('proof received')}</b>\n#{pid} — {sc('await admin')}",
                 parse_mode="HTML")

def _handle_payment_proof_text(m: types.Message, st: Dict[str, Any]) -> None:
    _handle_payment_proof(m, st)

def _handle_topup_proof(m: types.Message) -> None:
    pid = rand_token(8)
    cap = (m.caption or m.text or "").strip()
    amt = 0
    if cap.isdigit():
        amt = int(cap)
    else:
        ms = re.search(r"\d+", cap)
        if ms:
            amt = int(ms.group(0))
    d = db_load()
    d["payments"].append({
        "id": pid, "uid": m.from_user.id, "method": "topup", "plan": None,
        "amount": amt, "status": "pending", "ts": ts_iso(),
        "telegram_msg_id": m.message_id, "kind": "wallet_topup",
    })
    db_save(d)
    USER_STATES.pop(m.from_user.id, None)
    try:
        bot.forward_message(OWNER_ID, m.chat.id, m.message_id)
    except Exception:
        pass
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(f"{G['ok']}  {sc('Approve')}", callback_data=f"payapprove_{pid}"),
        types.InlineKeyboardButton(f"{G['no']}  {sc('Reject')}", callback_data=f"payreject_{pid}"),
    )
    notify_owner(
        f"<b>{G['wallet']} ᴡᴀʟʟᴇᴛ ᴛᴏᴘᴜᴘ</b>\n"
        f"{bullet('ID', pid)}\n"
        f"{bullet('From', m.from_user.id)}\n"
        f"{bullet('Amount', '৳' + str(amt))}")
    try:
        bot.send_message(OWNER_ID, f"<b>{sc('Decide')} #{pid}</b>",
                         parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    bot.reply_to(m, f"<b>{G['ok']} {sc('top-up proof received')}</b>", parse_mode="HTML")

def action_payment_approve(call: types.CallbackQuery, pid: str) -> None:
    if not admin_only_call(call, "approve_payment"):
        return
    d = db_load()
    pay = next((x for x in d["payments"] if x.get("id") == pid), None)
    if not pay:
        ack(call, "Not found"); return
    if pay.get("status") in ("approved", "rejected"):
        ack(call, f"Already {pay['status']}."); return
    pay["status"] = "approved"
    pay["approved_by"] = call.from_user.id
    pay["approved_at"] = ts_iso()
    db_save(d)
    if pay.get("kind") == "wallet_topup":
        u = d["users"].get(str(pay["uid"]))
        if u:
            u["wallet"] = int(u.get("wallet", 0)) + int(pay.get("amount", 0))
            db_save(d)
            try:
                bot.send_message(pay["uid"],
                    f"<b>{G['ok']} {sc('Wallet credited')}</b>\n"
                    f"{bullet('Amount', '৳' + str(pay['amount']))}", parse_mode="HTML")
            except Exception:
                pass
    elif pay.get("plan"):
        grant_plan(pay["uid"], pay["plan"])
    audit(call.from_user.id, "pay_approve", f"pid={pid}")
    ack(call, "Approved")
    try:
        bot.edit_message_text(f"<b>{G['ok']} {sc('Approved')} #{pid}</b>",
                              chat_id=call.message.chat.id,
                              message_id=call.message.message_id, parse_mode="HTML")
    except Exception:
        pass

def action_payment_reject(call: types.CallbackQuery, pid: str) -> None:
    if not admin_only_call(call, "approve_payment"):
        return
    d = db_load()
    pay = next((x for x in d["payments"] if x.get("id") == pid), None)
    if not pay:
        ack(call, "Not found"); return
    if pay.get("status") in ("approved", "rejected"):
        ack(call, f"Already {pay['status']}."); return
    pay["status"] = "rejected"
    pay["rejected_by"] = call.from_user.id
    pay["rejected_at"] = ts_iso()
    db_save(d)
    audit(call.from_user.id, "pay_reject", f"pid={pid}")
    try:
        bot.send_message(pay["uid"],
            f"<b>{G['no']} {sc('Payment rejected')}</b> #{pid}", parse_mode="HTML")
    except Exception:
        pass
    ack(call, "Rejected")
    try:
        bot.edit_message_text(f"<b>{G['no']} {sc('Rejected')} #{pid}</b>",
                              chat_id=call.message.chat.id,
                              message_id=call.message.message_id, parse_mode="HTML")
    except Exception:
        pass

# ═════════════════════════════════════════════════════════════════
#  START FLOW
# ═════════════════════════════════════════════════════════════════

def _is_private(m) -> bool:
    try:
        return m.chat.type == "private"
    except Exception:
        return True


    def _is_verified(uid: int) -> bool:
    return True

def require_verified(chat_id: int, uid: int) -> bool:
    """Just auto-verify on first message. No captcha flow."""
    return True

# ═════════════════════════════════════════════════════════════════
#  CALLBACK ROUTER
# ═════════════════════════════════════════════════════════════════

_CB_SEEN: "deque" = deque(maxlen=512)
_CB_SEEN_LOCK = threading.Lock()
_CB_DEDUP_WINDOW = 12.0

def _is_duplicate_callback(call_id: str) -> bool:
    if not call_id:
        return False
    now = time.time()
    with _CB_SEEN_LOCK:
        while _CB_SEEN and now - _CB_SEEN[0][1] > _CB_DEDUP_WINDOW:
            _CB_SEEN.popleft()
        for cid, _ in _CB_SEEN:
            if cid == call_id:
                return True
        _CB_SEEN.append((call_id, now))
    return False

@bot.callback_query_handler(func=lambda c: True)
def cb_root(call: types.CallbackQuery) -> None:
    if _is_duplicate_callback(getattr(call, "id", "")):
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass
        return
    uid = call.from_user.id
    if not RATE.allow(uid):
        ack(call, "Slow down.")
        maybe_auto_ban(uid, "callback rate")
        return
    if banned_block(call):
        ack(call); return
    get_or_create_user(call.from_user)
    if maintenance_block(uid):
        ack(call, "Maintenance mode"); return
    data = call.data or ""
    try:
        _route_callback(call, data)
    except Exception as e:
        traceback.print_exc()
        try:
            bot.send_message(call.message.chat.id,
                             f"<b>{G['no']}</b> Eʀʀᴏʀ: <code>{esc(e)}</code>")
        except Exception:
            pass

def _route_callback(call: types.CallbackQuery, data: str) -> None:
    # Core menus
    if data == "menu_main":
        ack(call); render_main_menu(call.message.chat.id, call.from_user.id, call); return
    if data == "menu_bots":
        ack(call); render_bots_menu(call); return
    if data == "menu_upload":
        ack(call); render_upload_menu(call); return
    if data == "menu_plans":
        ack(call); render_plans_menu(call); return
    if data == "menu_profile":
        ack(call); render_profile(call); return
    if data == "menu_wallet":
        ack(call); render_wallet(call); return
    if data == "menu_tickets":
        ack(call); render_user_tickets(call); return
    if data == "menu_admin":
        ack(call); render_admin(call); return

    # Plans
    if data.startswith("plan_view_"):
        ack(call); render_plan_detail(call, data.split("_", 2)[2]); return
    if data.startswith("plan_buy_"):
        ack(call); render_payment_methods_for(call, data.split("_", 2)[2]); return

    # Payment
    if data.startswith("pay_") and data != "pay_proof":
        ack(call); render_payment_screen(call, data); return
    if data == "pay_proof":
        ack(call)
        st = USER_STATES.get(call.from_user.id) or {}
        if st.get("flow") != "await_payment_proof":
            USER_STATES[call.from_user.id] = {"flow": "await_payment_proof"}
        bot.send_message(call.message.chat.id,
            f"{G['plus']} {sc('Send your payment screenshot or transaction id now')}.\n"
            f"{sc('Use')} /cancel {sc('to abort')}.")
        return

    # Bot actions
    if data.startswith("bot_view_"):
        ack(call); render_bot_view(call, data.split("_", 2)[2]); return
    if data.startswith("bot_start_"):
        ack(call)
        b = find_bot(data.split("_", 2)[2])
        if b and (b["owner"] == call.from_user.id or is_admin(call.from_user.id)):
            res = start_child(b)
            ack(call, "Started" if res["ok"] else f"Err: {res.get('error')}")
            render_bot_view(call, b["_id"])
        return
    if data.startswith("bot_stop_"):
        ack(call)
        b = find_bot(data.split("_", 2)[2])
        if b and (b["owner"] == call.from_user.id or is_admin(call.from_user.id)):
            stop_child(b["_id"], manual=True)
            ack(call, "Stopped")
            render_bot_view(call, b["_id"])
        return
    if data.startswith("bot_restart_"):
        ack(call)
        b = find_bot(data.split("_", 2)[2])
        if b and (b["owner"] == call.from_user.id or is_admin(call.from_user.id)):
            res = restart_child(b)
            ack(call, "Restarted" if res.get("ok") else f"Err: {res.get('error')}")
            render_bot_view(call, b["_id"])
        return
    if data.startswith("bot_logs_"):
        ack(call)
        b = find_bot(data.split("_", 2)[2])
        if not b:
            ack(call, "Not found"); return
        if b["owner"] != call.from_user.id and not is_admin(call.from_user.id):
            ack(call, "Not yours"); return
        info = RUNNING.get(b["_id"])
        log = info["log"] if info else []
        last = log[-MAX_LOG_SEND:] if log else [f"({sc('no logs yet')})"]
        txt = (
            f"<b>{G['bolt']} {sc('Live Logs')} — {esc(b['name'])}</b>\n"
            f"{G['div_eq']}\n<pre>"
            + esc("\n".join(last))[:3500]
            + f"</pre>\n{G['div']}")
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton(f"{G['refresh']}  {sc('Refresh Logs')}",
                                       callback_data=f"bot_logs_{b['_id']}"),
            types.InlineKeyboardButton(f"{G['back']}  {sc('Back')}",
                                       callback_data=f"bot_view_{b['_id']}"),
        )
        show_text(call.message.chat.id, txt, kb, call=call)
        return
    if data.startswith("bot_info_"):
        ack(call); render_bot_view(call, data.split("_", 2)[2]); return
    if data.startswith("bot_env_"):
        ack(call); render_env_menu(call, data.split("_", 2)[2]); return
    if data.startswith("env_add_"):
        ack(call)
        USER_STATES[call.from_user.id] = {"flow": "await_env_kv",
                                          "bot_id": data.split("_", 2)[2]}
        bot.send_message(call.message.chat.id,
            f"{G['plus']} {sc('Send the variable as')} <code>KEY=VALUE</code>.\n"
            f"/cancel {sc('to abort')}.", parse_mode="HTML")
        return
    if data.startswith("env_del_"):
        parts = data.split("_", 3)
        if len(parts) >= 4:
            ack(call)
            b = find_bot(parts[2])
            if b and (b["owner"] == call.from_user.id or is_admin(call.from_user.id)):
                env = b.get("env") or {}
                env.pop(parts[3], None)
                b["env"] = env
                save_bot(b)
                ack(call, "Deleted")
                render_env_menu(call, parts[2])
        return
    if data.startswith("bot_cron_"):
        ack(call); render_cron(call, data.split("_", 2)[2]); return
    if data.startswith("bot_clone_"):
        ack(call)
        b = find_bot(data.split("_", 2)[2])
        if not b:
            ack(call, "Not found"); return
        if b["owner"] != call.from_user.id and not is_admin(call.from_user.id):
            ack(call, "Not yours"); return
        u = db_load()["users"][str(call.from_user.id)]
        if len(list_user_bots(call.from_user.id)) >= user_max_bots(u):
            ack(call, "Slot limit reached"); return
        new_id = secrets.token_hex(8)
        new_dir = DIRS["sandbox"] / f"{call.from_user.id}_{new_id}"
        new_dir.mkdir(parents=True, exist_ok=True)
        new_doc = {
            "_id": new_id, "owner": call.from_user.id,
            "name": f"{b['name']}_clone",
            "dir": str(new_dir), "created": ts_iso(),
            "enc_files": [], "env": dict(b.get("env") or {}), "status": "stopped",
        }
        for f in b.get("enc_files") or []:
            key = KEYRING.fetch(f["key_id"])
            if not key:
                continue
            try:
                plain = read_encrypted(Path(f["enc_path"]), key)
            except InvalidToken:
                continue
            kid, k2, cipher = encrypt_file(plain)
            rel = f"{call.from_user.id}/{int(time.time())}_{safe_name(f['filename'])}.enc"
            out = DIRS["encfiles"] / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(cipher)
            meta = dict(f); meta.update({"clone_of": b["_id"], "stored_at": str(out)})
            KEYRING.store(kid, k2, meta)
            new_doc["enc_files"].append({
                "key_id": kid, "enc_path": str(out),
                "filename": f["filename"], "rel_path": f.get("rel_path") or f["filename"],
            })
        save_bot(new_doc)
        audit(call.from_user.id, "bot_clone", f"src={b['_id']} dst={new_id}")
        ack(call, "Cloned")
        render_bots_menu(call)
        return
    if data.startswith("bot_dl_"):
        ack(call)
        b = find_bot(data.split("_", 2)[2])
        if not b:
            ack(call, "Not found"); return
        if b["owner"] != call.from_user.id and not is_admin(call.from_user.id):
            ack(call, "Not yours"); return
        files = b.get("enc_files") or []
        if not files:
            ack(call, "No files"); return
        out = Path(tempfile.gettempdir()) / f"dl_{b['_id']}.zip"
        try:
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
                for f in files:
                    key = KEYRING.fetch(f["key_id"])
                    if not key:
                        continue
                    try:
                        plain = read_encrypted(Path(f["enc_path"]), key)
                    except Exception:
                        continue
                    z.writestr(f.get("rel_path") or f["filename"], plain)
            with open(out, "rb") as fh:
                bot.send_document(call.message.chat.id, fh,
                    caption=f"{G['download']} {sc('Bot files')} — {esc(b['name'])}",
                    visible_file_name=f"{safe_name(b['name'])}.zip")
            ack(call, "Sent")
        except Exception as e:
            ack(call, f"Error: {e}")
        finally:
            try: out.unlink()
            except Exception: pass
        return
    if data.startswith("bot_pip_"):
        ack(call)
        USER_STATES[call.from_user.id] = {"flow": "await_pip_install",
                                          "bot_id": data.split("_", 2)[2]}
        bot.send_message(call.message.chat.id,
            f"<b>{G['download']} {sc('Install Python package')}</b>\n"
            f"{G['div']}\n"
            f"{sc('Send one or more package names separated by spaces')}.\n"
            f"{sc('Examples')}:\n"
            f"  <code>requests</code>\n"
            f"  <code>numpy pandas</code>\n"
            f"  <code>flask==3.0.0</code>\n\n"
            f"/cancel {sc('to abort')}.",
            parse_mode="HTML")
        return
    if data.startswith("bot_delete_"):
        ack(call); render_bot_delete_confirm(call, data.split("_", 2)[2]); return
    if data.startswith("bot_delyes_"):
        ack(call)
        b = find_bot(data.split("_", 2)[2])
        if not b:
            ack(call, "Not found"); return
        if b["owner"] != call.from_user.id and not is_admin(call.from_user.id):
            ack(call, "Not yours"); return
        stop_child(b["_id"], manual=True)
        for f in b.get("enc_files") or []:
            try:
                Path(f["enc_path"]).unlink(missing_ok=True)
            except Exception:
                pass
        rmrf(b.get("dir") or "")
        delete_bot_doc(b["_id"])
        ack(call, "Deleted")
        audit(call.from_user.id, "bot_delete", f"bot={b['_id']}")
        render_bots_menu(call)
        return
    if data.startswith("bot_delfiles_"):
        ack(call); render_bot_delfiles_confirm(call, data.split("_", 2)[2]); return
    if data.startswith("bot_delall_"):
        ack(call); render_bot_delall_confirm(call, data.split("_", 2)[2]); return
    if data.startswith("bot_delfilesyes_"):
        ack(call)
        b = find_bot(data.split("_", 2)[2])
        if not b:
            ack(call, "Not found"); return
        if b["owner"] != call.from_user.id and not is_admin(call.from_user.id):
            ack(call, "Not yours"); return
        stop_child(b["_id"], manual=True)
        for f in b.get("enc_files") or []:
            try:
                Path(f["enc_path"]).unlink(missing_ok=True)
            except Exception:
                pass
        rmrf(b.get("dir") or "")
        delete_bot_doc(b["_id"])
        ack(call, "Bot files deleted")
        audit(call.from_user.id, "bot_delfiles", f"bot={b['_id']}")
        render_bots_menu(call)
        return
    if data.startswith("bot_delalyes_"):
        ack(call)
        b = find_bot(data.split("_", 2)[2])
        if not b:
            ack(call, "Not found"); return
        if b["owner"] != call.from_user.id and not is_admin(call.from_user.id):
            ack(call, "Not yours"); return
        stop_child(b["_id"], manual=True)
        for f in b.get("enc_files") or []:
            try:
                Path(f["enc_path"]).unlink(missing_ok=True)
            except Exception:
                pass
        rmrf(b.get("dir") or "")
        delete_bot_doc(b["_id"])
        ack(call, "All data deleted")
        audit(call.from_user.id, "bot_delall", f"bot={b['_id']}")
        render_bots_menu(call)
        return

    # Approval
    if data.startswith("appr_ok_"):
        if not admin_only_call(call, "approve_payment"):
            return
        bid = data[len("appr_ok_"):]
        res = approve_bot(bid, call.from_user.id)
        ack(call, "Approved" if res.get("ok") else f"Err: {res.get('error')}")
        try:
            bot.edit_message_reply_markup(call.message.chat.id,
                                          call.message.message_id, reply_markup=None)
        except Exception:
            pass
        return
    if data.startswith("appr_no_"):
        if not admin_only_call(call, "approve_payment"):
            return
        bid = data[len("appr_no_"):]
        res = reject_bot(bid, call.from_user.id, reason="rejected by admin")
        ack(call, "Rejected" if res.get("ok") else f"Err: {res.get('error')}")
        try:
            bot.edit_message_reply_markup(call.message.chat.id,
                                          call.message.message_id, reply_markup=None)
        except Exception:
            pass
        return

    # Admin sub-routes
    if data.startswith("adm_"):
        if not admin_only_call(call, "view_stats"):
            return
        ack(call); _render_admin_subroute(call, data); return
    if data.startswith("gh_"):
        if not admin_only_call(call, "view_stats"):
            return
        ack(call); _render_gh_subroute(call, data); return

    # Tickets
    if data == "ticket_open":
        ack(call)
        USER_STATES[call.from_user.id] = {"flow": "await_ticket_subject"}
        bot.send_message(call.message.chat.id,
            f"{G['ticket']} {sc('Send the subject of your ticket (one line)')}.")
        return
    if data.startswith("ticket_view_"):
        ack(call); render_ticket_view(call, data.split("_", 2)[2]); return
    if data.startswith("ticket_close_"):
        ack(call)
        tid = data.split("_", 2)[2]
        d = db_load()
        t = d["tickets"].get(tid)
        if not t:
            ack(call, "Not found"); return
        if t["uid"] != call.from_user.id and not is_admin(call.from_user.id):
            ack(call, "Not yours"); return
        t["status"] = "closed"
        t["closed_at"] = ts_iso()
        db_save(d)
        audit(call.from_user.id, "ticket_close", f"tid={tid}")
        ack(call, "Closed")
        render_ticket_view(call, tid)
        return
    if data.startswith("ticket_reply_"):
        ack(call)
        tid = data.split("_", 2)[2]
        USER_STATES[call.from_user.id] = {"flow": "await_ticket_reply", "tid": tid}
        bot.send_message(call.message.chat.id,
            f"{G['plus']} {sc('Send your reply now')}. /cancel {sc('to abort')}.")
        return

    # Wallet
    if data == "wallet_topup":
        ack(call)
        USER_STATES[call.from_user.id] = {"flow": "await_topup_proof"}
        bot.send_message(call.message.chat.id,
            f"{G['plus']} {sc('Send a screenshot of your top-up payment')}.\n"
            f"{sc('Include the amount in the caption')}, e.g.  <code>200</code>.",
            parse_mode="HTML")
        return

    # Payment approve/reject
    if data.startswith("payapprove_"):
        ack(call); action_payment_approve(call, data.split("_", 1)[1]); return
    if data.startswith("payreject_"):
        ack(call); action_payment_reject(call, data.split("_", 1)[1]); return

    ack(call, "?")

def _render_admin_subroute(call: types.CallbackQuery, data: str) -> None:
    if data == "adm_stats":     return render_adm_stats(call)
    if data == "adm_users":     return render_adm_users(call)
    if data == "adm_allbots":   return render_adm_allbots(call)
    if data == "adm_payments":  return render_adm_payments(call)
    if data == "adm_broadcast": return render_adm_broadcast(call)
    if data == "adm_ban":       return render_adm_ban(call)
    if data == "adm_giveplan":  return render_adm_giveplan(call)
    if data == "adm_tickets":   return render_adm_tickets(call)
    if data == "adm_admins":    return render_adm_admins(call)
    if data == "adm_audit":     return render_adm_audit(call)
    if data == "adm_github":    return render_adm_github(call)
    if data == "adm_security":  return render_adm_security(call)
    if data == "adm_maint":     return render_adm_maint(call)
    if data == "adm_settings":  return render_adm_settings(call)
    if data == "adm_pending":   return render_adm_pending(call)
    if data == "adm_maint_toggle":
        cur = bool(get_setting("maintenance", False))
        set_setting("maintenance", not cur)
        audit(call.from_user.id, "maintenance_toggle", f"now={not cur}")
        ack(call, f"Maintenance: {'ON' if not cur else 'OFF'}")
        return render_adm_maint(call)
    if data == "adm_set_reload":
        cache_clear_all()
        audit(call.from_user.id, "reload_caches", "")
        ack(call, "Caches dropped")
        return render_adm_settings(call)
    if data == "adm_set_brand":
        if not is_owner(call.from_user.id):
            ack(call, "Owner only"); return
        USER_STATES[call.from_user.id] = {"flow": "await_set_brand"}
        bot.send_message(call.message.chat.id,
            f"{G['cog']} {sc('Send the new brand tag')}:")
        return
    if data == "adm_set_owner":
        if not is_owner(call.from_user.id):
            ack(call, "Owner only"); return
        USER_STATES[call.from_user.id] = {"flow": "await_set_owner"}
        bot.send_message(call.message.chat.id,
            f"{G['shield']} {sc('Send new owner numeric Telegram ID')}.")
        return
    if data == "adm_set_sysinfo":
        rss = 0
        if psutil is not None:
            try: rss = psutil.Process(os.getpid()).memory_info().rss
            except Exception: pass
        cap = (
            f"<b>{G['eye']} {sc('System Info')}</b>\n"
            f"{G['div_eq']}\n"
            f"{bullet('Uptime', fmt_dur(int(time.time() * 1000) - START_TS))}\n"
            f"{bullet('Panel RSS', fmt_bytes(rss))}\n"
            f"{bullet('PID', os.getpid())}\n"
            f"{bullet('Cache entries', len(_DB_CACHE))}\n"
            f"{G['div']}")
        show_text(call.message.chat.id, cap, back_admin_kb(), call=call)
        return
    if data == "adm_set_restart_all":
        return show_text(call.message.chat.id,
            f"<b>{G['warn']} {sc('Confirm')}</b>\n{G['div']}\n"
            f"{sc('Restart all running bots')}?",
            confirm_kb("adm_set_restart_all_yes", "adm_settings", "Yes", "Cancel"),
            call=call)
    if data == "adm_set_restart_all_yes":
        ack(call, "Restarting...")
        def _rb():
            ok = fail = 0
            for bid in list(RUNNING.keys()):
                b = find_bot(bid)
                if not b: continue
                try:
                    r = restart_child(b)
                    if r.get("ok"): ok += 1
                    else: fail += 1
                except Exception: fail += 1
            audit(call.from_user.id, "restart_all_bots", f"ok={ok} fail={fail}")
            try: bot.send_message(call.from_user.id,
                f"{G['ok']} Restart-all done: {ok} ok, {fail} fail.")
            except Exception: pass
        threading.Thread(target=_rb, daemon=True).start()
        return
    if data == "adm_set_stop_all":
        return show_text(call.message.chat.id,
            f"<b>{G['warn']} {sc('Confirm')}</b>\n{G['div']}\n"
            f"{sc('Stop every running bot')}?",
            confirm_kb("adm_set_stop_all_yes", "adm_settings", "Yes", "Cancel"),
            call=call)
    if data == "adm_set_stop_all_yes":
        ack(call, "Stopping...")
        def _sb():
            n = 0
            for bid in list(RUNNING.keys()):
                try: stop_child(bid, manual=True); n += 1
                except Exception: pass
            audit(call.from_user.id, "stop_all_bots", f"stopped={n}")
            try: bot.send_message(call.from_user.id,
                f"{G['ok']} Stopped {n} bot(s).")
            except Exception: pass
        threading.Thread(target=_sb, daemon=True).start()
        return
    if data == "adm_set_clean_orphans":
        ack(call, "Cleaning...")
        def _co():
            dirs, files = _do_clean_orphans()
            audit(call.from_user.id, "clean_orphans",
                  f"sandboxes={dirs} files={files}")
            try: bot.send_message(call.from_user.id,
                f"{G['ok']} Cleaned: {dirs} sandbox(es), {files} orphan file(s).")
            except Exception: pass
        threading.Thread(target=_co, daemon=True).start()
        return
    if data == "adm_set_export":
        if not is_owner(call.from_user.id):
            ack(call, "Owner only"); return
        ack(call, "Exporting...")
        def _ex():
            try:
                out = BASE_DIR / "exports"
                out.mkdir(exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                target = out / f"export_{stamp}.zip"
                with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
                    for name in ("user_data.json", "settings.json", "audit.log"):
                        p = BASE_DIR / "storage" / name
                        if p.exists(): zf.write(p, arcname=name)
                audit(call.from_user.id, "export_data", f"file={target.name}")
                with target.open("rb") as fh:
                    bot.send_document(call.from_user.id, fh,
                        caption=f"{G['ok']} Export ({target.stat().st_size // 1024} KB)")
            except Exception as e:
                try: bot.send_message(call.from_user.id,
                    f"{G['no']} Export error: <code>{esc(e)}</code>", parse_mode="HTML")
                except Exception: pass
        threading.Thread(target=_ex, daemon=True).start()
        return
    ack(call, "?")

def _render_gh_subroute(call: types.CallbackQuery, data: str) -> None:
    if data == "gh_backup_now":
        ack(call, "Backup started")
        def _bg():
            res = gh_backup_now()
            try:
                bot.send_message(call.from_user.id,
                    f"<b>{'OK' if res.get('ok') else G['no']} GitHub Backup</b>\n"
                    f"{bullet('Size', res.get('sizeMB', '?'))}\n"
                    f"{bullet('Error', res.get('error', 'none'))}",
                    parse_mode="HTML")
            except Exception: pass
        threading.Thread(target=_bg, daemon=True).start()
        return
    if data == "gh_restore_now":
        ack(call, "Restore started")
        def _bg():
            res = gh_restore_now(overwrite=True)
            try:
                bot.send_message(call.from_user.id,
                    f"<b>{'OK' if res.get('ok') else G['no']} Restore</b>\n"
                    f"{bullet('Size', fmt_bytes(res.get('sizeBytes', 0)))}\n"
                    f"{bullet('Error', res.get('error', 'none'))}",
                    parse_mode="HTML")
            except Exception: pass
        threading.Thread(target=_bg, daemon=True).start()
        return
    if data == "gh_toggle_auto":
        GH["autoEnabled"] = not GH["autoEnabled"]
        set_setting("github_auto_enabled", GH["autoEnabled"])
        ack(call, f"Auto: {'ON' if GH['autoEnabled'] else 'OFF'}")
        render_adm_github(call)
        return
    if data == "gh_set_token":
        if not is_owner(call.from_user.id):
            ack(call, "Owner only"); return
        USER_STATES[call.from_user.id] = {"flow": "await_gh_token"}
        bot.send_message(call.message.chat.id,
            f"{G['key']} {sc('Send the GitHub token now')}.")
        return
    if data == "gh_set_repo":
        if not is_owner(call.from_user.id):
            ack(call, "Owner only"); return
        USER_STATES[call.from_user.id] = {"flow": "await_gh_repo"}
        bot.send_message(call.message.chat.id,
            f"{G['diamond']} {sc('Send the repo as')} <code>owner/repo</code>.",
            parse_mode="HTML")
        return
    if data == "gh_set_branch":
        if not is_owner(call.from_user.id):
            ack(call, "Owner only"); return
        USER_STATES[call.from_user.id] = {"flow": "await_gh_branch"}
        bot.send_message(call.message.chat.id,
            f"{G['arrow']} {sc('Send the branch name')}.")
        return
    if data == "gh_set_interval":
        if not is_owner(call.from_user.id):
            ack(call, "Owner only"); return
        USER_STATES[call.from_user.id] = {"flow": "await_gh_interval"}
        bot.send_message(call.message.chat.id,
            f"{G['cog']} {sc('Send interval in minutes (>=15)')}.")
        return
    if data == "gh_clear":
        gh_set_config({"token": "", "repo": "", "branch": "main", "intervalMin": 360})
        gh_load_config()
        ack(call, "Cleared")
        render_adm_github(call)
        return
    ack(call, "?")

def _do_clean_orphans() -> Tuple[int, int]:
    valid_sandbox_keys: set = set()
    valid_bot_ids: set = set(db_load_ro()["bots"].keys())
    for b in db_load_ro()["bots"].values():
        owner = b.get("owner")
        bid = b.get("_id")
        if owner and bid:
            valid_sandbox_keys.add(f"{owner}_{bid}")
    removed_dirs = 0
    sandbox_root = BASE_DIR / "sandbox"
    if sandbox_root.exists():
        for entry in sandbox_root.iterdir():
            if entry.is_dir() and entry.name not in valid_sandbox_keys:
                try:
                    shutil.rmtree(entry, ignore_errors=True)
                    removed_dirs += 1
                except Exception:
                    pass
    return removed_dirs, 0

# ═════════════════════════════════════════════════════════════════
#  TEXT/DOCUMENT HANDLERS
# ═════════════════════════════════════════════════════════════════

@bot.message_handler(content_types=["document"])
def on_document(m: types.Message) -> None:
    if not _is_private(m):
        return
    if banned_block(m):
        return
    uid = m.from_user.id
    if not RATE.allow(uid):
        maybe_auto_ban(uid, "rate")
        return
    if not UPLOAD_RATE.allow(uid):
        bot.reply_to(m, f"{G['warn']} {sc('Too many uploads, slow down')}.")
        return
    if maintenance_block(uid):
        return
    get_or_create_user(m.from_user)
    st = USER_STATES.get(uid) or {}
    if st.get("flow") == "await_payment_proof":
        return _handle_payment_proof(m, st)
    if st.get("flow") == "await_topup_proof":
        return _handle_topup_proof(m)
    _handle_bot_upload(m)

@bot.message_handler(content_types=["photo"])
def on_photo(m: types.Message) -> None:
    if not _is_private(m):
        return
    if banned_block(m):
        return
    uid = m.from_user.id
    if not RATE.allow(uid):
        return
    get_or_create_user(m.from_user)
    st = USER_STATES.get(uid) or {}
    if st.get("flow") == "await_payment_proof":
        _handle_payment_proof(m, st); return
    if st.get("flow") == "await_topup_proof":
        _handle_topup_proof(m); return

@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(m: types.Message) -> None:
    if not _is_private(m):
        return
    if banned_block(m):
        return
    uid = m.from_user.id
    if not RATE.allow(uid):
        maybe_auto_ban(uid, "rate")
        return
    text = (m.text or "").strip()
    if text.startswith("/"):
        return
    get_or_create_user(m.from_user)
    if maintenance_block(uid):
        return

    st = USER_STATES.get(uid) or {}
    flow = st.get("flow")
    try:
        if flow == "await_env_kv":
            return _handle_env_kv(m, st)
        if flow == "await_pip_install":
            return _handle_pip_install(m, st)
        if flow == "await_cron":
            return _handle_cron(m, st)
        if flow == "await_admin_finduser":
            return _handle_admin_finduser(m)
        if flow == "await_ban_cmd":
            return _handle_ban_cmd(m)
        if flow == "await_giveplan":
            return _handle_giveplan_cmd(m)
        if flow == "await_broadcast":
            return _handle_broadcast(m)
        if flow == "await_admin_admins":
            return _handle_admin_admins(m)
        if flow == "await_ticket_subject":
            return _handle_ticket_subject(m)
        if flow == "await_ticket_body":
            return _handle_ticket_body(m, st)
        if flow == "await_ticket_reply":
            return _handle_ticket_reply(m, st)
        if flow == "await_payment_proof":
            return _handle_payment_proof_text(m, st)
        if flow == "await_topup_proof":
            return _handle_topup_proof(m)
        if flow == "await_gh_token":
            gh_set_config({"token": text}); gh_load_config()
            USER_STATES.pop(uid, None); bot.reply_to(m, f"{G['ok']} {sc('token saved')}"); return
        if flow == "await_gh_repo":
            gh_set_config({"repo": text}); gh_load_config()
            USER_STATES.pop(uid, None); bot.reply_to(m, f"{G['ok']} {sc('repo saved')}"); return
        if flow == "await_gh_branch":
            gh_set_config({"branch": text}); gh_load_config()
            USER_STATES.pop(uid, None); bot.reply_to(m, f"{G['ok']} {sc('branch saved')}"); return
        if flow == "await_gh_interval":
            try:
                v = max(15, int(text))
            except Exception:
                v = 360
            gh_set_config({"intervalMin": v}); gh_load_config()
            USER_STATES.pop(uid, None); bot.reply_to(m, f"{G['ok']} {sc('interval saved')}"); return
        if flow == "await_set_brand":
            if not is_owner(uid):
                USER_STATES.pop(uid, None); return
            new = (text or "").strip()[:64]
            if not new:
                bot.reply_to(m, f"{G['no']} {sc('empty — cancelled')}")
                USER_STATES.pop(uid, None); return
            global BRAND_TAG
            BRAND_TAG = new
            set_setting("brand_tag", new)
            audit(uid, "set_brand", new)
            USER_STATES.pop(uid, None)
            bot.reply_to(m, f"{G['ok']} {sc('Brand updated to')}: <b>{esc(new)}</b>",
                         parse_mode="HTML")
            return
        if flow == "await_set_owner":
            if not is_owner(uid):
                USER_STATES.pop(uid, None); return
            try:
                new_owner = int((text or "").strip())
                if new_owner <= 0:
                    raise ValueError
            except Exception:
                bot.reply_to(m, f"{G['no']} {sc('invalid id')}")
                return
            global OWNER_ID
            OWNER_ID = new_owner
            set_setting("owner_id", new_owner)
            audit(uid, "transfer_owner", f"new={new_owner}")
            USER_STATES.pop(uid, None)
            bot.reply_to(m,
                f"{G['ok']} {sc('Ownership transferred to')} <code>{new_owner}</code>.",
                parse_mode="HTML")
            return
    except Exception as e:
        traceback.print_exc()
        bot.reply_to(m, f"{G['no']} {sc('error')}: <code>{esc(e)}</code>", parse_mode="HTML")

# ═════════════════════════════════════════════════════════════════
#  COMMANDS
# ═════════════════════════════════════════════════════════════════

@bot.message_handler(commands=["start"])
def cmd_start(m: types.Message) -> None:
    if not _is_private(m):
        return
    uid = m.from_user.id
    if not RATE.allow(uid):
        maybe_auto_ban(uid, "rate")
        return
    if banned_block(m):
        return
    global OWNER_ID
    if OWNER_ID <= 0:
        stored = int(get_setting("owner_id", 0) or 0)
        if stored > 0:
            OWNER_ID = stored
        else:
            OWNER_ID = uid
            set_setting("owner_id", uid)
            audit(uid, "owner_claim", f"first /start, uid={uid}")
            try:
                bot.send_message(m.chat.id,
                    f"<b>{G['crown']} {sc('You are now the panel owner')}</b>\n"
                    f"{G['div']}\n"
                    f"{bullet('Owner ID', uid)}\n"
                    f"{sc('Set OWNER_ID env var to lock ownership permanently')}.",
                    parse_mode="HTML")
            except Exception:
                pass
    u, is_new = get_or_create_user(m.from_user)
    if maintenance_block(uid):
        bot.send_message(m.chat.id,
            f"<b>{G['warn']} {sc('Panel under maintenance')}</b>",
            parse_mode="HTML")
        return
    intro = (
        f"{sc('You are now registered')}. Tap <b>Plans</b> or <b>Upload</b> to begin."
        if is_new else
        f"{sc('Welcome back')}, <b>{esc(m.from_user.first_name or 'friend')}</b>!"
    )
    render_main_menu(m.chat.id, uid, intro=intro)

@bot.message_handler(commands=["help"])
def cmd_help(m: types.Message) -> None:
    if not _is_private(m):
        return
    if banned_block(m):
        return
    txt = (
        f"<b>{esc(BRAND_TAG)} — {sc('Quick Help')}</b>\n"
        f"{G['div_eq']}\n"
        f"{bullet('Upload', 'Send a .py / .js / .zip file')}\n"
        f"{bullet('Manage', 'My Bots → pick a bot → Start / Stop / Logs')}\n"
        f"{bullet('Plans', 'Plans → Buy Plan → choose method → send proof')}\n"
        f"{bullet('Wallet', 'Top-up via admin, then spend on plans')}\n"
        f"{bullet('Tickets', 'Open a ticket from Tickets menu')}\n"
        f"{G['div']}")
    bot.send_message(m.chat.id, txt, parse_mode="HTML",
                     reply_markup=back_main_kb(), disable_web_page_preview=True)

@bot.message_handler(commands=["menu"])
def cmd_menu(m: types.Message) -> None:
    if not _is_private(m):
        return
    if banned_block(m):
        return
    get_or_create_user(m.from_user)
    render_main_menu(m.chat.id, m.from_user.id)

@bot.message_handler(commands=["id"])
def cmd_id(m: types.Message) -> None:
    if not _is_private(m):
        return
    bot.reply_to(m, f"<code>{m.from_user.id}</code>")

@bot.message_handler(commands=["cancel"])
def cmd_cancel(m: types.Message) -> None:
    if not _is_private(m):
        return
    USER_STATES.pop(m.from_user.id, None)
    bot.reply_to(m, f"{G['ok']} {sc('Cancelled')}")

# ═════════════════════════════════════════════════════════════════
#  CRON RUNNER
# ═════════════════════════════════════════════════════════════════

def cron_runner() -> None:
    last_per_bot: Dict[str, Dict[str, float]] = {}
    while True:
        try:
            now = time.time()
            downgrade_expired_users()

            d = db_load()
            sb = d.get("scheduled_broadcasts", [])
            kept: List[Dict[str, Any]] = []
            for b in sb:
                try:
                    when = datetime.fromisoformat(str(b["at"]).replace("Z", "+00:00"))
                except Exception:
                    continue
                if when <= now_utc():
                    _send_broadcast(b["text"], b.get("plan"))
                    audit(b.get("by", 0), "broadcast_run", "scheduled")
                else:
                    kept.append(b)
            if len(kept) != len(sb):
                d["scheduled_broadcasts"] = kept
                db_save(d)

            for bid, bdoc in db_load()["bots"].items():
                cron = bdoc.get("cron") or {}
                last = last_per_bot.setdefault(bid, {})
                if cron.get("restart_hours"):
                    iv = int(cron["restart_hours"]) * 3600
                    if now - last.get("restart", 0) >= iv:
                        try: restart_child(bdoc)
                        except Exception: pass
                        last["restart"] = now
                if cron.get("backup_hours"):
                    iv = int(cron["backup_hours"]) * 3600
                    if now - last.get("backup", 0) >= iv:
                        try: gh_backup_now()
                        except Exception: pass
                        last["backup"] = now

            should_backup = False
            for bid, rinfo in list(RUNNING.items()):
                started_ms = rinfo.get("started", 0)
                online_sec = (time.time() * 1000 - started_ms) / 1000
                if online_sec >= 600:
                    should_backup = True
                    break
            if should_backup and gh_enabled():
                try:
                    gh_backup_now()
                except Exception as e:
                    print(f"[cron] auto backup error: {e}", flush=True)
        except Exception:
            traceback.print_exc()
        time.sleep(60)

# ═════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════

def banner() -> None:
    line = "=" * 64
    print(line)
    print(f"   {BRAND_TAG}")
    print(f"   uptime port : {KEEPALIVE_PORT}")
    print(f"   owner id    : {OWNER_ID}")
    print(f"   github keys : {'GitHub' if KEYRING.gh_enabled() else 'local cache'}")
    print(f"   github bkp  : {'on' if gh_enabled() else 'off'}")
    print(line)

def main() -> int:
    banner()
    global OWNER_ID, BRAND_TAG
    stored_owner = int(get_setting("owner_id", 0) or 0)
    if stored_owner > 0 and OWNER_ID <= 0:
        OWNER_ID = stored_owner
    bt = get_setting("brand_tag", None)
    if isinstance(bt, str) and bt:
        BRAND_TAG = bt
    gh_load_config()
    GH["autoEnabled"] = bool(get_setting("github_auto_enabled", True))

    try:
        res = gh_auto_restore_on_boot()
        if res and res.get("ok"):
            print(f"[boot] restored backup ({fmt_bytes(res.get('sizeBytes', 0))})")
    except Exception:
        pass

    threading.Thread(target=gh_auto_loop, daemon=True).start()
    threading.Thread(target=cron_runner, daemon=True).start()
    _start_keepalive()

    try:
        bot.set_my_commands([
            types.BotCommand("start", "Open main menu"),
            types.BotCommand("menu", "Main menu"),
            types.BotCommand("help", "Show help"),
            types.BotCommand("id", "Show your user id"),
            types.BotCommand("cancel", "Cancel current action"),
        ])
    except Exception:
        pass

    notify_owner(
        f"<b>{G['ok']} {sc('Panel online')}</b>\n"
        f"{bullet('Brand', BRAND_TAG)}\n"
        f"{bullet('Started', fmt_ts(ts_iso()))}\n"
        f"{bullet('Users', len(db_load()['users']))}\n"
        f"{bullet('Bots', len(db_load()['bots']))}")

    for b in db_load()["bots"].values():
        if b.get("status") == "running":
            try:
                start_child(b)
            except Exception:
                pass

    try:
        bot.remove_webhook()
        try:
            bot.delete_webhook(drop_pending_updates=True)
        except Exception:
            pass
        print("[bot] webhook cleared")
    except Exception as e:
        print(f"[bot] webhook clear warning: {e}")

    # 🟢 409 CONFLICT FIX: Railway purane process ko band hone ka time do
    print("[bot] waiting 5s for Railway to release old connections...")
    time.sleep(5)

    print("[bot] polling...")
    conflict_count = 0
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=25)
            time.sleep(2)
        except KeyboardInterrupt:
            print("\n[bot] stopping...")
            for bid in list(RUNNING.keys()):
                stop_child(bid, manual=False)
            return 0
        except Exception as e:
            err = str(e)
            if "409" in err or "Conflict" in err or "other getUpdates" in err:
                conflict_count += 1
                wait = min(60, 10 * conflict_count)
                print(f"[bot] ⚠️ 409 CONFLICT (attempt {conflict_count}). Waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"[bot] poll error: {e}")
                time.sleep(5)

if __name__ == "__main__":
    sys.exit(main())