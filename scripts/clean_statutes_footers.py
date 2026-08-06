#!/usr/bin/env python3
# /// script
# 一次性清理 statutes.jsonl 中，从官方 .doc 导入时残留的页脚/水印噪点
# （如 "扫一扫，手机阅读更方便…PAGE/NUMPAGES"）。
#
# 设计原则:
#   - 复用 build_law_pack.FOOTER_RE 的同一套清洗规则，避免两套正则漂移。
#   - 对所有节点幂等应用：仅真正含噪点的节点会被改写，其余字节不变。
#   - 不改 verification_status / verified_by 等签署字段（只修 content 脏数据）。
#   - statutes.jsonl 没有 content_hash 字段，清洗不会破坏 verify_kb 完整性。
#
# 用法:
#   python3 -S scripts/clean_statutes_footers.py --dry-run
#   python3 -S scripts/clean_statutes_footers.py
# ///
import argparse
import json
import os
import re
import sys

# 与 scripts/build_law_pack.py 中的 FOOTER_RE 保持一致（doc 转 txt 页脚/水印噪点）
FOOTER_RE = re.compile(
    r'PAGE/NUMPAGES|NUMPAGES|PAGE\s*\d+|'
    r'扫[^\n]*?NUMPAGES|扫[^\n]*?AGE/NUMPAGES'
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--statutes', default='knowledge_base/laws/statutes.jsonl')
    ap.add_argument('--dry-run', action='store_true',
                    help='只报告将被改写的节点，不写文件')
    args = ap.parse_args()

    path = args.statutes
    lines = open(path, encoding='utf-8').read().splitlines()
    out = []
    changed = []
    for ln in lines:
        if not ln.strip():
            out.append(ln)
            continue
        d = json.loads(ln)
        new = FOOTER_RE.sub('', d['content']).strip()
        if new != d['content']:
            changed.append((d['law_code'], d['article_number'],
                            d['content'][-48:], new[-48:]))
            d['content'] = new
        out.append(json.dumps(d, ensure_ascii=False))

    if args.dry_run:
        print(f'[dry-run] 将被改写的节点: {len(changed)}')
        for c in changed:
            print(f'  {c[0]} {c[1]}')
            print(f'     - {c[2]!r}')
            print(f'     + {c[3]!r}')
        return

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')
    print(f'[clean] 改写 {len(changed)} 个节点 -> {path}')
    for c in changed:
        print(f'  {c[0]} {c[1]}')
        print(f'     - {c[2]!r}')
        print(f'     + {c[3]!r}')


if __name__ == '__main__':
    main()
