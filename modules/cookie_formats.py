import json

NETSCAPE_HEADER = "# Netscape HTTP Cookie File"
COLUMNS = ["domain", "flag", "path", "secure", "expiry", "name", "value"]


def detect_format(filepath):
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read(4096).strip()

    if not content:
        return "netscape"

    # JSON array/object
    if content.startswith("[") or content.startswith("{"):
        try:
            json.loads(content if len(content) < 4096 else _read_all(filepath))
            return "json"
        except (json.JSONDecodeError, Exception):
            pass

    # Netscape: comment header or tab-separated
    if content.startswith("#") or "\t" in content.split("\n")[0]:
        return "netscape"

    # Header string: single line with semicolons and equals
    first_line = content.split("\n")[0].strip()
    if ";" in first_line and "=" in first_line:
        return "header"

    return "netscape"


def _read_all(filepath):
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def parse_netscape(filepath):
    cookies = []
    comments = []
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line_num, raw in enumerate(f):
            line = raw.rstrip("\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                comments.append((line_num, line))
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies.append({
                    "domain": parts[0],
                    "flag": parts[1],
                    "path": parts[2],
                    "secure": parts[3],
                    "expiry": parts[4],
                    "name": parts[5],
                    "value": "\t".join(parts[6:]),  # value may contain tabs
                })
    return cookies, comments


def save_netscape(filepath, cookies, comments):
    lines = []
    # Write preserved comment lines
    if comments:
        for _, text in comments:
            lines.append(text)
    else:
        lines.append(NETSCAPE_HEADER)

    for c in cookies:
        domain = c.get("domain", "")
        flag = c.get("flag", "FALSE")
        path = c.get("path", "/")
        secure = c.get("secure", "FALSE")
        expiry = c.get("expiry", "0")
        name = c.get("name", "")
        value = c.get("value", "")
        lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")

    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def parse_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        data = [data]

    cookies = []
    for item in data:
        raw_expiry = item.get("expirationDate", item.get("expires", item.get("expiry", "")))
        if isinstance(raw_expiry, (int, float)):
            expiry = str(int(raw_expiry))
        else:
            expiry = str(raw_expiry) if raw_expiry is not None else ""

        secure = item.get("secure", False)
        host_only = item.get("hostOnly", False)

        cookie = {
            "domain": item.get("domain", ""),
            "flag": "TRUE" if not host_only else "FALSE",
            "path": item.get("path", "/"),
            "secure": "TRUE" if secure else "FALSE",
            "expiry": expiry,
            "name": item.get("name", ""),
            "value": item.get("value", ""),
        }
        # Preserve extra JSON fields as metadata
        for key in ("httpOnly", "sameSite", "storeId", "session"):
            if key in item:
                cookie[f"_json_{key}"] = item[key]
        cookies.append(cookie)

    return cookies, []


def save_json(filepath, cookies):
    output = []
    for c in cookies:
        expiry_str = c.get("expiry", "")
        try:
            expiry_val = int(expiry_str)
        except (ValueError, TypeError):
            expiry_val = 0

        item = {
            "domain": c.get("domain", ""),
            "expirationDate": expiry_val,
            "hostOnly": c.get("flag", "FALSE").upper() != "TRUE",
            "httpOnly": c.get("_json_httpOnly", False),
            "name": c.get("name", ""),
            "path": c.get("path", "/"),
            "sameSite": c.get("_json_sameSite", "unspecified"),
            "secure": c.get("secure", "FALSE").upper() == "TRUE",
            "session": c.get("_json_session", False),
            "storeId": c.get("_json_storeId", "0"),
            "value": c.get("value", ""),
        }
        output.append(item)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
        f.write("\n")


def parse_header(filepath):
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read().strip()

    if content.lower().startswith("cookie:"):
        content = content[7:].strip()

    cookies = []
    for part in content.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            name, _, value = part.partition("=")
            cookies.append({
                "domain": "",
                "flag": "",
                "path": "",
                "secure": "",
                "expiry": "",
                "name": name.strip(),
                "value": value.strip(),
            })

    return cookies, []


def save_header(filepath, cookies):
    parts = [
        f"{c.get('name', '')}={c.get('value', '')}"
        for c in cookies
        if c.get("name", "").strip()
    ]
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("; ".join(parts) + "\n")


def parse_file_as(filepath, fmt):
    if fmt == "netscape":
        cookies, comments = parse_netscape(filepath)
        return {"cookies": cookies, "comments": comments}
    elif fmt == "json":
        cookies, comments = parse_json(filepath)
        return {"cookies": cookies, "comments": comments}
    elif fmt == "header":
        cookies, comments = parse_header(filepath)
        return {"cookies": cookies, "comments": comments}
    else:
        raise ValueError(f"Unknown format: {fmt}")


def save_file(filepath, data, fmt):
    cookies = data.get("cookies", [])
    comments = data.get("comments", [])
    if fmt == "netscape":
        save_netscape(filepath, cookies, comments)
    elif fmt == "json":
        save_json(filepath, cookies)
    elif fmt == "header":
        save_header(filepath, cookies)
    else:
        raise ValueError(f"Unknown format: {fmt}")
