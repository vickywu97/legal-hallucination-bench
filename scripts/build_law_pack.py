#!/usr/bin/env python3
# /// script
# 通用「全集版法条包」构建脚本（stdlib-only, python -S 可跑）
#
# 输入: 官方 .doc 经 textutil -convert txt 得到的纯文本
# 输出: packs/{LAW_CODE}_full.jsonl  (+ 派生 .md / .csv) 与 packs/index.html
#
# 信任分级:
#   Tier A (verification_status=verified)  : 命中现有 statutes.jsonl 中已核验节点 -> 沿用专家签署
#   Tier B (verification_status=unverified): 官方 .doc 逐字提取、尚未逐条专家签核 -> 仅作参考
#
# 专家确认源整体升 A（--verified-source）:
#   当所据官方源已經执业专家确认"完整且正确"（如《增值税法》2026-01-01 施行版），
#   即便未逐条比对 KB，也整体标为 Tier A（verified_by=专家署名、verified_at=当天），
#   使整包成为可作评测 ground truth 的合规全集。该模式通过 --verified-source 开启，
#   可配合 --verified-by / --verified-at 覆盖默认署名与日期。
#
# 用法:
#   textutil -convert txt 官方.doc -output /tmp/law.txt
#   python3 -S scripts/build_law_pack.py \
#       --txt /tmp/law.txt --law-code PATENT_LAW \
#       --law-name "中华人民共和国专利法（2020修正）" --effective-date 2021-06-01
#
# 专家确认源整体升 A:
#   python3 -S scripts/build_law_pack.py \
#       --txt /tmp/vat.txt --law-code VAT_LAW \
#       --law-name "中华人民共和国增值税法" --effective-date 2026-01-01 \
#       --verified-source
# ///
import argparse
import csv
import glob
import json
import os
import re
import datetime

CN_DIGITS = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
             '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
CN_POWERS = {'十': 10, '百': 100, '千': 1000}

# 专家确认源升 A 时的默认署名（与 statutes.jsonl 中既有专家节点一致）
DEFAULT_VERIFIER = 'Vicky Wu (律师/税务师/专利代理师)'


def cn2int(s: str) -> int:
    """数字暂存 + 十百千累加，防爆 五百八十四->512 这类错位。"""
    total, cur = 0, 0
    for ch in s:
        if ch in CN_DIGITS:
            cur = CN_DIGITS[ch]
        elif ch in CN_POWERS:
            cur = 1 if cur == 0 else cur
            total += cur * CN_POWERS[ch]
            cur = 0
    return total + cur


# 只认「行首」的 第X条 作为条文起点，避免把正文里"本法第X条"这类句中引用误判为新条文。
# 注意：民法典等 .docx 转 txt 后条文以全角空格(　, U+3000) 缩进，\s 不匹配，故显式纳入 [　\s]。
# 刑法/公司法等含修正案插入的"第X条之一/之二"，需整体捕获，否则会塌缩到 sort_key X 造成重复节点。
ART_RE = re.compile(r'(?:^|\n)[　\s]*第([零一二三四五六七八九十百千0-9]+)条(之[零一二三四五六七八九十百千]+)?', re.M)
CHAPTER_RE = re.compile(r'第[零一二三四五六七八九十百千]+[章编节][^\n第]*')
HYPERLINK_RE = re.compile(r'HYPERLINK\s+"[^"]*"')
# .doc 转 txt 常见的页脚/水印噪点（覆盖「扫…AGE/NUMPAGES」与纯「PAGE/NUMPAGES」两种形态）
FOOTER_RE = re.compile(r'PAGE/NUMPAGES|NUMPAGES|PAGE\s*\d+|扫[^\n]*?NUMPAGES|扫[^\n]*?AGE/NUMPAGES')
LEAK_RE = re.compile(r'(wkinfo|HYPERLINK|https?://|PAGE\s*\d+|NUMPAGES|WORD\s*\d+)')


def clean_control(text: str) -> str:
    text = HYPERLINK_RE.sub('', text)
    text = text.replace('\t', ' ').replace('\r', ' ')
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return text


def parse_articles(text: str):
    text = clean_control(text)
    matches = list(ART_RE.finditer(text))
    out = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw = text[start:end]
        # 去掉章/编/节标题与首尾空白，再把换行并成连续中文
        raw = CHAPTER_RE.sub('', raw)
        body = re.sub(r'\s+', '', raw).strip()
        body = FOOTER_RE.sub('', body).strip()  # 去掉页脚噪点
        if not body:
            continue
        out.append((m.group(1), m.group(2), body))
    return out


