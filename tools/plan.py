#!/usr/bin/env python3
"""Print the Spordle game ids the daily run should scan, as a JSON list.

Usage: python3 tools/plan.py --today YYYY-MM-DD [--explore 25]

Includes: known Junior C games dated on/before today that aren't merged yet (new results, late sheets),
Lions schedule games dated on/before today not merged yet, and up to --explore ids never looked at
(to find games played on a rescheduled date, e.g. the missing Tigers vs Mustangs 1 game).
"""
import argparse, csv, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'data')

ap = argparse.ArgumentParser(); ap.add_argument('--today', required=True); ap.add_argument('--explore', type=int, default=25)
a = ap.parse_args()
s = json.load(open(os.path.join(D, 'state.json'), encoding='utf-8'))
done = set(s['league_processed'])
ids = []
for sid, v in s['id_index'].items():
    no = v.get('no')
    if not no or no >= 7500 or no in done: continue
    if v.get('date') and v['date'] > a.today: continue
    ids.append(int(sid))
for r in csv.DictReader(open(os.path.join(D, 'lions_schedule_2026-27.csv'), encoding='utf-8')):
    if r['date'] <= a.today and int(r['game_no']) not in done and int(r['spordle_id']) not in ids:
        ids.append(int(r['spordle_id']))
ids += [i for i in s['unscanned_ids'][:a.explore] if i not in ids]
print(json.dumps(sorted(set(ids))))
