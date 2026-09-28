import os
import re
import time

import requests


HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
}

CATEGORY_MARKERS = {
    'клининг': ('клининг', 'уборк', 'мойк', 'химчист'),
    'металлообработка': (
        'металлообработ', 'резк', 'гибк', 'токар', 'фрезер', 'детал',
    ),
    'монтаж': ('монтаж', 'демонтаж', 'металлоконструк'),
    'металл': (
        'металлопрокат', 'арматур', 'швеллер', 'лист', 'трубн', 'прокат',
    ),
}


def safe_filename(name: str) -> str:
    name = (name or 'file').replace('\\', '/')
    name = os.path.basename(name)
    name = re.sub(r'[^\wа-яА-ЯёЁ.\- ]+', '_', name, flags=re.IGNORECASE)
    name = name.strip(' ._')
    return (name[:120] if name else 'file')


def guess_category(title: str, hint: str = '') -> str:
    blob = f'{hint} {title}'.lower()
    for category, markers in CATEGORY_MARKERS.items():
        if any(marker in blob for marker in markers):
            return category
    if hint.strip():
        return hint.strip()[:40]
    return 'разное'


def _get_json(url, timeout=20):
    try:
        response = requests.get(url, timeout=timeout, headers=HEADERS)
    except requests.RequestException as error:
        raise ConnectionError(f'Bidzaar не ответил: {error}') from error
    if response.status_code != 200:
        raise ConnectionError(f'Bidzaar код {response.status_code}')
    return response.json()


def _resolve_procedure_id(maybe_id: str) -> str:
    common = (
        f'https://bidzaar.com/api/process/light/procedures/{maybe_id}/common'
    )
    try:
        response = requests.get(common, timeout=20, headers=HEADERS)
    except requests.RequestException as error:
        raise ConnectionError(f'Bidzaar не ответил: {error}') from error
    if response.status_code == 200:
        return maybe_id
    info = _get_json(
        f'https://bidzaar.com/api/process/aggregator/tenders/{maybe_id}'
    )
    procedure_id = info.get('procedureId')
    if not procedure_id:
        raise ConnectionError('У закупки нет procedureId')
    return procedure_id


def parse_bidzaar(url):
    found = re.search(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
        url,
    )
    if not found:
        raise ValueError('В ссылке нет id закупки')
    raw_id = found.group()
    procedure_id = _resolve_procedure_id(raw_id)
    data = _get_json(
        f'https://bidzaar.com/api/process/light/procedures/{procedure_id}/common'
    )
    title = data.get('name') or 'без названия'
    return {
        'id': procedure_id,
        'title': title,
        'url': f'https://bidzaar.com/app/process/light/{procedure_id}',
        'files': data.get('files') or [],
        'category': guess_category(title),
        'law': 'коммерция',
        'price': '',
    }


def search_bidzaar(query, limit=5):
    query = (query or '').strip()
    if not query:
        return []
    api = 'https://bidzaar.com/api/process/aggregator/tenders/filter'
    try:
        response = requests.get(
            api,
            params={'search': query},
            timeout=20,
            headers=HEADERS,
        )
    except requests.RequestException as error:
        raise ConnectionError(f'Bidzaar не ответил: {error}') from error
    if response.status_code != 200:
        raise ConnectionError(f'Bidzaar код {response.status_code}')
    items = response.json().get('items') or []
    result = []
    for item in items[:limit]:
        procedure_id = item.get('procedureId') or item.get('id')
        if not procedure_id:
            continue
        title = item.get('name') or 'без названия'
        result.append({
            'id': procedure_id,
            'title': title,
            'url': f'https://bidzaar.com/app/process/light/{procedure_id}',
            'category': guess_category(title, query),
            'law': 'коммерция',
            'price': '',
        })
    return result


def download_bidzaar_file(file_id, folder, filename):
    url = 'https://bidzaar.com/api/filestorage/files/download/' + file_id
    try:
        response = requests.get(url, timeout=30, headers=HEADERS)
    except requests.RequestException as error:
        raise ConnectionError(f'файл не скачался: {error}') from error
    if response.status_code != 200:
        raise ConnectionError(f'файл не скачался, код {response.status_code}')
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, safe_filename(filename))
    with open(path, 'wb') as handle:
        handle.write(response.content)
    return path


def download_bidzaar_files(files, folder):
    saved = []
    for file in files:
        file_id = file.get('fileId') or file.get('id')
        if not file_id:
            continue
        name = file.get('name') or 'file'
        ext = file.get('extension') or ''
        filename = f'{name}.{ext}' if ext else name
        path = download_bidzaar_file(file_id, folder, filename)
        saved.append(path)
        time.sleep(1)
    return saved
