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
    "VAT_LAW": "https://flk.npc.gov.cn/",
    "EIT_LAW": "https://flk.npc.gov.cn/",
    "IIT_LAW": "https://flk.npc.gov.cn/",
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
     "effective_date": "2024-07-01", "notes": "股东权利滥用（新法第20条）"},
    {"law_code": "COMPANY_LAW", "article_number": "第23条",
     "content": "公司股东滥用公司法人独立地位和股东有限责任，逃避债务，严重损害公司债权人利益的，应当对公司债务承担连带责任。股东利用其控制的两个以上公司实施前款规定行为的，各公司应当对任一公司的债务承担连带责任。只有一个股东的公司，股东不能证明公司财产独立于股东自己的财产的，应当对公司债务承担连带责任。",
     "effective_date": "2024-07-01", "notes": "法人人格否认（由旧法第20条 relocation 而来；新法第23条，含横向否认与一人公司）"},
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

    # ===================== 专利法 PATENT_LAW 补强 (2021-06-01) =====================
    {"law_code": "PATENT_LAW", "article_number": "第6条",
     "content": "执行本单位的任务或者主要是利用本单位的物质技术条件所完成的发明创造为职务发明创造。职务发明创造申请专利的权利属于该单位，申请被批准后，该单位为专利权人。该单位可以依法处置其职务发明创造申请专利的权利和专利权，促进相关发明创造的实施和运用。非职务发明创造，申请专利的权利属于发明人或者设计人；申请被批准后，该发明人或者设计人为专利权人。利用本单位的物质技术条件所完成的发明创造，单位与发明人或者设计人订有合同，对申请专利的权利和专利权的归属作出约定的，从其约定。",
     "effective_date": "2021-06-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "职务发明创造"},
    {"law_code": "PATENT_LAW", "article_number": "第12条",
     "content": "任何单位或者个人实施他人专利的，应当与专利权人订立实施许可合同，向专利权人支付专利使用费。被许可人无权允许合同规定以外的任何单位或者个人实施该专利。",
     "effective_date": "2021-06-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "实施许可合同"},
    {"law_code": "PATENT_LAW", "article_number": "第16条",
     "content": "发明人或者设计人有权在专利文件中写明自己是发明人或者设计人。专利权人有权在其专利产品或者该产品的包装上标明专利标识。",
     "effective_date": "2021-06-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "发明人署名权"},
    {"law_code": "PATENT_LAW", "article_number": "第17条",
     "content": "在中国没有经常居所或者营业所的外国人、外国企业或者外国其他组织在中国申请专利的，依照其所属国同中国签订的协议或者共同参加的国际条约，或者依照互惠原则，根据本法办理。",
     "effective_date": "2021-06-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "涉外专利申请"},
    {"law_code": "PATENT_LAW", "article_number": "第24条",
     "content": "申请专利的发明创造在申请日以前六个月内，有下列情形之一的，不丧失新颖性：（一）在国家出现紧急状态或者非常情况时，为公共利益目的首次公开的；（二）在中国政府主办或者承认的国际展览会上首次展出的；（三）在规定的学术会议或者技术会议上首次发表的；（四）他人未经申请人同意而泄露其内容的。",
     "effective_date": "2021-06-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "不丧失新颖性宽限期"},
    {"law_code": "PATENT_LAW", "article_number": "第27条",
     "content": "申请外观设计专利的，应当提交请求书、该外观设计的图片或者照片以及对该外观设计的简要说明等文件。申请人提交的有关图片或者照片应当清楚地显示要求专利保护的产品的外观设计。",
     "effective_date": "2021-06-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "外观设计申请文件"},
    {"law_code": "PATENT_LAW", "article_number": "第28条",
     "content": "国务院专利行政部门收到专利申请文件之日为申请日。如果申请文件是邮寄的，以寄出的邮戳日为申请日。",
     "effective_date": "2021-06-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "申请日确定"},
    {"law_code": "PATENT_LAW", "article_number": "第29条",
     "content": "申请人自发明或者实用新型在外国第一次提出专利申请之日起十二个月内，或者自外观设计在外国第一次提出专利申请之日起六个月内，又在中国就相同主题提出专利申请的，依照该外国同中国签订的协议或者共同参加的国际条约，或者依照相互承认优先权的原则，可以享有优先权。申请人自发明或者实用新型在中国第一次提出专利申请之日起十二个月内，或者自外观设计在中国第一次提出专利申请之日起六个月内，又向国务院专利行政部门就相同主题提出专利申请的，可以享有优先权。",
     "effective_date": "2021-06-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "优先权"},
    {"law_code": "PATENT_LAW", "article_number": "第30条",
     "content": "申请人要求发明、实用新型专利优先权的，应当在申请的时候提出书面声明，并且在第一次提出申请之日起十六个月内，提交第一次提出的专利申请文件的副本。申请人要求外观设计专利优先权的，应当在申请的时候提出书面声明，并且在三个月内提交第一次提出的专利申请文件的副本。申请人未提出书面声明或者逾期未提交专利申请文件副本的，视为未要求优先权。",
     "effective_date": "2021-06-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "优先权手续"},
    {"law_code": "PATENT_LAW", "article_number": "第39条",
     "content": "发明专利申请经实质审查没有发现驳回理由的，由国务院专利行政部门作出授予发明专利权的决定，发给发明专利证书，同时予以登记和公告。发明专利权自公告之日起生效。",
     "effective_date": "2021-06-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "发明专利授权"},
    {"law_code": "PATENT_LAW", "article_number": "第40条",
     "content": "实用新型和外观设计专利申请经初步审查没有发现驳回理由的，由国务院专利行政部门作出授予实用新型专利权或者外观设计专利权的决定，发给相应的专利证书，同时予以登记和公告。实用新型专利权和外观设计专利权自公告之日起生效。",
     "effective_date": "2021-06-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "实用新型/外观设计授权"},
    {"law_code": "PATENT_LAW", "article_number": "第46条",
     "content": "国务院专利行政部门对宣告专利权无效的请求应当及时审查和作出决定，并通知请求人和专利权人。宣告专利权无效的决定，由国务院专利行政部门登记和公告。对国务院专利行政部门宣告专利权无效或者维持专利权的决定不服的，可以自收到通知之日起三个月内向人民法院起诉。人民法院应当通知无效宣告请求程序的对方当事人作为第三人参加诉讼。",
     "effective_date": "2021-06-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "无效宣告审查"},
    {"law_code": "PATENT_LAW", "article_number": "第47条",
     "content": "宣告无效的专利权视为自始即不存在。宣告专利权无效的决定，对在宣告专利权无效前人民法院作出并已执行的专利侵权的判决、调解书，已经履行或者强制执行的专利侵权纠纷处理决定，以及已经履行的专利实施许可合同和专利权转让合同，不具有追溯力。但是因专利权人的恶意给他人造成的损失，应当给予赔偿。依照前款规定不返还专利侵权赔偿金、专利使用费、专利权转让费，明显违反公平原则的，应当全部或者部分返还。",
     "effective_date": "2021-06-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "无效宣告效力"},
    {"law_code": "PATENT_LAW", "article_number": "第60条",
     "content": "国务院专利行政部门作出的给予实施强制许可的决定，应当及时通知专利权人，并予以登记和公告。给予实施强制许可的决定，应当根据强制许可的理由规定实施的范围和时间。强制许可的理由消除并不再发生时，国务院专利行政部门应当根据专利权人的请求，经审查后作出终止实施强制许可的决定。",
     "effective_date": "2021-06-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "强制许可决定"},

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

    # ===================== 个人所得税法 IIT_LAW (2019-01-01) =====================
    {"law_code": "IIT_LAW", "article_number": "第1条",
     "content": "在中国境内有住所，或者无住所而一个纳税年度内在中国境内居住累计满一百八十三天的个人，为居民个人。居民个人从中国境内和境外取得的所得，依照本法规定缴纳个人所得税。在中国境内无住所又不居住，或者无住所而一个纳税年度内在中国境内居住累计不满一百八十三天的个人，为非居民个人。非居民个人从中国境内取得的所得，依照本法规定缴纳个人所得税。纳税年度，自公历一月一日起至十二月三十一日止。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "在中国境内有住所，或者无住所而一"},
    {"law_code": "IIT_LAW", "article_number": "第2条",
     "content": "下列各项个人所得，应当缴纳个人所得税：（一）工资、薪金所得；（二）劳务报酬所得；（三）稿酬所得；（四）特许权使用费所得；（五）经营所得；（六）利息、股息、红利所得；（七）财产租赁所得；（八）财产转让所得；（九）偶然所得。居民个人取得前款第一项至第四项所得（以下称综合所得），按纳税年度合并计算个人所得税；非居民个人取得前款第一项至第四项所得，按月或者按次分项计算个人所得税。纳税人取得前款第五项至第九项所得，依照本法规定分别计算个人所得税。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "下列各项个人所得，应当缴纳个人所"},
    {"law_code": "IIT_LAW", "article_number": "第3条",
     "content": "个人所得税的税率：（一）综合所得，适用百分之三至百分之四十五的超额累进税率（税率表附后）；（二）经营所得，适用百分之五至百分之三十五的超额累进税率（税率表附后）；（三）利息、股息、红利所得，财产租赁所得，财产转让所得和偶然所得，适用比例税率，税率为百分之二十。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "个人所得税的税率：（一）综合所得"},
    {"law_code": "IIT_LAW", "article_number": "第4条",
     "content": "下列各项个人所得，免征个人所得税：（一）省级人民政府、国务院部委和中国人民解放军军以上单位，以及外国组织、国际组织颁发的科学、教育、技术、文化、卫生、体育、环境保护等方面的奖金；（二）国债和国家发行的金融债券利息；（三）按照国家统一规定发给的补贴、津贴；（四）福利费、抚恤金、救济金；（五）保险赔款；（六）军人的转业费、复员费、退役金；（七）按照国家统一规定发给干部、职工的安家费、退职费、基本养老金或者退休费、离休费、离休生活补助费；（八）依照有关法律规定应予免税的各国驻华使馆、领事馆的外交代表、领事官员和其他人员的所得；（九）中国政府参加的国际公约、签订的协议中规定免税的所得；（十）国务院规定的其他免税所得。前款第十项免税规定，由国务院报全国人民代表大会常务委员会备案。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "下列各项个人所得，免征个人所得税"},
    {"law_code": "IIT_LAW", "article_number": "第5条",
     "content": "有下列情形之一的，可以减征个人所得税，具体幅度和期限，由省、自治区、直辖市人民政府规定，并报同级人民代表大会常务委员会备案：（一）残疾、孤老人员和烈属的所得；（二）因自然灾害遭受重大损失的。国务院可以规定其他减税情形，报全国人民代表大会常务委员会备案。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "有下列情形之一的，可以减征个人所"},
    {"law_code": "IIT_LAW", "article_number": "第6条",
     "content": "应纳税所得额的计算：（一）居民个人的综合所得，以每一纳税年度的收入额减除费用六万元以及专项扣除、专项附加扣除和依法确定的其他扣除后的余额，为应纳税所得额。（二）非居民个人的工资、薪金所得，以每月收入额减除费用五千元后的余额为应纳税所得额；劳务报酬所得、稿酬所得、特许权使用费所得，以每次收入额为应纳税所得额。（三）经营所得，以每一纳税年度的收入总额减除成本、费用以及损失后的余额，为应纳税所得额。（四）财产租赁所得，每次收入不超过四千元的，减除费用八百元；四千元以上的，减除百分之二十的费用，其余额为应纳税所得额。（五）财产转让所得，以转让财产的收入额减除财产原值和合理费用后的余额，为应纳税所得额。（六）利息、股息、红利所得和偶然所得，以每次收入额为应纳税所得额。劳务报酬所得、稿酬所得、特许权使用费所得以收入减除百分之二十的费用后的余额为收入额。稿酬所得的收入额减按百分之七十计算。个人将其所得对教育、扶贫、济困等公益慈善事业进行捐赠，捐赠额未超过纳税人申报的应纳税所得额百分之三十的部分，可以从其应纳税所得额中扣除；国务院规定对公益慈善事业捐赠实行全额税前扣除的，从其规定。本条第一款第一项规定的专项扣除，包括居民个人按照国家规定的范围和标准缴纳的基本养老保险、基本医疗保险、失业保险等社会保险费和住房公积金等；专项附加扣除，包括子女教育、继续教育、大病医疗、住房贷款利息或者住房租金、赡养老人等支出，具体范围、标准和实施步骤由国务院确定，并报全国人民代表大会常务委员会备案。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "应纳税所得额的计算：（一）居民个"},
    {"law_code": "IIT_LAW", "article_number": "第7条",
     "content": "居民个人从中国境外取得的所得，可以从其应纳税额中抵免已在境外缴纳的个人所得税税额，但抵免额不得超过该纳税人境外所得依照本法规定计算的应纳税额。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "居民个人从中国境外取得的所得，可"},
    {"law_code": "IIT_LAW", "article_number": "第8条",
     "content": "有下列情形之一的，税务机关有权按照合理方法进行纳税调整：（一）个人与其关联方之间的业务往来不符合独立交易原则而减少本人或者其关联方应纳税额，且无正当理由；（二）居民个人控制的，或者居民个人和居民企业共同控制的设立在实际税负明显偏低的国家（地区）的企业，无合理经营需要，对应当归属于居民个人的利润不作分配或者减少分配；（三）个人实施其他不具有合理商业目的的安排而获取不当税收利益。税务机关依照前款规定作出纳税调整，需要补征税款的，应当补征税款，并依法加收利息。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "有下列情形之一的，税务机关有权按"},
    {"law_code": "IIT_LAW", "article_number": "第9条",
     "content": "个人所得税以所得人为纳税人，以支付所得的单位或者个人为扣缴义务人。纳税人有中国公民身份号码的，以中国公民身份号码为纳税人识别号；纳税人没有中国公民身份号码的，由税务机关赋予其纳税人识别号。扣缴义务人扣缴税款时，纳税人应当向扣缴义务人提供纳税人识别号。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "个人所得税以所得人为纳税人，以支"},
    {"law_code": "IIT_LAW", "article_number": "第10条",
     "content": "有下列情形之一的，纳税人应当依法办理纳税申报：（一）取得综合所得需要办理汇算清缴；（二）取得应税所得没有扣缴义务人；（三）取得应税所得，扣缴义务人未扣缴税款；（四）取得境外所得；（五）因移居境外注销中国户籍；（六）非居民个人在中国境内从两处以上取得工资、薪金所得；（七）国务院规定的其他情形。扣缴义务人应当按照国家规定办理全员全额扣缴申报，并向纳税人提供其个人所得和已扣缴税款等信息。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "有下列情形之一的，纳税人应当依法"},
    {"law_code": "IIT_LAW", "article_number": "第11条",
     "content": "居民个人取得综合所得，按年计算个人所得税；有扣缴义务人的，由扣缴义务人按月或者按次预扣预缴税款；需要办理汇算清缴的，应当在取得所得的次年三月一日至六月三十日内办理汇算清缴。预扣预缴办法由国务院税务主管部门制定。居民个人向扣缴义务人提供专项附加扣除信息的，扣缴义务人按月预扣预缴税款时应当按照规定予以扣除，不得拒绝。非居民个人取得工资、薪金所得，劳务报酬所得，稿酬所得和特许权使用费所得，有扣缴义务人的，由扣缴义务人按月或者按次代扣代缴税款，不办理汇算清缴。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "居民个人取得综合所得，按年计算个"},
    {"law_code": "IIT_LAW", "article_number": "第12条",
     "content": "纳税人取得经营所得，按年计算个人所得税，由纳税人在月度或者季度终了后十五日内向税务机关报送纳税申报表，并预缴税款；在取得所得的次年三月三十一日前办理汇算清缴。纳税人取得利息、股息、红利所得，财产租赁所得，财产转让所得和偶然所得，按月或者按次计算个人所得税，有扣缴义务人的，由扣缴义务人按月或者按次代扣代缴税款。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "纳税人取得经营所得，按年计算个人"},
    {"law_code": "IIT_LAW", "article_number": "第13条",
     "content": "纳税人取得应税所得没有扣缴义务人的，应当在取得所得的次月十五日内向税务机关报送纳税申报表，并缴纳税款。纳税人取得应税所得，扣缴义务人未扣缴税款的，纳税人应当在取得所得的次年六月三十日前，缴纳税款；税务机关通知限期缴纳的，纳税人应当按照期限缴纳税款。居民个人从中国境外取得所得的，应当在取得所得的次年三月一日至六月三十日内申报纳税。非居民个人在中国境内从两处以上取得工资、薪金所得的，应当在取得所得的次月十五日内申报纳税。纳税人因移居境外注销中国户籍的，应当在注销中国户籍前办理税款清算。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "纳税人取得应税所得没有扣缴义务人"},
    {"law_code": "IIT_LAW", "article_number": "第14条",
     "content": "扣缴义务人每月或者每次预扣、代扣的税款，应当在次月十五日内缴入国库，并向税务机关报送扣缴个人所得税申报表。纳税人办理汇算清缴退税或者扣缴义务人为纳税人办理汇算清缴退税的，税务机关审核后，按照国库管理的有关规定办理退税。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "扣缴义务人每月或者每次预扣、代扣"},
    {"law_code": "IIT_LAW", "article_number": "第15条",
     "content": "公安、人民银行、金融监督管理等相关部门应当协助税务机关确认纳税人的身份、金融账户信息。教育、卫生、医疗保障、民政、人力资源社会保障、住房城乡建设、公安、人民银行、金融监督管理等相关部门应当向税务机关提供纳税人子女教育、继续教育、大病医疗、住房贷款利息、住房租金、赡养老人等专项附加扣除信息。个人转让不动产的，税务机关应当根据不动产登记等相关信息核验应缴的个人所得税，登记机构办理转移登记时，应当查验与该不动产转让相关的个人所得税的完税凭证。个人转让股权办理变更登记的，市场主体登记机关应当查验与该股权交易相关的个人所得税的完税凭证。有关部门依法将纳税人、扣缴义务人遵守本法的情况纳入信用信息系统，并实施联合激励或者惩戒。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "公安、人民银行、金融监督管理等相"},
    {"law_code": "IIT_LAW", "article_number": "第16条",
     "content": "各项所得的计算，以人民币为单位。所得为人民币以外的货币的，按照人民币汇率中间价折合成人民币缴纳税款。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "各项所得的计算，以人民币为单位。"},
    {"law_code": "IIT_LAW", "article_number": "第17条",
     "content": "对扣缴义务人按照所扣缴的税款，付给百分之二的手续费。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "对扣缴义务人按照所扣缴的税款，付"},
    {"law_code": "IIT_LAW", "article_number": "第18条",
     "content": "对储蓄存款利息所得开征、减征、停征个人所得税及其具体办法，由国务院规定，并报全国人民代表大会常务委员会备案。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "对储蓄存款利息所得开征、减征、停"},
    {"law_code": "IIT_LAW", "article_number": "第19条",
     "content": "纳税人、扣缴义务人和税务机关及其工作人员违反本法规定的，依照《中华人民共和国税收征收管理法》和有关法律法规的规定追究法律责任。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "纳税人、扣缴义务人和税务机关及其"},
    {"law_code": "IIT_LAW", "article_number": "第20条",
     "content": "个人所得税的征收管理，依照本法和《中华人民共和国税收征收管理法》的规定执行。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "个人所得税的征收管理，依照本法和"},
    {"law_code": "IIT_LAW", "article_number": "第21条",
     "content": "国务院根据本法制定实施条例。",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "国务院根据本法制定实施条例。"},
    {"law_code": "IIT_LAW", "article_number": "第22条",
     "content": "本法自公布之日起施行。个人所得税税率表一（综合所得适用）级数全年应纳税所得额税率（％）1不超过36000元的32超过36000元至144000元的部分103超过144000元至300000元的部分204超过300000元至420000元的部分255超过420000元至660000元的部分306超过660000元至960000元的部分357超过960000元的部分45个人所得税税率表二（经营所得适用）级数全年应纳税所得额税率（％）1不超过30000元的52超过30000元至90000元的部分103超过90000元至300000元的部分204超过300000元至500000元的部分305超过500000元的部分35扫一扫，手机阅读更方便中华人民共和国个人所得税法（2018修正）PAGE/NUMPAGESPAGE/NUMPAGES",
     "effective_date": "2019-01-01", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "本法自公布之日起施行。个人所得税"},

    # ===================== 企业所得税法 EIT_LAW (2018-12-29) =====================
    {"law_code": "EIT_LAW", "article_number": "第1条",
     "content": "在中华人民共和国境内，企业和其他取得收入的组织（以下统称企业）为企业所得税的纳税人，依照本法的规定缴纳企业所得税。个人独资企业、合伙企业不适用本法。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "在中华人民共和国境内，企业和其他"},
    {"law_code": "EIT_LAW", "article_number": "第2条",
     "content": "企业分为居民企业和非居民企业。本法所称居民企业，是指依法在中国境内成立，或者依照外国（地区）法律成立但实际管理机构在中国境内的企业。本法所称非居民企业，是指依照外国（地区）法律成立且实际管理机构不在中国境内，但在中国境内设立机构、场所的，或者在中国境内未设立机构、场所，但有来源于中国境内所得的企业。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业分为居民企业和非居民企业。本"},
    {"law_code": "EIT_LAW", "article_number": "第3条",
     "content": "居民企业应当就其来源于中国境内、境外的所得缴纳企业所得税。非居民企业在中国境内设立机构、场所的，应当就其所设机构、场所取得的来源于中国境内的所得，以及发生在中国境外但与其所设机构、场所有实际联系的所得，缴纳企业所得税。非居民企业在中国境内未设立机构、场所的，或者虽设立机构、场所但取得的所得与其所设机构、场所没有实际联系的，应当就其来源于中国境内的所得缴纳企业所得税。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "居民企业应当就其来源于中国境内、"},
    {"law_code": "EIT_LAW", "article_number": "第4条",
     "content": "企业所得税的税率为25％。非居民企业取得本法第三条第三款规定的所得，适用税率为20％。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业所得税的税率为25％。非居民"},
    {"law_code": "EIT_LAW", "article_number": "第5条",
     "content": "企业每一纳税年度的收入总额，减除不征税收入、免税收入、各项扣除以及允许弥补的以前年度亏损后的余额，为应纳税所得额。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业每一纳税年度的收入总额，减除"},
    {"law_code": "EIT_LAW", "article_number": "第6条",
     "content": "企业以货币形式和非货币形式从各种来源取得的收入，为收入总额。包括：（一）销售货物收入；（二）提供劳务收入；（三）转让财产收入；（四）股息、红利等权益性投资收益；（五）利息收入；（六）租金收入；（七）特许权使用费收入；（八）接受捐赠收入；（九）其他收入。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业以货币形式和非货币形式从各种"},
    {"law_code": "EIT_LAW", "article_number": "第7条",
     "content": "收入总额中的下列收入为不征税收入：（一）财政拨款；（二）依法收取并纳入财政管理的行政事业性收费、政府性基金；（三）国务院规定的其他不征税收入。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "收入总额中的下列收入为不征税收入"},
    {"law_code": "EIT_LAW", "article_number": "第8条",
     "content": "企业实际发生的与取得收入有关的、合理的支出，包括成本、费用、税金、损失和其他支出，准予在计算应纳税所得额时扣除。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业实际发生的与取得收入有关的、"},
    {"law_code": "EIT_LAW", "article_number": "第9条",
     "content": "企业发生的公益性捐赠支出，在年度利润总额12％以内的部分，准予在计算应纳税所得额时扣除；超过年度利润总额12％的部分，准予结转以后三年内在计算应纳税所得额时扣除。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业发生的公益性捐赠支出，在年度"},
    {"law_code": "EIT_LAW", "article_number": "第10条",
     "content": "在计算应纳税所得额时，下列支出不得扣除：（一）向投资者支付的股息、红利等权益性投资收益款项；（二）企业所得税税款；（三）税收滞纳金；（四）罚金、罚款和被没收财物的损失；（五）本法第九条规定以外的捐赠支出；（六）赞助支出；（七）未经核定的准备金支出；（八）与取得收入无关的其他支出。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "在计算应纳税所得额时，下列支出不"},
    {"law_code": "EIT_LAW", "article_number": "第11条",
     "content": "在计算应纳税所得额时，企业按照规定计算的固定资产折旧，准予扣除。下列固定资产不得计算折旧扣除：（一）房屋、建筑物以外未投入使用的固定资产；（二）以经营租赁方式租入的固定资产；（三）以融资租赁方式租出的固定资产；（四）已足额提取折旧仍继续使用的固定资产；（五）与经营活动无关的固定资产；（六）单独估价作为固定资产入账的土地；（七）其他不得计算折旧扣除的固定资产。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "在计算应纳税所得额时，企业按照规"},
    {"law_code": "EIT_LAW", "article_number": "第12条",
     "content": "在计算应纳税所得额时，企业按照规定计算的无形资产摊销费用，准予扣除。下列无形资产不得计算摊销费用扣除：（一）自行开发的支出已在计算应纳税所得额时扣除的无形资产；（二）自创商誉；（三）与经营活动无关的无形资产；（四）其他不得计算摊销费用扣除的无形资产。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "在计算应纳税所得额时，企业按照规"},
    {"law_code": "EIT_LAW", "article_number": "第13条",
     "content": "在计算应纳税所得额时，企业发生的下列支出作为长期待摊费用，按照规定摊销的，准予扣除：（一）已足额提取折旧的固定资产的改建支出；（二）租入固定资产的改建支出；（三）固定资产的大修理支出；（四）其他应当作为长期待摊费用的支出。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "在计算应纳税所得额时，企业发生的"},
    {"law_code": "EIT_LAW", "article_number": "第14条",
     "content": "企业对外投资期间，投资资产的成本在计算应纳税所得额时不得扣除。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业对外投资期间，投资资产的成本"},
    {"law_code": "EIT_LAW", "article_number": "第15条",
     "content": "企业使用或者销售存货，按照规定计算的存货成本，准予在计算应纳税所得额时扣除。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业使用或者销售存货，按照规定计"},
    {"law_code": "EIT_LAW", "article_number": "第16条",
     "content": "企业转让资产，该项资产的净值，准予在计算应纳税所得额时扣除。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业转让资产，该项资产的净值，准"},
    {"law_code": "EIT_LAW", "article_number": "第17条",
     "content": "企业在汇总计算缴纳企业所得税时，其境外营业机构的亏损不得抵减境内营业机构的盈利。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业在汇总计算缴纳企业所得税时，"},
    {"law_code": "EIT_LAW", "article_number": "第18条",
     "content": "企业纳税年度发生的亏损，准予向以后年度结转，用以后年度的所得弥补，但结转年限最长不得超过五年。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业纳税年度发生的亏损，准予向以"},
    {"law_code": "EIT_LAW", "article_number": "第19条",
     "content": "非居民企业取得本法第三条第三款规定的所得，按照下列方法计算其应纳税所得额：（一）股息、红利等权益性投资收益和利息、租金、特许权使用费所得，以收入全额为应纳税所得额；（二）转让财产所得，以收入全额减除财产净值后的余额为应纳税所得额；（三）其他所得，参照前两项规定的方法计算应纳税所得额。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "非居民企业取得本法第三条第三款规"},
    {"law_code": "EIT_LAW", "article_number": "第20条",
     "content": "本章规定的收入、扣除的具体范围、标准和资产的税务处理的具体办法，由国务院财政、税务主管部门规定。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "本章规定的收入、扣除的具体范围、"},
    {"law_code": "EIT_LAW", "article_number": "第21条",
     "content": "在计算应纳税所得额时，企业财务、会计处理办法与税收法律、行政法规的规定不一致的，应当依照税收法律、行政法规的规定计算。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "在计算应纳税所得额时，企业财务、"},
    {"law_code": "EIT_LAW", "article_number": "第22条",
     "content": "企业的应纳税所得额乘以适用税率，减除依照本法关于税收优惠的规定减免和抵免的税额后的余额，为应纳税额。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业的应纳税所得额乘以适用税率，"},
    {"law_code": "EIT_LAW", "article_number": "第23条",
     "content": "企业取得的下列所得已在境外缴纳的所得税税额，可以从其当期应纳税额中抵免，抵免限额为该项所得依照本法规定计算的应纳税额；超过抵免限额的部分，可以在以后五个年度内，用每年度抵免限额抵免当年应抵税额后的余额进行抵补：（一）居民企业来源于中国境外的应税所得；（二）非居民企业在中国境内设立机构、场所，取得发生在中国境外但与该机构、场所有实际联系的应税所得。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业取得的下列所得已在境外缴纳的"},
    {"law_code": "EIT_LAW", "article_number": "第24条",
     "content": "居民企业从其直接或者间接控制的外国企业分得的来源于中国境外的股息、红利等权益性投资收益，外国企业在境外实际缴纳的所得税税额中属于该项所得负担的部分，可以作为该居民企业的可抵免境外所得税税额，在本法第二十三条规定的抵免限额内抵免。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "居民企业从其直接或者间接控制的外"},
    {"law_code": "EIT_LAW", "article_number": "第25条",
     "content": "国家对重点扶持和鼓励发展的产业和项目，给予企业所得税优惠。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "国家对重点扶持和鼓励发展的产业和"},
    {"law_code": "EIT_LAW", "article_number": "第26条",
     "content": "企业的下列收入为免税收入：（一）国债利息收入；（二）符合条件的居民企业之间的股息、红利等权益性投资收益；（三）在中国境内设立机构、场所的非居民企业从居民企业取得与该机构、场所有实际联系的股息、红利等权益性投资收益；（四）符合条件的非营利组织的收入。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业的下列收入为免税收入：（一）"},
    {"law_code": "EIT_LAW", "article_number": "第27条",
     "content": "企业的下列所得，可以免征、减征企业所得税：（一）从事农、林、牧、渔业项目的所得；（二）从事国家重点扶持的公共基础设施项目投资经营的所得；（三）从事符合条件的环境保护、节能节水项目的所得；（四）符合条件的技术转让所得；（五）本法第三条第三款规定的所得。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业的下列所得，可以免征、减征企"},
    {"law_code": "EIT_LAW", "article_number": "第28条",
     "content": "符合条件的小型微利企业，减按20％的税率征收企业所得税。国家需要重点扶持的高新技术企业，减按15％的税率征收企业所得税。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "符合条件的小型微利企业，减按20"},
    {"law_code": "EIT_LAW", "article_number": "第29条",
     "content": "民族自治地方的自治机关对本民族自治地方的企业应缴纳的企业所得税中属于地方分享的部分，可以决定减征或者免征。自治州、自治县决定减征或者免征的，须报省、自治区、直辖市人民政府批准。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "民族自治地方的自治机关对本民族自"},
    {"law_code": "EIT_LAW", "article_number": "第30条",
     "content": "企业的下列支出，可以在计算应纳税所得额时加计扣除：（一）开发新技术、新产品、新工艺发生的研究开发费用；（二）安置残疾人员及国家鼓励安置的其他就业人员所支付的工资。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业的下列支出，可以在计算应纳税"},
    {"law_code": "EIT_LAW", "article_number": "第31条",
     "content": "创业投资企业从事国家需要重点扶持和鼓励的创业投资，可以按投资额的一定比例抵扣应纳税所得额。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "创业投资企业从事国家需要重点扶持"},
    {"law_code": "EIT_LAW", "article_number": "第32条",
     "content": "企业的固定资产由于技术进步等原因，确需加速折旧的，可以缩短折旧年限或者采取加速折旧的方法。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业的固定资产由于技术进步等原因"},
    {"law_code": "EIT_LAW", "article_number": "第33条",
     "content": "企业综合利用资源，生产符合国家产业政策规定的产品所取得的收入，可以在计算应纳税所得额时减计收入。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业综合利用资源，生产符合国家产"},
    {"law_code": "EIT_LAW", "article_number": "第34条",
     "content": "企业购置用于环境保护、节能节水、安全生产等专用设备的投资额，可以按一定比例实行税额抵免。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业购置用于环境保护、节能节水、"},
    {"law_code": "EIT_LAW", "article_number": "第35条",
     "content": "本法规定的税收优惠的具体办法，由国务院规定。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "本法规定的税收优惠的具体办法，由"},
    {"law_code": "EIT_LAW", "article_number": "第36条",
     "content": "根据国民经济和社会发展的需要，或者由于突发事件等原因对企业经营活动产生重大影响的，国务院可以制定企业所得税专项优惠政策，报全国人民代表大会常务委员会备案。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "根据国民经济和社会发展的需要，或"},
    {"law_code": "EIT_LAW", "article_number": "第37条",
     "content": "对非居民企业取得本法第三条第三款规定的所得应缴纳的所得税，实行源泉扣缴，以支付人为扣缴义务人。税款由扣缴义务人在每次支付或者到期应支付时，从支付或者到期应支付的款项中扣缴。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "对非居民企业取得本法第三条第三款"},
    {"law_code": "EIT_LAW", "article_number": "第38条",
     "content": "对非居民企业在中国境内取得工程作业和劳务所得应缴纳的所得税，税务机关可以指定工程价款或者劳务费的支付人为扣缴义务人。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "对非居民企业在中国境内取得工程作"},
    {"law_code": "EIT_LAW", "article_number": "第39条",
     "content": "依照本法第三十七条、第三十八条规定应当扣缴的所得税，扣缴义务人未依法扣缴或者无法履行扣缴义务的，由纳税人在所得发生地缴纳。纳税人未依法缴纳的，税务机关可以从该纳税人在中国境内其他收入项目的支付人应付的款项中，追缴该纳税人的应纳税款。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "依照本法第三十七条、第三十八条规"},
    {"law_code": "EIT_LAW", "article_number": "第40条",
     "content": "扣缴义务人每次代扣的税款，应当自代扣之日起七日内缴入国库，并向所在地的税务机关报送扣缴企业所得税报告表。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "扣缴义务人每次代扣的税款，应当自"},
    {"law_code": "EIT_LAW", "article_number": "第41条",
     "content": "企业与其关联方之间的业务往来，不符合独立交易原则而减少企业或者其关联方应纳税收入或者所得额的，税务机关有权按照合理方法调整。企业与其关联方共同开发、受让无形资产，或者共同提供、接受劳务发生的成本，在计算应纳税所得额时应当按照独立交易原则进行分摊。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业与其关联方之间的业务往来，不"},
    {"law_code": "EIT_LAW", "article_number": "第42条",
     "content": "企业可以向税务机关提出与其关联方之间业务往来的定价原则和计算方法，税务机关与企业协商、确认后，达成预约定价安排。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业可以向税务机关提出与其关联方"},
    {"law_code": "EIT_LAW", "article_number": "第43条",
     "content": "企业向税务机关报送年度企业所得税纳税申报表时，应当就其与关联方之间的业务往来，附送年度关联业务往来报告表。税务机关在进行关联业务调查时，企业及其关联方，以及与关联业务调查有关的其他企业，应当按照规定提供相关资料。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业向税务机关报送年度企业所得税"},
    {"law_code": "EIT_LAW", "article_number": "第44条",
     "content": "企业不提供与其关联方之间业务往来资料，或者提供虚假、不完整资料，未能真实反映其关联业务往来情况的，税务机关有权依法核定其应纳税所得额。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业不提供与其关联方之间业务往来"},
    {"law_code": "EIT_LAW", "article_number": "第45条",
     "content": "由居民企业，或者由居民企业和中国居民控制的设立在实际税负明显低于本法第四条第一款规定税率水平的国家（地区）的企业，并非由于合理的经营需要而对利润不作分配或者减少分配的，上述利润中应归属于该居民企业的部分，应当计入该居民企业的当期收入。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "由居民企业，或者由居民企业和中国"},
    {"law_code": "EIT_LAW", "article_number": "第46条",
     "content": "企业从其关联方接受的债权性投资与权益性投资的比例超过规定标准而发生的利息支出，不得在计算应纳税所得额时扣除。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业从其关联方接受的债权性投资与"},
    {"law_code": "EIT_LAW", "article_number": "第47条",
     "content": "企业实施其他不具有合理商业目的的安排而减少其应纳税收入或者所得额的，税务机关有权按照合理方法调整。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业实施其他不具有合理商业目的的"},
    {"law_code": "EIT_LAW", "article_number": "第48条",
     "content": "税务机关依照本章规定作出纳税调整，需要补征税款的，应当补征税款，并按照国务院规定加收利息。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "税务机关依照本章规定作出纳税调整"},
    {"law_code": "EIT_LAW", "article_number": "第49条",
     "content": "企业所得税的征收管理除本法规定外，依照《中华人民共和国税收征收管理法》的规定执行。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业所得税的征收管理除本法规定外"},
    {"law_code": "EIT_LAW", "article_number": "第50条",
     "content": "除税收法律、行政法规另有规定外，居民企业以企业登记注册地为纳税地点；但登记注册地在境外的，以实际管理机构所在地为纳税地点。居民企业在中国境内设立不具有法人资格的营业机构的，应当汇总计算并缴纳企业所得税。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "除税收法律、行政法规另有规定外，"},
    {"law_code": "EIT_LAW", "article_number": "第51条",
     "content": "非居民企业取得本法第三条第二款规定的所得，以机构、场所所在地为纳税地点。非居民企业在中国境内设立两个或者两个以上机构、场所，符合国务院税务主管部门规定条件的，可以选择由其主要机构、场所汇总缴纳企业所得税。非居民企业取得本法第三条第三款规定的所得，以扣缴义务人所在地为纳税地点。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "非居民企业取得本法第三条第二款规"},
    {"law_code": "EIT_LAW", "article_number": "第52条",
     "content": "除国务院另有规定外，企业之间不得合并缴纳企业所得税。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "除国务院另有规定外，企业之间不得"},
    {"law_code": "EIT_LAW", "article_number": "第53条",
     "content": "企业所得税按纳税年度计算。纳税年度自公历1月1日起至12月31日止。企业在一个纳税年度中间开业，或者终止经营活动，使该纳税年度的实际经营期不足十二个月的，应当以其实际经营期为一个纳税年度。企业依法清算时，应当以清算期间作为一个纳税年度。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业所得税按纳税年度计算。纳税年"},
    {"law_code": "EIT_LAW", "article_number": "第54条",
     "content": "企业所得税分月或者分季预缴。企业应当自月份或者季度终了之日起十五日内，向税务机关报送预缴企业所得税纳税申报表，预缴税款。企业应当自年度终了之日起五个月内，向税务机关报送年度企业所得税纳税申报表，并汇算清缴，结清应缴应退税款。企业在报送企业所得税纳税申报表时，应当按照规定附送财务会计报告和其他有关资料。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业所得税分月或者分季预缴。企业"},
    {"law_code": "EIT_LAW", "article_number": "第55条",
     "content": "企业在年度中间终止经营活动的，应当自实际经营终止之日起六十日内，向税务机关办理当期企业所得税汇算清缴。企业应当在办理注销登记前，就其清算所得向税务机关申报并依法缴纳企业所得税。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "企业在年度中间终止经营活动的，应"},
    {"law_code": "EIT_LAW", "article_number": "第56条",
     "content": "依照本法缴纳的企业所得税，以人民币计算。所得以人民币以外的货币计算的，应当折合成人民币计算并缴纳税款。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "依照本法缴纳的企业所得税，以人民"},
    {"law_code": "EIT_LAW", "article_number": "第57条",
     "content": "本法公布前已经批准设立的企业，依照当时的税收法律、行政法规规定，享受低税率优惠的，按照国务院规定，可以在本法施行后五年内，逐步过渡到本法规定的税率；享受定期减免税优惠的，按照国务院规定，可以在本法施行后继续享受到期满为止，但因未获利而尚未享受优惠的，优惠期限从本法施行年度起计算。法律设置的发展对外经济合作和技术交流的特定地区内，以及国务院已规定执行上述地区特殊政策的地区内新设立的国家需要重点扶持的高新技术企业，可以享受过渡性税收优惠，具体办法由国务院规定。国家已确定的其他鼓励类企业，可以按照国务院规定享受减免税优惠。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "本法公布前已经批准设立的企业，依"},
    {"law_code": "EIT_LAW", "article_number": "第58条",
     "content": "中华人民共和国政府同外国政府订立的有关税收的协定与本法有不同规定的，依照协定的规定办理。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "中华人民共和国政府同外国政府订立"},
    {"law_code": "EIT_LAW", "article_number": "第59条",
     "content": "国务院根据本法制定实施条例。",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "国务院根据本法制定实施条例。"},
    {"law_code": "EIT_LAW", "article_number": "第60条",
     "content": "本法自2008年1月1日起施行。1991年4月9日第七届全国人民代表大会第四次会议通过的《中华人民共和国外商投资企业和外国企业所得税法》和1993年12月13日国务院发布的《中华人民共和国企业所得税暂行条例》同时废止。扫一扫，手机阅读更方便中华人民共和国企业所得税法（2018修正）PAGE/NUMPAGESPAGE/NUMPAGES",
     "effective_date": "2018-12-29", "source_url": "https://flk.npc.gov.cn/",
     "source_accessed_at": "2026-08-06", "notes": "本法自2008年1月1日起施行。"},

    # ===================== 增值税法 VAT_LAW (2026-01-01) =====================
    # 2024-12-25 第十四届全国人大常委会第十三次会议通过，2026-01-01 施行；
    # 同步废止《增值税暂行条例》。以下为 Phase 1 实体税法 pilot 的起草节点
    # （SEED 草稿，默认 unverified，待专家对照 flk.npc.gov.cn 核验后翻 verified）。
    {"law_code": "VAT_LAW", "article_number": "第3条",
     "content": "在中华人民共和国境内（以下简称境内）销售货物、服务、无形资产、不动产（以下称应税交易），以及进口货物的单位和个人（包括个体工商户），为增值税的纳税人，应当依照本法规定缴纳增值税。销售货物、服务、无形资产、不动产，是指有偿转让货物、不动产的所有权，有偿提供服务，有偿转让无形资产的所有权或者使用权。",
     "effective_date": "2026-01-01",
     "source_url": "https://www.gov.cn/yaowen/liebiao/202412/content_6994557.htm",
     "source_accessed_at": "2026-08-05", "notes": "纳税人/应税交易定义"},
    {"law_code": "VAT_LAW", "article_number": "第4条",
     "content": "在境内发生应税交易，是指下列情形：（一）销售货物的，货物的起运地或者所在地在境内；（二）销售或者租赁不动产、转让自然资源使用权的，不动产、自然资源所在地在境内；（三）销售金融商品的，金融商品在境内发行，或者销售方为境内单位和个人；（四）除本条第二项、第三项规定外，销售服务、无形资产的，服务、无形资产在境内消费，或者销售方为境内单位和个人。",
     "effective_date": "2026-01-01",
     "source_url": "https://www.gov.cn/yaowen/liebiao/202412/content_6994557.htm",
     "source_accessed_at": "2026-08-05", "notes": "境内应税交易认定"},
    {"law_code": "VAT_LAW", "article_number": "第5条",
     "content": "有下列情形之一的，视同应税交易，应当依照本法规定缴纳增值税：（一）单位和个体工商户将自产或者委托加工的货物用于集体福利或者个人消费；（二）单位和个体工商户无偿转让货物；（三）单位和个人无偿转让无形资产、不动产或者金融商品。",
     "effective_date": "2026-01-01",
     "source_url": "https://www.gov.cn/yaowen/liebiao/202412/content_6994557.htm",
     "source_accessed_at": "2026-08-05", "notes": "视同应税交易"},
    {"law_code": "VAT_LAW", "article_number": "第8条",
     "content": "纳税人发生应税交易，应当按照一般计税方法，通过销项税额抵扣进项税额计算应纳税额的方式，计算缴纳增值税；本法另有规定的除外。小规模纳税人可以按照销售额和征收率计算应纳税额的简易计税方法，计算缴纳增值税。中外合作开采海洋石油、天然气增值税的计税方法等，按照国务院的有关规定执行。",
     "effective_date": "2026-01-01",
     "source_url": "https://www.gov.cn/yaowen/liebiao/202412/content_6994557.htm",
     "source_accessed_at": "2026-08-05", "notes": "一般计税/简易计税"},
    {"law_code": "VAT_LAW", "article_number": "第9条",
     "content": "本法所称小规模纳税人，是指年应征增值税销售额未超过五百万元的纳税人。小规模纳税人会计核算健全，能够提供准确税务资料的，可以向主管税务机关办理登记，按照本法规定的一般计税方法计算缴纳增值税。根据国民经济和社会发展的需要，国务院可以对小规模纳税人的标准作出调整，报全国人民代表大会常务委员会备案。",
     "effective_date": "2026-01-01",
     "source_url": "https://www.gov.cn/yaowen/liebiao/202412/content_6994557.htm",
     "source_accessed_at": "2026-08-05", "notes": "小规模纳税人标准（500万）"},
    {"law_code": "VAT_LAW", "article_number": "第10条",
     "content": "增值税税率：（一）纳税人销售货物、加工修理修配服务、有形动产租赁服务，进口货物，除本条第二项、第四项、第五项规定外，税率为百分之十三。（二）纳税人销售交通运输、邮政、基础电信、建筑、不动产租赁服务，销售不动产，转让土地使用权，销售或者进口下列货物，除本条第四项、第五项规定外，税率为百分之九：1.农产品、食用植物油、食用盐；2.自来水、暖气、冷气、热水、煤气、石油液化气、天然气、二甲醚、沼气、居民用煤炭制品；3.图书、报纸、杂志、音像制品、电子出版物；4.饲料、化肥、农药、农机、农膜。（三）纳税人销售服务、无形资产，除本条第一项、第二项、第五项规定外，税率为百分之六。（四）纳税人出口货物，税率为零；国务院另有规定的除外。（五）境内单位和个人跨境销售国务院规定范围内的服务、无形资产，税率为零。",
     "effective_date": "2026-01-01",
     "source_url": "https://www.gov.cn/yaowen/liebiao/202412/content_6994557.htm",
     "source_accessed_at": "2026-08-05", "notes": "税率（13%/9%/6%/0）"},
    {"law_code": "VAT_LAW", "article_number": "第11条",
     "content": "适用简易计税方法计算缴纳增值税的征收率为百分之三。",
     "effective_date": "2026-01-01",
     "source_url": "https://www.gov.cn/yaowen/liebiao/202412/content_6994557.htm",
     "source_accessed_at": "2026-08-05", "notes": "征收率3%"},
    {"law_code": "VAT_LAW", "article_number": "第14条",
     "content": "按照一般计税方法计算缴纳增值税的，应纳税额为当期销项税额抵扣当期进项税额后的余额。按照简易计税方法计算缴纳增值税的，应纳税额为当期销售额乘以征收率。进口货物，按照本法规定的组成计税价格乘以适用税率计算缴纳增值税。组成计税价格，为关税计税价格加上关税和消费税；国务院另有规定的，从其规定。",
     "effective_date": "2026-01-01",
     "source_url": "https://www.gov.cn/yaowen/liebiao/202412/content_6994557.htm",
     "source_accessed_at": "2026-08-05", "notes": "应纳税额（销项抵进项）"},
    {"law_code": "VAT_LAW", "article_number": "第16条",
     "content": "销项税额，是指纳税人发生应税交易，按照销售额乘以本法规定的税率计算的增值税税额。进项税额，是指纳税人购进货物、服务、无形资产、不动产支付或者负担的增值税税额。纳税人应当凭法律、行政法规或者国务院规定的增值税扣税凭证从销项税额中抵扣进项税额。",
     "effective_date": "2026-01-01",
     "source_url": "https://www.gov.cn/yaowen/liebiao/202412/content_6994557.htm",
     "source_accessed_at": "2026-08-05", "notes": "销项/进项定义"},
    {"law_code": "VAT_LAW", "article_number": "第21条",
     "content": "当期进项税额大于当期销项税额的部分，纳税人可以按照国务院的规定选择结转下期继续抵扣或者申请退还。",
     "effective_date": "2026-01-01",
     "source_url": "https://www.gov.cn/yaowen/liebiao/202412/content_6994557.htm",
     "source_accessed_at": "2026-08-05", "notes": "留抵退税（结转/退还）"},
    {"law_code": "VAT_LAW", "article_number": "第22条",
     "content": "纳税人的下列进项税额不得从其销项税额中抵扣：（一）适用简易计税方法计税项目对应的进项税额；（二）免征增值税项目对应的进项税额；（三）非正常损失项目对应的进项税额；（四）购进并用于集体福利或者个人消费的货物、服务、无形资产、不动产对应的进项税额；（五）购进并直接用于消费的餐饮服务、居民日常服务和娱乐服务对应的进项税额；（六）国务院规定的其他进项税额。",
     "effective_date": "2026-01-01",
     "source_url": "https://www.gov.cn/yaowen/liebiao/202412/content_6994557.htm",
     "source_accessed_at": "2026-08-05", "notes": "不得抵扣的进项税额"},
    {"law_code": "VAT_LAW", "article_number": "第23条",
     "content": "小规模纳税人发生应税交易，销售额未达到起征点的，免征增值税；达到起征点的，依照本法规定全额计算缴纳增值税。前款规定的起征点标准由国务院规定，报全国人民代表大会常务委员会备案。",
     "effective_date": "2026-01-01",
     "source_url": "https://www.gov.cn/yaowen/liebiao/202412/content_6994557.htm",
     "source_accessed_at": "2026-08-05", "notes": "起征点免税"},
    {"law_code": "VAT_LAW", "article_number": "第24条",
     "content": "下列项目免征增值税：（一）农业生产者销售的自产农产品，农业机耕、排灌、病虫害防治、植物保护、农牧保险以及相关技术培训业务，家禽、牲畜、水生动物的配种和疾病防治；（二）医疗机构提供的医疗服务；（三）古旧图书，自然人销售的自己使用过的物品；（四）直接用于科学研究、科学试验和教学的进口仪器、设备；（五）外国政府、国际组织无偿援助的进口物资和设备；（六）由残疾人的组织直接进口供残疾人专用的物品，残疾人个人提供的服务；（七）托儿所、幼儿园、养老机构、残疾人服务机构提供的育养服务，婚姻介绍服务，殡葬服务；（八）学校提供的学历教育服务，学生勤工俭学提供的服务；（九）纪念馆、博物馆、文化馆、文物保护单位管理机构、美术馆、展览馆、书画院、图书馆举办文化活动的门票收入，宗教场所举办文化、宗教活动的门票收入。前款规定的免税项目具体标准由国务院规定。",
     "effective_date": "2026-01-01",
     "source_url": "https://www.gov.cn/yaowen/liebiao/202412/content_6994557.htm",
     "source_accessed_at": "2026-08-05", "notes": "免征增值税项目"},
    {"law_code": "VAT_LAW", "article_number": "第28条",
     "content": "增值税纳税义务发生时间，按照下列规定确定：（一）发生应税交易，纳税义务发生时间为收讫销售款项或者取得销售款项索取凭据的当日；先开具发票的，为开具发票的当日。（二）发生视同应税交易，纳税义务发生时间为完成视同应税交易的当日。（三）进口货物，纳税义务发生时间为货物报关进口的当日。增值税扣缴义务发生时间为纳税人增值税纳税义务发生的当日。",
     "effective_date": "2026-01-01",
     "source_url": "https://www.gov.cn/yaowen/liebiao/202412/content_6994557.htm",
     "source_accessed_at": "2026-08-05", "notes": "纳税义务发生时间"},
    {"law_code": "VAT_LAW", "article_number": "第30条",
     "content": "增值税的计税期间分别为十日、十五日、一个月或者一个季度。纳税人的具体计税期间，由主管税务机关根据纳税人应纳税额的大小分别核定。不经常发生应税交易的纳税人，可以按次纳税。纳税人以一个月或者一个季度为一个计税期间的，自期满之日起十五日内申报纳税；以十日或者十五日为一个计税期间的，自次月一日起十五日内申报纳税。扣缴义务人解缴税款的计税期间和申报纳税期限，依照前两款规定执行。纳税人进口货物，应当按照海关规定的期限申报并缴纳税款。",
     "effective_date": "2026-01-01",
     "source_url": "https://www.gov.cn/yaowen/liebiao/202412/content_6994557.htm",
     "source_accessed_at": "2026-08-05", "notes": "计税期间与申报期限"},
]


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
_ZHI = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}


def _parse_sort_key(article_number: str) -> float:
    """Numeric sort/group key for an article_number string.

    Aligns with the decimal scheme used by ``loader`` / ``build_law_pack`` so a
    sub-article '之一/之二/之三' (e.g. 第234条之一 -> 234.001) occupies its own
    (law_code, sort_key) slot and never chains onto the parent article during
    window-integrity validation. Return type is float to preserve the fractional
    sub-article offset; plain articles return an integral float (e.g. 234.0).
    """
    m = re.search(r"(\d+)", article_number)
    if not m:
        raise ValueError(f"cannot parse article number from {article_number!r}")
    base = int(m.group(1))
    suf = re.search(r"之([一二三四五六七八九])", article_number)
    if suf:
        return base + _ZHI[suf.group(1)] / 1000.0
    return float(base)


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
