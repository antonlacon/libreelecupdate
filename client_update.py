#!/usr/bin/env python

# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2023-present Team LibreELEC (https://libreelec.tv)

# disables pylint checks for:
# variable/function naming convention
# lack of docstring to start module
# line length check
# pylint: disable=C0103,C0114,C0301


import argparse
import importlib.machinery
import importlib.util
import os
import sys
import urllib.request

# shutil, tempfile, urllib.error and hashlib/sha256 also imoprted when starting file download


def import_from_file(module_name, file_path):
    '''Import python source code module from file path.'''
    if os.path.isfile(file_path) and module_name not in sys.modules:
        spec = importlib.util.spec_from_loader(
            module_name,
            importlib.machinery.SourceFileLoader(module_name, file_path)
            )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[module_name] = module
        return module
    elif module_name in sys.modules:
        print(f'Module already loaded: {module_name}')
    else:
        print(f'File not found: {file_path}')
        sys.exit(1)

update_lib = import_from_file(module_name='update_lib', file_path='/usr/lib/libreelec/update_lib.py')


def fetch_update_file(url, sha256sum, file_name, update_dir='/storage/.update', verbose=False):
    '''Download update_url to a temporary directory. Copy to update directory when finished.'''
    import shutil, tempfile, urllib.error
    from hashlib import sha256

    def get_sha256_hash(file_path, buf):
        '''Calculate sha256 sum of file_path.'''
        h = sha256()
        with open(file_path, mode='rb') as f:
            while True:
                nbytes = f.readinto(buf)
                if not nbytes:
                    break
                h.update(memoryview(buf)[:nbytes])
        return h.hexdigest()

    buf = bytearray(32768)

    print(f"Starting download: {url}")
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_file = os.path.join(tmpdir, 'update.file')
        try:
            with urllib.request.urlopen(url, timeout=30) as download, open(temp_file, 'wb') as out:
                while True:
                    nbytes = download.readinto(buf)
                    if not nbytes:
                        break
                    out.write(buf[:nbytes])

        except urllib.error.HTTPError as e:
            print(f'HTTP error: {e.code}: {url}')
            return False
        except urllib.error.URLError as e:
            print(f'Network error: {e.reason}')
            return False
        except Exception as e:
            print(f'Unexpected error: {e}')
            return False

        if not os.path.isfile(temp_file):
            print('Download failed: no file created.')
            return False

        download_checksum = get_sha256_hash(temp_file, buf)
        if verbose:
            print(f'Expected: {sha256sum}\nGot: {download_checksum}')

        if sha256sum != download_checksum:
            print('ERROR: sha256 checksum mismatch. Deleting file.')
            os.remove(temp_file)
            return False

        os.makedirs(update_dir, exist_ok=True)
        shutil.copy2(temp_file, os.path.join(update_dir, file_name))
        print('Update file successfully downloaded. Reboot to continue with update.')
        return True


if __name__ == '__main__':
    # parse CLI arguments
    parser = argparse.ArgumentParser(description='Parse releases.json for suitable update files.', argument_default=False)
    parser.add_argument('-v', '--verbose', default=False,
        help = 'Verbose output', action = 'store_true')
    parser.add_argument('-b', '--bugfix', default=False,
        help = 'Check for bugfix updates only (ex 12.0.x -> 12.0.y).', action = 'store_true')
    parser.add_argument('-m', '--major', default=False,
        help = 'Check for major/minor updates only (ex 12.x -> 13.x).', action = 'store_true')
    parser.add_argument('-n', '--nightly', default=False,
        help = 'Check for newer nightly test build. Only works if already running a test or development build.', action = 'store_true')
    parser.add_argument('-f', '--force', default=False,
        help = 'Ignore testing periods for updates.', action = 'store_true')
    parser.add_argument('-j', '--json', default=None,
        help = 'http or file path to an alternative releases.json file.', action = 'store')
    parser.add_argument('-u', '--update', default=False,
        help = 'Download update file for latest minor bugfix release, if available.', action = 'store_true')
    args = parser.parse_args()

    # sanity check
    if args.nightly and (args.bugfix or args.major):
        print('Error: --nightly may not be combined with --bugfix or --major. Assuming --nightly intended.')
        args.bugfix = False
        args.major = False

    if args.json:
        if args.json.startswith(('http://', 'https://')):
            releases_json = args.json
        elif os.path.isfile(os.path.join(os.getcwd(), args.json)):
            releases_json = f'file://{os.path.join(os.getcwd(), args.json)}'
        else:
            print(f'ERROR: Unable to locate: {args.json}')
            sys.exit(1)
    elif args.nightly:
        releases_json = 'https://test.libreelec.tv/releases.json'
    else:
        releases_json = 'https://releases.libreelec.tv/releases.json'

    client_update = update_lib.UpdateSystem(
        json_url=releases_json,
        json_data=None,
        nightly=args.nightly,
        verbose=args.verbose
    )

    if args.bugfix:
        client_update.check_for_bugfix()
    elif args.major:
        client_update.check_for_major()
    elif args.nightly:
        client_update.check_for_nightly()
    else:
        client_update.check_for_bugfix()
        if not client_update.update_available:
            client_update.check_for_major()

    if args.verbose:
        print(f'{client_update.update_available=}\n{client_update.update_major=}\n{client_update.update_url=}')

    if client_update.update_available:
        print(f'Found update file: {client_update.update_url}')
        if client_update.update_major:
            print('Major system update found. See https://libreelec.tv for release notes.')
        else:
            if args.update:
                print(f'Downloading: {client_update.update_url}')
                success = fetch_update_file(
                    url=client_update.update_url,
                    sha256sum=client_update.candidate['sha256'],
                    file_name=client_update.candidate['filename'],
                    verbose=args.verbose
                )
            else:
                print('System update found. Run command again with --update to apply.')
    else:
        print('No eligible system updates found to apply.')
