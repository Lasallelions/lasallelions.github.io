#!/usr/bin/env python3
"""Build the website (index.html) and the Claude dashboard page (build/dashboard_index.html) from data/ and template/.

Usage: python3 tools/build.py --today YYYY-MM-DD
"""
import argparse, csv, json, os, re, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'data')
DATASETS = {  # dashboard dataset id -> data file
    'gamelog': 'game_log.csv', 'goalies': 'goalie_stats.csv', 'periods': 'goals_by_period.csv', 'schedule': 'lions_schedule_2026-27.csv',
    'pens': 'penalty_types.csv', 'pgames': 'player_games.csv', 'players': 'player_stats.csv', 'team': 'team_summary.csv',
    'roster': 'roster.csv', 'league_players': 'league_players.csv', 'standings': 'standings.csv', 'suspensions': 'suspensions.csv',
    'special': 'special_teams.csv'}
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--today', required=True); a = ap.parse_args()
    d = datetime.date.fromisoformat(a.today)
    updated = '%d %s %d' % (d.day, MONTHS[d.month - 1], d.year)
    import sys; sys.path.insert(0, os.path.join(ROOT, 'tools')); import special; special.compute()
    state = json.load(open(os.path.join(D, 'state.json'), encoding='utf-8'))
    st = list(csv.DictReader(open(os.path.join(D, 'standings.csv'), encoding='utf-8')))
    played = sum(int(r['gp']) for r in st) // 2
    sheets = len([n for n in state['league_processed'] if n < 7500])
    sheets = min(sheets, played)
    missing = ''
    if state.get('no_sheet_yet'):
        missing = ' Not yet included (no score sheet posted): ' + '; '.join('game %s (%s)' % (k, v.split(':')[0]) for k, v in sorted(state['no_sheet_yet'].items())) + '.'
    if played - sheets > len(state.get('no_sheet_yet', {})):
        missing += ' Games still missing a posted sheet are added automatically once the league posts them.'
    page = open(os.path.join(ROOT, 'template', 'page.html'), encoding='utf-8').read()
    page = page.replace('{{UPDATED}}', updated).replace('{{SHEETS}}', str(sheets)).replace('{{PLAYED}}', str(played)).replace('{{MISSING}}', missing)
    assert '{{' not in page, 'unfilled placeholder in template/page.html'
    os.makedirs(os.path.join(ROOT, 'build'), exist_ok=True)
    open(os.path.join(ROOT, 'build', 'dashboard_index.html'), 'w', encoding='utf-8').write(page)
    # website: drop the dashboard-only meta, give each inline script its own block scope (the dashboard runs each script in its own scope)
    site = page.replace('<meta name="dash-one-writer">', '', 1)
    site = re.sub(r'(<script>)([\s\S]*?)(</script>)', lambda m: m.group(1) + '{\n' + m.group(2) + '\n}' + m.group(3), site)
    data = {k: open(os.path.join(D, f), encoding='utf-8').read() for k, f in DATASETS.items()}
    shell = open(os.path.join(ROOT, 'template', 'shell.html'), encoding='utf-8').read()
    html = shell.replace('{{DATA}}', json.dumps(data, ensure_ascii=False).replace('</', '<\\/')).replace('{{UPDATED}}', updated).replace('{{PAGE}}', site)
    open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8').write(html)
    print('Built index.html (%d bytes): %d of %d games, updated %s.%s' % (len(html), sheets, played, updated, missing))


if __name__ == '__main__':
    main()
