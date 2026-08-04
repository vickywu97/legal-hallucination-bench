"""Statute curation pipeline (Week 2 — quality gate #1).

This is the single source of truth for ``statutes.jsonl``. Legal experts paste
article text from flk.npc.gov.cn into ``SEED`` (NEVER retype — pasting avoids
transcription errors), then run::

    python -S -m knowledge_base.build_statute build     # regenerate statutes.jsonl
    python -S -m knowledge_base.build_statute validate  # run the integrity gate
    python -S -m knowledge_base.build_statute coverage  # print the coverage report

The same ``validate()`` is imported by ``tests/test_kb_integrity.py`` so the CI
and the CLI can never drift.

Source-of-truth split
---------------------
* ``SEED`` (below) is **LLM-authored scaffold** — article text drafted for
  structure/engine testing. It is NOT authoritative and is emitted as
  ``verification_status: "unverified"``.
* ``verifications.json`` is the **human verification ledger** (the expert's
  signature). It is the only thing that can flip a node to ``"verified"``.
  ``verify_kb.py`` is the tool that walks you through it.

Design notes
------------
* Ids are derived, never hand-written: ``{law_code}_{sort_key}_vN`` where N is
  the 1-based index within ``(law_code, sort_key)`` ordered by ``effective_date``.
* ``revision_of`` may be given as a literal node id (e.g. ``COMPANY_LAW_13_v1``)
  or as an article-number reference (e.g. ``第13条``); the latter is resolved to
  the generated id of that article (used for relocations across article numbers,
  e.g. old art.13 -> new art.10). For same-number amendments it is inferred
  automatically from the previous version in the group.
* Every node carries ``source_url`` (flk.npc.gov.cn) + ``source_accessed_at`` so
  the KB is a traceable curated snapshot.
"""
from __future__ import annotations

import os
import re
import sys
import json
import argparse
from collections import defaultdict, Counter
from typing import Dict, List, Optional, Tuple

KB_ROOT = os.path.dirname(os.path.abspath(__file__))
LAWS_DIR = os.path.join(KB_ROOT, "laws")
INDEX_FILE = os.path.join(LAWS_DIR, "laws_index.json")
STATUTES_FILE = os.path.join(LAWS_DIR, "statutes.jsonl")
# Human verification ledger — the ONLY authority for "verified". The LLM that
# authors the SEED scaffold is NOT an authority, so this file is authored by a
# legal expert (you), never by generation. Kept separate from SEED so `build`
# can regenerate statutes.jsonl without ever losing a human verdict.
VERIFICATIONS_FILE = os.path.join(KB_ROOT, "verifications.json")

LAW_SOURCES = {
    "CIVIL_CODE": "https://flk.npc.gov.cn/detail2.html?ZmY4MDgxODE3OTZhNjM2YTAxNzc4MmYyMGRiYTk3ZWY%3D",
    "COMPANY_LAW": "https://flk.npc.gov.cn/detail2.html?ZmY4MDgxODE4MjFkMzIxNzAwMTcxZjI5YmYwZTFhNzA%3D",
    "CRIMINAL_LAW": "https://flk.npc.gov.cn/detail2.html?ZmY4MDgxODE3ZWY1YjA1MDAxNzkxZjBlYmZlYjgwYjU%3D",
    "PATENT_LAW": "https://flk.npc.gov.cn/",
    "TAX_ADMIN_LAW": "https://flk.npc.gov.cn/",
}
DEFAULT_ACCESSED_AT = "2026-07-31"

