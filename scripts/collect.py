import json, re, urllib.request, concurrent.futures, os
from html.parser import HTMLParser
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
path = Path(__file__).resolve().parents[1] / 'sales.json'
data = json.loads(path.read_text(encoding='utf-8'))
now = datetime.now(KST)

if os.environ.get('BACKUP_RUN') == '1':
    if all(s.get('last_success_at', '').startswith(now.date().isoformat())
           and s.get('collection_status') != 'error' for s in data['shops']):
        print('All shops already collected today')
        raise SystemExit(0)

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'): self.skip += 1
        if tag == 'img':
            alt = dict(attrs).get('alt','')
            if alt: self.parts.append(alt)
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.skip = max(0,self.skip-1)
    def handle_data(self, value):
        if not self.skip and value.strip(): self.parts.append(value.strip())

def collect(shop):
    s = dict(shop)
    s['checked_at'] = now.isoformat()
    url = s.get('url')
    if not url:
        s['collection_status'] = 'error'
        return s
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'KnitSaleMonitor/1.0 (public promotion check)'})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read(2000000)
            encoding = r.headers.get_content_charset() or 'utf-8'
        page = Page()
        page.feed(raw.decode(encoding, errors='replace'))
        candidates = []
        for line in page.parts:
            line = re.sub(r'\s+', ' ', line).strip()
            if len(line) <= 240 and re.search(r'블랙\s*프라이데이|블프|할인|세일|특가|SALE|쿠폰',line,re.I):
                if line not in candidates: candidates.append(line)
        s['status'] = 'unknown'
        s.pop('end', None)
        s['last_success_at'] = now.isoformat()
        s['description'] = ('행사 후보 · 기간 및 적용 조건 확인 필요: ' + ' / '.join(candidates[:4])) if candidates else '홈페이지에서 행사 문구를 찾지 못함 · 할인 여부 미확인'
        s['collection_status'] = 'candidate' if candidates else 'no_evidence'
    except Exception as e:
        s['collection_status'] = 'error'
        print(s['name'], type(e).__name__)
    return s

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    data['shops'] = list(pool.map(collect,data['shops']))
failed = sum(s.get('collection_status') == 'error' for s in data['shops'])
data['last_attempt_at'] = now.isoformat()
data['collection_status'] = 'error' if failed == len(data['shops']) else 'partial' if failed else 'success'
if failed == 0:
    data['last_success_at'] = now.isoformat()
data['updated'] = now.strftime('%Y-%m-%d %H:%M KST')
data['source'] = '공식 홈페이지 자동 탐색 · 행사 후보는 미확정'
tmp = path.with_suffix('.tmp')
tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
tmp.replace(path)
