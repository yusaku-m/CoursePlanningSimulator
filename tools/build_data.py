"""高専Webシラバスから科目一覧を取得し、入学年度ごとのカリキュラムを data.js に書き出す。

使い方: python tools/build_data.py
入学年度 E の g 年生の科目は、開講年度 min(E+g-1, LATEST_YEAR) の科目一覧から取る。
"""
import json
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

SCHOOL_ID = 39          # 香川高専
DEPARTMENT_ID = 31      # 機械工学科（2019年度以降入学者）
FIRST_YEAR = 2019
LATEST_YEAR = 2026
COHORTS = range(2019, 2026)
URL = 'https://syllabus.kosen-k.go.jp/Pages/PublicSubjects?school_id={s}&department_id={d}&year={y}&lang=ja'
OUT = Path(__file__).resolve().parent.parent / 'data.js'


class SubjectTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'table' and a.get('id') == 'sytablenc':
            self.in_table = True
        if not self.in_table:
            return
        if tag == 'tr':
            self.row = []
        elif tag == 'td':
            self.cell = {'text': '', 'attrs': a}
        elif tag == 'a' and self.cell is not None and 'subject_code' in (a.get('href') or ''):
            self.cell['href'] = a['href']
        elif tag == 'span' and self.cell is not None and 'mcc-hide' in (a.get('class') or ''):
            self.cell['skip'] = True

    def handle_endtag(self, tag):
        if not self.in_table:
            return
        if tag == 'span' and self.cell is not None:
            self.cell.pop('skip', None)
        elif tag == 'td' and self.cell is not None:
            self.cell['text'] = re.sub(r'\s+', ' ', self.cell['text']).strip()
            self.row.append(self.cell)
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == 'table':
            self.in_table = False

    def handle_data(self, data):
        if self.cell is not None and not self.cell.get('skip'):
            self.cell['text'] += data


def fetch(year):
    url = URL.format(s=SCHOOL_ID, d=DEPARTMENT_ID, y=year)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as r:
        return r.read().decode('utf-8')


def parse(html):
    p = SubjectTable()
    p.feed(html)
    subjects = []
    for r in p.rows:
        if len(r) < 28 or 'href' not in r[2]:
            continue
        # 1年1Q〜5年4Q の20列。colspan=2 のセルは2クォーター分、display:none のセルは結合で隠れた側
        q = [None] * 20
        for i, c in enumerate(r[6:26]):
            if 'display:none' in (c['attrs'].get('style') or '').replace(' ', ''):
                continue
            for k in range(int(c['attrs'].get('colspan') or 1)):
                if i + k < 20 and c['text']:
                    q[i + k] = c['text']
        name = r[2]['text']
        h = len(name) // 2
        if len(name) % 2 == 1 and name[:h] == name[h + 1:]:
            name = name[:h]
        subjects.append({
            'cat': r[0]['text'], 'req': r[1]['text'], 'name': name,
            'kind': r[4]['text'], 'cr': int(r[5]['text'] or 0), 'q': q,
            'code': re.search(r'subject_code=(\w+)', r[2]['href']).group(1),
            # シラバスURLの year は開講年度ではなく、その科目を履修する学年の入学年度
            'syl_year': int(re.search(r'year=(\d+)', r[2]['href']).group(1)),
        })
    return subjects


def main():
    pages = {y: parse(fetch(y)) for y in range(FIRST_YEAR, LATEST_YEAR + 1)}
    out = {}
    for e in COHORTS:
        rows = []
        for g in range(1, 6):
            y = min(e + g - 1, LATEST_YEAR)
            for s in pages[y]:
                qs = s['q'][(g - 1) * 4:g * 4]
                if not any(qs):
                    continue
                hours = [0] * 4
                intensive = False
                for k, v in enumerate(qs):
                    if v is None:
                        continue
                    if re.fullmatch(r'\d+(\.\d+)?', v):
                        hours[k] = float(v) if '.' in v else int(v)
                    else:
                        intensive = True  # 「集中講義」など
                first, second = any(hours[:2]), any(hours[2:])
                if intensive and not (first or second):
                    term = '集中'
                elif first and second:
                    term = '通年'
                else:
                    term = '前期' if first else '後期'
                # [学年, 開講年度, 区分(0一般/1専門), 必修(1)/選択(0), 科目名, 単位種別(0履修/1学修), 単位数, 週時数[1Q..4Q], 開講期, 科目コード, シラバスURLのyear]
                rows.append([g, y, 0 if s['cat'] == '一般' else 1, 1 if s['req'] == '必修' else 0, s['name'],
                             1 if s['kind'] == '学修単位' else 0, s['cr'], hours, term, s['code'], s['syl_year']])
        out[str(e)] = rows
    OUT.write_text('const DATA=' + json.dumps(out, ensure_ascii=False, separators=(',', ':')) + ';\n', encoding='utf-8')
    print(f'wrote {OUT}')


if __name__ == '__main__':
    main()
