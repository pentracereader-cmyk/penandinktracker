#!/usr/bin/env python3
"""First-run setup for Pen & Ink Tracker.

Stdlib only. Runs once (guarded by a ``.setup-done`` marker file next to
this script) and is safe to run again — it will just say hello and exit.
Every question has a sensible default if you just press Enter.
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MARKER = os.path.join(BASE_DIR, '.setup-done')
CONFIG_EXAMPLE = os.path.join(BASE_DIR, 'config.example.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

DATA_FILES = {
    'pens.json': [],
    'inks.json': [],
    'papers.json': [],
    'photos.json': {},
    'catalog_learned.json': {},
}


def ensure_data_files():
    """Make sure the empty starting data files exist. Never overwrites
    a file that already has real data in it (e.g. on a re-run)."""
    created = []
    for name, empty_value in DATA_FILES.items():
        path = os.path.join(BASE_DIR, name)
        if not os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(empty_value, f)
            created.append(name)
    photos_dir = os.path.join(BASE_DIR, 'photos')
    if not os.path.isdir(photos_dir):
        os.makedirs(photos_dir, exist_ok=True)
        created.append('photos/')
    return created


def print_intro():
    print()
    print('=' * 62)
    print('  Pen & Ink Tracker - first-time setup')
    print('=' * 62)
    print()
    print('This app tracks your fountain pen, ink, and paper collection.')
    print('It runs entirely on this computer: there is no cloud service,')
    print('no account, and no company on the other end. Your collection')
    print('data is stored in plain files right next to this program and')
    print('is never sent anywhere unless you choose to use the optional')
    print('AI feature described below.')
    print()


def ask_yes_no(prompt, default=False):
    suffix = ' [Y/n] ' if default else ' [y/N] '
    try:
        answer = input(prompt + suffix).strip().lower()
    except EOFError:
        answer = ''
    if not answer:
        return default
    return answer.startswith('y')


def offer_ai_setup():
    print('-' * 62)
    print('Optional: AI auto-fill (Google Gemini, free tier)')
    print('-' * 62)
    print()
    print('One feature in the app, "Auto-fill with AI", can look up a pen')
    print('or ink by name and propose the details and photos for you. It')
    print("uses Google Gemini's FREE tier, called directly over HTTPS -")
    print('no extra software to install.')
    print()
    print('EVERYTHING ELSE IN THE APP WORKS FULLY WITHOUT THIS - pens,')
    print('inks, papers, photos, the swab wall, imports, exports, and the')
    print('phone hand-off all work with no key at all. This step is')
    print('entirely optional and can be skipped by pressing Enter.')
    print()
    print('A free key takes about a minute to get, at:')
    print('    https://aistudio.google.com/apikey')
    print('(sign in with any Google account, no credit card needed)')
    print()

    try:
        key = input(
            'Paste your Gemini API key here, or press Enter to skip: '
        ).strip()
    except EOFError:
        key = ''

    if not key:
        print()
        print('Skipping AI setup - no config.json was written. You can add')
        print('a key later by copying config.example.json to config.json')
        print('and pasting it in, and you can always try the app first and')
        print('decide later.')
        return False

    if os.path.exists(CONFIG_EXAMPLE):
        with open(CONFIG_EXAMPLE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    else:
        # Fallback shape if config.example.json is somehow missing.
        config = {
            'provider': 'gemini',
            'gemini_api_key': '',
            'gemini_model': 'gemini-2.5-flash',
            'enable_web_search': True,
        }

    config['provider'] = 'gemini'
    config['gemini_api_key'] = key

    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)

    print()
    print('Saved your key to config.json. AI auto-fill is ready to use.')
    return True


def main():
    if os.path.exists(MARKER):
        print('Pen & Ink Tracker is already set up.')
        print('Starting the server...')
        return 0

    print_intro()

    offer_ai_setup()

    print()
    print('-' * 62)
    created = ensure_data_files()
    if created:
        print('Created empty data files: ' + ', '.join(created))
    print('Checked: pens.json, inks.json, papers.json, photos.json, and')
    print('catalog_learned.json all exist and start empty.')
    print()

    with open(MARKER, 'w', encoding='utf-8') as f:
        f.write('Setup completed. Delete this file to see the first-run\n'
                'questions again.\n')

    print('-' * 62)
    print('Setup complete!')
    print()
    print('Starting the server now. Once it is running, open:')
    print()
    print('    http://localhost:3838')
    print()
    print('in your web browser (this should also happen automatically).')
    print()
    print('Next time, just run the same launcher again')
    print('(Start on Windows.bat / start-mac.command / start-linux.sh) -')
    print("these questions won't be asked again.")
    print('-' * 62)
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
