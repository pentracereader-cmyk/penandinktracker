#!/usr/bin/env python3
"""Build the distributable Pen & Ink Tracker package.

Stdlib only. Stages a clean copy of the app (with EMPTY starting data, no
personal data, no API keys) into ``dist/staging/PenInkTracker/``, adds
launchers / first-run setup / docs, runs a set of hard-fail exclusion
checks, and zips the result to ``dist/PenInkTracker-<version>.zip``.

Usage:
    python packaging/build.py

Never invokes PyInstaller and never touches anything under ../tracker
except to *read* the specific files listed in APP_FILES below.
"""
import json
import os
import re
import shutil
import stat
import sys
import zipfile

PACKAGING_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(PACKAGING_DIR)
TRACKER_DIR = os.path.join(ROOT_DIR, 'tracker')
FILES_DIR = os.path.join(PACKAGING_DIR, 'files')
DIST_DIR = os.path.join(ROOT_DIR, 'dist')
STAGING_ROOT = os.path.join(DIST_DIR, 'staging')
APP_NAME = 'PenInkTracker'
STAGE_DIR = os.path.join(STAGING_ROOT, APP_NAME)

# --- What we read out of tracker/ (source of truth: the running app) ------
# Only these exact files are ever copied from the developer's working
# tracker/ directory. Everything else in tracker/ (personal data, photos,
# backups, working copies, the real config.json, __pycache__, _source/)
# is never looked at, let alone copied.
# Which UI ships. The working copies live beside it in tracker/ as index.v2/v3;
# whichever we ship is renamed to index.html so server.py's default serves it.
UI_SOURCE = 'index.v3.html'

# Entries are either 'name' (copied as-is) or ('source name', 'name in package').
APP_FILES = [
    'server.py',
    (UI_SOURCE, 'index.html'),
    'qrcode.min.js',
    'manifest.json',
    'icon-192.png',
    'icon-512.png',
    'apple-touch-icon.png',
    'ink_catalog.json',
    'config.example.json',
    'requirements.txt',
]

# Fresh, empty starting data written directly by the build (never copied
# from the developer's real collection files).
EMPTY_JSON_FILES = {
    'pens.json': [],
    'inks.json': [],
    'papers.json': [],
    'photos.json': {},
    'catalog_learned.json': {},
}

# Docs / launchers / first-run setup, authored under packaging/files/ and
# copied verbatim into the staged root.
ROOT_EXTRA_FILES = [
    'LICENSE',
    'CREDITS.md',
    'README.md',
    'CHANGELOG.md',
    'DISCLAIMER.md',
    'PRIVACY.md',
    'setup_first_run.py',
    'Start on Windows.bat',
    'start-mac.command',
    'start-linux.sh',
]

# Files that must get the executable bit set inside the zip (Windows does
# not preserve unix permissions, so we set them explicitly on the
# ZipInfo entries at zip time).
EXECUTABLE_IN_ZIP = {
    'start-mac.command',
    'start-linux.sh',
}

# --- Hard exclusion rules ---------------------------------------------------
# Directory names that must NEVER appear anywhere in the staged tree.
FORBIDDEN_DIR_NAMES = {
    'backups', '__pycache__', '_source', 'user_photos', '.git', '_design',
}

# Exact file names that must NEVER appear anywhere in the staged tree.
FORBIDDEN_FILE_NAMES = {
    'config.json', 'index.v2.html', 'index.v3.html',
}

# Filename patterns (fnmatch-style, checked with regex below) that must
# never appear.
FORBIDDEN_FILE_PATTERNS = [
    re.compile(r'.*\.bak.*', re.IGNORECASE),
]

# Files we deliberately create that are allowed to start with a dot.
DOTFILE_ALLOWLIST = {'.gitkeep'}

# Fragment of the developer's real Google API key. If this turns up
# anywhere in the staged tree, the build must abort. Note the '.' is a
# wildcard (matches any single character), same as in the task spec.
SECRET_FRAGMENT_PATTERN = re.compile(rb'AQ.Ab8RN')

