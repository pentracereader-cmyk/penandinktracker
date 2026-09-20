#!/usr/bin/env python3
"""
Pen & Ink Tracker — local server.

Serves the SPA, stores collection data, accepts photo uploads (including from
an iPhone over the LAN via a QR hand-off), and proxies AI auto-fill requests
to the Anthropic API.

Run:  python tracker/server.py
Then open the URL it prints. The same URL works from your phone on the same
Wi-Fi (that's what the in-app QR code encodes).

Writer separation (avoids data races):
  - The browser owns pens.json and inks.json (collection fields).
  - The server owns photos.json (photo<->record associations) and the photo
    files on disk. Phone uploads therefore never clobber desktop edits.
"""

import http.server
import socketserver
import json
import os
import re
import base64
import difflib
import binascii
import socket
import secrets
import threading
import time
import ipaddress
import urllib.request
import urllib.error
import urllib.parse
import html as html_lib
import io
import zipfile
import xml.etree.ElementTree as ET
import sys
import shutil
from datetime import date, timedelta

PORT = int(os.environ.get('PI_PORT', '3838'))  # PI_PORT lets a v2 instance run alongside
INDEX = os.environ.get('PI_INDEX', 'index.html')  # which shell to serve at /

# When PyInstaller freezes this into a --onefile .exe, __file__ resolves
# inside the ephemeral per-run extraction folder (sys._MEIPASS) rather than
# next to the actual .exe -- that folder is deleted when the process exits,
# so anything saved there (a new pen, a photo) would silently vanish on the
# next launch. Persist data next to the real executable instead.
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PHOTOS_DIR  = os.path.join(BASE_DIR, 'photos')
BACKUP_DIR  = os.path.join(BASE_DIR, 'backups')
PENS_FILE   = os.path.join(BASE_DIR, 'pens.json')
INKS_FILE   = os.path.join(BASE_DIR, 'inks.json')
PAPERS_FILE = os.path.join(BASE_DIR, 'papers.json')
LEARNED_FILE = os.path.join(BASE_DIR, 'catalog_learned.json')
PHOTOS_FILE = os.path.join(BASE_DIR, 'photos.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

# Names PyInstaller's --add-data bundles into sys._MEIPASS (see
# packaging/build_exe.py's DATA_FILES_FROM_TRACKER -- keep the two lists in
# sync). Copied out to BASE_DIR once, next to the real .exe, so the static
# assets are servable and the data files are real, persistent, editable
# files rather than read-only copies trapped in the temp bundle. Never
# overwrites a file that already exists, so re-running (or upgrading to a
# newer .exe) never clobbers an existing collection.
_FROZEN_RESOURCE_NAMES = [
    'index.html', 'qrcode.min.js', 'manifest.json', 'icon-192.png',
    'icon-512.png', 'apple-touch-icon.png', 'ink_catalog.json',
    'config.example.json', 'pens.json', 'inks.json', 'papers.json',
    'photos.json', 'catalog_learned.json',
]


def _ensure_frozen_resources():
    if not getattr(sys, 'frozen', False):
        return
    bundle_dir = getattr(sys, '_MEIPASS', None)
    if not bundle_dir or not os.path.isdir(bundle_dir):
        return
    for name in _FROZEN_RESOURCE_NAMES:
        src = os.path.join(bundle_dir, name)
        dst = os.path.join(BASE_DIR, name)
        if os.path.exists(dst) or not os.path.isfile(src):
            continue
        try:
            shutil.copy2(src, dst)
        except OSError:
            pass
    src_photos = os.path.join(bundle_dir, 'photos')
    dst_photos = os.path.join(BASE_DIR, 'photos')
    if os.path.isdir(src_photos) and not os.path.isdir(dst_photos):
        try:
            shutil.copytree(src_photos, dst_photos)
        except OSError:
            pass


_ensure_frozen_resources()
os.makedirs(PHOTOS_DIR, exist_ok=True)

MAX_UPLOAD_BYTES   = 25 * 1024 * 1024   # 25 MB per photo (base64 overhead ~33%)
MAX_DATA_BYTES     =  4 * 1024 * 1024   # 4 MB collection JSON

# Per-run token. LAN (phone) clients must present it; localhost is trusted.
UPLOAD_TOKEN = secrets.token_urlsafe(12)

_write_lock = threading.Lock()

IMAGE_SIGNATURES = [
    b'\xff\xd8\xff',          # JPEG
    b'\x89PNG\r\n\x1a\n',     # PNG
    b'GIF87a', b'GIF89a',     # GIF
    b'RIFF',                  # WebP (RIFF....WEBP)
    b'\x00\x00\x00',          # MP4/HEIC container box
]


def load_config():
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            # utf-8-sig tolerates a BOM, which Windows editors / PowerShell add.
            with open(CONFIG_FILE, encoding='utf-8-sig') as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError):
            cfg = {}
    # env vars supplement the file
    if os.environ.get('ANTHROPIC_API_KEY'):
        cfg.setdefault('anthropic_api_key', os.environ['ANTHROPIC_API_KEY'])
    env_gem = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if env_gem:
        cfg.setdefault('gemini_api_key', env_gem)
    cfg.setdefault('provider', 'gemini')               # 'gemini' (default) | 'anthropic'
    cfg.setdefault('gemini_model', 'gemini-2.5-flash')
    cfg.setdefault('model', 'claude-opus-4-8')          # used when provider == 'anthropic'
    cfg.setdefault('enable_web_search', True)
    return cfg




def _placeholder_key(k):
    """True if the key is empty or still the example placeholder."""
    k = str(k or '')
    return (not k) or k.startswith('sk-ant-...') or k.startswith('AIza...') or 'YOUR' in k.upper()


def lan_ip():
    """Best-effort primary LAN IPv4 (no traffic actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def is_image_bytes(data: bytes) -> bool:
    for sig in IMAGE_SIGNATURES:
        if data[:len(sig)] == sig:
            return True
    if len(data) >= 12 and data[8:12] == b'WEBP':
        return True
    return False


# ── SSRF-safe outbound fetch ─────────────────────────────────────────────────
# Every fetch of a user-supplied URL (image import, og:image scraping, the URL
# capture feature) must go through _safe_fetch. The server binds 0.0.0.0 and
# exposes these fetchers to any client that can reach it (including the phone
# over Wi-Fi), so a hostile URL must not be usable to probe the LAN, this
# machine's own loopback services, or cloud metadata endpoints.

_ALLOWED_SCHEMES = ('http', 'https')
_BROWSER_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
               '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')


def _unsafe_ip(ip):
    """True if *ip* is not a public, externally-routable address."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (ip.is_private or ip.is_loopback or ip.is_link_local or
            ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def _validate_url_host(url):
    """Raise RuntimeError unless *url* is http(s) and every address its host
    resolves to is public. Returns the hostname on success."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise RuntimeError(f'Refusing to fetch — unsupported URL scheme "{parsed.scheme or "?"}". '
                            f'Only http/https URLs are allowed.')
    host = parsed.hostname
    if not host:
        raise RuntimeError('Refusing to fetch — that URL has no hostname.')
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise RuntimeError(f'Could not resolve host "{host}": {e}')
    if not infos:
        raise RuntimeError(f'Could not resolve host "{host}".')
    for info in infos:
        addr = info[4][0].split('%', 1)[0]  # strip IPv6 zone id, e.g. fe80::1%eth0
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            raise RuntimeError(f'Refusing to fetch — could not parse a resolved address for "{host}".')
        if _unsafe_ip(ip):
            raise RuntimeError(
                f'Refusing to fetch "{host}" — it resolves to a non-public address ({ip}). '
                f'This looks like an attempt to reach a local or internal service.')
    return host


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validates every redirect hop against _validate_url_host and caps the
    chain at 5 hops. The stdlib default follows many more redirects and never
    re-checks the destination host, which would otherwise let an attacker
    bounce a first, innocuous-looking URL onto an internal address."""

    def __init__(self):
        self.hops = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.hops += 1
        if self.hops > 5:
            raise RuntimeError('Too many redirects.')
        _validate_url_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _safe_fetch(url, max_bytes=1_500_000, timeout=12, expect=None, truncate=False):
    """Fetch *url* with SSRF protections and a hard size cap.

    Validates the scheme and every resolved address before connecting,
    re-validates on each redirect hop (capped at 5), and enforces
    Content-Length plus a streamed-size ceiling of *max_bytes*. When *expect*
    is 'html' or 'json', also rejects a mismatched Content-Type.

    Returns (data: bytes, content_type: str, final_url: str). Raises
    RuntimeError with a short, user-facing message on any violation — never
    lets a raw exception/stack trace reach the caller.
    """
    _validate_url_host(url)
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    req = urllib.request.Request(url, headers={'User-Agent': _BROWSER_UA, 'Accept': '*/*'})
    try:
        with opener.open(req, timeout=timeout) as r:
            final_url = r.geturl()
            _validate_url_host(final_url)  # belt-and-braces on the address we actually connected to
            ctype = r.headers.get('Content-Type', '') or ''
            clen = r.headers.get('Content-Length')
            if clen is not None and not truncate:
                try:
                    if int(clen) > max_bytes:
                        raise RuntimeError(f'Response too large ({clen} bytes; limit {max_bytes}).')
                except ValueError:
                    pass
            if expect == 'html' and ctype and 'html' not in ctype.lower() and 'json' not in ctype.lower():
                raise RuntimeError(f'Expected an HTML page but got content-type "{ctype}".')
            if expect == 'json' and ctype and 'json' not in ctype.lower():
                raise RuntimeError(f'Expected JSON but got content-type "{ctype}".')
            data = r.read(max_bytes + 1)
            if len(data) > max_bytes:
                # truncate=True: callers that only need the <head> (og:image scraping)
                # take a bounded prefix instead of failing on a large-but-legitimate page.
                if truncate:
                    data = data[:max_bytes]
                else:
                    raise RuntimeError(f'Response exceeded {max_bytes} bytes; aborted.')
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Server returned HTTP {e.code} for that URL.')
    except urllib.error.URLError as e:
        raise RuntimeError(f'Could not reach that URL: {e.reason}')
    except socket.timeout:
        raise RuntimeError('Timed out fetching that URL.')
    return data, ctype, final_url


