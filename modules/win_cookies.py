"""
Direct Windows Chromium cookie extraction (Edge, Chrome, Brave).
Reads the SQLite cookies DB and decrypts values without browser_cookie3.
Requires: pywin32 (win32crypt), pycryptodome or pycryptodomex (AES-GCM).
"""

import base64
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time


class BrowserLockedError(PermissionError):
    """The browser holds an exclusive lock on the cookies DB (Windows error 32).
    The only reliable fix is to close the browser first."""
    def __init__(self, browser):
        self.browser = browser
        super().__init__(
            f"{browser.title()} has the cookies file exclusively locked.\n\n"
            "Windows error 32 (ERROR_SHARING_VIOLATION) — the browser opened the\n"
            "file without allowing any other process to read it."
        )


_BROWSER_EXE = {
    "brave":  "brave.exe",
    "chrome": "chrome.exe",
    "edge":   "msedge.exe",
}

_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


def close_browser(browser):
    """Gracefully close a Chromium browser; force-kill if it won't quit in 8 s.
    Returns when the process is gone."""
    exe = _BROWSER_EXE.get(browser.lower(), f"{browser}.exe")
    subprocess.run(["taskkill", "/im", exe], capture_output=True, creationflags=_NO_WINDOW)
    deadline = time.time() + 8
    while time.time() < deadline:
        r = subprocess.run(
            ["tasklist", "/fi", f"imagename eq {exe}"],
            capture_output=True, text=True, creationflags=_NO_WINDOW,
        )
        if exe.lower() not in r.stdout.lower():
            return
        time.sleep(0.5)
    subprocess.run(["taskkill", "/f", "/im", exe], capture_output=True, creationflags=_NO_WINDOW)
    time.sleep(1)


def _copy_file_shared(src, dst):
    """Copy src → dst using CreateFile(FILE_SHARE_READ|WRITE|DELETE).

    shutil.copy2 uses Python's default open() which sets no sharing flags,
    so it fails with PermissionError if another process has the file open.
    FILE_SHARE_ALL lets us open the file regardless — unless the other process
    opened it with dwShareMode=0 (exclusive), in which case we get
    ERROR_SHARING_VIOLATION (32) and must close the browser first.
    """
    k32 = ctypes.windll.kernel32
    k32.CreateFileW.restype = ctypes.c_void_p

    GENERIC_READ   = 0x80000000
    FILE_SHARE_ALL = 0x00000007
    OPEN_EXISTING  = 3

    handle = k32.CreateFileW(
        ctypes.c_wchar_p(src), GENERIC_READ, FILE_SHARE_ALL,
        None, OPEN_EXISTING, 0, None,
    )
    INVALID_HANDLE = ctypes.c_void_p(-1).value
    if handle is None or handle == INVALID_HANDLE:
        err = k32.GetLastError()
        if err == 32:   # ERROR_SHARING_VIOLATION — caller raises BrowserLockedError
            raise _SharingViolation()
        raise PermissionError(f"Cannot open file (Windows error {err}): {src}")

    try:
        high = wt.DWORD(0)
        low  = k32.GetFileSize(ctypes.c_void_p(handle), ctypes.byref(high))
        size = (high.value << 32) | low
        if size:
            buf  = (ctypes.c_char * size)()
            read = wt.DWORD(0)
            k32.ReadFile(ctypes.c_void_p(handle), buf, size, ctypes.byref(read), None)
            data = bytes(buf)[: read.value]
        else:
            data = b""
    finally:
        k32.CloseHandle(ctypes.c_void_p(handle))

    with open(dst, "wb") as f:
        f.write(data)


class _SharingViolation(Exception):
    """Internal sentinel for ERROR_SHARING_VIOLATION (32)."""


BROWSER_PATHS = {
    "edge":   r"Microsoft\Edge\User Data",
    "chrome": r"Google\Chrome\User Data",
    "brave":  r"BraveSoftware\Brave-Browser\User Data",
}

_CHROME_EPOCH_OFFSET_US = 11_644_473_600 * 1_000_000


def _get_master_key(user_data_dir):
    local_state = os.path.join(user_data_dir, "Local State")
    with open(local_state, "r", encoding="utf-8") as f:
        data = json.load(f)

    b64 = data["os_crypt"]["encrypted_key"]
    raw = base64.b64decode(b64)
    raw = raw[5:]  # strip 'DPAPI' prefix

    import win32crypt
    _, master_key = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
    return master_key


