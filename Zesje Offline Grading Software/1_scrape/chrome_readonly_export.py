"""Download Zesje exam metadata and detailed exports through a Chrome session.

The user signs in in the Chrome window. No credentials or cookies are copied.
Outputs are written to a new directory supplied outside the source repository.
"""
import argparse
import base64
from contextlib import closing
import json
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

from selenium import webdriver


def fetch(driver, path):
    return driver.execute_async_script("""
        const done = arguments[arguments.length - 1];
        fetch(arguments[0], {credentials: 'same-origin'}).then(async r => {
          const bytes = new Uint8Array(await r.arrayBuffer());
          let chunks = [];
          for (let i=0; i<bytes.length; i+=32768)
            chunks.push(String.fromCharCode(...bytes.subarray(i, i+32768)));
          done({status:r.status, type:r.headers.get('content-type'), body:btoa(chunks.join(''))});
        }).catch(e => done({error:String(e)}));
    """, path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base-url', required=True)
    p.add_argument('--exam', type=int, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cookie-profile', type=Path, help='Existing Chrome profile directory')
    args = p.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.zesje.tudelft.nl') or parsed.path not in ('', '/'):
        p.error('base-url must be an HTTPS Zesje instance root')
    args.output.mkdir(parents=True, exist_ok=False)
    options = webdriver.ChromeOptions()
    temporary_profile = None
    if args.cookie_profile:
        source = args.cookie_profile / 'Network' / 'Cookies'
        state = args.cookie_profile.parent / 'Local State'
        if not source.is_file() or not state.is_file():
            p.error('Chrome profile Cookies or Local State is missing')
        temporary_profile = tempfile.TemporaryDirectory(prefix='zesje-chrome-')
        root = Path(temporary_profile.name)
        shutil.copy2(state, root / 'Local State')
        target = root / 'Default' / 'Network' / 'Cookies'
        target.parent.mkdir(parents=True)
        snapshot = root / 'source-cookies.sqlite'
        shutil.copy2(source, snapshot)
        for suffix in ('-wal', '-shm'):
            companion = Path(str(source) + suffix)
            if companion.exists():
                shutil.copy2(companion, Path(str(snapshot) + suffix))
        with closing(sqlite3.connect(snapshot)) as src, closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            dst.execute('PRAGMA secure_delete=ON')
            dst.execute('DELETE FROM cookies WHERE host_key NOT IN (?, ?)', (parsed.hostname, '.' + parsed.hostname))
            dst.commit()
            dst.execute('VACUUM')
        for suffix in ('', '-wal', '-shm'):
            Path(str(snapshot) + suffix).unlink(missing_ok=True)
        options.add_argument(f'--user-data-dir={root}')
        options.add_argument('--profile-directory=Default')
    driver = webdriver.Chrome(options=options)
    try:
        driver.set_script_timeout(120)
        driver.get(args.base_url)
        print('Sign in to Zesje in the opened Chrome window, then return to the exam page.', flush=True)
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            if urlparse(driver.current_url).hostname == parsed.hostname:
                result = fetch(driver, '/api/exams')
                if result.get('status') == 200:
                    try:
                        exams = json.loads(base64.b64decode(result['body']))
                        if isinstance(exams, list):
                            break
                    except (ValueError, KeyError):
                        pass
            time.sleep(3)
        else:
            raise RuntimeError('Timed out waiting for an authenticated Zesje session')
        (args.output / 'exams.json').write_text(json.dumps(exams, ensure_ascii=False, indent=2), encoding='utf-8')
        for exam in args.exam:
            for endpoint, filename, kind in [
                (f'/api/exams/{exam}', f'_api_exams_{exam}.json', 'json'),
                (f'/api/export/xlsx_detailed/{exam}', f'export_xlsx_detailed_{exam}.xlsx', 'xlsx'),
            ]:
                result = fetch(driver, endpoint)
                if result.get('status') != 200:
                    raise RuntimeError(f'{endpoint}: HTTP {result.get("status")}')
                data = base64.b64decode(result['body'], validate=True)
                if kind == 'json':
                    json.loads(data)
                elif not data.startswith(b'PK\x03\x04'):
                    raise RuntimeError(f'{endpoint}: response is not an XLSX file')
                (args.output / filename).write_bytes(data)
                print(f'Saved {filename} ({len(data)} bytes)', flush=True)
    finally:
        driver.quit()
        if temporary_profile:
            temporary_profile.cleanup()


if __name__ == '__main__':
    main()