def safe_join(directory, filename):
    final = os.path.realpath(os.path.join(directory, filename))
    if os.path.commonpath([final, os.path.realpath(directory)]) == os.path.realpath(directory):
        return final
    return None


def read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        # utf-8-sig tolerates a BOM from hand-edits on Windows.
        with open(path, encoding='utf-8-sig') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def write_json_atomic(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


PHOTO_TAGS = ('photo', 'swab', 'writing')


def normalize_photos(ph):
    """Photos were once plain URL strings; canonical form is {url, tag}."""
    out = {}
    for k, v in (ph or {}).items():
        entries = []
        for e in v or []:
            if isinstance(e, str):
                entries.append({'url': e, 'tag': 'photo'})
            elif isinstance(e, dict) and e.get('url'):
                tag = e.get('tag') if e.get('tag') in PHOTO_TAGS else 'photo'
                entries.append({'url': e['url'], 'tag': tag})
        if entries:
            out[k] = entries
    return out


# per kind: (identity keys, attribute keys worth remembering)
LEARN_KEYS = {
    'ink':   (('brand', 'name'), ('color_match', 'sheen', 'shimmer', 'shading', 'alkaline')),
    'pen':   (('make', 'model'), ('material_color', 'filling', 'year_or_era', 'nib_material')),
    'paper': (('brand', 'name'), ('type', 'size', 'gsm', 'ruling', 'surface')),
}


def learn_item(kind, fields):
    """Cache a researched item into the self-growing local catalog (best effort)."""
    if kind not in LEARN_KEYS:
        return
    id_keys, attr_keys = LEARN_KEYS[kind]
    ids = [str(fields.get(k) or '').strip() for k in id_keys]
    if not all(ids):
        return
    entry = {'kind': kind}
    entry.update(dict(zip(id_keys, ids)))
    for k in attr_keys:
        if fields.get(k) not in (None, ''):
            entry[k] = fields[k]
    try:
        with _write_lock:
            learned = read_json(LEARNED_FILE, [])
            if not isinstance(learned, list):
                learned = []
            kl = tuple(s.lower() for s in ids)
            for e in learned:
                if (e.get('kind', 'ink') == kind and
                        tuple(str(e.get(k, '')).lower() for k in id_keys) == kl):
                    return
            learned.append(entry)
            write_json_atomic(LEARNED_FILE, learned)
    except Exception as e:  # noqa: BLE001 — learning must never break a fill
        print(f'[learn warning] {e}')


def backup_file(path, keep=20):
    """Snapshot *path* into backups/ before overwriting; keep the newest N."""
    if not os.path.exists(path):
        return
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        base = os.path.basename(path)
        dest = os.path.join(BACKUP_DIR, f"{time.strftime('%Y%m%d-%H%M%S')}_{base}")
        with open(path, 'rb') as s, open(dest, 'wb') as d:
            d.write(s.read())
        old = sorted(f for f in os.listdir(BACKUP_DIR) if f.endswith('_' + base))
        for f in old[:-keep]:
            os.remove(os.path.join(BACKUP_DIR, f))
    except OSError as e:
        print(f'[backup warning] {e}')


# ── .xlsx parsing (stdlib only: an xlsx is a zip of XML parts) ───────────────
XLSX_MAX_ROWS = 5000
XLSX_MAX_COLS = 100

_NS_MAIN    = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
_NS_DOC_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_NS_PKG_REL = 'http://schemas.openxmlformats.org/package/2006/relationships'

_XLSX_BUILTIN_DATE_FMT_IDS = {14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47}


def _qn(ns, tag):
    return f'{{{ns}}}{tag}'


def _xlsx_col_to_index(letters):
    """'A' -> 0, 'B' -> 1, ... 'Z' -> 25, 'AA' -> 26, ..."""
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch.upper()) - ord('A') + 1)
    return idx - 1


def _xlsx_split_ref(ref):
    """'C5' -> (2, 5). Returns (None, None) if unparseable."""
    m = re.match(r'^([A-Za-z]+)(\d+)$', ref or '')
    if not m:
        return None, None
    return _xlsx_col_to_index(m.group(1)), int(m.group(2))


def _is_date_format_code(code):
    """True if a numFmt format code represents a date/time (contains a bare
    y, m or d outside quoted literals and [bracketed] color/condition tags)."""
    s = re.sub(r'"[^"]*"', '', code or '')
    s = re.sub(r'\[[^\]]*\]', '', s)
    s = re.sub(r'\\.', '', s)
    return bool(re.search(r'[ymd]', s, re.IGNORECASE))


def _excel_serial_to_date(raw):
    """Excel 1900-epoch serial number -> 'YYYY-MM-DD', including the
    fictitious 1900-02-29 leap-year bug (serial 60)."""
    try:
        n = float(raw)
    except (TypeError, ValueError):
        return None
    if n == 60:
        return '1900-02-29'
    days = int(n)
    if days > 59:
        days -= 1  # compensate for the nonexistent Feb 29, 1900
    try:
        d = date(1899, 12, 31) + timedelta(days=days)
    except OverflowError:
        return None
    return d.strftime('%Y-%m-%d')


def _xlsx_shared_strings(zf):
    try:
        data = zf.read('xl/sharedStrings.xml')
    except KeyError:
        return []
    root = ET.fromstring(data)
    out = []
    for si in root.findall(_qn(_NS_MAIN, 'si')):
        out.append(''.join(t.text or '' for t in si.iter(_qn(_NS_MAIN, 't'))))
    return out


def _xlsx_date_style_ids(zf):
    """Return the set of cellXfs style indices (the `s=` attribute on <c>)
    that are formatted as a date, so numeric values under them get converted."""
    try:
        data = zf.read('xl/styles.xml')
    except KeyError:
        return set()
    root = ET.fromstring(data)
    custom_fmts = {}
    numfmts_el = root.find(_qn(_NS_MAIN, 'numFmts'))
    if numfmts_el is not None:
        for nf in numfmts_el.findall(_qn(_NS_MAIN, 'numFmt')):
            try:
                custom_fmts[int(nf.get('numFmtId'))] = nf.get('formatCode', '')
            except (TypeError, ValueError):
                continue
    date_ids = set()
    cellxfs_el = root.find(_qn(_NS_MAIN, 'cellXfs'))
    if cellxfs_el is not None:
        for i, xf in enumerate(cellxfs_el.findall(_qn(_NS_MAIN, 'xf'))):
            fid_attr = xf.get('numFmtId')
            if fid_attr is None:
                continue
            try:
                fid = int(fid_attr)
            except ValueError:
                continue
            if fid in _XLSX_BUILTIN_DATE_FMT_IDS:
                date_ids.add(i)
            elif fid in custom_fmts and _is_date_format_code(custom_fmts[fid]):
                date_ids.add(i)
    return date_ids


def _xlsx_read_sheet_list(zf):
    """Sheet names/order from xl/workbook.xml, resolved to their worksheet
    part paths via xl/_rels/workbook.xml.rels (NOT assumed to be sheetN.xml
    in visible order — the rels are the source of truth)."""
    try:
        wb_root = ET.fromstring(zf.read('xl/workbook.xml'))
    except KeyError:
        raise RuntimeError('That zip file does not look like an Excel workbook '
                            '(missing xl/workbook.xml).')
    sheets = []
    sheets_el = wb_root.find(_qn(_NS_MAIN, 'sheets'))
    if sheets_el is not None:
        for sh in sheets_el.findall(_qn(_NS_MAIN, 'sheet')):
            sheets.append({
                'name': sh.get('name', ''),
                'rid': sh.get(_qn(_NS_DOC_REL, 'id')),
                'hidden': sh.get('state', 'visible') in ('hidden', 'veryHidden'),
            })
    rels_map = {}
    try:
        rels_root = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
        for rel in rels_root.findall(_qn(_NS_PKG_REL, 'Relationship')):
            rels_map[rel.get('Id')] = rel.get('Target', '')
    except KeyError:
        pass
    for sh in sheets:
        target = (rels_map.get(sh['rid']) or '').lstrip('/')
        if target and not target.startswith('xl/'):
            target = 'xl/' + target
        sh['path'] = target
    return sheets


