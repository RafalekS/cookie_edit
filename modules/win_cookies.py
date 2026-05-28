"""
Direct Windows Chromium cookie extraction (Edge, Chrome, Brave).

Two extraction methods are provided:

extract()      – reads the SQLite Cookies DB directly.
                 Works for v10 cookies (DPAPI-wrapped AES key).
                 v20 cookies (Chrome 127+ app-bound encryption) decrypt to ""
                 because the app-bound key requires Chrome's Elevation Service
                 (SYSTEM-level); DPAPI alone is not sufficient.

extract_cdp()  – closes the browser, relaunches it headless with
                 --remote-debugging-port, pulls all cookies via the Chrome
                 DevTools Protocol (the browser decrypts them internally),
                 then terminates the headless process.
                 Works for all cookie versions including v20.
"""

import base64
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import socket
import sqlite3
import struct
import subprocess
import tempfile
import time
import urllib.request


class BrowserLockedError(PermissionError):
    """The browser holds an exclusive lock on the cookies DB (Windows error 32)."""
    def __init__(self, browser):
        self.browser = browser
        super().__init__(
            f"{browser.title()} has the cookies file exclusively locked "
            "(Windows error 32 — ERROR_SHARING_VIOLATION)."
        )


_BROWSER_EXE = {
    "brave":  "brave.exe",
    "chrome": "chrome.exe",
    "edge":   "msedge.exe",
}

