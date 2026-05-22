"""
Direct Windows Chromium cookie extraction (Edge, Chrome, Brave).
Reads the SQLite cookies DB and decrypts values without browser_cookie3.
Requires: pywin32 (win32crypt), pycryptodome or pycryptodomex (AES-GCM).
"""

import base64
import json
import os
import shutil
import sqlite3
import tempfile

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

    # Copy the DB and any WAL/SHM files to a temp dir for a consistent read.
    # Chromium uses WAL mode — recent cookies may only be in the -wal file.
    # A PermissionError here means the browser is running with an exclusive lock.
    tmp_dir = tempfile.mkdtemp()
    try:
        tmp_db = os.path.join(tmp_dir, "cookies.db")
        try:
            shutil.copy2(db_path, tmp_db)
            for ext in ("-wal", "-shm"):
                src = db_path + ext
                if os.path.exists(src):
                    shutil.copy2(src, tmp_db + ext)
        except PermissionError:
            raise PermissionError(
                f"{browser.title()} is running and has locked the cookies file.\n\n"
                "Close the browser and try again."
            )
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