def _xlsx_cell_value(c_el, shared, date_ids):
    ctype = c_el.get('t')
    style = c_el.get('s')
    if ctype == 'inlineStr':
        is_el = c_el.find(_qn(_NS_MAIN, 'is'))
        if is_el is None:
            return ''
        return ''.join(t.text or '' for t in is_el.iter(_qn(_NS_MAIN, 't')))
    v_el = c_el.find(_qn(_NS_MAIN, 'v'))
    if v_el is None or v_el.text is None:
        return ''
    raw = v_el.text
    if ctype == 's':
        try:
            idx = int(raw)
        except ValueError:
            return ''
        return shared[idx] if 0 <= idx < len(shared) else ''
    if ctype == 'str':
        return raw
    if ctype == 'b':
        return 'TRUE' if raw == '1' else 'FALSE'
    if ctype == 'e':
        return raw
    # Plain numeric cell (t absent or t="n").
    try:
        style_idx = int(style) if style is not None else None
    except ValueError:
        style_idx = None
    if style_idx is not None and style_idx in date_ids:
        d = _excel_serial_to_date(raw)
        if d:
            return d
    try:
        f = float(raw)
        if f.is_integer() and abs(f) < 1e15:
            return str(int(f))
    except ValueError:
        pass
    return raw


def _xlsx_parse_sheet_xml(xml_bytes, shared, date_ids):
    root = ET.fromstring(xml_bytes)
    sheet_data = root.find(_qn(_NS_MAIN, 'sheetData'))
    if sheet_data is None:
        return []
    raw_rows = []
    for row_el in sheet_data.findall(_qn(_NS_MAIN, 'row')):
        if len(raw_rows) >= XLSX_MAX_ROWS:
            raise RuntimeError(f'That workbook has more than {XLSX_MAX_ROWS} rows in '
                                f'this sheet — please split or trim it before importing.')
        row_vals = {}
        next_idx = 0
        for c_el in row_el.findall(_qn(_NS_MAIN, 'c')):
            # Cell refs are sparse (a missing <c r="B5"> means B5 is empty), so
            # the column position must come from parsing `r`, not from list order.
            col_idx, _rownum = _xlsx_split_ref(c_el.get('r'))
            if col_idx is None:
                col_idx = next_idx
            row_vals[col_idx] = _xlsx_cell_value(c_el, shared, date_ids)
            next_idx = col_idx + 1
        raw_rows.append(row_vals)
    max_col = max((max(rv.keys()) + 1 for rv in raw_rows if rv), default=0)
    if max_col > XLSX_MAX_COLS:
        raise RuntimeError(f'That workbook has more than {XLSX_MAX_COLS} columns in '
                            f'this sheet — please trim it before importing.')
    return [[rv.get(i, '') for i in range(max_col)] for rv in raw_rows]