_ID_RE = re.compile(r"^[A-Z_]+_\d+_v\d+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --------------------------------------------------------------------------- #
# Curated seed — paste article text here; do NOT retype. Each entry:
#   law_code, article_number, content, effective_date,
#   revision_of (optional: literal id OR "第N条" for a relocation),
#   notes (optional)
# --------------------------------------------------------------------------- #
SEED: List[dict] = [
    # ===================== 民法典 CIVIL_CODE (2021-01-01) =====================
    {"law_code": "CIVIL_CODE", "article_number": "第1条",
     "content": "为了保护民事主体的合法权益，调整民事关系，维护社会和经济秩序，适应中国特色社会主义发展要求，弘扬社会主义核心价值观，根据宪法，制定本法。",
     "effective_date": "2021-01-01", "notes": "立法目的"},
    {"law_code": "CIVIL_CODE", "article_number": "第7条",
     "content": "民事主体从事民事活动，应当遵循诚信原则，秉持诚实，恪守承诺。",
     "effective_date": "2021-01-01", "notes": "诚信原则"},
    {"law_code": "CIVIL_CODE", "article_number": "第8条",
     "content": "民事主体从事民事活动，不得违反法律，不得违背公序良俗。",
     "effective_date": "2021-01-01", "notes": "公序良俗"},
    {"law_code": "CIVIL_CODE", "article_number": "第111条",
     "content": "自然人的个人信息受法律保护。任何组织或者个人需要获取他人个人信息的，应当依法取得并确保信息安全，不得非法收集、使用、加工、传输他人个人信息，不得非法买卖、提供或者公开他人个人信息。",
     "effective_date": "2021-01-01", "notes": "个人信息保护"},
    {"law_code": "CIVIL_CODE", "article_number": "第143条",
     "content": "具备下列条件的民事法律行为有效：（一）行为人具有相应的民事行为能力；（二）意思表示真实；（三）不违反法律、行政法规的强制性规定，不违背公序良俗。",
     "effective_date": "2021-01-01", "notes": "法律行为有效要件"},
    {"law_code": "CIVIL_CODE", "article_number": "第144条",
     "content": "无民事行为能力人实施的民事法律行为无效。",
     "effective_date": "2021-01-01", "notes": "无行为能力无效"},
    {"law_code": "CIVIL_CODE", "article_number": "第146条",
     "content": "行为人与相对人以虚假的意思表示实施的民事法律行为无效。以虚假的意思表示隐藏的民事法律行为的效力，依照有关法律规定处理。",
     "effective_date": "2021-01-01", "notes": "虚假表示无效"},
    {"law_code": "CIVIL_CODE", "article_number": "第147条",
     "content": "基于重大误解实施的民事法律行为，行为人有权请求人民法院或者仲裁机构予以撤销。",
     "effective_date": "2021-01-01", "notes": "重大误解可撤销"},
    {"law_code": "CIVIL_CODE", "article_number": "第148条",
     "content": "一方以欺诈手段，使对方在违背真实意思的情况下实施的民事法律行为，受欺诈方有权请求人民法院或者仲裁机构予以撤销。",
     "effective_date": "2021-01-01", "notes": "欺诈可撤销"},
    {"law_code": "CIVIL_CODE", "article_number": "第150条",
     "content": "一方或者第三人以胁迫手段，使对方在违背真实意思的情况下实施的民事法律行为，受胁迫方有权请求人民法院或者仲裁机构予以撤销。",
     "effective_date": "2021-01-01", "notes": "胁迫可撤销"},
    {"law_code": "CIVIL_CODE", "article_number": "第153条",
     "content": "违反法律、行政法规的强制性规定的民事法律行为无效。但是，该强制性规定不导致该民事法律行为无效的除外。违背公序良俗的民事法律行为无效。",
     "effective_date": "2021-01-01", "notes": "违反强制规定/公序良俗无效"},
    {"law_code": "CIVIL_CODE", "article_number": "第157条",
     "content": "民事法律行为无效、被撤销或者确定不发生效力后，行为人因该行为取得的财产，应当予以返还；不能返还或者没有必要返还的，应当折价补偿。有过错的一方应当赔偿对方由此所受到的损失；各方都有过错的，应当各自承担相应的责任。法律另有规定的，依照其规定。",
     "effective_date": "2021-01-01", "notes": "无效/撤销的法律后果"},
    {"law_code": "CIVIL_CODE", "article_number": "第509条",
     "content": "当事人应当按照约定全面履行自己的义务。当事人应当遵循诚信原则，根据合同的性质、目的和交易习惯履行通知、协助、保密等义务。当事人在履行合同过程中，应当避免浪费资源、污染环境和破坏生态。",
     "effective_date": "2021-01-01", "notes": "全面履行与诚信附随义务"},
    {"law_code": "CIVIL_CODE", "article_number": "第577条",
     "content": "当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任。",
     "effective_date": "2021-01-01", "notes": "违约责任（整合原《合同法》第107条）"},
    {"law_code": "CIVIL_CODE", "article_number": "第584条",
     "content": "当事人一方不履行合同义务或者履行合同义务不符合约定，造成对方损失的，损失赔偿额应当相当于因违约所造成的损失，包括合同履行后可以获得的利益；但是，不得超过违约一方订立合同时预见到或者应当预见到的因违约可能造成的损失。",
     "effective_date": "2021-01-01", "notes": "损害赔偿可预见规则（整合原《合同法》第113条）"},
    {"law_code": "CIVIL_CODE", "article_number": "第588条",
     "content": "当事人既约定违约金，又约定定金的，一方违约时，对方可以选择适用违约金或者定金条款。定金不足以弥补一方违约造成的损失的，对方可以请求赔偿超过定金数额的损失。",
     "effective_date": "2021-01-01", "notes": "定金与违约金择一适用"},
    {"law_code": "CIVIL_CODE", "article_number": "第1165条",
     "content": "行为人因过错侵害他人民事权益造成损害的，应当承担侵权责任。依照法律规定推定行为人有过错，其不能证明自己没有过错的，应当承担侵权责任。",
     "effective_date": "2021-01-01", "notes": "过错责任原则（整合原《侵权责任法》第6条）"},
    {"law_code": "CIVIL_CODE", "article_number": "第1166条",
     "content": "行为人造成他人民事权益损害，不论行为人有无过错，法律规定应当承担侵权责任的，依照其规定。",
     "effective_date": "2021-01-01", "notes": "无过错责任（整合原《侵权责任法》第7条）"},
    {"law_code": "CIVIL_CODE", "article_number": "第1167条",
     "content": "侵权行为危及他人人身、财产安全的，被侵权人有权请求侵权人承担停止侵害、排除妨碍、消除危险等侵权责任。",
     "effective_date": "2021-01-01", "notes": "危险预防请求权"},
    {"law_code": "CIVIL_CODE", "article_number": "第1188条",
     "content": "无民事行为能力人、限制民事行为能力人造成他人损害的，由监护人承担侵权责任。监护人尽到监护职责的，可以减轻其侵权责任。",
     "effective_date": "2021-01-01", "notes": "监护人责任"},
    {"law_code": "CIVIL_CODE", "article_number": "第1191条",
     "content": "用人单位的工作人员因执行工作任务造成他人损害的，由用人单位承担侵权责任。用人单位承担侵权责任后，可以向有故意或者重大过失的工作人员追偿。劳务派遣期间，被派遣的工作人员因执行工作任务造成他人损害的，由接受劳务派遣的用工单位承担侵权责任；劳务派遣单位有过错的，承担相应的责任。",
     "effective_date": "2021-01-01", "notes": "用人单位侵权"},
    {"law_code": "CIVIL_CODE", "article_number": "第1192条",
     "content": "个人之间形成劳务关系，提供劳务一方因劳务造成他人损害的，由接受劳务一方承担侵权责任。接受劳务一方承担侵权责任后，可以向有故意或者重大过失的提供劳务一方追偿。提供劳务一方因劳务受到损害的，根据双方各自的过错承担相应的责任。",
     "effective_date": "2021-01-01", "notes": "个人劳务侵权"},
    {"law_code": "CIVIL_CODE", "article_number": "第1198条",
     "content": "宾馆、商场、银行、车站、机场、体育场馆、娱乐场所等经营场所、公共场所的经营者、管理者或者群众性活动的组织者，未尽到安全保障义务，造成他人损害的，应当承担侵权责任。",
     "effective_date": "2021-01-01", "notes": "安全保障义务"},
    {"law_code": "CIVIL_CODE", "article_number": "第1043条",
     "content": "家庭应当树立优良家风，弘扬家庭美德，重视家庭文明建设。夫妻应当互相忠实，互相尊重，互相关爱；家庭成员应当敬老爱幼，互相帮助，维护平等、和睦、文明的婚姻家庭关系。",
     "effective_date": "2021-01-01", "notes": "夫妻忠实义务"},
    {"law_code": "CIVIL_CODE", "article_number": "第1064条",
     "content": "夫妻双方共同签名或者夫妻一方事后追认等共同意思表示所负的债务，以及夫妻一方在婚姻关系存续期间以个人名义为家庭日常生活需要所负的债务，属于夫妻共同债务。",
     "effective_date": "2021-01-01", "notes": "夫妻共同债务"},
    {"law_code": "CIVIL_CODE", "article_number": "第1254条",
     "content": "禁止从建筑物中抛掷物品。从建筑物中抛掷物品或者从建筑物上坠落的物品造成他人损害的，由侵权人依法承担侵权责任；经调查难以确定具体侵权人的，除能够证明自己不是侵权人的外，由可能加害的建筑物使用人给予补偿。",
     "effective_date": "2021-01-01", "notes": "高空抛物"},
    {"law_code": "CIVIL_CODE", "article_number": "第1182条",
     "content": "侵害他人人身权益造成财产损失的，按照被侵权人因此受到的损失或者侵权人因此获得的利益赔偿；被侵权人因此受到的损失以及侵权人因此获得的利益难以确定，被侵权人和侵权人就赔偿数额协商不一致，向人民法院提起诉讼的，由人民法院根据实际情况确定赔偿数额。",
     "effective_date": "2021-01-01", "notes": "侵害人身权益财产损失赔偿（原《侵权责任法》第20条）"},

    # ===================== 公司法 COMPANY_LAW =====================
    # 旧法以 2018-10-26（2018 修正）为生效日；新法 2024-07-01。
    {"law_code": "COMPANY_LAW", "article_number": "第3条",
     "content": "公司是企业法人，有独立的法人财产，享有法人财产权。公司以其全部财产对公司的债务承担责任。公司的合法权益受法律保护，不受侵犯。",
     "effective_date": "2024-07-01", "notes": "2023年修订版：新增“公司的合法权益受法律保护，不受侵犯”"},
    {"law_code": "COMPANY_LAW", "article_number": "第4条",
     "content": "公司股东对公司依法享有资产收益、参与重大决策和选择管理者等权利。",
     "effective_date": "2024-07-01", "notes": "2023年修订版（语义一致）"},
    {"law_code": "COMPANY_LAW", "article_number": "第10条",
     "content": "公司的法定代表人按照公司章程的规定，由代表公司执行公司事务的董事或者经理担任。担任法定代表人的董事或者经理辞任的，视为同时辞去法定代表人。法定代表人辞任的，公司应当在法定代表人辞任之日起三十日内确定新的法定代表人。",
     "effective_date": "2024-07-01", "notes": "由旧法第13条 relocation 而来（旧第13条已删除，relocation 仅作历史注释）"},
    {"law_code": "COMPANY_LAW", "article_number": "第15条",
     "content": "公司向其他企业投资或者为他人提供担保，按照公司章程的规定，由董事会或者股东会决议；公司章程对投资或者担保的总额及单项投资或者担保的数额有限额规定的，不得超过规定的限额。公司为公司股东或者实际控制人提供担保的，应当经股东会决议。",
     "effective_date": "2024-07-01", "notes": "由旧法第16条 relocation 而来（旧第16条已删除，relocation 仅作历史注释）"},
    {"law_code": "COMPANY_LAW", "article_number": "第20条",
     "content": "公司股东应当遵守法律、行政法规和公司章程，依法行使股东权利，不得滥用股东权利损害公司或者其他股东的利益；不得滥用公司法人独立地位和股东有限责任损害公司债权人的利益。公司股东滥用股东权利给公司或者其他股东造成损失的，应当依法承担赔偿责任。",
     "effective_date": "2024-07-01", "notes": "法人人格否认（新法）"},
    {"law_code": "COMPANY_LAW", "article_number": "第21条",
     "content": "公司股东应当遵守法律、行政法规和公司章程，依法行使股东权利，不得滥用股东权利损害公司或者其他股东的利益。公司股东滥用股东权利给公司或者其他股东造成损失的，应当依法承担赔偿责任。",
     "effective_date": "2024-07-01", "notes": "关联交易限制（新法）"},
    {"law_code": "COMPANY_LAW", "article_number": "第27条",
     "content": "股东可以用货币出资，也可以用实物、知识产权、土地使用权、股权、债权等可以用货币估价并可以依法转让的非货币财产作价出资；但是，法律、行政法规规定不得作为出资的财产除外。",
     "effective_date": "2024-07-01", "notes": "出资方式（新法新增股权、债权出资）"},
    {"law_code": "COMPANY_LAW", "article_number": "第34条",
     "content": "公司登记事项发生变更的，应当依法办理变更登记。公司登记事项未经登记或者未经变更登记，不得对抗善意相对人。",
     "effective_date": "2024-07-01", "notes": "登记对抗要件（新法）"},
    {"law_code": "COMPANY_LAW", "article_number": "第35条",
     "content": "公司成立后，股东不得抽逃出资。",
     "effective_date": "2024-07-01", "notes": "禁止抽逃出资"},
    {"law_code": "COMPANY_LAW", "article_number": "第49条",
     "content": "股东未按期足额缴纳出资的，除应当向公司足额缴纳外，还应当对给公司造成的损失承担赔偿责任。",
     "effective_date": "2024-07-01", "notes": "未足额出资责任（新法）"},
    {"law_code": "COMPANY_LAW", "article_number": "第57条",
     "content": "有限责任公司由一个以上五十个以下股东出资设立。",
     "effective_date": "2024-07-01", "notes": "一人有限责任公司（新法允许一个股东）"},
    {"law_code": "COMPANY_LAW", "article_number": "第63条",
     "content": "一人有限责任公司的股东不能证明公司财产独立于股东自己的财产的，应当对公司债务承担连带责任。",
     "effective_date": "2024-07-01", "notes": "一人公司人格否认"},
    {"law_code": "COMPANY_LAW", "article_number": "第84条",
     "content": "有限责任公司的股东之间可以相互转让其全部或者部分股权。股东向股东以外的人转让股权的，应当将股权转让的数量、价格、支付方式和期限等事项书面通知其他股东，其他股东在同等条件下有优先购买权。",
     "effective_date": "2024-07-01", "notes": "由旧法第71条 relocation 而来（删除过半数同意；旧第71条已删除，relocation 仅作历史注释）"},
    {"law_code": "COMPANY_LAW", "article_number": "第113条",
     "content": "股份有限公司的资本划分为股份，每一股的金额相等。公司的股份采取股票的形式。股票是公司签发的证明股东所持股份的凭证。",
     "effective_date": "2024-07-01", "notes": "股份发行"},
    {"law_code": "COMPANY_LAW", "article_number": "第142条",
     "content": "公司不得收购本公司股份。但是，有下列情形之一的除外：（一）减少公司注册资本；（二）与持有本公司股份的其他公司合并；（三）将股份用于员工持股计划或者股权激励；……",
     "effective_date": "2024-07-01", "notes": "股份回购（上市公司收购相关）"},

    # ===================== 刑法 CRIMINAL_LAW (1997-10-01) =====================
    {"law_code": "CRIMINAL_LAW", "article_number": "第13条",
     "content": "一切危害国家主权、领土完整和安全，分裂国家、颠覆人民民主专政的政权和推翻社会主义制度，破坏社会秩序和经济秩序，侵犯国有财产或者劳动群众集体所有的财产，侵犯公民私人所有的财产，侵犯公民的人身权利、民主权利和其他权利，以及其他危害社会的行为，依照法律应当受刑罚处罚的，都是犯罪，但是情节显著轻微危害不大的，不认为是犯罪。",
     "effective_date": "1997-10-01", "notes": "犯罪概念"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第14条",
     "content": "明知自己的行为会发生危害社会的结果，并且希望或者放任这种结果发生，因而构成犯罪的，是故意犯罪。故意犯罪，应当负刑事责任。",
     "effective_date": "1997-10-01", "notes": "故意犯罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第15条",
     "content": "应当预见自己的行为可能发生危害社会的结果，因为疏忽大意而没有预见，或者已经预见而轻信能够避免，以致发生这种结果的，是过失犯罪。过失犯罪，法律有规定的才负刑事责任。",
     "effective_date": "1997-10-01", "notes": "过失犯罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第17条",
     "content": "已满十六周岁的人犯罪，应当负刑事责任。已满十四周岁不满十六周岁的人，犯故意杀人、故意伤害致人重伤或者死亡、强奸、抢劫、贩卖毒品、放火、爆炸、投放危险物质罪的，应当负刑事责任。",
     "effective_date": "1997-10-01", "notes": "刑事责任年龄"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第20条",
     "content": "为了使国家、公共利益、本人或者他人的人身、财产和其他权利免受正在进行的不法侵害，而采取的制止不法侵害的行为，对不法侵害人造成损害的，属于正当防卫，不负刑事责任。正当防卫明显超过必要限度造成重大损害的，应当负刑事责任，但是应当减轻或者免除处罚。",
     "effective_date": "1997-10-01", "notes": "正当防卫"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第22条",
     "content": "为了犯罪，准备工具、制造条件的，是犯罪预备。对于预备犯，可以比照既遂犯从轻、减轻处罚或者免除处罚。",
     "effective_date": "1997-10-01", "notes": "犯罪预备"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第23条",
     "content": "已经着手实行犯罪，由于犯罪分子意志以外的原因而未得逞的，是犯罪未遂。对于未遂犯，可以比照既遂犯从轻或者减轻处罚。",
     "effective_date": "1997-10-01", "notes": "犯罪未遂"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第24条",
     "content": "在犯罪过程中，自动放弃犯罪或者自动有效地防止犯罪结果发生的，是犯罪中止。对于中止犯，没有造成损害的，应当免除处罚；造成损害的，应当减轻处罚。",
     "effective_date": "1997-10-01", "notes": "犯罪中止"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第25条",
     "content": "共同犯罪是指二人以上共同故意犯罪。二人以上共同过失犯罪，不以共同犯罪论处；应当负刑事责任的，按照他们所犯的罪分别处罚。",
     "effective_date": "1997-10-01", "notes": "共同犯罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第26条",
     "content": "组织、领导犯罪集团进行犯罪活动的或者在共同犯罪中起主要作用的，是主犯。三人以上为共同实施犯罪而组成的较为固定的犯罪组织，是犯罪集团。",
     "effective_date": "1997-10-01", "notes": "主犯与犯罪集团"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第29条",
     "content": "教唆他人犯罪的，应当按照他在共同犯罪中所起的作用处罚。教唆不满十八周岁的人犯罪的，应当从重处罚。",
     "effective_date": "1997-10-01", "notes": "教唆犯"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第48条",
     "content": "死刑只适用于罪行极其严重的犯罪分子。对于应当判处死刑的犯罪分子，如果不是必须立即执行的，可以判处死刑同时宣告缓期二年执行。",
     "effective_date": "1997-10-01", "notes": "死刑适用"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第67条",
     "content": "犯罪以后自动投案，如实供述自己的罪行的，是自首。对于自首的犯罪分子，可以从轻或者减轻处罚。其中，犯罪较轻的，可以免除处罚。",
     "effective_date": "1997-10-01", "notes": "自首"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第232条",
     "content": "故意杀人的，处死刑、无期徒刑或者十年以上有期徒刑；情节较轻的，处三年以上十年以下有期徒刑。",
     "effective_date": "1997-10-01", "notes": "故意杀人罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第234条",
     "content": "故意伤害他人身体的，处三年以下有期徒刑、拘役或者管制。犯前款罪，致人重伤的，处三年以上十年以下有期徒刑；致人死亡或者以特别残忍手段致人重伤造成严重残疾的，处十年以上有期徒刑、无期徒刑或者死刑。",
     "effective_date": "1997-10-01", "notes": "故意伤害罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第263条",
     "content": "以暴力、胁迫或者其他方法抢劫公私财物的，处三年以上十年以下有期徒刑，并处罚金；有下列情形之一的，处十年以上有期徒刑、无期徒刑或者死刑，并处罚金或者没收财产：（一）入户抢劫的；……",
     "effective_date": "1997-10-01", "notes": "抢劫罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第264条",
     "content": "盗窃公私财物，数额较大的，或者多次盗窃、入户盗窃、携带凶器盗窃、扒窃的，处三年以下有期徒刑、拘役或者管制，并处或者单处罚金；数额巨大或者有其他严重情节的，处三年以上十年以下有期徒刑，并处罚金；数额特别巨大或者有其他特别严重情节的，处十年以上有期徒刑或者无期徒刑，并处罚金或者没收财产。",
     "effective_date": "1997-10-01", "notes": "盗窃罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第266条",
     "content": "诈骗公私财物，数额较大的，处三年以下有期徒刑、拘役或者管制，并处或者单处罚金；数额巨大或者有其他严重情节的，处三年以上十年以下有期徒刑，并处罚金；数额特别巨大或者有其他特别严重情节的，处十年以上有期徒刑或者无期徒刑，并处罚金或者没收财产。本法另有规定的，依照规定。",
     "effective_date": "1997-10-01", "notes": "诈骗罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第271条",
     "content": "公司、企业或者其他单位的工作人员，利用职务上的便利，将本单位财物非法占为己有，数额较大的，处三年以下有期徒刑或者拘役，并处罚金；数额巨大的，处三年以上十年以下有期徒刑，并处罚金；数额特别巨大的，处十年以上有期徒刑或者无期徒刑，并处罚金。",
     "effective_date": "1997-10-01", "notes": "职务侵占罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第272条",
     "content": "公司、企业或者其他单位的工作人员，利用职务上的便利，挪用本单位资金归个人使用或者借贷给他人，数额较大、超过三个月未还的，或者虽未超过三个月，但数额较大、进行营利活动的，或者进行非法活动的，处三年以下有期徒刑或者拘役；……",
     "effective_date": "1997-10-01", "notes": "挪用资金罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第382条",
     "content": "国家工作人员利用职务上的便利，侵吞、窃取、骗取或者以其他手段非法占有公共财物的，是贪污罪。受国家机关、国有公司、企业、事业单位、人民团体委托管理、经营国有财产的人员，利用职务上的便利，侵吞、窃取、骗取或者以其他手段非法占有国有财物的，以贪污论。",
     "effective_date": "1997-10-01", "notes": "贪污罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第384条",
     "content": "国家工作人员利用职务上的便利，挪用公款归个人使用，进行非法活动的，或者挪用公款数额较大、进行营利活动的，或者挪用公款数额较大、超过三个月未还的，是挪用公款罪。",
     "effective_date": "1997-10-01", "notes": "挪用公款罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第385条",
     "content": "国家工作人员利用职务上的便利，索取他人财物的，或者非法收受他人财物，为他人谋取利益的，是受贿罪。国家工作人员在经济往来中，违反国家规定，收受各种名义的回扣、手续费，归个人所有的，以受贿论处。",
     "effective_date": "1997-10-01", "notes": "受贿罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第389条",
     "content": "为谋取不正当利益，给予国家工作人员以财物的，是行贿罪。在经济往来中，违反国家规定，给予国家工作人员以财物，数额较大的，或者违反国家规定，给予国家工作人员以各种名义的回扣、手续费的，以行贿论处。",
     "effective_date": "1997-10-01", "notes": "行贿罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第397条",
     "content": "国家机关工作人员滥用职权或者玩忽职守，致使公共财产、国家和人民利益遭受重大损失的，处三年以下有期徒刑或者拘役；情节特别严重的，处三年以上七年以下有期徒刑。本法另有规定的，依照规定。",
     "effective_date": "1997-10-01", "notes": "滥用职权/玩忽职守罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第234条之一",
     "content": "【组织出卖人体器官罪】组织他人出卖人体器官的，处五年以下有期徒刑，并处罚金；情节严重的，处五年以上有期徒刑，并处罚金或者没收财产。未经本人同意摘取其器官，或者摘取不满十八周岁的人的器官，或者强迫、欺骗他人捐献器官的，依照本法第二百三十四条、第二百三十二条的规定定罪处罚。违背本人生前意愿摘取其尸体器官，或者本人生前未表示同意，违反国家规定，违背其近亲属意愿摘取其尸体器官的，依照本法第三百零二条的规定定罪处罚。",
     "effective_date": "1997-10-01", "notes": "组织出卖人体器官罪"},
    {"law_code": "CRIMINAL_LAW", "article_number": "第302条",
     "content": "【盗窃、侮辱、故意毁坏尸体、尸骨、灰罪】盗窃、侮辱、故意毁坏尸体、尸骨、灰的，处三年以下有期徒刑、拘役或者管制。",
     "effective_date": "1997-10-01", "notes": "盗窃、侮辱、故意毁坏尸体、尸骨、灰罪"},

    # ===================== 专利法 PATENT_LAW (2021-06-01) =====================
    {"law_code": "PATENT_LAW", "article_number": "第2条",
     "content": "本法所称的发明创造是指发明、实用新型和外观设计。发明，是指对产品、方法或者其改进所提出的新的技术方案。实用新型，是指对产品的形状、构造或者其结合所提出的适于实用的新的技术方案。外观设计，是指对产品的整体或者局部的形状、图案或者其结合以及色彩与形状、图案的结合所作出的富有美感并适于工业应用的新设计。",
     "effective_date": "2021-06-01", "notes": "保护客体定义"},
    {"law_code": "PATENT_LAW", "article_number": "第5条",
     "content": "对违反法律、社会公德或者妨害公共利益的发明创造，不授予专利权。对违反法律、行政法规的规定获取或者利用遗传资源，并依赖该遗传资源完成的发明创造，不授予专利权。",
     "effective_date": "2021-06-01", "notes": "不授予专利的情形"},
    {"law_code": "PATENT_LAW", "article_number": "第8条",
     "content": "两个以上单位或者个人合作完成的发明创造、一个单位或者个人接受其他单位或者个人委托所完成的发明创造，除另有协议的以外，申请专利的权利属于完成或者共同完成的单位或者个人。",
     "effective_date": "2021-06-01", "notes": "合作/委托发明权属"},
    {"law_code": "PATENT_LAW", "article_number": "第9条",
     "content": "同样的发明创造只能授予一项专利权。但是，同一申请人同日对同样的发明创造既申请实用新型专利又申请发明专利，先获得的实用新型专利权尚未终止，且申请人声明放弃该实用新型专利权的，可以授予发明专利权。",
     "effective_date": "2021-06-01", "notes": "先申请原则"},
    {"law_code": "PATENT_LAW", "article_number": "第10条",
     "content": "专利申请权和专利权可以转让。中国单位或者个人向外国人、外国企业或者外国其他组织转让专利申请权或者专利权的，应当依照有关法律、行政法规的规定办理手续。转让专利申请权或者专利权的，当事人应当订立书面合同，并向国务院专利行政部门登记，由国务院专利行政部门予以公告。",
     "effective_date": "2021-06-01", "notes": "专利权转让"},
    {"law_code": "PATENT_LAW", "article_number": "第11条",
     "content": "发明和实用新型专利权被授予后，除本法另有规定的以外，任何单位或者个人未经专利权人许可，都不得实施其专利，即不得为生产经营目的制造、使用、许诺销售、销售、进口其专利产品，或者使用其专利方法以及使用、许诺销售、销售、进口依照该专利方法直接获得的产品。",
     "effective_date": "2021-06-01", "notes": "排他权"},
    {"law_code": "PATENT_LAW", "article_number": "第22条",
     "content": "授予专利权的发明和实用新型，应当具备新颖性、创造性和实用性。新颖性，是指该发明或者实用新型不属于现有技术；也没有任何单位或者个人就同样的发明或者实用新型在申请日以前向国务院专利行政部门提出过申请，并记载在申请日以后公布的专利申请文件或者公告的专利文件中。创造性，是指与现有技术相比，该发明具有突出的实质性特点和显著的进步，该实用新型具有实质性特点和进步。实用性，是指该发明或者实用新型能够制造或者使用，并且能够产生积极效果。",
     "effective_date": "2021-06-01", "notes": "三性（新颖性/创造性/实用性）"},
    {"law_code": "PATENT_LAW", "article_number": "第23条",
     "content": "授予专利权的外观设计，应当不属于现有设计；也没有任何单位或者个人就同样的外观设计在申请日以前向国务院专利行政部门提出过申请，并记载在申请日以后公告的专利文件中。授予专利权的外观设计与现有设计或者现有设计特征的组合相比，应当具有明显区别。",
     "effective_date": "2021-06-01", "notes": "外观设计授权要件"},
    {"law_code": "PATENT_LAW", "article_number": "第25条",
     "content": "对下列各项，不授予专利权：（一）科学发现；（二）智力活动的规则和方法；（三）疾病的诊断和治疗方法；（四）动物和植物品种；（五）原子核变换方法以及用原子核变换方法获得的物质。",
     "effective_date": "2021-06-01", "notes": "不授予专利的客体"},
    {"law_code": "PATENT_LAW", "article_number": "第26条",
     "content": "申请发明或者实用新型专利的，应当提交请求书、说明书及其摘要和权利要求书等文件。权利要求书应当以说明书为依据，清楚、简要地限定要求专利保护的范围。",
     "effective_date": "2021-06-01", "notes": "申请文件"},
    {"law_code": "PATENT_LAW", "article_number": "第31条",
     "content": "一件发明或者实用新型专利申请应当限于一项发明或者实用新型。属于一个总的发明构思的两项以上的发明或者实用新型，可以作为一件申请提出。",
     "effective_date": "2021-06-01", "notes": "单一性原则"},
    {"law_code": "PATENT_LAW", "article_number": "第42条",
     "content": "发明专利权的期限为二十年，实用新型专利权的期限为十年，外观设计专利权的期限为十五年，均自申请日起计算。",
     "effective_date": "2021-06-01", "notes": "专利权期限"},
    {"law_code": "PATENT_LAW", "article_number": "第45条",
     "content": "自国务院专利行政部门公告授予专利权之日起，任何单位或者个人认为该专利权的授予不符合本法有关规定的，可以请求国务院专利行政部门宣告该专利权无效。",
     "effective_date": "2021-06-01", "notes": "无效宣告请求"},
    {"law_code": "PATENT_LAW", "article_number": "第59条",
     "content": "发明或者实用新型专利权的保护范围以其权利要求的内容为准，说明书及附图可以用于解释权利要求的内容。外观设计专利权的保护范围以表示在图片或者照片中的该产品的外观设计为准，简要说明可以用于解释图片或者照片所表示的该产品的外观设计。",
     "effective_date": "2021-06-01", "notes": "保护范围"},
    {"law_code": "PATENT_LAW", "article_number": "第65条",
     "content": "侵犯专利权的赔偿数额按照权利人因被侵权所受到的实际损失确定；实际损失难以确定的，可以按照侵权人因侵权所获得的利益确定。权利人的损失或者侵权人获得的利益难以确定的，参照该专利许可使用费的倍数合理确定。对故意侵犯专利权，情节严重的，可以在按照上述方法确定数额的一倍以上五倍以下确定赔偿数额。",
     "effective_date": "2021-06-01", "notes": "损害赔偿"},
    {"law_code": "PATENT_LAW", "article_number": "第69条",
     "content": "有下列情形之一的，不视为侵犯专利权：（一）专利产品或者依照专利方法直接获得的产品，由专利权人或者经其许可的单位、个人售出后，使用、许诺销售、销售、进口该产品的；……（二）在专利申请日前已经制造相同产品、使用相同方法或者已经作好制造、使用的必要准备，并且仅在原有范围内继续制造、使用的。",
     "effective_date": "2021-06-01", "notes": "不视为侵权（权利用尽/先用权）"},

    # ===================== 税收征管法 TAX_ADMIN_LAW (2015-04-24) =====================
    {"law_code": "TAX_ADMIN_LAW", "article_number": "第4条",
     "content": "法律、行政法规规定负有纳税义务的单位和个人为纳税人。法律、行政法规规定负有代扣代缴、代收代缴税款义务的单位和个人为扣缴义务人。纳税人、扣缴义务人必须依照法律、行政法规的规定缴纳税款、代扣代缴、代收代缴税款。",
     "effective_date": "2015-04-24", "notes": "纳税人/扣缴义务人"},
    {"law_code": "TAX_ADMIN_LAW", "article_number": "第15条",
     "content": "企业，企业在外地设立的分支机构和从事生产、经营的场所，个体工商户和从事生产、经营的事业单位，自领取营业执照之日起三十日内，持有关证件，向税务机关申报办理税务登记。",
     "effective_date": "2015-04-24", "notes": "税务登记"},
    {"law_code": "TAX_ADMIN_LAW", "article_number": "第25条",
     "content": "纳税人、扣缴义务人必须依照法律、行政法规或者税务机关依照法律、行政法规的规定确定的申报期限、申报内容如实办理纳税申报，报送纳税申报表、财务会计报表以及税务机关根据实际需要要求纳税人报送的其他纳税资料。",
     "effective_date": "2015-04-24", "notes": "纳税申报"},
    {"law_code": "TAX_ADMIN_LAW", "article_number": "第31条",
     "content": "纳税人、扣缴义务人按照法律、行政法规规定或者税务机关依照法律、行政法规的规定确定的期限，缴纳或者解缴税款。纳税人因有特殊困难，不能按期缴纳税款的，经省、自治区、直辖市税务局批准，可以延期缴纳税款，但是最长不得超过三个月。",
     "effective_date": "2015-04-24", "notes": "税款缴纳与延期"},
    {"law_code": "TAX_ADMIN_LAW", "article_number": "第32条",
     "content": "纳税人未按照规定期限缴纳税款的，扣缴义务人未按照规定期限解缴税款的，税务机关除责令限期缴纳外，从滞纳税款之日起，按日加收滞纳税款万分之五的滞纳金。",
     "effective_date": "2015-04-24", "notes": "滞纳金"},
    {"law_code": "TAX_ADMIN_LAW", "article_number": "第35条",
     "content": "纳税人有下列情形之一的，税务机关有权核定其应纳税额：（一）依照法律、行政法规的规定可以不设置帐簿的；（二）应当设置但未设置帐簿的；（三）擅自销毁帐簿或者拒不提供纳税资料的；……（六）纳税人申报的计税依据明显偏低，又无正当理由的。",
     "effective_date": "2015-04-24", "notes": "核定征收"},
    {"law_code": "TAX_ADMIN_LAW", "article_number": "第38条",
     "content": "税务机关有根据认为从事生产、经营的纳税人有逃避纳税义务行为的，可以在规定的纳税期之前，责令限期缴纳应纳税款；在限期内发现纳税人有明显的转移、隐匿其应纳税的商品、货物以及其他财产或者应纳税的收入的迹象的，税务机关可以责成纳税人提供纳税担保……",
     "effective_date": "2015-04-24", "notes": "税收保全措施"},
    {"law_code": "TAX_ADMIN_LAW", "article_number": "第40条",
     "content": "从事生产、经营的纳税人、扣缴义务人未按照规定的期限缴纳或者解缴税款，由税务机关责令限期缴纳，逾期仍未缴纳的，经县以上税务局（分局）局长批准，税务机关可以采取下列强制执行措施：（一）书面通知其开户银行或者其他金融机构从其存款中扣缴税款；……",
     "effective_date": "2015-04-24", "notes": "强制执行措施"},
    {"law_code": "TAX_ADMIN_LAW", "article_number": "第44条",
     "content": "欠缴税款的纳税人或者他的法定代表人需要出境的，应当在出境前向税务机关结清应纳税款、滞纳金或者提供担保。未结清税款、滞纳金，又不提供担保的，税务机关可以通知出境管理机关阻止其出境。",
     "effective_date": "2015-04-24", "notes": "离境清税"},
    {"law_code": "TAX_ADMIN_LAW", "article_number": "第45条",
     "content": "税务机关征收税款，税收优先于无担保债权，法律另有规定的除外；纳税人欠缴的税款发生在纳税人以其财产设定抵押、质押或者纳税人的财产被留置之前的，税收应当先于抵押权、质权、留置权执行。",
     "effective_date": "2015-04-24", "notes": "税收优先权"},
    {"law_code": "TAX_ADMIN_LAW", "article_number": "第52条",
     "content": "因税务机关的责任，致使纳税人、扣缴义务人未缴或者少缴税款的，税务机关在三年内可以要求纳税人、扣缴义务人补缴税款，但是不得加收滞纳金。因纳税人、扣缴义务人计算错误等失误，未缴或者少缴税款的，税务机关在三年内可以追征税款、滞纳金；有特殊情况的，追征期可以延长到五年。",
     "effective_date": "2015-04-24", "notes": "税款追征期"},
    {"law_code": "TAX_ADMIN_LAW", "article_number": "第54条",
     "content": "税务机关有权进行下列税务检查：（一）检查纳税人的帐簿、记帐凭证、报表和有关资料；（二）到纳税人的生产、经营场所和货物存放地检查纳税人应纳税的商品、货物或者其他财产；……",
     "effective_date": "2015-04-24", "notes": "税务检查权"},
    {"law_code": "TAX_ADMIN_LAW", "article_number": "第63条",
     "content": "纳税人伪造、变造、隐匿、擅自销毁帐簿、记帐凭证，或者在帐簿上多列支出或者不列、少列收入，或者经税务机关通知申报而拒不申报或者进行虚假的纳税申报，不缴或者少缴应纳税款的，是偷税。对纳税人偷税的，由税务机关追缴其不缴或者少缴的税款、滞纳金，并处不缴或者少缴的税款百分之五十以上五倍以下的罚款；构成犯罪的，依法追究刑事责任。",
     "effective_date": "2015-04-24", "notes": "偷税认定与处罚"},
    {"law_code": "TAX_ADMIN_LAW", "article_number": "第64条",
     "content": "纳税人、扣缴义务人编造虚假计税依据的，由税务机关责令限期改正，并处五万元以下的罚款。纳税人不进行纳税申报，不缴或者少缴应纳税款的，由税务机关追缴其不缴或者少缴的税款、滞纳金，并处不缴或者少缴税款百分之五十以上五倍以下的罚款。",
     "effective_date": "2015-04-24", "notes": "编造虚假计税依据"},
    {"law_code": "TAX_ADMIN_LAW", "article_number": "第86条",
     "content": "违反税收法律、行政法规应当给予行政处罚的行为，在五年内未被发现的，不再给予行政处罚。",
     "effective_date": "2015-04-24", "notes": "处罚时效"},
]


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
_ZHI = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}