# Extensions we treat as binary/opaque for the secret-fragment grep (still
# scanned as raw bytes, just not decoded).
TEXT_SCAN_MAX_BYTES = 5 * 1024 * 1024  # skip scanning anything absurdly large


def log(msg=''):
    print(msg, flush=True)


def fail(msg):
    log()
    log('BUILD FAILED: ' + msg)
    sys.exit(1)


def read_version():
    version_path = os.path.join(PACKAGING_DIR, 'VERSION')
    if not os.path.isfile(version_path):
        fail(f'Missing version file: {version_path}')
    with open(version_path, 'r', encoding='utf-8') as f:
        version = f.read().strip()
    if not re.match(r'^\d+\.\d+\.\d+$', version):
        fail(f'VERSION file does not look like a semantic version: {version!r}')
    return version


def clean_staging():
    if os.path.isdir(STAGING_ROOT):
        shutil.rmtree(STAGING_ROOT)
    os.makedirs(STAGE_DIR, exist_ok=True)


def copy_app_files():
    log('Copying app files from tracker/ ...')
    for entry in APP_FILES:
        src_name, dst_name = entry if isinstance(entry, tuple) else (entry, entry)
        src = os.path.join(TRACKER_DIR, src_name)
        if not os.path.isfile(src):
            fail(f'Expected app file is missing from tracker/: {src_name}')
        dst = os.path.join(STAGE_DIR, dst_name)
        shutil.copy2(src, dst)
        log(f'  copied {src_name}' + (f' -> {dst_name}' if src_name != dst_name else ''))


def write_empty_data_files():
    log('Writing empty starting data files ...')
    for name, empty_value in EMPTY_JSON_FILES.items():
        dst = os.path.join(STAGE_DIR, name)
        with open(dst, 'w', encoding='utf-8') as f:
            json.dump(empty_value, f)
        log(f'  wrote {name} = {json.dumps(empty_value)}')

    photos_dir = os.path.join(STAGE_DIR, 'photos')
    os.makedirs(photos_dir, exist_ok=True)
    with open(os.path.join(photos_dir, '.gitkeep'), 'w', encoding='utf-8') as f:
        f.write('')
    log('  created empty photos/ with .gitkeep')


def copy_root_extras():
    log('Copying launchers, first-run setup, and docs ...')
    for name in ROOT_EXTRA_FILES:
        src = os.path.join(FILES_DIR, name)
        if not os.path.isfile(src):
            fail(f'Missing packaging/files/{name} — cannot stage it.')
        dst = os.path.join(STAGE_DIR, name)
        shutil.copy2(src, dst)
        log(f'  copied {name}')


# --- Exclusion assertions ---------------------------------------------------

def assert_no_forbidden_paths():
    log('Checking staged tree for forbidden files/directories ...')
    violations = []
    for dirpath, dirnames, filenames in os.walk(STAGE_DIR):
        for d in list(dirnames):
            if d in FORBIDDEN_DIR_NAMES:
                violations.append(os.path.join(dirpath, d) + ' (forbidden directory)')
        for fn in filenames:
            if fn in FORBIDDEN_FILE_NAMES:
                violations.append(os.path.join(dirpath, fn) + ' (forbidden file name)')
            if fn.startswith('.') and fn not in DOTFILE_ALLOWLIST:
                violations.append(os.path.join(dirpath, fn) + ' (unexpected dotfile)')
            for pattern in FORBIDDEN_FILE_PATTERNS:
                if pattern.match(fn):
                    violations.append(os.path.join(dirpath, fn) + ' (forbidden pattern)')
    if violations:
        fail('Forbidden paths found in staged tree:\n  ' + '\n  '.join(violations))
    log('  none found')


def assert_empty_data_contents():
    log('Checking that shipped data files are actually empty ...')
    for name, expected in EMPTY_JSON_FILES.items():
        path = os.path.join(STAGE_DIR, name)
        with open(path, 'r', encoding='utf-8') as f:
            actual = json.load(f)
        if actual != expected:
            fail(f'{name} in staged tree is not empty as expected! '
                 f'Refusing to ship what may be personal data.')
    photos_dir = os.path.join(STAGE_DIR, 'photos')
    contents = os.listdir(photos_dir)
    if contents != ['.gitkeep']:
        fail(f'photos/ in staged tree should contain only .gitkeep, found: {contents}')
    log('  pens.json, inks.json, papers.json, photos.json, catalog_learned.json all empty')
    log('  photos/ contains only .gitkeep')