def _aes_decrypt(encrypted_value, master_key):
    try:
        from Cryptodome.Cipher import AES
    except ImportError:
        from Crypto.Cipher import AES

    nonce = encrypted_value[3:15]
    payload = encrypted_value[15:]
    cipher = AES.new(master_key, AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(payload[:-16], payload[-16:]).decode("utf-8")


def _decrypt_value(encrypted_value, master_key):
    if not encrypted_value:
        return ""
    if encrypted_value[:3] in (b"v10", b"v20"):
        try:
            return _aes_decrypt(encrypted_value, master_key)
        except Exception:
            return ""
    try:
        import win32crypt
        _, plain = win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)
        return plain.decode("utf-8")
    except Exception:
        return ""


def _chrome_ts_to_unix(chrome_ts):
    if not chrome_ts:
        return 0
    try:
        return int((chrome_ts - _CHROME_EPOCH_OFFSET_US) / 1_000_000)
    except Exception:
        return 0


def _find_cookies_db(user_data_dir, profile="Default"):
    for subpath in (
        os.path.join(profile, "Network", "Cookies"),
        os.path.join(profile, "Cookies"),
    ):
        path = os.path.join(user_data_dir, subpath)
        if os.path.isfile(path):
            return path
    return None


def _copy_db(db_path, tmp_dir):
    """Copy the SQLite DB + WAL/SHM to tmp_dir. Raises BrowserLockedError on error 32."""
    tmp_db = os.path.join(tmp_dir, "cookies.db")
    try:
        _copy_file_shared(db_path, tmp_db)
    except _SharingViolation:
        raise BrowserLockedError(_db_browser(db_path))
    for ext in ("-wal", "-shm"):
        src = db_path + ext
        if os.path.exists(src):
            try:
                _copy_file_shared(src, tmp_db + ext)
            except (_SharingViolation, PermissionError):
                pass  # SQLite will cope without WAL/SHM
    return tmp_db


def _db_browser(db_path):
    """Best-guess browser name from a DB path (for error messages)."""
    p = db_path.lower()
    for name in ("brave", "edge", "chrome"):
        if name in p:
            return name
    return "browser"


def extract(browser, domain_filter=None):
    """Extract and decrypt cookies from a Windows Chromium browser.

    Raises BrowserLockedError if the browser is running with an exclusive
    file lock — call close_browser(browser) and retry.
    """
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if not local_appdata:
        raise EnvironmentError("LOCALAPPDATA is not set.")

    rel = BROWSER_PATHS.get(browser)
    if not rel:
        raise ValueError(f"Unsupported browser: {browser!r}")

    user_data_dir = os.path.join(local_appdata, rel)
    if not os.path.isdir(user_data_dir):
        raise FileNotFoundError(
            f"{browser.title()} profile directory not found:\n{user_data_dir}\n\n"
            "Is the browser installed and has been launched at least once?"
        )

    master_key = _get_master_key(user_data_dir)

    db_path = _find_cookies_db(user_data_dir)
    if not db_path:
        raise FileNotFoundError(
            f"Cookies database not found under {user_data_dir}.\n"
            "Try closing the browser and retrying."
        )

    tmp_dir = tempfile.mkdtemp()
    try:
        tmp_db = _copy_db(db_path, tmp_dir)
        return _read_db(tmp_db, master_key, domain_filter)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _read_db(db_path, master_key, domain_filter):
    cookies = []
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT host_key, path, is_secure, expires_utc, name, encrypted_value "
            "FROM cookies"
        )
        for host_key, path, is_secure, expires_utc, name, enc_value in cur.fetchall():
            if domain_filter and domain_filter.lower() not in (host_key or "").lower():
                continue
            cookies.append({
                "domain": host_key or "",
                "flag":   "TRUE" if (host_key or "").startswith(".") else "FALSE",
                "path":   path or "/",
                "secure": "TRUE" if is_secure else "FALSE",
                "expiry": str(_chrome_ts_to_unix(expires_utc)),
                "name":   name or "",
                "value":  _decrypt_value(enc_value, master_key),
            })
    finally:
        con.close()
    return cookies