def parse_xlsx(file_bytes, sheet_name=None):
    """Parse an .xlsx file's bytes into (sheet_names, chosen_sheet_name, rows).

    `rows` is a header row followed by data rows, every cell a string, padded
    to a rectangular grid. Raises RuntimeError with a plain-English message
    on anything invalid or corrupt — never lets a stack trace escape.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile:
        raise RuntimeError('That does not look like a valid .xlsx file (not a zip archive). '
                            'Try exporting as CSV instead.')
    try:
        sheets = _xlsx_read_sheet_list(zf)
    except ET.ParseError:
        raise RuntimeError('Could not read that workbook — it looks corrupt. '
                            'Try exporting as CSV instead.')
    if not sheets:
        raise RuntimeError('No sheets found in that workbook.')
    names = [s['name'] for s in sheets]
    if sheet_name:
        chosen = next((s for s in sheets if s['name'] == sheet_name), None)
        if chosen is None:
            raise RuntimeError(f'Sheet "{sheet_name}" was not found in that workbook.')
    else:
        chosen = next((s for s in sheets if not s['hidden']), sheets[0])
    if not chosen.get('path'):
        raise RuntimeError(f'Could not locate the "{chosen["name"]}" sheet inside the workbook.')
    try:
        sheet_xml = zf.read(chosen['path'])
    except KeyError:
        raise RuntimeError(f'Could not locate the "{chosen["name"]}" sheet inside the workbook.')
    try:
        shared = _xlsx_shared_strings(zf)
        date_ids = _xlsx_date_style_ids(zf)
    except ET.ParseError:
        raise RuntimeError('Could not read that workbook — it looks corrupt. '
                            'Try exporting as CSV instead.')
    try:
        rows = _xlsx_parse_sheet_xml(sheet_xml, shared, date_ids)
    except ET.ParseError:
        raise RuntimeError('Could not read that sheet — it looks corrupt. '
                            'Try exporting as CSV instead.')
    return names, chosen['name'], rows


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def is_local(self):
        return self.client_address[0] in ('127.0.0.1', '::1', 'localhost')

    def end_headers(self):
        # Always revalidate the app shell so UI updates show up on plain reload.
        p = self.path.split('?', 1)[0]
        if p in ('/', '/index.html', '/' + INDEX):
            self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    # ── routing ──────────────────────────────────────────────────────────────
    def do_GET(self):
        if self.path == '/' :
            self.path = '/' + INDEX
            return super().do_GET()
        if self.path.startswith('/api/data'):
            return self._get_data()
        if self.path.startswith('/api/qr-info'):
            return self._qr_info()
        if self.path.startswith('/m'):
            return self._mobile_page()
        # Block direct download of secrets and source. The server binds 0.0.0.0 so the
        # phone can reach it, which means anything on the Wi-Fi can request these too.
        if not self._servable(self.path):
            return self.send_error(404)
        return super().do_GET()

    # Files the browser legitimately needs. Everything else is refused rather than
    # denylisted, so a new file added next to server.py is private by default.
    SERVE_EXT = ('.html', '.css', '.js', '.json', '.png', '.jpg', '.jpeg',
                 '.gif', '.webp', '.svg', '.ico', '.woff', '.woff2')
    PRIVATE_NAMES = ('config.json',)
    PRIVATE_DIRS = ('backups/', '_source/', '__pycache__/', '.git/')

    @classmethod
    def _servable(cls, path):
        rel = urllib.parse.unquote(path.split('?', 1)[0]).lstrip('/')
        rel = rel.replace('\\', '/')
        if rel == '':
            return True
        low = rel.lower()
        if low in cls.PRIVATE_NAMES:
            return False
        if any(low == d.rstrip('/') or low.startswith(d) for d in cls.PRIVATE_DIRS):
            return False
        if low.startswith('.'):                      # dotfiles
            return False
        return low.endswith(cls.SERVE_EXT)

    def do_POST(self):
        routes = {
            '/api/save-pens':    lambda b: self._save_collection(b, PENS_FILE),
            '/api/save-inks':    lambda b: self._save_collection(b, INKS_FILE),
            '/api/save-papers':  lambda b: self._save_collection(b, PAPERS_FILE),
            '/api/upload-photo': self._upload_photo,
            '/api/import-image': self._import_image,
            '/api/delete-photo': self._delete_photo,
            '/api/set-photo-tag': self._set_photo_tag,
            '/api/reorder-photos': self._reorder_photos,
            '/api/replace-photo': self._replace_photo,
            '/api/ai-fill':      self._ai_fill,
            '/api/ai-map':       self._ai_map,
            '/api/ai-pair':      self._ai_pair,
            '/api/find-photos':  self._find_photos,
            '/api/capture-url':  self._capture_url,
            '/api/parse-xlsx':   self._parse_xlsx,
        }
        handler = routes.get(self.path)
        if not handler:
            return self.send_error(404)
        # Uniform gate: every mutating endpoint requires the per-run token for
        # non-local clients (the app fetches it from /api/qr-info on load).
        # This is a seam for real auth later, not strong security today.
        if not self.is_local() and self.headers.get('X-Upload-Token') != UPLOAD_TOKEN:
            return self._json(403, {'ok': False, 'error': 'Bad or missing token'})
        try:
            length = int(self.headers.get('Content-Length', 0))
        except ValueError:
            return self._json(400, {'ok': False, 'error': 'Bad length'})
        cap = MAX_UPLOAD_BYTES if self.path == '/api/upload-photo' else MAX_DATA_BYTES
        if length <= 0 or length > cap:
            return self._json(413, {'ok': False, 'error': 'Payload too large'})
        raw = self.rfile.read(length)
        handler(raw)

    # ── handlers ─────────────────────────────────────────────────────────────
    def _get_data(self):
        self._json(200, {
            'pens':   read_json(PENS_FILE, []),
            'inks':   read_json(INKS_FILE, []),
            'papers': read_json(PAPERS_FILE, []),
            'photos': normalize_photos(read_json(PHOTOS_FILE, {})),
        })

    def _save_collection(self, raw, path):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._json(400, {'ok': False, 'error': 'Invalid JSON'})
        if not isinstance(data, list):
            return self._json(400, {'ok': False, 'error': 'Expected a JSON array'})
        with _write_lock:
            backup_file(path)
            write_json_atomic(path, data)
        self._json(200, {'ok': True, 'count': len(data)})

    def _upload_photo(self, raw):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._json(400, {'ok': False, 'error': 'Bad request'})

        rtype = data.get('type')
        if rtype not in ('pen', 'ink', 'paper'):
            return self._json(400, {'ok': False, 'error': 'type must be pen, ink or paper'})
        rid = str(data.get('id', ''))
        if not re.fullmatch(r'[a-z0-9]{1,24}', rid):
            return self._json(400, {'ok': False, 'error': 'Invalid id'})
        tag = data.get('tag') if data.get('tag') in PHOTO_TAGS else 'photo'

        fname = data.get('filename', 'photo.jpg')
        ext = os.path.splitext(os.path.basename(fname))[1].lower()
        if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif'):
            ext = '.jpg'
        save_name = f"{rtype}_{rid}_{secrets.token_hex(4)}{ext}"

        try:
            img = base64.b64decode(data.get('data', ''))
        except (ValueError, binascii.Error):
            return self._json(400, {'ok': False, 'error': 'Invalid base64'})
        if not is_image_bytes(img):
            return self._json(400, {'ok': False, 'error': 'Not a valid image'})

        save_path = safe_join(PHOTOS_DIR, save_name)
        if save_path is None:
            return self._json(400, {'ok': False, 'error': 'Bad path'})

        with _write_lock:
            with open(save_path, 'wb') as f:
                f.write(img)
            photos = normalize_photos(read_json(PHOTOS_FILE, {}))
            key = f"{rtype}:{rid}"
            photos.setdefault(key, []).append({'url': f"photos/{save_name}", 'tag': tag})
            write_json_atomic(PHOTOS_FILE, photos)

        self._json(200, {'ok': True, 'url': f"photos/{save_name}"})

    def _import_image(self, raw):
        """Fetch an external image URL server-side and store it locally."""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._json(400, {'ok': False, 'error': 'Bad request'})
        rtype = data.get('type')
        rid = str(data.get('id', ''))
        url = data.get('url', '')
        if rtype not in ('pen', 'ink', 'paper') or not re.fullmatch(r'[a-z0-9]{1,24}', rid):
            return self._json(400, {'ok': False, 'error': 'Bad type/id'})
        tag = data.get('tag') if data.get('tag') in PHOTO_TAGS else 'photo'
        if not re.match(r'https?://', url):
            return self._json(400, {'ok': False, 'error': 'Bad url'})
        try:
            img, _ctype, _final = _safe_fetch(url, max_bytes=MAX_UPLOAD_BYTES, timeout=30)
        except Exception as e:  # noqa: BLE001
            return self._json(502, {'ok': False, 'error': f'Could not fetch image: {e}'})
        if len(img) > MAX_UPLOAD_BYTES or not is_image_bytes(img):
            return self._json(400, {'ok': False, 'error': 'Not a usable image'})
        if len(img) < 2500:
            # Reject tracking pixels / tiny placeholders that pass the magic-byte check.
            return self._json(400, {'ok': False, 'error': 'Image too small (looks like a placeholder, not a photo)'})
        ext = '.png' if img[:8] == b'\x89PNG\r\n\x1a\n' else '.jpg'
        save_name = f"{rtype}_{rid}_{secrets.token_hex(4)}{ext}"
        save_path = safe_join(PHOTOS_DIR, save_name)
        if save_path is None:
            return self._json(400, {'ok': False, 'error': 'Bad path'})
        with _write_lock:
            with open(save_path, 'wb') as f:
                f.write(img)
            photos = normalize_photos(read_json(PHOTOS_FILE, {}))
            photos.setdefault(f"{rtype}:{rid}", []).append({'url': f"photos/{save_name}", 'tag': tag})
            write_json_atomic(PHOTOS_FILE, photos)
        self._json(200, {'ok': True, 'url': f"photos/{save_name}"})

    def _delete_photo(self, raw):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._json(400, {'ok': False, 'error': 'Bad request'})
        key = data.get('key', '')
        url = data.get('url', '')
        if not re.fullmatch(r'(pen|ink|paper):[a-z0-9]{1,24}', key or ''):
            return self._json(400, {'ok': False, 'error': 'Bad key'})
        with _write_lock:
            photos = normalize_photos(read_json(PHOTOS_FILE, {}))
            if key in photos:
                keep = [e for e in photos[key] if e['url'] != url]
                if len(keep) != len(photos[key]):
                    if keep:
                        photos[key] = keep
                    else:
                        del photos[key]
                    write_json_atomic(PHOTOS_FILE, photos)
                    # remove the file from disk
                    fp = safe_join(PHOTOS_DIR, os.path.basename(url))
                    if fp and os.path.exists(fp):
                        try:
                            os.remove(fp)
                        except OSError:
                            pass
        self._json(200, {'ok': True})

    def _set_photo_tag(self, raw):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._json(400, {'ok': False, 'error': 'Bad request'})
        key, url, tag = data.get('key', ''), data.get('url', ''), data.get('tag', '')
        if not re.fullmatch(r'(pen|ink|paper):[a-z0-9]{1,24}', key or ''):
            return self._json(400, {'ok': False, 'error': 'Bad key'})
        if tag not in PHOTO_TAGS:
            return self._json(400, {'ok': False, 'error': 'Bad tag'})
        with _write_lock:
            photos = normalize_photos(read_json(PHOTOS_FILE, {}))
            for e in photos.get(key, []):
                if e['url'] == url:
                    e['tag'] = tag
                    write_json_atomic(PHOTOS_FILE, photos)
                    return self._json(200, {'ok': True})
        self._json(404, {'ok': False, 'error': 'Photo not found'})

    def _replace_photo(self, raw):
        """Overwrite a photo with an edited (cropped/rotated) version.

        Writes a NEW filename and swaps the entry in place — same position and
        tag — so browser caches can never show the stale image.
        """
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._json(400, {'ok': False, 'error': 'Bad request'})
        key = data.get('key', '')
        old_url = data.get('url', '')
        if not re.fullmatch(r'(pen|ink|paper):[a-z0-9]{1,24}', key or ''):
            return self._json(400, {'ok': False, 'error': 'Bad key'})
        try:
            img = base64.b64decode(data.get('data', ''))
        except (ValueError, binascii.Error):
            return self._json(400, {'ok': False, 'error': 'Invalid base64'})
        if len(img) < 500 or len(img) > MAX_UPLOAD_BYTES or not is_image_bytes(img):
            return self._json(400, {'ok': False, 'error': 'Not a usable image'})
        rtype, rid = key.split(':', 1)
        save_name = f"{rtype}_{rid}_{secrets.token_hex(4)}.jpg"
        save_path = safe_join(PHOTOS_DIR, save_name)
        if save_path is None:
            return self._json(400, {'ok': False, 'error': 'Bad path'})
        with _write_lock:
            photos = normalize_photos(read_json(PHOTOS_FILE, {}))
            entry = next((e for e in photos.get(key, []) if e['url'] == old_url), None)
            if entry is None:
                return self._json(404, {'ok': False, 'error': 'Photo not found'})
            with open(save_path, 'wb') as f:
                f.write(img)
            entry['url'] = f"photos/{save_name}"
            write_json_atomic(PHOTOS_FILE, photos)
            oldfp = safe_join(PHOTOS_DIR, os.path.basename(old_url))
            if oldfp and os.path.exists(oldfp):
                try:
                    os.remove(oldfp)
                except OSError:
                    pass
        self._json(200, {'ok': True, 'url': f"photos/{save_name}"})

    def _reorder_photos(self, raw):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._json(400, {'ok': False, 'error': 'Bad request'})
        key = data.get('key', '')
        urls = data.get('urls', [])
        if not re.fullmatch(r'(pen|ink|paper):[a-z0-9]{1,24}', key or ''):
            return self._json(400, {'ok': False, 'error': 'Bad key'})
        if not isinstance(urls, list) or not urls:
            return self._json(400, {'ok': False, 'error': 'Bad urls'})
        with _write_lock:
            photos = normalize_photos(read_json(PHOTOS_FILE, {}))
            current = photos.get(key, [])
            by_url = {e['url']: e for e in current}
            # Every requested url must already belong to this record — and vice versa —
            # or we silently drop/invent photos.
            if set(urls) != set(by_url.keys()):
                return self._json(400, {'ok': False, 'error': 'Photo set mismatch'})
            photos[key] = [by_url[u] for u in urls]
            write_json_atomic(PHOTOS_FILE, photos)
        self._json(200, {'ok': True})

    def _qr_info(self):
        ip = lan_ip()
        self._json(200, {
            'lan_url': f'http://{ip}:{PORT}',
            'token': UPLOAD_TOKEN,
        })

    def _ai_fill(self, raw):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._json(400, {'ok': False, 'error': 'Bad request'})
        cfg = load_config()
        provider = cfg.get('provider', 'gemini')
        try:
            if provider == 'anthropic':
                if _placeholder_key(cfg.get('anthropic_api_key')):
                    raise RuntimeError('No Anthropic API key. Add anthropic_api_key to '
                                       'config.json (or set ANTHROPIC_API_KEY).')
                result = anthropic_fill(cfg, data)
            else:  # gemini (default)
                if _placeholder_key(cfg.get('gemini_api_key')):
                    raise RuntimeError('No Google Gemini API key. Get a free one at '
                                       'aistudio.google.com/apikey, then add gemini_api_key '
                                       'to config.json (or set GEMINI_API_KEY).')
                result = gemini_fill(cfg, data)
            learn_item(data.get('kind', 'pen'), result.get('fields') or {})
            self._json(200, {'ok': True, **result})
        except RuntimeError as e:
            # Clear, user-actionable problems (missing package, refusal, etc.)
            self._json(400, {'ok': False, 'error': str(e)})
        except Exception as e:  # noqa: BLE001
            print(f'[ai-fill error] {type(e).__name__}: {e}')
            self._json(502, {'ok': False, 'error': f'AI fill failed ({type(e).__name__}): {str(e)[:200]}'})

    def _ai_map(self, raw):
        """Map spreadsheet columns to schema fields for the import wizard."""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._json(400, {'ok': False, 'error': 'Bad request'})
        cfg = load_config()
        try:
            if _placeholder_key(cfg.get('gemini_api_key')):
                raise RuntimeError('AI mapping needs a Google Gemini API key (see config.json). '
                                   'You can still map the columns manually below.')
            self._json(200, {'ok': True, **gemini_map(cfg, data)})
        except RuntimeError as e:
            self._json(400, {'ok': False, 'error': str(e)})
        except Exception as e:  # noqa: BLE001
            print(f'[ai-map error] {type(e).__name__}: {e}')
            self._json(502, {'ok': False, 'error': f'AI mapping failed ({type(e).__name__})'})

    def _parse_xlsx(self, raw):
        """Parse an uploaded .xlsx workbook for the spreadsheet import wizard.

        Request: {"filename": "...", "data": "<base64>", "sheet": "optional name"}
        Response: {"ok": true, "sheets": [...], "sheet": "chosen", "rows": [[...], ...]}
        """
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._json(400, {'ok': False, 'error': 'Bad request'})
        b64 = data.get('data', '')
        sheet_name = data.get('sheet') or None
        try:
            file_bytes = base64.b64decode(b64, validate=False)
        except (ValueError, binascii.Error):
            return self._json(400, {'ok': False, 'error': 'Invalid base64 data'})
        if not file_bytes:
            return self._json(400, {'ok': False, 'error': 'Empty file'})
        if len(file_bytes) > MAX_DATA_BYTES:
            return self._json(400, {'ok': False, 'error': 'File too large. Try exporting as CSV instead.'})
        try:
            names, chosen_name, rows = parse_xlsx(file_bytes, sheet_name)
            self._json(200, {'ok': True, 'sheets': names, 'sheet': chosen_name, 'rows': rows})
        except RuntimeError as e:
            self._json(400, {'ok': False, 'error': str(e)})
        except Exception as e:  # noqa: BLE001
            print(f'[parse-xlsx error] {type(e).__name__}: {e}')
            self._json(400, {'ok': False, 'error': 'Could not read that Excel file. Try exporting as CSV instead.'})

    def _ai_pair(self, raw):
        """Creative pairing suggestions for one item against the collection."""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._json(400, {'ok': False, 'error': 'Bad request'})
        cfg = load_config()
        try:
            if _placeholder_key(cfg.get('gemini_api_key')):
                raise RuntimeError('AI pairing ideas need a Google Gemini API key (see config.json).')
            self._json(200, {'ok': True, **gemini_pair(cfg, data)})
        except RuntimeError as e:
            self._json(400, {'ok': False, 'error': str(e)})
        except Exception as e:  # noqa: BLE001
            print(f'[ai-pair error] {type(e).__name__}: {e}')
            self._json(502, {'ok': False, 'error': f'AI pairing failed ({type(e).__name__})'})

    def _find_photos(self, raw):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._json(400, {'ok': False, 'error': 'Bad request'})
        cfg = load_config()
        try:
            if cfg.get('provider', 'gemini') == 'anthropic':
                raise RuntimeError('Photo search uses Google grounding — set provider to '
                                   '"gemini" in config.json.')
            if _placeholder_key(cfg.get('gemini_api_key')):
                raise RuntimeError('No Google Gemini API key set (see config.json).')
            self._json(200, {'ok': True, **find_photos(cfg, data)})
        except RuntimeError as e:
            self._json(400, {'ok': False, 'error': str(e)})
        except Exception as e:  # noqa: BLE001
            print(f'[find-photos error] {type(e).__name__}: {e}')
            self._json(502, {'ok': False, 'error': f'Photo search failed ({type(e).__name__})'})

    def _capture_url(self, raw):
        """Fetch a listing/post URL (eBay, Reddit, retailer, ...) and have
        Gemini turn it into pre-filled pen fields, all through _safe_fetch."""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._json(400, {'ok': False, 'error': 'Bad request'})
        url = str(data.get('url') or '').strip()
        text = str(data.get('text') or '').strip()
        if not url and not text:
            return self._json(400, {'ok': False, 'error': 'Paste a link or the listing text.'})
        cfg = load_config()
        try:
            if _placeholder_key(cfg.get('gemini_api_key')):
                raise RuntimeError('No Google Gemini API key. Get a free one at '
                                   'aistudio.google.com/apikey, then add gemini_api_key '
                                   'to config.json (or set GEMINI_API_KEY).')
            result = capture_text(cfg, text) if text else capture_url(cfg, url)
            learn_item('pen', result.get('fields') or {})
            self._json(200, {'ok': True, **result})
        except RuntimeError as e:
            # Clear, user-actionable problems: missing key, unfetchable/blocked
            # URL, SSRF guard rejection, etc. — plain English, no stack trace.
            self._json(400, {'ok': False, 'error': str(e)})
        except Exception as e:  # noqa: BLE001
            print(f'[capture-url error] {type(e).__name__}: {e}')
            self._json(502, {'ok': False, 'error': f'Could not capture that page ({type(e).__name__}).'})

    # ── mobile capture page ──────────────────────────────────────────────────
    def _mobile_page(self):
        body = MOBILE_HTML.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── helpers ──────────────────────────────────────────────────────────────
    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        if args and (str(args[1]) not in ('200', '304') or '/api/' in str(args[0])):
            super().log_message(fmt, *args)


# ── Anthropic auto-fill ───────────────────────────────────────────────────────
PEN_FIELDS = ("make, model, material_color, nib_grind, nib_material, filling "
              "(e.g. Piston, Lever, Cartridge/Converter, Eyedropper), "
              "year_or_era, country, msrp_usd (number or null), notes")
INK_FIELDS = ("brand, name, shimmer (true/false), sheen (one of: Gold, Blue, "
              "Silver, Red, Green, Pink, None), shading (one of: None, Moderate, Strong), "
              "alkaline (Yes if the ink is alkaline / high pH — true of most Pilot Iroshizuku "
              "and Sailor-made inks — No if acidic or neutral, null if unknown), "
              "color_match (one of: Red, Orange, Yellow, "
              "Green, Brown, Blue, Purple, Grey, Black), type (Bottle or Sample), notes")
PAPER_FIELDS = ("brand, name, type (one of: Notebook, Pad, Loose Sheets, Journal), "
                "size (e.g. A5, B5, Letter), gsm (number or null), "
                "ruling (one of: Blank, Lined, Grid, Dot), "
                "surface (one of: Coated, Smooth, Absorbent — Coated means slow-absorbing "
                "sheen-friendly stock like Tomoe River or Cosmo Air Light), "
                "notes (fountain-pen friendliness: ghosting, bleedthrough, "
                "feathering, dry time — use the exact key \"notes\")")


def build_fill_prompt(data):
    kind = data.get('kind', 'pen')
    if kind == 'ink':
        subject = f"the fountain pen ink \"{data.get('brand','')} {data.get('name','')}\""
        fields = INK_FIELDS
    elif kind == 'paper':
        subject = (f"the paper/notebook \"{data.get('brand','')} {data.get('name','')}\" "
                   f"as used with fountain pens")
        fields = PAPER_FIELDS
    else:
        subject = f"the fountain pen \"{data.get('make','')} {data.get('model','')}\""
        fields = PEN_FIELDS
    return (
        f"You are helping catalog a fountain pen collection. Research {subject} "
        f"using web search, then return what you find.\n\n"
        f"Respond with ONLY a JSON object (no prose, no markdown fences) of the form:\n"
        f'{{"fields": {{ ... }}, "images": ["url", ...], "confidence": "high|medium|low", '
        f'"sources": ["url", ...]}}\n\n'
        f"The \"fields\" object should contain these keys where known ({fields}). "
        f"Use null for anything you cannot determine — do not guess. "
        f"Keep every field value short — a brief phrase, not a paragraph (notes: "
        f"two sentences max). "
        f"\"images\" should be up to 4 direct URLs (ending in .jpg/.png/.webp) to "
        f"representative product photos you found."
    )


def _normalize_fill(parsed, text, extra_sources=None):
    """Shape a parsed model response into the API result dict."""
    extra_sources = extra_sources or []
    if parsed is None:
        return {'fields': {}, 'images': [], 'confidence': 'low',
                'sources': extra_sources[:6], 'raw': text[:2000]}
    sources, seen = [], set()
    for s in (parsed.get('sources') or []) + extra_sources:
        if s and s not in seen:
            seen.add(s)
            sources.append(s)
    return {
        'fields': parsed.get('fields', {}) or {},
        'images': (parsed.get('images') or [])[:6],
        'confidence': parsed.get('confidence', 'medium'),
        'sources': sources[:6],
    }


def _gemini_call(cfg, prompt, use_search=True, max_tokens=2048):
    """Call Gemini once; return (text, [grounding source URLs]). Stdlib only."""
    model = cfg.get('gemini_model', 'gemini-2.5-flash')
    gen = {"temperature": 0.2, "maxOutputTokens": max_tokens}
    # gemini-2.5 "thinks" by default, eating the output budget — off for our tasks.
    if model.startswith('gemini-2.5'):
        gen["thinkingConfig"] = {"thinkingBudget": 0}
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": gen}
    if use_search:
        body["tools"] = [{"google_search": {}}]  # Google Search grounding (Gemini 2.0+)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode('utf-8'),
        headers={"content-type": "application/json",
                 "x-goog-api-key": cfg['gemini_api_key']},
        method="POST")
    payload = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                payload = json.loads(resp.read().decode('utf-8'))
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', 'replace')
            try:
                msg = json.loads(detail).get('error', {}).get('message', detail)
            except (json.JSONDecodeError, ValueError):
                msg = detail
            # 429/500/503 are transient on the free tier — back off and retry.
            if e.code in (429, 500, 503) and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise RuntimeError(f"Gemini API {e.code}: {msg[:300]}")

    candidates = payload.get('candidates', [])
    if not candidates:
        fb = (payload.get('promptFeedback') or {}).get('blockReason', 'none')
        raise RuntimeError(f"Gemini returned no result (block reason: {fb}).")
    cand = candidates[0]
    parts = cand.get('content', {}).get('parts', []) or []
    text = "".join(p.get('text', '') for p in parts if isinstance(p, dict)).strip()
    sources = []
    for chunk in (cand.get('groundingMetadata', {}) or {}).get('groundingChunks', []) or []:
        uri = (chunk.get('web') or {}).get('uri')
        if uri:
            sources.append(uri)
    return text, sources


def gemini_fill(cfg, data):
    """Google Gemini (free tier) via REST — no SDK / pip install required."""
    text, sources = _gemini_call(cfg, build_fill_prompt(data),
                                 use_search=cfg.get('enable_web_search', True),
                                 max_tokens=8192)
    if not text:
        raise RuntimeError("Gemini returned no text.")
    return _normalize_fill(extract_json(text), text, sources)


# Pull og:image / twitter:image out of a page's <head> (handles attr order both ways).
_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image(?::secure_url)?|twitter:image(?::src)?)["\']'
    r'[^>]+content=["\']([^"\']+)["\']', re.I)
_OG_IMAGE_RE_REV = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)='
    r'["\'](?:og:image(?::secure_url)?|twitter:image(?::src)?)["\']', re.I)


def _page_main_image(page_url):
    """Fetch a page (SSRF-guarded, following redirects) and return its
    og:image URL, or None."""
    try:
        raw, ctype, final = _safe_fetch(page_url, max_bytes=700_000, timeout=15, truncate=True)
    except RuntimeError:  # any fetch/guard failure → just skip this page
        return None
    if ctype.startswith('image/'):
        return final  # the link was a direct image
    if 'html' not in ctype:
        return None
    page = raw.decode('utf-8', 'replace')
    m = _OG_IMAGE_RE.search(page) or _OG_IMAGE_RE_REV.search(page)
    if not m:
        return None
    img = html_lib.unescape(m.group(1)).strip()
    if img.startswith('//'):
        img = 'https:' + img
    elif img.startswith('/'):
        img = urllib.parse.urljoin(final, img)
    return img if img.startswith('http') else None


def gemini_map(cfg, data):
    """One cheap Gemini call (no search): spreadsheet headers -> schema fields."""
    headers = [str(h) for h in (data.get('headers') or [])][:40]
    fields = [str(f) for f in (data.get('fields') or [])][:40]
    samples = (data.get('samples') or [])[:3]
    if not headers or not fields:
        raise RuntimeError('Missing headers or fields.')
    prompt = (
        "You are mapping spreadsheet columns to database fields for a fountain pen "
        "collection app.\n"
        f"Spreadsheet column headers: {json.dumps(headers, ensure_ascii=False)}\n"
        f"Sample data rows: {json.dumps(samples, ensure_ascii=False)}\n"
        f"Available target fields: {json.dumps(fields)}\n\n"
        "Respond with ONLY a JSON object mapping each column header (exactly as given) "
        "to the best-fitting target field name, or null if none fits. "
        "Use each target field at most once. No prose, no markdown fences."
    )
    text, _ = _gemini_call(cfg, prompt, use_search=False, max_tokens=1024)
    parsed = extract_json(text)
    if not isinstance(parsed, dict):
        raise RuntimeError('AI mapping returned an unparseable answer — map manually below.')
    # keep only valid header->field pairs, one use per field
    used, mapping = set(), {}
    for h in headers:
        f = parsed.get(h)
        if isinstance(f, str) and f in fields and f not in used:
            mapping[h] = f
            used.add(f)
    return {'mapping': mapping}


def gemini_pair(cfg, data):
    """One Gemini call (no search): expert pairing ideas from the user's own collection."""
    item = data.get('item') or {}
    pens = (data.get('pens') or [])[:60]
    inks = (data.get('inks') or [])[:60]
    papers = (data.get('papers') or [])[:40]
    prompt = (
        "You are a fountain pen pairing expert. Fundamentals: shimmer needs wet broad/stub/"
        "cursive-italic nibs and easy-clean modern fillers, never vintage sac fillers; sheen "
        "needs saturated wet lines plus slow-absorbing coated paper (e.g. Tomoe River); "
        "shading shows best with flex or italic grinds on smooth paper; vintage pens prefer "
        "well-behaved low-maintenance inks.\n\n"
        f"Suggest up to 3 pairings for this item: {json.dumps(item, ensure_ascii=False)}\n"
        f"The user's pens: {json.dumps(pens, ensure_ascii=False)}\n"
        f"The user's inks: {json.dumps(inks, ensure_ascii=False)}\n"
        f"The user's papers: {json.dumps(papers, ensure_ascii=False)}\n\n"
        "Only combine items that appear in those lists (never invent products). If a list is "
        "empty, work with what exists. Respond with ONLY JSON of the form "
        '{"suggestions": [{"combo": "Pen + Ink (+ Paper)", "why": "one sentence"}]} '
        "— no prose, no markdown fences."
    )
    text, _ = _gemini_call(cfg, prompt, use_search=False, max_tokens=1024)
    parsed = extract_json(text) or {}
    sugg = [s for s in (parsed.get('suggestions') or [])
            if isinstance(s, dict) and s.get('combo')][:5]
    if not sugg:
        raise RuntimeError('No AI suggestions returned — try again.')
    return {'suggestions': sugg}


