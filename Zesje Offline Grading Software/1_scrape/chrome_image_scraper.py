"""Scrape configured Zesje question images using a visible Chrome session."""
import argparse
import base64
import io
import json
import time
from pathlib import Path
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from PIL import Image


def save_source_image(driver, image, target):
    result = driver.execute_async_script('''
        const img = arguments[0], done = arguments[arguments.length - 1];
        fetch(img.currentSrc, {credentials: 'same-origin'}).then(async r => {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const data = new Uint8Array(await r.arrayBuffer());
            let chunks = [];
            for (let i=0; i<data.length; i+=32768)
                chunks.push(String.fromCharCode(...data.subarray(i, i+32768)));
            done({body:btoa(chunks.join('')), width:img.naturalWidth, height:img.naturalHeight});
        }).catch(e => done({error:String(e)}));
    ''', image)
    if result.get('error'):
        raise RuntimeError(result['error'])
    with Image.open(io.BytesIO(base64.b64decode(result['body'], validate=True))) as source:
        if source.size != (result['width'], result['height']):
            raise RuntimeError('source image dimensions differ from browser image')
        source.save(target, format='PNG')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base-url', required=True)
    p.add_argument('--exam-json', type=Path, action='append', required=True)
    p.add_argument('--problem', action='append', required=True, help='exam ID:problem ID')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--login-timeout', type=int, default=3600, help='seconds to wait for manual sign-in')
    p.add_argument('--user-data-dir', type=Path, help='existing Chrome user-data directory, which must not be in use')
    args = p.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.zesje.tudelft.nl'):
        p.error('expected a TU Delft Zesje HTTPS URL')
    exams = {e['id']: e for e in (json.loads(path.read_text(encoding='utf-8')) for path in args.exam_json)}
    try:
        requested = [tuple(map(int, item.split(':'))) for item in args.problem]
        if any(len(pair) != 2 or pair[0] not in exams or pair[1] not in {v['id'] for v in exams[pair[0]]['problems']} for pair in requested):
            raise ValueError()
    except ValueError:
        p.error('problem must be a valid exam ID:problem ID pair')
    args.output.mkdir(parents=True, exist_ok=True)
    options = webdriver.ChromeOptions()
    if args.user_data_dir:
        options.add_argument(f'--user-data-dir={args.user_data_dir}')
        options.add_argument('--profile-directory=Default')
    driver = webdriver.Chrome(options=options)
    report = {'problems': requested, 'saved': [], 'failed': []}
    try:
        driver.get(args.base_url)
        print('Sign in in Chrome; the scraper will start automatically.', flush=True)
        deadline = time.monotonic() + args.login_timeout
        while time.monotonic() < deadline:
            if urlparse(driver.current_url).hostname == parsed.hostname:
                status = driver.execute_async_script("const done=arguments[0]; fetch('/api/exams',{credentials:'same-origin'}).then(r=>done(r.status)).catch(()=>done(0))")
                if status == 200:
                    break
            time.sleep(3)
        else:
            raise RuntimeError('Timed out waiting for sign-in')
        print('Authenticated. Beginning image extraction.', flush=True)
        for exam_id, pid in requested:
            exam = exams[exam_id]
            folder = args.output / f'exam_{exam_id}' / f'problem_{pid}'
            folder.mkdir(parents=True, exist_ok=True)
            for sub in exam['submissions']:
                sid = sub['id']
                target = folder / f'sub_{sid}.png'
                if target.exists() and target.stat().st_size:
                    report['saved'].append([sid, pid, 'existing'])
                    continue
                try:
                    driver.get(f"{args.base_url.rstrip('/')}/exams/{exam['id']}/grade/{sid}/{pid}")
                    image = WebDriverWait(driver, 30).until(lambda d: next((i for i in d.find_elements(By.CSS_SELECTOR, 'img') if i.is_displayed() and i.size['width'] > 100 and i.size['height'] > 100 and d.execute_script('return arguments[0].complete && arguments[0].naturalWidth > 0', i)), False))
                    save_source_image(driver, image, target)
                    report['saved'].append([sid, pid, 'new'])
                except Exception as exc:
                    report['failed'].append([sid, pid, type(exc).__name__])
                finally:
                    temporary_report = args.output / 'scrape_report.json.tmp'
                    temporary_report.write_text(json.dumps(report, indent=2), encoding='utf-8')
                    temporary_report.replace(args.output / 'scrape_report.json')
            print(f"Problem {pid}: {sum(1 for x in report['saved'] if x[1] == pid)} saved, {sum(1 for x in report['failed'] if x[1] == pid)} failed", flush=True)
    finally:
        driver.quit()
        print('Browser closed.', flush=True)


if __name__ == '__main__':
    main()
