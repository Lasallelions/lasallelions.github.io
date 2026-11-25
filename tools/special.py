#!/usr/bin/env python3
"""League-wide special teams (power play / penalty kill) from the raw score sheets in data/games.json.

Writes data/special_teams.csv. Run by tools/build.py; can also be run on its own.
Method (same as the Lions' own PP/PK in tools/update.py): every minor, double minor, major or match penalty that
isn't cancelled by a same-time penalty to the other team gives the other team one power-play chance; a goal scored
while the other team has more players in the box is a power-play goal (it ends the earliest-ending minor);
penalty-shot goals are neither power-play nor shorthanded.
"""
import csv, json, os, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'data')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from update import strength_analysis, r2  # noqa: E402

FIELDS = ['team', 'gp', 'pp_goals', 'pp_opps', 'pp_pct', 'pp_rank', 'ppga', 'times_sh', 'pk_pct', 'pk_rank', 'shg', 'shga', 'special_index', 'special_rank']


def compute():
    t = defaultdict(lambda: defaultdict(int))
    base = json.load(open(os.path.join(D, 'special_base.json'), encoding='utf-8'))
    for team, v in base['totals'].items():
        for k, n in v.items(): t[team][k] += n
    p = os.path.join(D, 'games.json')
    games = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}
    for g in games.values():
        if not g.get('final') or len(g.get('teams', [])) != 2 or g['no'] in base['games']: continue
        for us in g['teams']:
            sa = strength_analysis(g, us); r = t[us]
            r['gp'] += 1; r['pp_goals'] += len(sa['ppg']); r['pp_opps'] += sa['pp_opps']
            r['ppga'] += sa['ppga']; r['times_sh'] += sa['pk_times']; r['shg'] += len(sa['shg']); r['shga'] += sa['shga']
    rows = []
    for team, r in t.items():
        pp = 100 * r['pp_goals'] / r['pp_opps'] if r['pp_opps'] else 0
        pk = 100 * (r['times_sh'] - r['ppga']) / r['times_sh'] if r['times_sh'] else 100
        rows.append({'team': team, 'gp': r['gp'], 'pp_goals': r['pp_goals'], 'pp_opps': r['pp_opps'], 'pp_pct': r2(pp, 1),
                     'ppga': r['ppga'], 'times_sh': r['times_sh'], 'pk_pct': r2(pk, 1), 'shg': r['shg'], 'shga': r['shga'],
                     'special_index': r2(pp + pk, 1)})
    for key, rk in (('pp_pct', 'pp_rank'), ('pk_pct', 'pk_rank'), ('special_index', 'special_rank')):
        for r in rows: r[rk] = 1 + sum(1 for o in rows if o[key] > r[key])
    rows.sort(key=lambda r: (r['special_rank'], r['team']))
    with open(os.path.join(D, 'special_teams.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    return rows


if __name__ == '__main__':
    for r in compute(): print(r)