def find_photos(cfg, data):
    """No-extra-key photo finder: Gemini grounding -> real source pages -> og:image."""
    kind = data.get('kind', 'pen')
    if kind == 'ink':
        subject = f"{data.get('brand','')} {data.get('name','')} fountain pen ink"
    elif kind == 'paper':
        subject = f"{data.get('brand','')} {data.get('name','')} notebook paper"
    else:
        subject = f"{data.get('make','')} {data.get('model','')} fountain pen"
    prompt = (f"Search the web for retailer product pages and review pages that show clear "
              f"photos of the {subject}. List the page URLs. Keep it brief.")
    _, sources = _gemini_call(cfg, prompt, use_search=True, max_tokens=1024)

    images, seen = [], set()
    for url in sources[:10]:
        img = _page_main_image(url)
        if img and img not in seen:
            seen.add(img)
            images.append(img)
        if len(images) >= 6:
            break
    return {'images': images, 'sources': sources[:6]}


# ── URL capture (paste an eBay/Reddit/shop link → pre-filled pen) ───────────
_SHOP_HOSTS = ('gouletpens.com', 'vanness1938.com', 'fountainpenhospital.com',
               'cultpens.com', 'jetpens.com')

_SCRIPT_STYLE_RE = re.compile(r'<(script|style)[^>]*>.*?</\1>', re.I | re.S)
_TAG_RE = re.compile(r'<[^>]+>')
_WS_RE = re.compile(r'\s+')


