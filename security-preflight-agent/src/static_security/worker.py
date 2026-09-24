"""Bounded, offline rule evaluation. Input is data and is never executed."""
import bisect
import json
from pathlib import Path
import re
import resource
import sys

ROOT = Path(__file__).resolve().parent
MAX_FINDINGS = 100


def scan(source, entries):
    lines = source.split('\n')
    offsets = [i for i, c in enumerate(source) if c == '\n']
    findings = []
    for entry in entries:
        detection = entry['detection']
        exclusion = detection.get('exclude_regex')
        if exclusion and re.search(exclusion, source):
            continue
        corr = detection.get('corroboration')
        for match in re.finditer(detection['signature_regex'], source):
            line = bisect.bisect_left(offsets, match.start())
            confidence = detection.get('confidence', 'medium')
            fired = []
            if corr:
                window = corr.get('window_lines', 12)
                context = '\n'.join(lines[max(0, line-window):line+window+1])
                def text_for(signal, default='window'):
                    scope = signal.get('scope', default)
                    return source if scope == 'file' else lines[line] if scope == 'line' else context
                idiom = corr.get('idiom_excludes')
                if idiom and re.search(idiom['regex'], text_for(idiom, 'line')):
                    continue
                fired = [name for name, signal in corr.get('signals', {}).items()
                         if re.search(signal['regex'], text_for(signal))]
                for tier in corr.get('policy', {}).get('tiers', []):
                    if all(name in fired for name in tier.get('when', [])):
                        confidence = tier['confidence']
                        break
            levels = ['low', 'medium', 'high', 'critical']
            severity = levels[min(levels.index(entry['severity']), levels.index(confidence))]
            findings.append({'rule_id': entry['id'], 'line': line+1, 'severity': severity,
                             'confidence': confidence, 'signals': fired,
                             'mitigation': entry['mitigation'], 'references': entry['references']})
            if len(findings) >= MAX_FINDINGS:
                return {'findings': findings, 'truncated': True}
    return {'findings': findings, 'truncated': False}


def screen(texts, patterns):
    findings = []
    for index, text in enumerate(texts):
        for pattern in patterns:
            if re.search(pattern['pattern'], text, re.I if pattern['ignore_case'] else 0):
                findings.append({'sample_index': index, 'rule_id': pattern['id'],
                                 'category': pattern['category']})
                if len(findings) >= MAX_FINDINGS:
                    return {'findings': findings, 'truncated': True}
    return {'findings': findings, 'truncated': False}


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (1, 1))
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024, 256*1024*1024))
    # A 64 KiB input can expand sixfold when JSON escapes control characters.
    payload = json.loads(sys.stdin.read(600_000))
    action = payload['action']
    if action == 'scan_source':
        result = scan(payload['source'], json.loads((ROOT/'canon_rules.json').read_text()))
    elif action == 'screen_injection':
        result = screen(payload['texts'], json.loads((ROOT/'injection_rules.json').read_text()))
    else:
        raise ValueError('Unknown operation')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