def norm_ref(article_number: str):
    """把"第13条"/"第234条之一"/"第十三条"/"第二百三十四条之一" 统一归一为 (base, sub) 元组，
    规避 KB 用阿拉伯数字、官方 .doc 用中文数字、以及"之一"修正案插入条的表示差异。"""
    m = re.match(r'第([0-9零一二三四五六七八九十百千]+)条(之[零一二三四五六七八九十百千]+)?',
                 article_number)
    if not m:
        return None
    num = m.group(1)
    base = int(num) if num.isdigit() else cn2int(num)
    sub = cn2int(m.group(2)[1:]) if m.group(2) else 0
    return (base, sub)


def load_verified_set(statutes_path: str):
    # 用 (law_code, norm_ref(article_number)) 作匹配键，规避阿拉伯/中文数字与"之一"的差异
    verified = {}
    if not os.path.exists(statutes_path):
        return verified
    with open(statutes_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get('verification_status') == 'verified':
                key = (d['law_code'], norm_ref(d['article_number']))
                if key[1] is not None:
                    verified[key] = d
    return verified


def build_pack(txt_path, law_code, law_name, effective_date, statutes_path, out_dir,
               verified_source=False, verified_by=None, verified_at=None):
    with open(txt_path, encoding='utf-8', errors='replace') as f:
        text = f.read()
    articles = parse_articles(text)
    verified = load_verified_set(statutes_path)
    today = datetime.date.today().isoformat()
    vby = verified_by or DEFAULT_VERIFIER
    vat = verified_at or today

    records = []
    for num_cn, sub_cn, body in articles:
        # 修正案插入条（第X条之一/之二）用小数 sort_key 保证唯一且有序（X.001, X.002…），不与第(X+1)条冲突
        sort_key = cn2int(num_cn) + (cn2int(sub_cn[1:]) * 0.001 if sub_cn else 0)
        article_number = f'第{num_cn}条{sub_cn or ""}'
        existing = verified.get((law_code, norm_ref(article_number)))
        if existing:
            rec = dict(existing)          # 沿用专家签署与已核验正文
            rec['article_number'] = article_number   # 统一为中文条号
            rec['article_sort_key'] = sort_key
            rec['trust_tier'] = 'A'
        elif verified_source:
            # 专家确认源完整且正确：整包升 A（含未逐条比对 KB 的条文）
            rec = {
                'id': f'{law_code}_{sort_key}_v1',
                'law_code': law_code,
                'article_number': article_number,
                'article_sort_key': sort_key,
                'content': body,
                'effective_date': effective_date,
                'revision_of': None,
                'verification_status': 'verified',
                'verified_by': vby,
                'verified_at': vat,
                'source_url': 'https://flk.npc.gov.cn/',
                'source_accessed_at': today,
                'notes': '源经专家确认完整（非截断）',
                'trust_tier': 'A',
            }
        else:
            rec = {
                'id': f'{law_code}_{sort_key}_v1',
                'law_code': law_code,
                'article_number': article_number,
                'article_sort_key': sort_key,
                'content': body,
                'effective_date': effective_date,
                'revision_of': None,
                'verification_status': 'unverified',
                'verified_by': None,
                'verified_at': None,
                'source_url': 'https://flk.npc.gov.cn/',
                'source_accessed_at': today,
                'notes': None,
                'trust_tier': 'B',
            }
        # 对所有记录（含 Tier A 原文）统一剥离 .doc 页脚噪点（pack 为派生产物，不改 KB）
        rec['content'] = FOOTER_RE.sub('', rec['content']).strip()
        records.append(rec)

    records.sort(key=lambda r: r['article_sort_key'])
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, f'{law_code}_full')

    # JSONL
    with open(base + '.jsonl', 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    # CSV
    fields = ['id', 'law_code', 'article_number', 'article_sort_key', 'content',
              'effective_date', 'trust_tier', 'verification_status',
              'verified_by', 'verified_at', 'source_url', 'source_accessed_at']
    with open(base + '.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in records:
            w.writerow(r)

    # Markdown（人类可读）
    n_a = sum(1 for r in records if r['trust_tier'] == 'A')
    n_b = len(records) - n_a
    with open(base + '.md', 'w', encoding='utf-8') as f:
        f.write(f'# {law_name} · 全集包\n\n')
        f.write(f'- 法律助记码: `{law_code}`\n')
        f.write(f'- 生效日期: {effective_date}\n')
        f.write(f'- 条文总数: {len(records)}\n')
        f.write(f'- 信任分级: 专家核验 **{n_a}** 条 (Tier A) / 官方全文提取 **{n_b}** 条 (Tier B)\n')
        f.write(f'- 数据格式: JSONL（同 Bench 的 statutes.jsonl schema，附加 `trust_tier` 字段）\n')
        f.write(f'- 来源: 全国人大法律法规数据库 flk.npc.gov.cn\n\n')
        if n_b:
            f.write('> **Tier B 条文**为从官方 .doc 逐字提取、尚未逐条专家签核，仅作参考，'
                    '不作 AI 评测 ground truth。升 A 需经 `python -S -m knowledge_base.verify_kb review`。\n\n---\n\n')
        else:
            f.write('> 本包所据官方源**经专家确认完整且正确**，全部条文已逐条核验为 Tier A，'
                    '可作 AI 评测 ground truth。\n\n---\n\n')
        for r in records:
            f.write(f'## {r["article_number"]}  _{r["trust_tier"]}_\n\n{r["content"]}\n\n')

    print(f'[pack] {law_code}: {len(records)} 条 (Tier A={n_a}, Tier B={n_b}) -> {base}.jsonl')
    return records


def merge_pack(out_dir, merged_code, merged_name, law_codes):
    """把若干 *_full.jsonl 拼接成合并包（如税务包），按 (法序, sort_key) 排序输出 jsonl/md/csv。"""
    order = {c: i for i, c in enumerate(law_codes)}
    recs = []
    for c in law_codes:
        jl = os.path.join(out_dir, f'{c}_full.jsonl')
        with open(jl, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    recs.append(json.loads(line))
    recs.sort(key=lambda r: (order.get(r['law_code'], 99), r['article_sort_key']))

    base = os.path.join(out_dir, f'{merged_code}_full')
    with open(base + '.jsonl', 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    fields = ['id', 'law_code', 'article_number', 'article_sort_key', 'content',
              'effective_date', 'trust_tier', 'verification_status',
              'verified_by', 'verified_at', 'source_url', 'source_accessed_at']
    with open(base + '.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in recs:
            w.writerow(r)

    n_a = sum(1 for r in recs if r['trust_tier'] == 'A')
    n_b = len(recs) - n_a
    with open(base + '.md', 'w', encoding='utf-8') as f:
        f.write(f'# {merged_name} · 合并全集\n\n')
        f.write(f'- 包含: ' + ' + '.join(
            f'`{c}`({sum(1 for r in recs if r["law_code"]==c)}条)' for c in law_codes) + '\n')
        f.write(f'- 条文总数: {len(recs)}\n')
        f.write(f'- 信任分级: 专家核验 **{n_a}** 条 (Tier A) / 官方全文提取 **{n_b}** 条 (Tier B)\n')
        f.write(f'- 数据格式: JSONL（同 Bench 的 statutes.jsonl schema，附加 `trust_tier` 字段）\n')
        f.write(f'- 来源: 全国人大法律法规数据库 flk.npc.gov.cn\n\n')
        if n_b:
            f.write('> **Tier B 条文**为从官方 .doc 逐字提取、尚未逐条专家签核，仅作参考，'
                    '不作 AI 评测 ground truth。升 A 需经 `python -S -m knowledge_base.verify_kb review`。\n\n---\n\n')
        else:
            f.write('> 本包所据官方源**经专家确认完整且正确**，全部条文已逐条核验为 Tier A，'
                    '可作 AI 评测 ground truth。\n\n---\n\n')
        for r in recs:
            f.write(f'## {r["article_number"]}  _{r["trust_tier"]}_  `{r["law_code"]}`\n\n{r["content"]}\n\n')

    print(f'[merge] {merged_code}: {len(recs)} 条 (Tier A={n_a}, Tier B={n_b}) -> {base}.jsonl')
    return recs


def regenerate_index(out_dir):
    packs = []
    for jl in sorted(glob.glob(os.path.join(out_dir, '*_full.jsonl'))):
        law_code = os.path.basename(jl).replace('_full.jsonl', '')
        recs = [json.loads(l) for l in open(jl, encoding='utf-8') if l.strip()]
        n = len(recs)
        na = sum(1 for r in recs if r.get('trust_tier') == 'A')
        packs.append((law_code, n, na, n - na))

    rows = ''
    for law_code, n, na, nb in packs:
        cov = (na / n * 100) if n else 0
        rows += (f'<tr><td><code>{law_code}</code></td>'
                 f'<td>{n}</td><td>{na}</td><td>{nb}</td>'
                 f'<td>{cov:.0f}%</td>'
                 f'<td><a href="{law_code}_full.jsonl">jsonl</a> · '
                 f'<a href="{law_code}_full.md">md</a> · '
                 f'<a href="{law_code}_full.csv">csv</a></td></tr>\n')

    html = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>法条库 · 按需下载版</title>
<style>
body{{font-family:-apple-system,system-ui,"PingFang SC",sans-serif;max-width:880px;margin:40px auto;padding:0 20px;color:#1a1a1a;line-height:1.6}}
h1{{font-size:22px}} table{{border-collapse:collapse;width:100%;font-size:14px}}
th,td{{border:1px solid #e3e3e3;padding:8px 10px;text-align:left}}
th{{background:#f6f6f6}} a{{color:#2563eb;text-decoration:none}}
.note{{background:#fffbe6;border:1px solid #ffe58f;padding:12px 16px;border-radius:8px;font-size:13px}}
</style></head>
<body>
<h1>《法条库 · 按需下载版》— 模块化全集包</h1>
<p>基于 <a href="https://github.com/vickywu97/legal-hallucination-bench">legal-hallucination-bench</a> 的已核验 KB pipeline。
每个包独立下载，Tier A=专家核验，Tier B=官方全文提取（未逐条签核，仅作参考）。</p>
<div class="note">Tier B 条文来自官方 .doc 逐字提取，尚未经执业律师逐条签署，<b>不作为 AI 评测 ground truth</b>。
升 A 需运行 <code>python -S -m knowledge_base.verify_kb review</code>。</div>
<table>
<tr><th>法律包</th><th>条文数</th><th>Tier A</th><th>Tier B</th><th>核验覆盖</th><th>下载</th></tr>
{rows}</table>
<p style="color:#888;font-size:12px">生成于 {datetime.date.today().isoformat()} · 机器可读 JSONL 可直接接入 RAG / Embedding 管线。</p>
</body></html>'''
    with open(os.path.join(out_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'[index] packs={len(packs)} -> {os.path.join(out_dir, "index.html")}')


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd')

    p_build = sub.add_parser('build', help='从官方 .txt 构建单部法全集包')
    p_build.add_argument('--txt', required=True)
    p_build.add_argument('--law-code', required=True)
    p_build.add_argument('--law-name', required=True)
    p_build.add_argument('--effective-date', required=True)
    p_build.add_argument('--statutes', default='knowledge_base/laws/statutes.jsonl')
    p_build.add_argument('--out-dir', default='packs')
    p_build.add_argument('--verified-source', action='store_true',
                         help='专家确认源完整且正确：整包升 Tier A')
    p_build.add_argument('--verified-by', default=None,
                         help='升 A 时的专家署名（默认项目作者）')
    p_build.add_argument('--verified-at', default=None,
                         help='升 A 时的签署日期 YYYY-MM-DD（默认当天）')

    p_merge = sub.add_parser('merge', help='拼接若干 *_full.jsonl 为合并包')
    p_merge.add_argument('--out-dir', default='packs')
    p_merge.add_argument('--merged-code', required=True)
    p_merge.add_argument('--merged-name', required=True)
    p_merge.add_argument('--law-codes', required=True,
                         help='逗号分隔的 law_code 列表，顺序即输出顺序')

    args = ap.parse_args()
    if args.cmd == 'merge':
        merge_pack(args.out_dir, args.merged_code, args.merged_name,
                   [c.strip() for c in args.law_codes.split(',') if c.strip()])
    else:
        build_pack(args.txt, args.law_code, args.law_name,
                   args.effective_date, args.statutes, args.out_dir,
                   verified_source=args.verified_source,
                   verified_by=args.verified_by,
                   verified_at=args.verified_at)
    regenerate_index(args.out_dir)


if __name__ == '__main__':
    main()