def _classify_source(host):
    """Bucket a hostname into one of the source kinds the UI understands."""
    host = (host or '').lower()
    if host.startswith('www.'):
        host = host[4:]
    if 'ebay.' in host:
        return 'ebay'
    if host == 'redd.it' or host.endswith('.redd.it') or host == 'reddit.com' or host.endswith('.reddit.com'):
        return 'reddit'
    if any(host == h or host.endswith('.' + h) for h in _SHOP_HOSTS):
        return 'shop'
    return 'unknown'


def _meta_content(page, *names):
    """First matching content="" value for any of the given meta property/name keys."""
    for name in names:
        esc = re.escape(name)
        pat1 = re.compile(r'<meta[^>]+(?:property|name)=["\']' + esc + r'["\']'
                           r'[^>]+content=["\']([^"\']*)["\']', re.I)
        pat2 = re.compile(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)='
                           r'["\']' + esc + r'["\']', re.I)
        m = pat1.search(page) or pat2.search(page)
        if m:
            val = html_lib.unescape(m.group(1)).strip()
            if val:
                return val
    return None


def _html_to_text(src, cap=12000):
    """Strip scripts/styles/tags, unescape entities, collapse whitespace."""
    text = _SCRIPT_STYLE_RE.sub(' ', src)
    text = _TAG_RE.sub(' ', text)
    text = html_lib.unescape(text)
    text = _WS_RE.sub(' ', text).strip()
    return text[:cap]


