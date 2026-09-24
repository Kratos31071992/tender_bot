import os
import re
import time
import requests

HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
}


def _get_json(url, timeout=20):
    try:
        response = requests.get(url, timeout=timeout, headers=HEADERS)
    except requests.RequestException as error:
        raise ConnectionError(f'Bidzaar не ответил: {error}') from error
    if response.status_code != 200:
        raise ConnectionError(f'Bidzaar код {response.status_code}')
    return response.json()


def _resolve_procedure_id(maybe_id: str) -> str:
    common = f'https://bidzaar.com/api/process/light/procedures/{maybe_id}/common'
    try:
        response = requests.get(common, timeout=20, headers=HEADERS)
    except requests.RequestException as error:
        raise ConnectionError(f'Bidzaar не ответил: {error}') from error
    if response.status_code == 200:
        return maybe_id
    info = _get_json(f'https://bidzaar.com/api/process/aggregator/tenders/{maybe_id}')
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
    return {
        'id': procedure_id,
        'title': data.get('name') or 'без названия',
        'url': f'https://bidzaar.com/app/process/light/{procedure_id}',
        'files': data.get('files') or [],
    }
    

def search_bidzaar(query, limit=5):
    query = (query or '').strip()
    if not query:
        return []
    api = 'https://bidzaar.com/api/process/aggregator/tenders/filter'
    try:
        data = requests.get(api, params={'search': query}, timeout=20).json()
    except requests.RequestException:
        raise ConnectionError('Bidzaar не ответил')
    items = data.get('items') or []
    result = []
    for item in items[:limit]:
        procedure_id = item.get('procedureId') or item.get('id')
        if not procedure_id:
            continue
        result.append({
            'id': procedure_id,
            'title': item.get('name') or 'без названия',
            'url': f'https://bidzaar.com/app/process/light/{procedure_id}',
        })
    return result





def download_bidzaar_file(file_id, folder, filename):
    url = 'https://bidzaar.com/api/filestorage/files/download/' + file_id
    response = requests.get(url, timeout=30)
    if response.status_code != 200:
     raise ConnectionError('файл с Bidzaar не скачался')
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)   
    with open(path, 'wb') as f:  
     f.write(response.content)
     
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