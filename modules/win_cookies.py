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
import tempfile

def _copy_file_shared(src, dst):
    """Copy a file using CreateFile with FILE_SHARE_READ|WRITE|DELETE.

    shutil.copy2 fails if the file is held open by another process (e.g. a
    running browser). Using the Windows API with full sharing flags lets us
    read and copy the file regardless.
    """
    k32 = ctypes.windll.kernel32
    k32.CreateFileW.restype = ctypes.c_void_p

    GENERIC_READ   = 0x80000000
    FILE_SHARE_ALL = 0x00000007   # READ | WRITE | DELETE
    OPEN_EXISTING  = 3

    handle = k32.CreateFileW(
        ctypes.c_wchar_p(src),
        GENERIC_READ,
        FILE_SHARE_ALL,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    INVALID_HANDLE = ctypes.c_void_p(-1).value
    if handle is None or handle == INVALID_HANDLE:
        err = k32.GetLastError()
        raise PermissionError(
            f"Cannot read cookies file (Windows error {err}).\n"
            "The browser may be holding an exclusive lock — try closing it."
        )

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


BROWSER_PATHS = {
    "edge":   r"Microsoft\Edge\User Data",
    "chrome": r"Google\Chrome\User Data",
    "brave":  r"BraveSoftware\Brave-Browser\User Data",
}

# Microseconds between 1601-01-01 (Chrome epoch) and 1970-01-01 (Unix epoch)
_CHROME_EPOCH_OFFSET_US = 11_644_473_600 * 1_000_000


def _get_master_key(user_data_dir):
    local_state = os.path.join(user_data_dir, "Local State")
    with open(local_state, "r", encoding="utf-8") as f:
        data = json.load(f)

    b64 = data["os_crypt"]["encrypted_key"]
    raw = base64.b64decode(b64)
    raw = raw[5:]  # strip 'DPAPI' prefix added by Chrome

    import win32crypt
    _, master_key = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
    return master_key


def _aes_decrypt(encrypted_value, master_key):
    """Decrypt a v10/v20 AES-256-GCM encrypted cookie value."""
    try:
        from Cryptodome.Cipher import AES
    except ImportError:
        from Crypto.Cipher import AES

    # Format: 3-byte version tag | 12-byte nonce | ciphertext | 16-byte auth tag
    nonce = encrypted_value[3:15]
    payload = encrypted_value[15:]
    cipher = AES.new(master_key, AES.MODE_GCM, nonce=nonce)
    plaintext = cipher.decrypt_and_verify(payload[:-16], payload[-16:])
    return plaintext.decode("utf-8")


def _decrypt_value(encrypted_value, master_key):
    if not encrypted_value:
        return ""

    if encrypted_value[:3] in (b"v10", b"v20"):
        try:
            return _aes_decrypt(encrypted_value, master_key)
        except Exception:
            return ""

    # Very old cookies: per-value DPAPI (no AES layer)
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


def extract(browser, domain_filter=None):
    """
    Extract and decrypt cookies from a Windows Chromium browser.

    Args:
        browser: 'edge', 'chrome', or 'brave'
        domain_filter: optional string; only return cookies whose host_key
                       contains this string (case-insensitive)

    Returns:
        List of cookie dicts with keys: domain, flag, path, secure, expiry, name, value

    Raises:
        EnvironmentError, FileNotFoundError, ImportError, Exception
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
            "Is the browser installed and has it been launched at least once?"
        )

    master_key = _get_master_key(user_data_dir)

    db_path = _find_cookies_db(user_data_dir)
    if not db_path:
        raise FileNotFoundError(
            f"Cookies database not found under {user_data_dir}.\n"
            "Try closing the browser and retrying."
        )

    # Copy the DB and WAL/SHM files to a temp dir for a consistent read.
    # Chromium uses WAL mode — recent cookies may only be in the -wal file.
    # We use _copy_file_shared (CreateFile with FILE_SHARE_ALL) so the copy
    # works even while the browser is running with the file open.
    tmp_dir = tempfile.mkdtemp()
    try:
        tmp_db = os.path.join(tmp_dir, "cookies.db")
        _copy_file_shared(db_path, tmp_db)
        for ext in ("-wal", "-shm"):
            src = db_path + ext
            if os.path.exists(src):
                try:
                    _copy_file_shared(src, tmp_db + ext)
                except PermissionError:
                    pass  # WAL/SHM missing or locked — SQLite will cope
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
            if domain_filter:
                if domain_filter.lower() not in (host_key or "").lower():
                    continue

            value = _decrypt_value(enc_value, master_key)

            cookies.append({
                "domain": host_key or "",
                "flag": "TRUE" if (host_key or "").startswith(".") else "FALSE",
                "path": path or "/",
                "secure": "TRUE" if is_secure else "FALSE",
                "expiry": str(_chrome_ts_to_unix(expires_utc)),
                "name": name or "",
                "value": value,
            })
    finally:
        con.close()
    return cookies