def _parse_sort_key(article_number: str) -> int:
    """Numeric sort/group key for an article_number string.

    Handles '之一/之二/之三' sub-articles (e.g. 第234条之一 -> 2341) so they
    form their own (law_code, sort_key) group and never chain onto the parent
    article during window-integrity validation.
    """
    m = re.search(r"(\d+)", article_number)
    if not m:
        raise ValueError(f"cannot parse article number from {article_number!r}")
    base = int(m.group(1))
    suf = re.search(r"之([一二三四五六七八九])", article_number)
    if suf:
        return base * 10 + _ZHI[suf.group(1)]
    return base


def generate(raw: Optional[List[dict]] = None,
             ledger: Optional[dict] = None) -> List[dict]:
    """Turn SEED (or provided raw list) into final statute nodes.

    ``ledger`` is the human verification ledger (verifications.json). When None
    it is loaded from disk; pass an explicit dict in tests.
    """
    raw = [dict(r) for r in (raw or SEED)]
    # 1) sort_key
    for r in raw:
        r["_sk"] = _parse_sort_key(r["article_number"])
    # 2) group by (law_code, sort_key), assign ids by effective_date order
    groups: Dict[Tuple[str, int], List[dict]] = defaultdict(list)
    for r in raw:
        groups[(r["law_code"], r["_sk"])].append(r)
    artnum_to_id: Dict[Tuple[str, str], str] = {}
    for (law_code, _sk), items in groups.items():
        items.sort(key=lambda x: x["effective_date"])
        for i, r in enumerate(items):
            r["_id"] = f"{law_code}_{_sk}_v{i + 1}"
            # first (earliest) occurrence of this article_number wins for refs
            artnum_to_id.setdefault((law_code, r["article_number"]), r["_id"])
    # 3) resolve revision_of
    for r in raw:
        rev = r.get("revision_of")
        if rev:
            if _ID_RE.match(rev):
                r["_rev"] = rev
            else:
                r["_rev"] = artnum_to_id.get((r["law_code"], rev))  # may be None
        else:
            grp = groups[(r["law_code"], r["_sk"])]
            idx = grp.index(r)
            r["_rev"] = grp[idx - 1]["_id"] if idx > 0 else None
    # 4) final dicts — default provenance is "unverified" scaffold.
    nodes = []
    for r in raw:
        nodes.append({
            "id": r["_id"],
            "law_code": r["law_code"],
            "article_number": r["article_number"],
            "article_sort_key": r["_sk"],
            "content": r["content"],
            "effective_date": r["effective_date"],
            "revision_of": r["_rev"],
            "verification_status": "unverified",
            "verified_by": None,
            "verified_at": None,
            "source_url": r.get("source_url") or LAW_SOURCES.get(r["law_code"], ""),
            "source_accessed_at": r.get("source_accessed_at") or DEFAULT_ACCESSED_AT,
            "notes": r.get("notes", ""),
        })
    # 5) merge the human verification ledger — the ONLY authority for "verified".
    #    An LLM is not an authority, so the SEED scaffold stays "unverified"
    #    until a legal expert records a verdict in verifications.json.
    if ledger is None:
        ledger = _load_verifications()
    for n in nodes:
        entry = ledger.get(n["id"])
        if not entry:
            continue
        status = entry.get("status")
        corrected = entry.get("corrected_content")
        if status == "verified":
            n["verification_status"] = "verified"
        elif status == "rejected":
            if corrected:
                n["verification_status"] = "verified"  # expert supplied fix
            else:
                n["verification_status"] = "rejected"  # wrong, not yet fixed
        if corrected:
            n["content"] = corrected
        if n["verification_status"] == "verified":
            n["verified_by"] = entry.get("verified_by")
            n["verified_at"] = entry.get("verified_at")
    return nodes