def _capture_images_from_html(page, base_url):
    """Candidate photo URLs from og:image / twitter:image meta tags."""
    urls = []
    for name in ('og:image:secure_url', 'og:image', 'twitter:image:src', 'twitter:image'):
        v = _meta_content(page, name)
        if v:
            urls.append(v)
    out, seen = [], set()
    for u in urls:
        if u.startswith('//'):
            u = 'https:' + u
        elif u.startswith('/'):
            u = urllib.parse.urljoin(base_url, u)
        if u.startswith('http') and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _capture_filter_photos(urls, limit=8):
    """Keep only URLs whose host passes the SSRF guard, capped at *limit*."""
    out = []
    for u in urls:
        try:
            _validate_url_host(u)
        except RuntimeError:
            continue
        out.append(u)
        if len(out) >= limit:
            break
    return out


_CAPTURE_RESPONSE_SHAPE = (
    '{"multi": false, '
    '"items": [{"title": "", "price": null, "nib": "", "blurb": ""}], '
    '"fields": {"make": "", "model": "", "material_color": "", "nib_grind": "", '
    '"nib_material": "", "filling": "", "paid": null, "seller": "", "source": "", "notes": ""}}'
)


def _build_capture_prompt(source, title, price_hint, text):
    label = {'ebay': 'an eBay listing', 'reddit': 'a Reddit post',
              'shop': 'a retailer product page'}.get(source, 'a web page')
    hints = []
    if title:
        hints.append(f'Page title: {title}')
    if price_hint:
        hints.append(f'Price hint found in page metadata: {price_hint}')
    hint_block = ('\n'.join(hints) + '\n\n') if hints else ''
    return (
        f"You are helping catalog a fountain pen collection. Below is the extracted text of "
        f"{label} that may describe one or more fountain pens for sale or discussion.\n\n"
        f"{hint_block}"
        f"Page text (may be truncated):\n\"\"\"\n{text}\n\"\"\"\n\n"
        "First, decide whether this page/post offers MORE THAN ONE distinct pen for sale — "
        "set \"multi\" to true or false accordingly.\n\n"
        "Respond with ONLY a JSON object (no prose, no markdown fences) of exactly this form:\n"
        f"{_CAPTURE_RESPONSE_SHAPE}\n\n"
        "Rules:\n"
        "- If \"multi\" is true, include one entry in \"items\" per distinct pen found "
        "(a short title, its price if stated, a brief nib description, a one-sentence "
        "blurb, and \"sold\": true/false), and fill \"fields\" from the FIRST item. "
        "If \"multi\" is false, \"items\" should have exactly one entry.\n"
        "- Set an item's \"sold\" to true when the text marks it sold, pending or on hold "
        "(e.g. \"SOLD\", \"SOLD (Off platform)\", \"PENDING\", strikethrough). List it "
        "normally — a sold item is often the one the reader just bought.\n"
        "- Copy usernames, seller names and model numbers EXACTLY, character for "
        "character. Never normalise, correct or re-spell them.\n"
        "- NEVER invent a price — use null (in \"paid\" and in each item's \"price\") when no "
        "price is stated in the text.\n"
        "- \"seller\" is the individual seller's username or the shop's name. If the "
        "text does not name one, return an empty string — never the site, the "
        "marketplace or the subreddit (those belong in \"source\"), and never a "
        "placeholder like \"unknown\" or \"not provided\".\n"
        "- \"source\" is a short human label for where this came from, e.g. \"r/Pen_Swap\", "
        "\"eBay\", or the shop's name — not a URL.\n"
        "- Keep \"blurb\" and \"notes\" brief — one or two sentences.\n"
        "- Use null / an empty string for anything you cannot determine — do not guess."
    )


def _capture_ai_extract(cfg, source, title, price_hint, text):
    """Ask Gemini to turn extracted page text into the capture-url schema."""
    prompt = _build_capture_prompt(source, title, price_hint, text)
    resp_text, _ = _gemini_call(cfg, prompt, use_search=False, max_tokens=2048)
    parsed = extract_json(resp_text) or {}

    raw_items = parsed.get('items')
    if not isinstance(raw_items, list) or not raw_items:
        raw_items = [{'title': title or '', 'price': None, 'nib': '', 'blurb': ''}]
    items = []
    for it in raw_items[:20]:
        if not isinstance(it, dict):
            continue
        price = it.get('price')
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            price = None
        items.append({
            'title': str(it.get('title') or '')[:200],
            'price': price,
            'nib': str(it.get('nib') or '')[:120],
            'blurb': str(it.get('blurb') or '')[:500],
            'sold': bool(it.get('sold')),
        })
    if not items:
        items = [{'title': title or '', 'price': None, 'nib': '', 'blurb': ''}]

    fin = parsed.get('fields') if isinstance(parsed.get('fields'), dict) else {}
    paid = fin.get('paid')
    if not isinstance(paid, (int, float)) or isinstance(paid, bool):
        paid = None
    fields = {
        'make': str(fin.get('make') or ''),
        'model': str(fin.get('model') or ''),
        'material_color': str(fin.get('material_color') or ''),
        'nib_grind': str(fin.get('nib_grind') or ''),
        'nib_material': str(fin.get('nib_material') or ''),
        'filling': str(fin.get('filling') or ''),
        'paid': paid,
        'seller': str(fin.get('seller') or ''),
        'source': str(fin.get('source') or ''),
        'notes': str(fin.get('notes') or ''),
    }
    # The model sometimes answers "unknown" / "[username not provided]" instead of
    # leaving a field blank. An empty box is honest; a placeholder is not.
    _PLACEHOLDER = re.compile(
        r'^\s*(u/\s*)?[\[\(]?\s*(n/?a|none|unknown|not (provided|specified|stated|listed|given)|'
        r'no[t]? (mentioned|available)|tbd|\?+)\s*[\]\)]?\s*$', re.I)
    for k, v in list(fields.items()):
        if isinstance(v, str) and (_PLACEHOLDER.match(v) or 'not provided' in v.lower()
                                   or 'not specified' in v.lower()):
            fields[k] = ''
    # Which pen did the reader buy? If exactly one item is marked sold, almost
    # certainly that one — they are pasting the post BECAUSE they bought it.
    # Otherwise the first. Reported as "suggested"; the client pre-selects it
    # and re-fills the draft from that lot, so make, model and price stay together.
    sold_idx = [n for n, i in enumerate(items) if i.get('sold')]
    suggested = sold_idx[0] if len(sold_idx) == 1 else 0
    # "fields" describes items[0] (what the model was told), so its price is items[0]'s.
    if fields.get('paid') is None and items and items[0].get('price') is not None:
        fields['paid'] = items[0]['price']
    # Seller is provenance you rely on years later at resale, and a model will
    # happily retype a username with a digit wrong (seen in testing: a real handle
    # came back with an extra digit). Only keep it if it appears verbatim; otherwise
    # snap to the closest literal token, and blank it rather than guess.
    fields['seller'] = _verbatim_or_blank(fields.get('seller', ''), text)
    return {'multi': bool(parsed.get('multi')), 'items': items, 'fields': fields,
            'suggested': suggested}


def _verbatim_or_blank(value, source):
    """Return *value* only if it really occurs in *source*; else the closest
    token found there; else ''. Guards against transcription drift."""
    v = (value or '').strip()
    if not v or not source:
        return ''
    if v.lower() in source.lower():
        return v
    tokens = set(re.findall(r'[A-Za-z0-9_\-]{3,40}', source))
    near = difflib.get_close_matches(v, tokens, n=1, cutoff=0.85)
    return near[0] if near else ''


REDDIT_BLOCKED_MSG = (
    'Reddit does not allow programs to read posts directly anymore — its free '
    'API was closed to new registrations in November 2025, and the old '
    'unauthenticated view now returns a bot check instead of the post. Select '
    'the post text in your browser and paste it into the box: everything else, '
    'including splitting a multi-pen listing, works exactly the same.'
)


def capture_text(cfg, text):
    """Parse listing text the user pasted in. The reliable path for any site that
    blocks automated reads — Reddit chief among them."""
    text = text.strip()
    if len(text) < 20:
        raise RuntimeError('That is too short to read. Paste the whole listing.')
    low = text[:400].lower()
    source = 'reddit' if ('r/pen_swap' in low or 'wts' in low or 'wtt' in low) else 'unknown'
    title = text.splitlines()[0].strip()[:200] if text.splitlines() else ''
    result = _capture_ai_extract(cfg, source, title, None, text[:12000])
    result['photos'] = []          # pasted text carries no images
    result['source'] = source
    return result


def _capture_reddit(cfg, url):
    # Reddit closed self-service API registration in November 2025 and killed
    # the unauthenticated .json view in May 2026, so there is no network path
    # left for a personal tool to read a post server-side. Fail fast with the
    # paste instruction rather than spend a timeout on a request that cannot
    # succeed.
    raise RuntimeError(REDDIT_BLOCKED_MSG)


