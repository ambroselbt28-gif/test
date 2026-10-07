# -*- coding: utf-8 -*-
"""
把 世界书v2_世界一试改/ 里的条目和提示词套到现有角色卡 JSON 上，生成 v2 测试卡。
只替换下表列出的条目内容和两段提示词，并加入思维链正则（与 pack.js 读取 *.regex.json 的方式一致），其余字段（条目 key、关键词、开关、页面资源配置等）原样保留。
原角色卡和原条目文件都不会被修改。

用法（在项目根目录或本文件夹里运行均可）：
    python3 世界书v2_世界一试改/apply_v2.py
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

VARIANTS = {
    # 输出文件名: (原角色卡, 变体)
    '修复黑月光-v2世界一试改.json': ('修复黑月光.json', 'formal'),
    '修复黑月光-charx_vars实验测试版-v2世界一试改.json': ('修复黑月光-charx_vars实验测试版.json', 'charx'),
}

W1 = '世界一_现代娱乐圈'
ENTRY_FILES = {
    'global.narrative-tone': {'formal': '根目录/[蓝灯]_AI职责与叙事基调.md', 'charx': '根目录/[蓝灯]_AI职责与叙事基调-charx-vars.md'},
    'global.pacing': '根目录/[蓝灯]_叙事风格与打脸节奏.md',
    'global.variable-rules': {'formal': '根目录/[蓝灯]_变量更新规则与输出格式.md', 'charx': '根目录/[蓝灯]_变量更新规则与输出格式-charx-vars.md'},
    'w1.architecture': W1 + '/[绿灯]_世界一娱乐圈架构.md',
    'w1.wishes': W1 + '/[绿灯]_世界一心愿清单.md',
    'w1.regret-rules': W1 + '/[绿灯]_世界一后悔值规则.md',
    'w1.evidence': W1 + '/[绿灯]_世界一关键证据.md',
    'w1.phase-rules': W1 + '/[蓝灯]_世界一阶段推进约束.md',
    'w1.shen-lingyi': W1 + '/[绿灯]_沈令仪·原主前情.md',
    'w1.fang-jie': W1 + '/[绿灯]_方姐·金牌经纪人.md',
    'w1.lin-zhiwei': W1 + '/[绿灯]_林知微·被抢角后辈.md',
    'w1.shen-tinglan': W1 + '/[绿灯]_沈听澜·被控弟弟.md',
}
PROMPT_FILES = {
    'system_prompt': {'formal': '根目录/系统提示词.md', 'charx': '根目录/系统提示词-charx-vars.md'},
    'post_history_instructions': {'formal': '根目录/对话后历史指令.md', 'charx': '根目录/对话后历史指令-charx-vars.md'},
}
# 顺序与 pack.js 读取目录时一致（按文件名排序）
REGEX_FILES = ['根目录/思维链-移出上下文', '根目录/思维链-隐藏显示']


def parse_entry_text(content):
    """与 pack.js 的 parseYamlEntry 取正文方式一致：XML 标签整段，或 --- 之后的 YAML 正文。"""
    content = content.lstrip('﻿')
    lines = content.split('\n')
    sep = next((i for i, l in enumerate(lines) if l.strip() == '---'), -1)
    start = end = -1
    tag = ''
    for i in range(sep if sep >= 0 else len(lines)):
        line = lines[i].strip()
        m = re.match(r'^<([^>/]+)>$', line)
        if m and start == -1:
            start, tag = i, m.group(1)
            continue
        m2 = re.match(r'^</([^>]+)>$', line)
        if m2 and m2.group(1) == tag:
            end = i
            break
    if start == -1 or end == -1:
        if sep == -1:
            raise ValueError('条目缺少 XML 标签或 YAML 分隔线')
        return '\n'.join(lines[sep + 1:]).strip()
    return '\n'.join(lines[start:end + 1])


def pick(spec, variant):
    return spec[variant] if isinstance(spec, dict) else spec


def read(rel):
    with open(os.path.join(HERE, rel), encoding='utf-8') as f:
        return f.read()


def load_regex(base):
    """与 pack.js 的 loadRegexScripts 一致：顶层带 flags，扩展层带 substituteRegex/minDepth/maxDepth。"""
    cfg = json.loads(read(base + '.regex.json').lstrip('\ufeff'))
    top = {
        'id': cfg['id'],
        'scriptName': cfg.get('scriptName') or os.path.basename(base),
        'findRegex': cfg['findRegex'],
        'replaceString': read(base + '.regex.html'),
        'flags': cfg.get('flags') or 'gi',
        'trimStrings': cfg.get('trimStrings') or [],
        'placement': cfg.get('placement') or [1, 2],
        'disabled': cfg.get('disabled') or False,
        'markdownOnly': cfg['markdownOnly'] if 'markdownOnly' in cfg else True,
        'promptOnly': cfg['promptOnly'] if 'promptOnly' in cfg else False,
        'runOnEdit': cfg['runOnEdit'] if 'runOnEdit' in cfg else True,
    }
    ext = {k: v for k, v in top.items() if k != 'flags'}
    ext.update({'substituteRegex': cfg.get('substituteRegex') or 0, 'minDepth': cfg.get('minDepth') or None, 'maxDepth': cfg.get('maxDepth') or None})
    return top, ext


def merge_scripts(existing, added):
    ids = {s['id'] for s in added}
    return [s for s in existing if s.get('id') not in ids] + list(added)


def build(out_name, base_name, variant):
    with open(os.path.join(ROOT, base_name), encoding='utf-8') as f:
        raw = f.read()
    card = json.loads(raw)
    data = card['data']
    entries = data['character_book']['entries']
    by_key = {e['entryKey']: e for e in entries}
    for key, spec in ENTRY_FILES.items():
        if key not in by_key:
            raise KeyError('角色卡里找不到条目 ' + key)
        by_key[key]['content'] = parse_entry_text(read(pick(spec, variant)))
    for field, spec in PROMPT_FILES.items():
        data[field] = read(pick(spec, variant)).strip()
    tops, exts = zip(*(load_regex(b) for b in REGEX_FILES))
    data['regex_scripts'] = merge_scripts(data.get('regex_scripts') or [], tops)
    data.setdefault('extensions', {})['regex_scripts'] = merge_scripts(data['extensions'].get('regex_scripts') or [], exts)
    data['character_version'] = str(data.get('character_version', '')) + '-v2世界一试改'
    with open(os.path.join(HERE, out_name), 'w', encoding='utf-8') as f:
        f.write(json.dumps(card, ensure_ascii=False, indent=2) + ('\n' if raw.endswith('\n') else ''))
    return card


if __name__ == '__main__':
    for out_name, (base_name, variant) in VARIANTS.items():
        build(out_name, base_name, variant)
        print('已生成', out_name)
