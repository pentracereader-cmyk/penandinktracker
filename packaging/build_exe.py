#!/usr/bin/env python3
"""Build a one-file Windows installer/executable for Pen & Ink Tracker
using PyInstaller.

============================================================================
KNOWN TRADE-OFFS — read before using this script
============================================================================
1. SIZE: PyInstaller's --onefile mode bundles a full Python interpreter
   plus the standard library into the executable. Expect roughly 15-30 MB
   for this app, versus a few hundred KB for the plain zip distribution
   built by build.py. For an app that only needs the stdlib, the plain
   zip + "install Python once" path in build.py is the leaner option;
   this .exe exists purely for users who would rather not install Python
   at all.
2. ANTIVIRUS FALSE POSITIVES: PyInstaller onefile executables are a
   well-known pattern abused by malware (self-extracting, runs from a
   temp directory), so Windows Defender and other AV engines sometimes
   flag freshly-built PyInstaller executables as suspicious, especially
   before the specific build has built up any reputation. This is a
   near-universal PyInstaller limitation, not a defect in this app. Users
   who hit this may need to allow the file through their AV, and/or the
   publisher may want to code-sign the executable (not done here) to
   reduce false positives over time.
3. WINDOWS-ONLY, AND ONLY FROM A WINDOWS MACHINE: PyInstaller does not
   cross-compile. Running this script on Windows produces a Windows-only
   .exe; producing a macOS or Linux binary would require running this
   same script on that platform. This project ships source + a stdlib
   launcher (see build.py) for Mac/Linux instead of a PyInstaller binary.
4. UPDATES: unlike the plain zip (where updating is "download the new
   zip, keep your data files"), a new .exe build must be re-downloaded in
   full for every update, since the interpreter is baked in.
============================================================================

This script is NEVER invoked automatically by build.py — it is a separate,
manual, Windows-only build step. It does not install anything for you: if
PyInstaller is not already installed, it prints the exact pip command to
run and exits non-zero rather than reaching for pip itself.

Usage (after `pip install pyinstaller`):
    python packaging/build_exe.py
"""
import importlib.util
import os
import shutil
import subprocess
import sys

PACKAGING_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(PACKAGING_DIR)
TRACKER_DIR = os.path.join(ROOT_DIR, 'tracker')
FILES_DIR = os.path.join(PACKAGING_DIR, 'files')
DIST_DIR = os.path.join(ROOT_DIR, 'dist')
BUILD_WORK_DIR = os.path.join(DIST_DIR, 'exe-build')
APP_NAME = 'PenInkTracker'

# Data files that must travel alongside the frozen executable, staged the
# same way build.py stages them for the zip: app assets from tracker/,
# plus fresh EMPTY collection files and the launcher's own setup script.
DATA_FILES_FROM_TRACKER = [
    'index.html',
    'qrcode.min.js',
    'manifest.json',
    'icon-192.png',
    'icon-512.png',
    'apple-touch-icon.png',
    'ink_catalog.json',
    'config.example.json',
]


def read_version():
    version_path = os.path.join(PACKAGING_DIR, 'VERSION')
    with open(version_path, 'r', encoding='utf-8') as f:
        return f.read().strip()


def check_pyinstaller_available():
    if importlib.util.find_spec('PyInstaller') is None:
        print('PyInstaller is not installed in this Python environment.')
        print()
        print('This script will not install packages on its own. To build')
        print('the Windows .exe, first run:')
        print()
        print('    pip install pyinstaller')
        print()
        print('...then run this script again:')
        print()
        print('    python packaging/build_exe.py')
        sys.exit(1)


def stage_exe_inputs(version):
    """Reuse the same staged app tree that build.py produces (it already
    excludes personal data and secrets), so this script doesn't duplicate
    that logic or risk drifting out of sync with it."""
    staged_app = os.path.join(DIST_DIR, 'staging', APP_NAME)
    if not os.path.isdir(staged_app):
        print(f'Expected staged app tree at {staged_app!r} but it does not exist.')
        print('Run `python packaging/build.py` first to stage and validate')
        print('the app contents (data-emptying + secret-exclusion checks')
        print('live there, and this script relies on them).')
        sys.exit(1)
    return staged_app


def build_add_data_args(staged_app):
    """PyInstaller --add-data wants 'SRC<sep>DEST_DIR_IN_BUNDLE' and the
    separator is ';' on Windows, ':' elsewhere. This script only targets
    Windows (see trade-off #3 above) but we compute it properly anyway."""
    sep = ';' if os.name == 'nt' else ':'
    args = []
    for name in DATA_FILES_FROM_TRACKER + list(
        {'pens.json', 'inks.json', 'papers.json', 'photos.json', 'catalog_learned.json'}
    ) + ['setup_first_run.py', 'LICENSE', 'CREDITS.md', 'README.md', 'CHANGELOG.md',
         'DISCLAIMER.md', 'PRIVACY.md']:
        src = os.path.join(staged_app, name)
        if os.path.isfile(src):
            args.append(f'--add-data={src}{sep}.')
    photos_dir = os.path.join(staged_app, 'photos')
    if os.path.isdir(photos_dir):
        args.append(f'--add-data={photos_dir}{sep}photos')
    return args


def main():
    if os.name != 'nt':
        print('build_exe.py only produces a Windows executable and is')
        print('intended to be run on Windows (see trade-off #3 in the')
        print('module docstring). Continuing anyway is unsupported.')

    check_pyinstaller_available()

    version = read_version()
    staged_app = stage_exe_inputs(version)

    entry_point = os.path.join(staged_app, 'server.py')
    if not os.path.isfile(entry_point):
        print(f'Missing entry point: {entry_point}')
        sys.exit(1)

    os.makedirs(BUILD_WORK_DIR, exist_ok=True)
    out_name = f'{APP_NAME}-Setup-{version}'

    add_data_args = build_add_data_args(staged_app)

    pyinstaller_cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--name', out_name,
        '--distpath', DIST_DIR,
        '--workpath', os.path.join(BUILD_WORK_DIR, 'work'),
        '--specpath', BUILD_WORK_DIR,
        '--console',
        *add_data_args,
        entry_point,
    ]

    print('Running PyInstaller:')
    print()
    print('  ' + ' '.join(f'"{a}"' if ' ' in a else a for a in pyinstaller_cmd))
    print()
    print('Notes:')
    print(f'  - Output will be: {os.path.join(DIST_DIR, out_name + ".exe")}')
    print('  - This bundles server.py plus the data files listed in')
    print('    DATA_FILES_FROM_TRACKER as read-only resources inside the')
    print('    frozen exe; on first run the app should copy any missing')
    print('    data files out next to the exe so they are still editable')
    print('    and backup-able as plain files (server.py already resolves')
    print('    its data paths relative to BASE_DIR, so run it from a')
    print('    writable working directory, e.g. by leaving the exe in its')
    print('    own folder rather than a locked-down Program Files path).')
    print('  - See the trade-offs documented at the top of this file')
    print('    before shipping the result: size, AV false positives, and')
    print('    that it must be built ON Windows, FOR Windows.')
    print()

    result = subprocess.run(pyinstaller_cmd)
    if result.returncode != 0:
        print(f'PyInstaller exited with status {result.returncode}.')
        return result.returncode

    exe_path = os.path.join(DIST_DIR, out_name + '.exe')
    if os.path.isfile(exe_path):
        size = os.path.getsize(exe_path)
        print(f'Built {exe_path} ({size:,} bytes).')
    else:
        print('PyInstaller reported success but the expected .exe was not found at:')
        print(f'  {exe_path}')
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