def assert_no_secret_fragment():
    log('Grepping staged tree for the real API key fragment ...')
    hits = []
    for dirpath, _dirnames, filenames in os.walk(STAGE_DIR):
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if size > TEXT_SCAN_MAX_BYTES:
                continue
            with open(path, 'rb') as f:
                data = f.read()
            if SECRET_FRAGMENT_PATTERN.search(data):
                hits.append(path)
    if hits:
        fail('Found the real API key fragment in staged output:\n  ' + '\n  '.join(hits))
    log('  clean — no key fragment found')


def assert_config_example_has_no_real_key():
    # Belt-and-braces: config.example.json must contain only placeholder
    # values, never a real key, since it IS shipped.
    path = os.path.join(STAGE_DIR, 'config.example.json')
    with open(path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    key = config.get('gemini_api_key', '')
    if key and not key.startswith('AIza...') and key != '':
        fail(f'config.example.json gemini_api_key does not look like a placeholder: {key!r}')


def run_exclusion_checks():
    assert_no_forbidden_paths()
    assert_empty_data_contents()
    assert_config_example_has_no_real_key()
    assert_no_secret_fragment()


# --- Zipping -----------------------------------------------------------------

def build_zip(version):
    os.makedirs(DIST_DIR, exist_ok=True)
    zip_path = os.path.join(DIST_DIR, f'{APP_NAME}-{version}.zip')
    if os.path.exists(zip_path):
        os.remove(zip_path)

    log(f'Writing {zip_path} ...')
    entries = []
    for dirpath, dirnames, filenames in os.walk(STAGE_DIR):
        dirnames.sort()
        for fn in sorted(filenames):
            abs_path = os.path.join(dirpath, fn)
            rel_path = os.path.relpath(abs_path, STAGING_ROOT)  # includes APP_NAME/ prefix
            entries.append((abs_path, rel_path))

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for abs_path, rel_path in entries:
            zi = zipfile.ZipInfo.from_file(abs_path, arcname=rel_path.replace(os.sep, '/'))
            zi.compress_type = zipfile.ZIP_DEFLATED
            basename = os.path.basename(abs_path)
            if basename in EXECUTABLE_IN_ZIP:
                # Set unix mode bits (rwxr-xr-x) in the high 16 bits of
                # external_attr, since Windows won't preserve them itself.
                unix_mode = 0o755
                zi.external_attr = (unix_mode & 0xFFFF) << 16
            with open(abs_path, 'rb') as f:
                zf.writestr(zi, f.read())

    return zip_path, entries


def print_manifest(entries, zip_path):
    log()
    log('=' * 70)
    log('BUILD MANIFEST')
    log('=' * 70)
    total = 0
    for abs_path, rel_path in sorted(entries, key=lambda e: e[1].lower()):
        size = os.path.getsize(abs_path)
        total += size
        log(f'  {size:>10,} bytes  {rel_path}')
    log('-' * 70)
    log(f'  {total:>10,} bytes  ({len(entries)} files, uncompressed total)')
    zip_size = os.path.getsize(zip_path)
    log('=' * 70)
    log(f'Zip file: {zip_path}')
    log(f'Zip size: {zip_size:,} bytes')
    log('=' * 70)


def main():
    version = read_version()
    log(f'Building Pen & Ink Tracker {version}')
    log(f'  tracker source: {TRACKER_DIR}')
    log(f'  staging dir:    {STAGE_DIR}')
    log()

    if not os.path.isdir(TRACKER_DIR):
        fail(f'tracker/ directory not found at {TRACKER_DIR}')

    clean_staging()
    copy_app_files()
    write_empty_data_files()
    copy_root_extras()

    log()
    run_exclusion_checks()

    log()
    zip_path, entries = build_zip(version)
    print_manifest(entries, zip_path)

    log()
    log('Build succeeded.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
