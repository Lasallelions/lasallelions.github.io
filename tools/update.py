#!/usr/bin/env python3
"""Merge newly scraped Junior C games into data/*.csv.

Usage:
  python3 tools/update.py --games scraped.json [--standings standings.txt] [--suspensions suspensions.txt] --today YYYY-MM-DD

scraped.json  : the string returned by window.__export() in tools/grab.js (a JSON list).
standings.txt : the string returned by window.__table('standings') (one pipe-separated row per team).
suspensions.txt: the string returned by window.__table('suspensions').

Every game is merged at most once (data/state.json keeps the lists), so re-running is safe.
"""
import argparse, csv, json, os, re, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'data')
LIONS = 'LIONS LASALLE'
MONTHS = {'janvier': 1, 'février': 2, 'fevrier': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8, 'aout': 8,
          'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12, 'decembre': 12}
# Penalty types as the league's sheets name them -> minutes (matches the league's standings PIM)
PEN_MIN = [('Double mineure', 4), ('Mineure de banc', 2), ('Mineure', 2), ('Majeure', 5), ('Match', 5), ('Inconduite grossière', 10),
           ('Extrême inconduite', 10), ('Inconduite de partie', 10), ('Inconduite', 10), ('Tir de pénalité', 0), ('Avertissement', 0)]
FR_EN = {'Accrocher': 'Hooking', 'Contact avec la tête': 'Head contact', 'Faire trébucher': 'Tripping', 'Mise en échec corporelle': 'Body checking',
         'Coup de bâton': 'Slashing', 'Retenir': 'Holding', 'Donner un double échec': 'Cross-checking', 'Obstruction': 'Interference',
         'Rudesse': 'Roughing', 'Retarder le jeu': 'Delay of game', 'Plonger et exagérer': 'Diving', 'Donner de la bande': 'Boarding',
         'Darder': 'Spearing', 'Cingler': 'High-sticking', 'Bâton élevé': 'High-sticking', 'Trop de joueurs sur la patinoire': 'Too many players',
         'Retenir le bâton': 'Holding the stick', 'Donner du genou': 'Kneeing', 'Donner du coude': 'Elbowing', 'Charger': 'Charging',
         'Assaut': 'Charging', 'Mise en échec par derrière': 'Checking from behind', 'Se battre': 'Fighting',
         'Abus verbal envers les officiels, conduite antisportive et inconduite': 'Unsportsmanlike conduct',
         'Quitter le banc des joueurs ou des punitions': 'Leaving the bench'}


def rd(name):
    p = os.path.join(D, name)
    with open(p, encoding='utf-8', newline='') as f:
        r = csv.DictReader(f); rows = list(r); return rows, r.fieldnames


def wr(name, rows, fields):
    with open(os.path.join(D, name), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader(); w.writerows(rows)


def tc(s):
    return re.sub(r"(^|[\s\-'])(\w)", lambda m: m.group(1) + m.group(2).upper(), s.lower())


def iso(fr):
    m = re.match(r'(\d+)\s+(\S+)\s+(\d{4})', (fr or '').strip())
    if not m: return ''
    return '%s-%02d-%02d' % (m.group(3), MONTHS.get(m.group(2).lower(), 0), int(m.group(1)))


def pen_type(text):
    for k, mins in PEN_MIN:
        if text.startswith(k):
            rest = re.sub(r'^\(\d+ min\)\s*', '', text[len(k):].strip())
            return k, mins, rest
    return '?', 0, text


def r2(x, n=2):
    from decimal import Decimal, ROUND_HALF_UP
    return float(Decimal(str(x)).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP))


def per_no(p):
    m = re.match(r'(\d+)', p or ''); return int(m.group(1)) if m else 4


def secs(per, t):
    mm, ss = t.split(':'); return (per_no(per) - 1) * 1200 + int(mm) * 60 + int(ss)


def strength_analysis(g, us):
    """Estimate PP/SH goals and chances for team `us` from one game's goals and penalties."""
    them = [t for t in g['teams'] if t != us][0]
    # box entries per team: list of [start, end, removable]
    by_time = defaultdict(lambda: defaultdict(list))
    for team, per, t, pids, text in g['pens']:
        kind, mins, _ = pen_type(text)
        if kind in ('Mineure', 'Double mineure', 'Mineure de banc', 'Majeure', 'Match'):
            by_time[secs(per, t)][team].append((pids[0] if pids else '?', kind))
    entries = {us: [], them: []}; chances = {us: 0, them: 0}
    for ts in sorted(by_time):
        minors = {tm: [p for p, k in by_time[ts][tm] if k in ('Mineure', 'Mineure de banc')] + [p for p, k in by_time[ts][tm] if k == 'Double mineure' for _ in (0, 1)] for tm in (us, them)}
        majors = {tm: sorted({p for p, k in by_time[ts][tm] if k in ('Majeure', 'Match')}) for tm in (us, them)}
        # coincidental: equal numbers cancel (minors with minors, majors with majors)
        c = min(len(minors[us]), len(minors[them])); minors = {tm: minors[tm][c:] for tm in minors}
        c = min(len(majors[us]), len(majors[them])); majors = {tm: majors[tm][c:] for tm in majors}
        for tm in (us, them):
            chain = defaultdict(int)
            for p in minors[tm]:
                start = ts + chain[p] * 120; chain[p] += 1
                entries[tm].append([start, start + 120, True]); chances[tm] += 1
            for p in majors[tm]:
                entries[tm].append([ts, ts + 300, False]); chances[tm] += 1
    res = {'ppg': [], 'shg': [], 'ppga': 0, 'shga': 0}
    pshots = {(tm, secs(per, t)) for tm, per, t, pids, text in g['pens'] if text.startswith('Tir de pénalité')}
    for team, per, t, pids in sorted(g['goals'], key=lambda x: secs(x[1], x[2])):
        ts = secs(per, t); other = them if team == us else us
        if (other, ts) in pshots: continue   # penalty-shot goal: neither PP nor SH
        active = lambda tm: [e for e in entries[tm] if e[0] <= ts < e[1]]
        a_own, a_other = len(active(team)[:2]), len(active(other)[:2])
        if a_other > a_own:
            rem = sorted([e for e in active(other) if e[2]], key=lambda e: e[1])
            if rem: rem[0][1] = ts
            if team == us: res['ppg'].append(pids[0] if pids else '')
            else: res['ppga'] += 1
        elif a_own > a_other:
            if team == us: res['shg'].append(pids[0] if pids else '')
            else: res['shga'] += 1
    res['pp_opps'] = chances[them]; res['pk_times'] = chances[us]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--games', required=True); ap.add_argument('--standings'); ap.add_argument('--suspensions')
    ap.add_argument('--today', required=True)
    a = ap.parse_args()
    state = json.load(open(os.path.join(D, 'state.json'), encoding='utf-8'))
    games = json.load(open(a.games, encoding='utf-8'))
    report = []

    # 1. id index
    for g in games:
        sid = str(g['id'])
        if g.get('err') == 'nohdr':
            state['id_index'][sid] = {'no': None, 'other': True}
        else:
            state['id_index'][sid] = {'no': int(g['no']) if g.get('no') else None, 'date': iso(g.get('date')), 'teams': g.get('teams'),
                                       'final': bool(g.get('final')), 'cat': g.get('cat', '')}
        if g['id'] in state['unscanned_ids']: state['unscanned_ids'].remove(g['id'])

    # raw sheets (team-level special teams use these; player corrections live in the CSVs, not here)
    gp_path = os.path.join(D, 'games.json')
    raw = json.load(open(gp_path, encoding='utf-8')) if os.path.exists(gp_path) else {}
    for g in games:
        if g.get('final') and 'goals' in g and g.get('no') and int(g['no']) < 7500:
            raw[str(int(g['no']))] = {'no': int(g['no']), 'date': iso(g.get('date')), 'teams': g['teams'], 'scores': g['scores'], 'final': True,
                                      'goals': g['goals'], 'pens': g['pens']}
    json.dump(raw, open(gp_path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))

    # 2. league player totals
    lp, lpf = rd('league_players.csv')
    lpi = {r['player_id']: r for r in lp}
    for r in lp:
        for k in ('gp', 'g', 'a', 'pts', 'pim'): r[k] = int(r[k])
    new_league = [g for g in games if g.get('final') and 'goals' in g and int(g['no']) not in state['league_processed']]
    for g in new_league:
        if len(g.get('lineup') or {}) < 2:
            report.append('Game %s: lineup not readable, skipped (will retry next run).' % g['no']); continue
        no = int(g['no'])
        lineup_pids = {}
        for tm, rows in g['lineup'].items():
            for kind, pid, name, num, _ in rows:
                if not pid: continue
                lineup_pids[pid] = (tm, name, num, kind)
        def P(pid, tm=None):
            if pid not in lpi:
                info = lineup_pids.get(pid)
                if not info: return None   # e.g. bench staff penalties: not in a lineup, left out
                tm2, name, num, kind = info
                lpi[pid] = {'player_id': pid, 'name': tc(name), 'num': num, 'team': tm2, 'gp': 0, 'g': 0, 'a': 0, 'pts': 0, 'ppgp': 0, 'pim': 0, '_G': kind == 'G'}
            return lpi[pid]
        for pid, (tm, name, num, kind) in lineup_pids.items():
            r = P(pid); r['gp'] += 1
        for team, per, t, pids in g['goals']:
            for i, pid in enumerate(pids):
                r = P(pid)
                if r is None: continue
                if i == 0: r['g'] += 1
                else: r['a'] += 1
        for team, per, t, pids, text in g['pens']:
            if not pids: continue
            r = P(pids[0])
            if r is None: continue
            r['pim'] += pen_type(text)[1]
        state['league_processed'].append(no)
        state['no_sheet_yet'].pop(str(no), None)
        report.append('League: added game %s (%s %s).' % (no, ' v '.join(g['teams']), '-'.join(g['scores'])))
    rows = []
    for r in lpi.values():
        r['pts'] = r['g'] + r['a']; r['ppgp'] = r2(r['pts'] / r['gp']) if r['gp'] else 0
        if r.get('_G') and r['pts'] == 0 and r['pim'] == 0: continue
        rows.append(r)
    rows.sort(key=lambda r: (-r['pts'], -r['g'], r['name']))
    wr('league_players.csv', rows, lpf)

    # 3. Lions games
    for g in sorted([g for g in games if g.get('final') and 'goals' in g and LIONS in g['teams'] and int(g['no']) not in state['lions_processed']], key=lambda g: iso(g['date'])):
        if len(g.get('lineup') or {}) < 2: continue
        lions_game(g, state, report)

    # 4. Standings
    if a.standings and os.path.exists(a.standings):
        out = []
        for line in open(a.standings, encoding='utf-8').read().strip().splitlines():
            c = [x.strip() for x in line.split('|')]
            if len(c) < 13 or not c[0].isdigit(): continue
            c[11] = str(int(c[11].replace('+', '').replace('−', '-')))
            out.append(dict(zip(['rank', 'team', 'gp', 'w', 't', 'l', 'fair_play_pts', 'pts', 'pts_pct', 'gf', 'ga', 'diff', 'pim'], c[:13])))
        if len(out) >= 10:
            wr('standings.csv', out, ['rank', 'team', 'gp', 'w', 't', 'l', 'fair_play_pts', 'pts', 'pts_pct', 'gf', 'ga', 'diff', 'pim'])
            report.append('Standings: %d teams.' % len(out))
            # check sheet goals against standings goals
            for s in out:
                sg = sum(r['g'] for r in rows if r['team'] == s['team'])
                if sg != int(s['gf']): report.append('  note: %s sheet goals %d vs standings %s (missing or late sheet)' % (s['team'], sg, s['gf']))
    # 5. Suspensions
    if a.suspensions and os.path.exists(a.suspensions):
        names = {r['name'].upper(): r['team'] for r in rows}
        out = []
        for line in open(a.suspensions, encoding='utf-8').read().strip().splitlines():
            c = [x.strip() for x in line.split('|')]
            if len(c) < 5: continue
            m = re.match(r'^(?:\S\s+)?(.+?)(?:\s*\((\w+)\))?$', c[0])
            nm = m.group(1).strip() if m else c[0]
            staff = 'Personnel' in c[1]
            g = re.search(r'#(\d+)', ' '.join(c)); sv = re.search(r'(\d+)\s*/\s*(\d+)', ' '.join(c))
            team = names.get(nm.upper(), '')
            if not team:
                for gg in state['id_index'].values():
                    pass
            out.append({'player': tc(nm) + (' (staff)' if staff else ''), 'team': team, 'code': c[2], 'game_no': g.group(1) if g else '',
                        'served': sv.group(1) if sv else '', 'games': sv.group(2) if sv else ''})
        out.sort(key=lambda r: (r['team'] != LIONS, -int(r['games'] or 0), r['player']))
        wr('suspensions.csv', out, ['player', 'team', 'code', 'game_no', 'served', 'games'])
        report.append('Suspensions: %d listed.' % len(out))

    # 6. played games with no sheet yet (date passed, not final)
    for sid, v in state['id_index'].items():
        if v.get('no') and v.get('no') < 7500 and v.get('date') and v['date'] < a.today and not v.get('final') and v['no'] not in state['league_processed']:
            state['no_sheet_yet'].setdefault(str(v['no']), '%s, %s: no final score sheet yet' % (' vs '.join(tc(t) for t in (v.get('teams') or [])), v['date']))
    state['league_processed'] = sorted(set(state['league_processed']))
    state['last_update'] = a.today
    json.dump(state, open(os.path.join(D, 'state.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('\n'.join(report) or 'Nothing new.')


def lions_game(g, state, report):
    no = int(g['no']); date = iso(g['date'])
    home = g['teams'][1] == LIONS
    opp = g['teams'][0] if home else g['teams'][1]
    ls, os_ = (int(g['scores'][1]), int(g['scores'][0])) if home else (int(g['scores'][0]), int(g['scores'][1]))
    res = 'W' if ls > os_ else ('L' if ls < os_ else 'T')
    lineup = g['lineup'][LIONS]
    names = {pid: (tc(name), num, kind, gr) for kind, pid, name, num, gr in lineup}
    goals = sorted(g['goals'], key=lambda x: secs(x[1], x[2]))
    pts = defaultdict(lambda: [0, 0, 0])  # g, a, pim by pid
    for team, per, t, pids in goals:
        if team != LIONS: continue
        for i, pid in enumerate(pids): pts[pid][0 if i == 0 else 1] += 1
    lions_pim = opp_pim = 0; minors_fr = []
    for team, per, t, pids, text in g['pens']:
        kind, mins, infr = pen_type(text)
        if team == LIONS:
            lions_pim += mins
            if pids: pts[pids[0]][2] += mins
            if kind == 'Mineure': minors_fr.append(infr)
            if kind == 'Double mineure': minors_fr += [infr, infr]
        else: opp_pim += mins
    sa = strength_analysis(g, LIONS)
    # player games
    pg, pgf = rd('player_games.csv')
    known = {}
    for r in pg: known.setdefault(r['name'].upper(), (r['name'], r['num'], r['pos']))
    pid_name = {}
    for pid, (nm, num, kind, gr) in names.items():
        if nm.upper() not in known:
            known[nm.upper()] = (nm, num, 'G' if kind == 'G' else 'F')
            report.append('Lions: new player on the sheet, %s #%s (position set to %s; fix in data/player_games.csv if wrong).' % (nm, num, known[nm.upper()][2]))
        pid_name[pid] = known[nm.upper()][0]
    goalie = next(((pid, v) for pid, v in names.items() if v[2] == 'G' and v[3]), None) or next(((pid, v) for pid, v in names.items() if v[2] == 'G'), None)
    for key, (nm, num, pos) in known.items():
        pid = next((p for p, n in pid_name.items() if n == nm), None)
        row = {'name': nm, 'num': num, 'pos': pos, 'game_no': str(no), 'date': date, 'ha': 'vs' if home else '@', 'opponent': opp,
               'dressed': '0', 'g': '', 'a': '', 'pts': '', 'pim': '', 'goalie_result': '', 'goalie_ga': ''}
        if pid:
            gg, aa, pim = pts[pid]
            row.update(dressed='1', g=str(gg), a=str(aa), pts=str(gg + aa), pim=str(pim))
            if goalie and pid == goalie[0]: row.update(goalie_result=res, goalie_ga=str(os_))
        pg.append(row)
    wr('player_games.csv', pg, pgf)
    # player stats
    pl, plf = rd('player_stats.csv')
    pli = {r['name']: r for r in pl}
    for nm, num, pos in known.values():
        if pos != 'G' and nm not in pli:
            pli[nm] = {k: 0 for k in plf}; pli[nm].update(num=num, name=nm, pos=pos)
    games = sorted({r['game_no'] for r in pg}, key=int)
    lions_goals = [x for x in goals if x[0] == LIONS]
    gwg = lions_goals[os_][3][0] if res == 'W' and len(lions_goals) > os_ else None
    first = goals[0] if goals else None
    fg = first[3][0] if first and first[0] == LIONS else None
    tg, _ = rd('team_summary.csv'); TSUM = tg[0]
    teamgf = int(TSUM['gf']) + ls
    for nm, p in pli.items():
        rows = {r['game_no']: r for r in pg if r['name'] == nm}
        dr = [r for r in rows.values() if r['dressed'] == '1']
        p['gp'] = len(dr); p['g'] = sum(int(r['g'] or 0) for r in dr); p['a'] = sum(int(r['a'] or 0) for r in dr)
        p['pts'] = p['g'] + p['a']; p['pim'] = sum(int(r['pim'] or 0) for r in dr)
        pid = next((x for x, n in pid_name.items() if n == nm), None)
        if pid:
            p['ppg'] = int(p['ppg'] or 0) + sa['ppg'].count(pid); p['shg'] = int(p['shg'] or 0) + sa['shg'].count(pid)
            p['gwg'] = int(p['gwg'] or 0) + (1 if gwg == pid else 0); p['fg'] = int(p['fg'] or 0) + (1 if fg == pid else 0)
        p['ppgp'] = r2(p['pts'] / p['gp']) if p['gp'] else 0.0
        p['share'] = r2(100 * p['pts'] / teamgf, 1) if teamgf else 0
        s = 0
        for gn in reversed(games):
            r = rows.get(gn)
            if not r or r['dressed'] != '1': continue
            if int(r['pts'] or 0) > 0: s += 1
            else: break
        p['pt_streak'] = s; p['multi'] = sum(1 for r in dr if int(r['pts'] or 0) >= 2)
    pl = sorted(pli.values(), key=lambda p: (-int(p['pts']), -int(p['g']), -int(p['gp']), p['name']))
    wr('player_stats.csv', pl, plf)
    # goalies
    go, gof = rd('goalie_stats.csv')
    for r in go:
        pid = next((x for x, n in pid_name.items() if n == r['name']), None)
        if pid:
            r['dressed'] = int(r['dressed']) + 1
            if goalie and pid == goalie[0]:
                r['gp'] = int(r['gp']) + 1; r['ga'] = int(r['ga']) + os_
                if res == 'W': r['w'] = int(r['w']) + 1
                elif res == 'L': r['l'] = int(r['l']) + 1
                if os_ == 0 and res != 'L': r['so'] = int(r['so']) + 1
                r['gaa'] = r2(int(r['ga']) / int(r['gp']))
    wr('goalie_stats.csv', go, gof)
    # periods
    pe, pef = rd('goals_by_period.csv')
    lab = {1: '1st', 2: '2nd', 3: '3rd'}
    for team, per, t, pids in goals:
        k = lab.get(min(per_no(per), 3))
        for r in pe:
            if r['period'] == k:
                if team == LIONS: r['lions_gf'] = int(r['lions_gf']) + 1
                else: r['lions_ga'] = int(r['lions_ga']) + 1
    wr('goals_by_period.csv', pe, pef)
    # minor penalties by type
    pn, pnf = rd('penalty_types.csv')
    byfr = {r['infraction_fr']: r for r in pn}
    for fr in minors_fr:
        if fr not in byfr:
            byfr[fr] = {'infraction': FR_EN.get(fr, fr), 'infraction_fr': fr, 'lions_minors': 0}; pn.append(byfr[fr])
        byfr[fr]['lions_minors'] = int(byfr[fr]['lions_minors']) + 1
    pn.sort(key=lambda r: -int(r['lions_minors']))
    wr('penalty_types.csv', pn, pnf)
    # game log
    gl, glf = rd('game_log.csv')
    perg = lambda tm, k: sum(1 for x in goals if x[0] == tm and min(per_no(x[1]), 3) == k)
    scorers = []
    for x in lions_goals:
        n = pid_name.get(x[3][0])
        if n and n not in scorers: scorers.append(n)
    gl.append({'game_no': no, 'date': date, 'home_away': 'Home' if home else 'Away', 'opponent': opp, 'lions': ls, 'opp': os_, 'result': res,
               'goalie': pid_name.get(goalie[0], '') if goalie else '', 'lions_p1': perg(LIONS, 1), 'lions_p2': perg(LIONS, 2), 'lions_p3': perg(LIONS, 3),
               'opp_p1': perg(opp, 1), 'opp_p2': perg(opp, 2), 'opp_p3': perg(opp, 3), 'lions_pim': lions_pim, 'opp_pim': opp_pim, 'lions_scorers': '; '.join(scorers)})
    gl.sort(key=lambda r: r['date'])
    wr('game_log.csv', gl, glf)
    # schedule
    sc, scf = rd('lions_schedule_2026-27.csv')
    for r in sc:
        if r['game_no'] == str(no): r.update(lions_score=ls, opp_score=os_, result=res)
    wr('lions_schedule_2026-27.csv', sc, scf)
    # team summary
    T = TSUM; I = lambda k: int(float(T[k] or 0))
    T['gp'] = I('gp') + 1; T['w'] = I('w') + (res == 'W'); T['l'] = I('l') + (res == 'L')
    T['gf'] = I('gf') + ls; T['ga'] = I('ga') + os_
    T['pp_goals'] = I('pp_goals') + len(sa['ppg']); T['pp_opps'] = I('pp_opps') + sa['pp_opps']
    T['pk_times'] = I('pk_times') + sa['pk_times']; T['pk_kills'] = I('pk_kills') + sa['pk_times'] - sa['ppga']
    T['shg_for'] = I('shg_for') + len(sa['shg']); T['shg_against'] = I('shg_against') + sa['shga']
    T['pim'] = I('pim') + lions_pim; T['opp_pim'] = I('opp_pim') + opp_pim
    hk = 'home' if home else 'away'
    if res in 'WL': T[hk + '_' + res.lower()] = I(hk + '_' + res.lower()) + 1
    if first and res in 'WL':
        k = ('scored_first_' if first[0] == LIONS else 'trailed_first_') + res.lower(); T[k] = I(k) + 1
    if abs(ls - os_) == 1: k = 'one_goal_' + res.lower(); T[k] = I(k) + 1
    gp = T['gp']
    T['gf_pg'] = r2(T['gf'] / gp); T['ga_pg'] = r2(T['ga'] / gp)
    T['pp_pct'] = r2(100 * T['pp_goals'] / T['pp_opps'], 1) if T['pp_opps'] else 0
    T['pk_pct'] = r2(100 * T['pk_kills'] / T['pk_times'], 1) if T['pk_times'] else 0
    T['pim_pg'] = r2(T['pim'] / gp, 1)
    T['pyth_win_pct'] = r2(T['gf'] ** 2 / (T['gf'] ** 2 + T['ga'] ** 2)) if T['gf'] + T['ga'] else 0
    wr('team_summary.csv', [T], list(T.keys()))
    state['lions_processed'].append(no)
    report.append('Lions: added game %s %s %s %d-%d (%s). PP %d/%d, PK %d/%d, PIM %d.' % (no, 'vs' if home else 'at', tc(opp), ls, os_, res,
                  len(sa['ppg']), sa['pp_opps'], sa['pk_times'] - sa['ppga'], sa['pk_times'], lions_pim))


if __name__ == '__main__':
    main()