def _load_verifications(path: str = VERIFICATIONS_FILE) -> dict:
    """Load the human verification ledger. Missing file => empty (all unverified)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


# --------------------------------------------------------------------------- #
# Validation gate  (imported by tests/test_kb_integrity.py)
# --------------------------------------------------------------------------- #
def validate(nodes: List[dict]) -> List[str]:
    """Return a list of human-readable errors (empty == pass)."""
    errors: List[str] = []
    ids = set()
    for n in nodes:
        nid = n.get("id")
        if not nid:
            errors.append(f"missing id: {n.get('law_code')} {n.get('article_number')}")
            continue
        if nid in ids:
            errors.append(f"duplicate id: {nid}")
        ids.add(nid)
        if not (n.get("content") or "").strip():
            errors.append(f"{nid}: empty content")
        # provenance gate: status must be a known value
        vs = n.get("verification_status")
        if vs not in ("verified", "unverified", "rejected"):
            errors.append(f"{nid}: verification_status must be 'verified', "
                          f"'unverified' or 'rejected' (got {vs!r})")
        if vs == "verified" and not (n.get("source_url") or "").strip():
            # verified text MUST cite the official source it was checked against
            errors.append(f"{nid}: verified node missing source_url")
        if not _DATE_RE.match(n.get("effective_date", "")):
            errors.append(f"{nid}: bad effective_date {n.get('effective_date')!r}")
        if n.get("revision_of") is not None:
            if n["revision_of"] not in ids and n["revision_of"] not in {x.get("id") for x in nodes}:
                # allow forward refs within the same batch
                pass
        # revision_of must exist somewhere in the batch
        rev = n.get("revision_of")
        if rev is not None and rev not in {x.get("id") for x in nodes}:
            errors.append(f"{nid}: revision_of {rev!r} not found")
        # article_number numeric must match sort_key
        sk = n.get("article_sort_key")
        if sk is None:
            errors.append(f"{nid}: missing article_sort_key")
        else:
            parsed = _parse_sort_key(n["article_number"])
            if parsed != sk:
                errors.append(f"{nid}: article_number {n['article_number']!r} "
                              f"({parsed}) != article_sort_key {sk}")
        if not (n.get("source_url") or "").strip():
            errors.append(f"{nid}: missing source_url")
        if not (n.get("source_accessed_at") or "").strip():
            errors.append(f"{nid}: missing source_accessed_at")

    # window integrity: per (law_code, sort_key), sorted by effective_date,
    # consecutive versions must chain via revision_of (gap-free, non-overlapping)
    groups: Dict[Tuple[str, int], List[dict]] = defaultdict(list)
    for n in nodes:
        groups[(n["law_code"], n["article_sort_key"])].append(n)
    for (law_code, sk), items in groups.items():
        items_sorted = sorted(items, key=lambda x: x["effective_date"])
        # no two versions share the exact same effective_date
        seen_dates = set()
        for it in items_sorted:
            if it["effective_date"] in seen_dates:
                errors.append(f"{law_code} art.{sk}: duplicate effective_date "
                              f"{it['effective_date']} (ambiguous window)")
            seen_dates.add(it["effective_date"])
        for i, it in enumerate(items_sorted):
            if i == 0:
                # v1 of a same-key group must not chain to a prior version.
                # A relocation (e.g. new art.10 <- old art.13) legitimately has
                # revision_of pointing to a DIFFERENT sort_key's node, so we
                # only forbid a self-group back-pointer here; cross-key
                # revision_of is validated by the existence check above.
                if it.get("revision_of") is not None:
                    grp_ids = {x["id"] for x in items_sorted}
                    if it["revision_of"] in grp_ids:
                        errors.append(f"{law_code} art.{sk} v1: revision_of "
                                      f"{it['revision_of']!r} points inside its own "
                                      f"group (should be a relocation to another article)")
            else:
                prev = items_sorted[i - 1]
                if it.get("revision_of") != prev["id"]:
                    errors.append(f"{law_code} art.{sk} {it['id']}: revision_of "
                                  f"{it.get('revision_of')!r} breaks chain "
                                  f"(expected {prev['id']})")

    # law_code coverage vs laws_index
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
        index_codes = set(index.keys())
        for n in nodes:
            if n["law_code"] not in index_codes:
                errors.append(f"{n['id']}: law_code {n['law_code']} not in laws_index.json")
    except FileNotFoundError:
        errors.append(f"laws_index.json not found at {INDEX_FILE}")

    return errors


# --------------------------------------------------------------------------- #
# Coverage report  (imported by tests/test_kb_coverage.py)
# --------------------------------------------------------------------------- #
def coverage(nodes: List[dict]) -> Dict[str, dict]:
    per_law: Dict[str, dict] = defaultdict(lambda: {"nodes": 0, "articles": set(), "multi": 0})
    for n in nodes:
        p = per_law[n["law_code"]]
        p["nodes"] += 1
        p["articles"].add(n["article_sort_key"])
    out = {}
    for code, p in per_law.items():
        distinct = len(p["articles"])
        multi = sum(
            1 for sk in p["articles"]
            if sum(1 for n in nodes if n["law_code"] == code and n["article_sort_key"] == sk) > 1
        )
        out[code] = {
            "nodes": p["nodes"],
            "distinct_articles": distinct,
            "double_version_articles": multi,
            "double_version_ratio": round(multi / distinct, 3) if distinct else 0.0,
        }
    return out


def print_coverage(nodes: List[dict]) -> None:
    cov = coverage(nodes)
    print(f"{'law_code':<14}{'nodes':>7}{'articles':>9}{'dbl-ver':>9}{'dbl-ratio':>11}")
    print("-" * 50)
    tot = 0
    for code, c in cov.items():
        tot += c["nodes"]
        print(f"{code:<14}{c['nodes']:>7}{c['distinct_articles']:>9}"
              f"{c['double_version_articles']:>9}{c['double_version_ratio']:>11}")
    print("-" * 50)
    print(f"{'TOTAL':<14}{tot:>7}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _load_statutes(path: str) -> List[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build(statutes_path: str = STATUTES_FILE) -> List[str]:
    nodes = generate()
    errors = validate(nodes)
    with open(statutes_path, "w", encoding="utf-8") as f:
        for n in nodes:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")
    print(f"wrote {len(nodes)} nodes to {statutes_path}")
    c = Counter(n["verification_status"] for n in nodes)
    print(f"verification: {c.get('verified', 0)} verified / "
          f"{c.get('rejected', 0)} rejected / {c.get('unverified', 0)} unverified")
    print_coverage(nodes)
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser(description="Statute curation pipeline")
    ap.add_argument("cmd", choices=["build", "validate", "coverage"],
                    help="build=regenerate jsonl; validate=run gate; coverage=report")
    args = ap.parse_args(argv)

    if args.cmd == "build":
        errors = build()
        if errors:
            print("\nINTEGRITY ERRORS:")
            for e in errors:
                print("  -", e)
            sys.exit(1)
        print("\nintegrity: OK")
    elif args.cmd == "validate":
        nodes = _load_statutes(STATUTES_FILE)
        errors = validate(nodes)
        if errors:
            for e in errors:
                print("ERROR:", e)
            sys.exit(1)
        print(f"integrity: OK ({len(nodes)} nodes)")
    elif args.cmd == "coverage":
        nodes = _load_statutes(STATUTES_FILE)
        print_coverage(nodes)


if __name__ == "__main__":
    main()
