#!/usr/bin/env python3
"""Read existing public aggregates; never infer identities or missing stages."""
import argparse
import datetime as dt
import json
from pathlib import Path
import urllib.request

URL = 'https://mcp.viridisconservation.com/healthz'
TOTAL_FIELDS = ('external_settlements', 'distinct_external_payers',
    'external_paid_results_delivered', 'external_paid_results_unknown',
    'external_buyer_feedback_useful', 'repeat_external_purchases')


def count(value):
    return value if type(value) is int and value >= 0 else None


def mapping(value):
    return value if isinstance(value, dict) else {}


def build(health):
    health = mapping(health)
    funnel = mapping(mapping(health.get('subscriptions')).get('frontdoor_funnel'))
    telemetry = mapping(mapping(mapping(health.get('payment_gate')).get('x402')).get('http_settlement_telemetry'))
    total = mapping(telemetry.get('total'))
    retention = mapping(telemetry.get('retention_cohorts'))
    sources = mapping(retention.get('by_acquisition_source'))
    valid = (retention.get('version') == 'viridis-x402-retention-cohorts-v1'
             and type(retention.get('payer_count')) is int
             and all(count(mapping(g).get('payer_count')) is not None for g in sources.values())
             and sum(g['payer_count'] for g in sources.values()) == retention['payer_count']
             and retention['payer_count'] == count(total.get('distinct_external_payers')))
    github = mapping(sources.get('github')) if valid else {}
    github_payers = (count(github.get('payer_count')) if github else 0) if valid else None
    windows = {}
    for name in ('7d', '14d', '30d'):
        w = mapping(mapping(github.get('windows')).get(name))
        eligible = count(w.get('eligible_payers'))
        repeated = count(w.get('repeat_payers'))
        pending = count(w.get('pending_maturity'))
        if github_payers == 0:
            eligible, repeated, pending = 0, 0, 0
        if (None in (eligible, repeated, pending) or github_payers is None
                or repeated > eligible or eligible + pending != github_payers):
            eligible = repeated = pending = None
        windows[name] = {'eligible_payers': eligible, 'repeat_payers': repeated,
            'pending_maturity': pending,
            'repeat_rate': repeated / eligible if eligible else None}
    quotes = mapping(health.get('repo_funnel'))
    quote_groups = mapping(quotes.get('by_acquisition_source'))
    github_quotes = mapping(quote_groups.get('github'))
    quotes_valid = (quotes.get('version') == 'viridis-quote-source-counts-v1'
                    and quotes.get('status') == 'available'
                    and isinstance(quotes.get('by_acquisition_source'), dict)
                    and all(isinstance(g, dict) and all(count(n) is not None for n in g.values())
                            for g in quote_groups.values()))
    outcomes = mapping(telemetry.get('source_outcomes'))
    outcome_groups = mapping(outcomes.get('by_acquisition_source'))
    outcome_fields = ('external_settlements','paid_results_delivered','paid_results_failed',
                      'paid_results_unknown','buyer_feedback_useful')
    outcomes_valid = (outcomes.get('version') == 'viridis-source-outcomes-v1'
        and outcomes.get('internal_and_self_excluded') is True
        and isinstance(outcomes.get('by_acquisition_source'), dict)
        and all(isinstance(g,dict) and all(count(g.get(k)) is not None for k in outcome_fields)
                and g['paid_results_delivered'] + g['paid_results_failed'] + g['paid_results_unknown'] == g['external_settlements']
                and g['buyer_feedback_useful'] <= g['paid_results_delivered'] for g in outcome_groups.values()))
    github_outcomes = mapping(outcome_groups.get('github'))
    def outcome_count(key):
        return github_outcomes.get(key, 0) if outcomes_valid else None
    return {
        'schema': 'viridis-repo-funnel-snapshot-v1',
        'captured_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'source': URL,
        'github': {
            'landing_page_views': count(mapping(funnel.get('acquisition_source_views')).get('github')),
            'service_quote_requests': sum(github_quotes.values()) if quotes_valid else None,
            'external_payers': github_payers,
            'paid_results_delivered': outcome_count('paid_results_delivered'),
            'buyer_confirmed_useful_results': outcome_count('buyer_feedback_useful'),
            'repeat_cohorts': windows,
        },
        'fleet_totals_not_attributed_to_github': {k: count(total.get(k)) for k in TOTAL_FIELDS},
        'historical_payers_unknown_source': count(mapping(sources.get('unknown')).get('payer_count')) if valid else None,
        'limits': [
            'Views are requests, not unique visitors; internal visits and automation may be included.',
            'Landing attribution uses the HTTP referrer; payer attribution is a separate buyer-declared label.',
            'Quote requests represent service choice, include retries, cover HTTP x402 only, and are not unique buyers.',
            'Source-specific delivery/usefulness are available only when the versioned production contract is present.',
            'Outcome source is per payment; retention source is the first purchase. There is no visitor-to-payer join or conversion rate.',
            'Null means unavailable or no eligible denominator; it never means zero.',
            'Cumulative counters and rolling retention cohorts must not be summed across captures.',
        ],
    }


def render(snapshot):
    g = snapshot['github']
    def show(v): return 'Unavailable' if v is None else str(v)
    lines = ['# GitHub to Fleet measurement', '', 'Captured: ' + snapshot['captured_at'], '',
        '| GitHub-attributed stage | Observed |', '|---|---:|']
    for key in ('landing_page_views','service_quote_requests','external_payers','paid_results_delivered','buyer_confirmed_useful_results'):
        lines.append(f'| {key.replace("_", " ")} | {show(g[key])} |')
    lines += ['', '## GitHub payer repeat cohorts', '', '| Window | Eligible payers | Repeat payers | Pending maturity |', '|---|---:|---:|---:|']
    for name, w in g['repeat_cohorts'].items():
        lines.append(f'| {name} | {show(w["eligible_payers"])} | {show(w["repeat_payers"])} | {show(w["pending_maturity"])} |')
    lines += ['', '## Fleet totals (not attributed to GitHub)', '']
    for k,v in snapshot['fleet_totals_not_attributed_to_github'].items(): lines.append(f'- {k}: {show(v)}')
    lines += ['', 'Historical payers with unknown source: ' + show(snapshot['historical_payers_unknown_source']), '', '## Measurement limits', '']
    lines += ['- ' + line for line in snapshot['limits']]
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Use a saved health response instead of the network')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.input:
            health = json.loads(args.input.read_text())
        else:
            with urllib.request.urlopen(URL, timeout=30) as response:
                health = json.load(response)
        if not isinstance(health, dict): raise ValueError('Expected health object')
        snapshot = build(health)
    except (OSError, ValueError):
        parser.exit(1, 'Snapshot unavailable; previous captures were not changed.\n')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = snapshot['captured_at'].replace(':', '').replace('+0000', 'Z')
    for name, content in [(stamp + '.json', json.dumps(snapshot, indent=2) + '\n'),
                          ('latest.json', json.dumps(snapshot, indent=2) + '\n'),
                          ('latest.md', render(snapshot))]:
        (args.output_dir / name).write_text(content)
    print(args.output_dir / 'latest.md')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