def capture_url(cfg, url):
    """Fetch a listing/post URL and turn it into pre-filled pen fields."""
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    source = _classify_source(host)

    if source == 'reddit':
        return _capture_reddit(cfg, url)

    try:
        raw, _ctype, final_url = _safe_fetch(url, max_bytes=2_000_000, timeout=15, expect='html')
    except RuntimeError as e:
        raise RuntimeError(f'Could not fetch that page: {e}')
    page = raw.decode('utf-8', 'replace')

    title = _meta_content(page, 'og:title', 'twitter:title')
    price_hint = _meta_content(page, 'og:price:amount', 'product:price:amount', 'og:price')
    text = _html_to_text(page)
    photo_urls = _capture_images_from_html(page, final_url)

    extracted = _capture_ai_extract(cfg, source, title, price_hint, text)
    return {'source': source, 'photos': _capture_filter_photos(photo_urls), **extracted}


def anthropic_fill(cfg, data):
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "The 'anthropic' package isn't installed. Run:  pip install anthropic")

    prompt = build_fill_prompt(data)
    client = anthropic.Anthropic(api_key=cfg['anthropic_api_key'])
    model = cfg.get('model', 'claude-opus-4-8')
    tools = []
    if cfg.get('enable_web_search'):
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}]

    messages = [{"role": "user", "content": prompt}]
    resp = None
    # Server-side web search runs a tool loop; on pause_turn, re-send to resume.
    for _ in range(6):
        resp = client.messages.create(
            model=model,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            output_config={"effort": "low"},
            tools=tools,
            messages=messages,
        )
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break

    if resp is not None and resp.stop_reason == "refusal":
        raise RuntimeError("Claude declined to answer this request.")

    text = "".join(b.text for b in (resp.content if resp else [])
                   if getattr(b, "type", None) == "text").strip()
    return _normalize_fill(extract_json(text), text)


def extract_json(text):
    """Pull the first balanced {...} JSON object out of a text blob."""
    # Models often wrap JSON in ```json … ``` fences — strip them first.
    text = text.replace('```json', '').replace('```', '')
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


MOBILE_HTML = r"""<!DOCTYPE html><html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>Add Photo</title>
<style>
  :root { color-scheme: light dark; }
  body { margin:0; font:16px -apple-system,system-ui,sans-serif; background:#111; color:#eee;
         display:flex; flex-direction:column; align-items:center; gap:18px; padding:28px 18px; }
  h1 { font-size:19px; font-weight:600; margin:6px 0 0; text-align:center; }
  .sub { color:#9aa; font-size:14px; text-align:center; margin-top:-10px; }
  #btnrow { display:flex; gap:12px; flex-wrap:wrap; justify-content:center; }
  label.btn { background:#2d6cdf; color:#fff; padding:16px 22px; border-radius:14px; font-size:17px;
              font-weight:600; display:inline-block; }
  label.btn.sec { background:#2a2a2a; border:1px solid #3a3a3a; }
  input[type=file] { display:none; }
  #tagrow { display:flex; gap:8px; }
  #tagrow label { background:#222; border:1px solid #333; color:#bbc; padding:9px 16px;
                  border-radius:20px; font-size:14px; }
  #tagrow input { display:none; }
  #tagrow label.on { background:#2d6cdf; border-color:#2d6cdf; color:#fff; }
  #grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; width:100%; max-width:520px; }
  .thumb { position:relative; aspect-ratio:1; border-radius:10px; overflow:hidden; background:#222; }
  .thumb img { width:100%; height:100%; object-fit:cover; }
  .thumb .badge { position:absolute; bottom:6px; right:6px; background:rgba(0,0,0,.6);
                  border-radius:6px; padding:2px 7px; font-size:12px; }
  .done { color:#5fd07a; } .err { color:#f08; }
  #status { min-height:22px; font-size:14px; text-align:center; }
</style></head><body>
<h1 id="title">Add a photo</h1>
<div class="sub" id="subtitle"></div>
<div id="tagrow">
  <label id="t-photo" class="on"><input type="radio" name="tag" value="photo" checked>📷 Photo</label>
  <label id="t-swab"><input type="radio" name="tag" value="swab">🎨 Swab</label>
  <label id="t-writing"><input type="radio" name="tag" value="writing">✍️ Writing</label>
</div>
<div id="btnrow">
  <label class="btn">📷 Take Photo
    <input id="fileCamera" type="file" accept="image/*" capture="environment">
  </label>
  <label class="btn sec">🖼️ Choose from Library
    <input id="fileLibrary" type="file" accept="image/*" multiple>
  </label>
</div>
<div id="status"></div>
<div id="grid"></div>
<script>
const q = new URLSearchParams(location.search);
const type = q.get('type') || 'pen';
const id = q.get('id') || '';
const token = q.get('token') || '';
const label = q.get('label') || '';
document.getElementById('subtitle').textContent =
  (label ? decodeURIComponent(label) + ' · ' : '') + 'photos upload straight to your desktop';
const grid = document.getElementById('grid');
const statusEl = document.getElementById('status');

// tag chips — inks default to Swab since that's the usual ink photo
const tagRow = document.getElementById('tagrow');
function currentTag(){ return tagRow.querySelector('input:checked').value; }
tagRow.querySelectorAll('label').forEach(l => l.addEventListener('click', () => {
  setTimeout(() => tagRow.querySelectorAll('label').forEach(x =>
    x.classList.toggle('on', x.querySelector('input').checked)), 0);
}));
if (type === 'ink') {
  tagRow.querySelector('input[value=swab]').checked = true;
  tagRow.querySelectorAll('label').forEach(x =>
    x.classList.toggle('on', x.querySelector('input').checked));
}

async function handleFiles(e){
  const files = [...e.target.files];
  for (const f of files) await uploadOne(f);
  statusEl.textContent = 'Done — you can keep adding or close this page.';
  e.target.value = '';
}
document.getElementById('fileCamera').addEventListener('change', handleFiles);
document.getElementById('fileLibrary').addEventListener('change', handleFiles);

function readAsDataURL(file){
  return new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(r.result);r.onerror=rej;r.readAsDataURL(file);});
}

async function uploadOne(file){
  const cell = document.createElement('div'); cell.className='thumb';
  const img = document.createElement('img'); cell.appendChild(img);
  const badge = document.createElement('div'); badge.className='badge'; badge.textContent='…';
  cell.appendChild(badge); grid.prepend(cell);
  try{
    const dataUrl = await readAsDataURL(file);
    img.src = dataUrl;
    const b64 = dataUrl.split(',')[1];
    const r = await fetch('/api/upload-photo', {
      method:'POST', headers:{'Content-Type':'application/json','X-Upload-Token':token},
      body: JSON.stringify({type, id, tag:currentTag(), filename:file.name||'photo.jpg', data:b64})
    });
    const j = await r.json();
    if(j.ok){ badge.textContent='✓'; badge.className='badge done'; }
    else { badge.textContent='✗'; badge.className='badge err'; statusEl.textContent=j.error||'Upload failed'; }
  }catch(err){ badge.textContent='✗'; badge.className='badge err'; statusEl.textContent='Upload error'; }
}
</script></body></html>"""


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        # The default implementation prints a full traceback to the
        # console, which (in the frozen .exe) includes the absolute build
        # path baked in at compile time. Log the full detail to a local
        # file instead, and keep the console output generic — this is a
        # console app users may screenshot for a bug report.
        import traceback
        try:
            with open(os.path.join(BASE_DIR, 'error.log'), 'a', encoding='utf-8') as f:
                f.write('-' * 60 + '\n')
                f.write(f'Error handling request from {client_address}\n')
                traceback.print_exc(file=f)
        except Exception:
            pass
        print(f'  (a request failed — see error.log next to the app for details)')


def _sanitized_crash_message(exc):
    return (
        f'\nPen & Ink Tracker hit an unexpected error and had to stop: '
        f'{type(exc).__name__}: {exc}\n'
        f'Full details were written to error.log next to the app.\n'
    )


if __name__ == '__main__':
    try:
        ip = lan_ip()
        cfg = load_config()
        provider = cfg.get('provider', 'gemini')
        key_field = 'anthropic_api_key' if provider == 'anthropic' else 'gemini_api_key'
        ai = (f'{provider} (key set)' if not _placeholder_key(cfg.get(key_field))
              else f'{provider} (no key — add one to tracker/config.json)')
        # Bind to all interfaces so the phone can reach it over Wi-Fi.
        server = ThreadingServer(('0.0.0.0', PORT), Handler)
        print('Pen & Ink Tracker')
        print(f'  Desktop:  http://localhost:{PORT}')
        print(f'  Phone:    http://{ip}:{PORT}   (same Wi-Fi; this is what the QR encodes)')
        print(f'  AI fill:  {ai}')
        print(f'  Photos:   {PHOTOS_DIR}')
        print('  Ctrl+C to stop.\n')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('\nStopped.')
    except Exception as exc:
        import traceback
        try:
            with open(os.path.join(BASE_DIR, 'error.log'), 'a', encoding='utf-8') as f:
                f.write('-' * 60 + '\n')
                f.write('Startup error\n')
                traceback.print_exc(file=f)
        except Exception:
            pass
        print(_sanitized_crash_message(exc))
        sys.exit(1)