_BROWSER_EXE_PATHS = {
    "brave": [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
}

BROWSER_PATHS = {
    "edge":   r"Microsoft\Edge\User Data",
    "chrome": r"Google\Chrome\User Data",
    "brave":  r"BraveSoftware\Brave-Browser\User Data",
}

_NO_WINDOW          = 0x08000000  # CREATE_NO_WINDOW
_CHROME_EPOCH_US    = 11_644_473_600 * 1_000_000
_CDP_PORT           = 9222
_CDP_STARTUP_WAIT   = 20   # seconds to wait for the debugging port


# ──────────────────────────────────────────────────── browser process helpers

def close_browser(browser):
    """Gracefully close a Chromium browser; force-kill after 8 s."""
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


def _find_exe(browser):
    for path in _BROWSER_EXE_PATHS.get(browser, []):
        if os.path.isfile(path):
            return path
    return None


def _user_data_dir(browser):
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    rel = BROWSER_PATHS.get(browser, "")
    return os.path.join(local_appdata, rel)


# ──────────────────────────────────────────────── minimal WebSocket client

def _ws_connect(host, port, path):
    key = base64.b64encode(os.urandom(16)).decode()
    sock = socket.create_connection((host, port), timeout=30)
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(req.encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Connection closed during WS handshake")
        buf += chunk
    if b"101" not in buf:
        raise ConnectionError(f"WebSocket upgrade failed: {buf[:120]}")
    return sock


def _ws_send(sock, text):
    data = text.encode()
    n    = len(data)
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    frame = bytearray([0x81])
    if n < 126:
        frame.append(0x80 | n)
    elif n < 65536:
        frame += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        frame += bytes([0x80 | 127]) + struct.pack(">Q", n)
    frame += mask + masked
    sock.sendall(bytes(frame))


def _ws_recv(sock):
    """Receive one complete (possibly multi-frame) WebSocket message."""
    def recv_exact(n):
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Connection closed mid-frame")
            buf += chunk
        return buf

    payload = b""
    while True:
        hdr    = recv_exact(2)
        fin    = (hdr[0] & 0x80) != 0
        opcode = hdr[0] & 0x0F
        masked = (hdr[1] & 0x80) != 0
        n      = hdr[1] & 0x7F
        if n == 126:
            n = struct.unpack(">H", recv_exact(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", recv_exact(8))[0]
        mask_key = recv_exact(4) if masked else b""
        data     = recv_exact(n)
        if masked:
            data = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))
        if opcode == 0x8:        # close
            return None
        if opcode in (0x1, 0x2, 0x0):  # text, binary, continuation
            payload += data
        if fin:
            return payload.decode("utf-8", errors="replace")


# ───────────────────────────────────────────────────────── CDP extraction

def _cdp_get_cookies(port, domain_filter):
    """Connect to a running browser on port and return all cookies."""
    base = f"http://127.0.0.1:{port}"

    # Get list of debuggable targets
    with urllib.request.urlopen(f"{base}/json", timeout=5) as r:
        targets = json.loads(r.read())

    # Prefer a page target; fall back to the first available
    ws_url = ""
    for t in targets:
        if t.get("type") == "page":
            ws_url = t.get("webSocketDebuggerUrl", "")
            break
    if not ws_url and targets:
        ws_url = targets[0].get("webSocketDebuggerUrl", "")
    if not ws_url:
        # No debuggable page — ask the browser to open one
        urllib.request.urlopen(f"{base}/json/new?about:blank", timeout=5).read()
        time.sleep(1)
        with urllib.request.urlopen(f"{base}/json", timeout=5) as r:
            targets = json.loads(r.read())
        ws_url = targets[0].get("webSocketDebuggerUrl", "") if targets else ""
    if not ws_url:
        raise ConnectionError("No debuggable target found on CDP port")

    from urllib.parse import urlparse
    p    = urlparse(ws_url)
    sock = _ws_connect(p.hostname, p.port, p.path)
    try:
        _ws_send(sock, json.dumps({"id": 1, "method": "Network.getAllCookies", "params": {}}))
        for _ in range(50):          # up to 50 messages before giving up
            msg = _ws_recv(sock)
            if msg is None:
                break
            data = json.loads(msg)
            if data.get("id") == 1:
                raw = data.get("result", {}).get("cookies", [])
                return _parse_cdp_cookies(raw, domain_filter)
    finally:
        try:
            sock.close()
        except OSError:
            pass
    raise ConnectionError("No response to Network.getAllCookies")


def _parse_cdp_cookies(raw, domain_filter):
    cookies = []
    for c in raw:
        domain = c.get("domain", "")
        if domain_filter and domain_filter.lower() not in domain.lower():
            continue
        expiry = c.get("expires", 0)
        cookies.append({
            "domain": domain,
            "flag":   "TRUE" if domain.startswith(".") else "FALSE",
            "path":   c.get("path", "/"),
            "secure": "TRUE" if c.get("secure", False) else "FALSE",
            "expiry": str(int(expiry)) if expiry and expiry > 0 else "0",
            "name":   c.get("name", ""),
            "value":  c.get("value", ""),
        })
    return cookies


def extract_cdp(browser, domain_filter=None, port=_CDP_PORT):
    """Extract cookies via Chrome DevTools Protocol.

    Closes the browser (if running), launches it headless with
    --remote-debugging-port, reads all cookies via CDP, then terminates
    the headless process.  Works for all encryption versions including v20.
    """
    exe = _find_exe(browser)
    if not exe:
        raise FileNotFoundError(
            f"Cannot find {browser.title()} executable.\n"
            "Check that the browser is installed in the default location."
        )

    udd = _user_data_dir(browser)
    if not os.path.isdir(udd):
        raise FileNotFoundError(
            f"{browser.title()} profile directory not found:\n{udd}"
        )

    # Close any running instance so the profile is not locked
    close_browser(browser)
    time.sleep(1)

    proc = subprocess.Popen(
        [
            exe,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={udd}",
            "--headless=new",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_NO_WINDOW,
    )
    try:
        # Wait for the debugging port to respond
        deadline = time.time() + _CDP_STARTUP_WAIT
        last_err = None
        while time.time() < deadline:
            try:
                return _cdp_get_cookies(port, domain_filter)
            except Exception as e:
                last_err = e
                time.sleep(0.5)
        raise ConnectionError(
            f"{browser.title()} did not expose CDP on port {port} within "
            f"{_CDP_STARTUP_WAIT} s.\nLast error: {last_err}"
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


# ──────────────────────────────────────────── file-based extraction (legacy)

class _SharingViolation(Exception):
    pass


def _copy_file_shared(src, dst):
    k32 = ctypes.windll.kernel32
    k32.CreateFileW.restype = ctypes.c_void_p
    handle = k32.CreateFileW(
        ctypes.c_wchar_p(src), 0x80000000, 0x7, None, 3, 0, None,
    )
    INVALID = ctypes.c_void_p(-1).value
    if handle is None or handle == INVALID:
        err = k32.GetLastError()
        if err == 32:
            raise _SharingViolation()
        raise PermissionError(f"Cannot open file (Windows error {err}): {src}")
    try:
        high = wt.DWORD(0)
        low  = k32.GetFileSize(ctypes.c_void_p(handle), ctypes.byref(high))
        size = (high.value << 32) | low
        buf  = (ctypes.c_char * size)() if size else None
        if buf:
            read = wt.DWORD(0)
            k32.ReadFile(ctypes.c_void_p(handle), buf, size, ctypes.byref(read), None)
            data = bytes(buf)[: read.value]
        else:
            data = b""
    finally:
        k32.CloseHandle(ctypes.c_void_p(handle))
    with open(dst, "wb") as f:
        f.write(data)


def _get_keys(user_data_dir):
    import win32crypt
    with open(os.path.join(user_data_dir, "Local State"), "r", encoding="utf-8") as f:
        ls = json.load(f)
    raw = base64.b64decode(ls["os_crypt"]["encrypted_key"])[5:]
    _, v10_key = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
    v20_key = None
    app_b64 = ls.get("os_crypt", {}).get("app_bound_encrypted_key", "")
    if app_b64:
        try:
            app_raw = base64.b64decode(app_b64)
            if app_raw[:4] == b"APPB":
                app_raw = app_raw[4:]
            for flag in (0, 4):
                try:
                    _, v20_key = win32crypt.CryptUnprotectData(app_raw, None, None, None, flag)
                    break
                except Exception:
                    continue
        except Exception:
            pass
    return v10_key, v20_key


def _aes_decrypt(data, key):
    try:
        from Cryptodome.Cipher import AES
    except ImportError:
        from Crypto.Cipher import AES
    cipher = AES.new(key, AES.MODE_GCM, nonce=data[3:15])
    return cipher.decrypt_and_verify(data[15:-16], data[-16:]).decode("utf-8")


def _decrypt_value(enc, v10_key, v20_key):
    if not enc:
        return ""
    prefix = enc[:3]
    if prefix == b"v10":
        try:
            return _aes_decrypt(enc, v10_key)
        except Exception:
            return ""
    if prefix == b"v20":
        if v20_key:
            try:
                return _aes_decrypt(enc, v20_key)
            except Exception:
                return ""
        return ""
    try:
        import win32crypt
        _, plain = win32crypt.CryptUnprotectData(enc, None, None, None, 0)
        return plain.decode("utf-8")
    except Exception:
        return ""


def _chrome_ts_to_unix(ts):
    if not ts:
        return 0
    try:
        return int((ts - _CHROME_EPOCH_US) / 1_000_000)
    except Exception:
        return 0


def _find_cookies_db(user_data_dir, profile="Default"):
    for sub in (os.path.join(profile, "Network", "Cookies"), os.path.join(profile, "Cookies")):
        p = os.path.join(user_data_dir, sub)
        if os.path.isfile(p):
            return p
    return None


def extract(browser, domain_filter=None):
    """File-based extraction (v10 only; v20 cookies will have empty values)."""
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if not local_appdata:
        raise EnvironmentError("LOCALAPPDATA is not set.")
    rel = BROWSER_PATHS.get(browser)
    if not rel:
        raise ValueError(f"Unsupported browser: {browser!r}")
    udd = os.path.join(local_appdata, rel)
    if not os.path.isdir(udd):
        raise FileNotFoundError(f"{browser.title()} profile not found: {udd}")

    v10_key, v20_key = _get_keys(udd)
    db_path = _find_cookies_db(udd)
    if not db_path:
        raise FileNotFoundError(f"Cookies DB not found under {udd}.")

    tmp_dir = tempfile.mkdtemp()
    try:
        tmp_db = os.path.join(tmp_dir, "cookies.db")
        try:
            _copy_file_shared(db_path, tmp_db)
        except _SharingViolation:
            raise BrowserLockedError(browser)
        for ext in ("-wal", "-shm"):
            src = db_path + ext
            if os.path.exists(src):
                try:
                    _copy_file_shared(src, tmp_db + ext)
                except (_SharingViolation, PermissionError):
                    pass
        cookies = []
        con = sqlite3.connect(tmp_db)
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT host_key, path, is_secure, expires_utc, name, encrypted_value "
                "FROM cookies"
            )
            for host_key, path, is_secure, expires_utc, name, enc in cur.fetchall():
                if domain_filter and domain_filter.lower() not in (host_key or "").lower():
                    continue
                cookies.append({
                    "domain": host_key or "",
                    "flag":   "TRUE" if (host_key or "").startswith(".") else "FALSE",
                    "path":   path or "/",
                    "secure": "TRUE" if is_secure else "FALSE",
                    "expiry": str(_chrome_ts_to_unix(expires_utc)),
                    "name":   name or "",
                    "value":  _decrypt_value(enc, v10_key, v20_key),
                })
        finally:
            con.close()
        return cookies
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
