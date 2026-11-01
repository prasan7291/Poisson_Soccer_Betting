import csv
import io
import json
import math
import os
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import requests

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"

LEAGUES = {
    "E0": {
        "code": "E0",
        "name": "Premier League (England)",
        "short_name": "Premier League",
        "file_2627": "E0_2627.csv",
        "file_2526": "E0_2526.csv",
    },
    "SP1": {
        "code": "SP1",
        "name": "La Liga (Spain)",
        "short_name": "La Liga",
        "file_2627": "SP1_2627.csv",
        "file_2526": "SP1_2526.csv",
    },
    "I1": {
        "code": "I1",
        "name": "Serie A (Italy)",
        "short_name": "Serie A",
        "file_2627": "I1_2627.csv",
        "file_2526": "I1_2526.csv",
    },
}

DATA_SOURCES = [
    {
        "id": "E0_2627",
        "league_code": "E0",
        "season": "2026-2027",
        "league": "Premier League (E0)",
        "url": "https://football-data.co.uk/mmz4281/2627/E0.csv",
        "filename": "E0_2627.csv",
    },
    {
        "id": "E0_2526",
        "league_code": "E0",
        "season": "2025-2026",
        "league": "Premier League (E0)",
        "url": "https://football-data.co.uk/mmz4281/2526/E0.csv",
        "filename": "E0_2526.csv",
    },
    {
        "id": "SP1_2627",
        "league_code": "SP1",
        "season": "2026-2027",
        "league": "La Liga (SP1)",
        "url": "https://football-data.co.uk/mmz4281/2627/SP1.csv",
        "filename": "SP1_2627.csv",
    },
    {
        "id": "SP1_2526",
        "league_code": "SP1",
        "season": "2025-2026",
        "league": "La Liga (SP1)",
        "url": "https://football-data.co.uk/mmz4281/2526/SP1.csv",
        "filename": "SP1_2526.csv",
    },
    {
        "id": "I1_2627",
        "league_code": "I1",
        "season": "2026-2027",
        "league": "Serie A (I1)",
        "url": "https://football-data.co.uk/mmz4281/2627/I1.csv",
        "filename": "I1_2627.csv",
    },
    {
        "id": "I1_2526",
        "league_code": "I1",
        "season": "2025-2026",
        "league": "Serie A (I1)",
        "url": "https://football-data.co.uk/mmz4281/2526/I1.csv",
        "filename": "I1_2526.csv",
    },
]


def get_file_metadata(source: dict) -> dict:
    file_path = DATA_DIR / source["filename"]
    info = {
        "id": source["id"],
        "league_code": source["league_code"],
        "season": source["season"],
        "league": source["league"],
        "url": source["url"],
        "filename": source["filename"],
        "path": str(file_path),
        "exists": file_path.exists(),
        "size_bytes": 0,
        "row_count": 0,
        "last_updated": None,
    }
    if file_path.exists():
        stat = file_path.stat()
        info["size_bytes"] = stat.st_size
        info["last_updated"] = datetime.fromtimestamp(stat.st_mtime).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        try:
            with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.reader(f)
                rows = [r for r in reader if any(cell.strip() for cell in r)]
                info["row_count"] = max(0, len(rows) - 1)
        except Exception:
            info["row_count"] = 0
    return info


def _parse_match_datetime(row: dict, index: int) -> tuple:
    date_str = (row.get("Date") or "").strip()
    time_str = (row.get("Time") or "00:00").strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%y %H:%M", "%d/%m/%Y", "%d/%m/%y"):
        try:
            dt = datetime.strptime(f"{date_str} {time_str}".strip(), fmt)
            return (dt, index)
        except ValueError:
            continue
    return (datetime.min, index)


def get_league_team_stats(
    league_code: str = "E0", max_matches: int = 15, decay_rate: float = 0.90
) -> dict:
    league_cfg = LEAGUES.get(league_code, LEAGUES["E0"])
    file_2627 = DATA_DIR / league_cfg["file_2627"]
    file_2526 = DATA_DIR / league_cfg["file_2526"]

    if not file_2627.exists():
        return {
            "league_code": league_code,
            "league_name": league_cfg["name"],
            "short_name": league_cfg["short_name"],
            "teams": [],
            "home": [],
            "away": [],
            "home_summary": {
                "total_games": 0,
                "total_goals_scored": 0,
                "total_goals_conceded": 0,
                "avg_goals_scored": 0.0,
                "avg_goals_conceded": 0.0,
            },
            "away_summary": {
                "total_games": 0,
                "total_goals_scored": 0,
                "total_goals_conceded": 0,
                "avg_goals_scored": 0.0,
                "avg_goals_conceded": 0.0,
            },
            "max_matches": max_matches,
            "decay_rate": decay_rate,
        }

    current_teams = set()
    rows_2627 = []
    with open(file_2627, "r", encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            home = (row.get("HomeTeam") or "").strip()
            away = (row.get("AwayTeam") or "").strip()
            if home:
                current_teams.add(home)
            if away:
                current_teams.add(away)
            rows_2627.append(row)

    rows_2526 = []
    if file_2526.exists():
        with open(file_2526, "r", encoding="utf-8-sig", errors="replace") as f:
            for row in csv.DictReader(f):
                rows_2526.append(row)

    sorted_teams = sorted(current_teams)
    home_matches = {team: [] for team in sorted_teams}
    away_matches = {team: [] for team in sorted_teams}

    combined_rows = rows_2526 + rows_2627
    sorted_rows = [
        row
        for _, row in sorted(
            enumerate(combined_rows),
            key=lambda item: _parse_match_datetime(item[1], item[0]),
        )
    ]

    for row in sorted_rows:
        home = (row.get("HomeTeam") or "").strip()
        away = (row.get("AwayTeam") or "").strip()
        fthg_raw = (row.get("FTHG") or "").strip()
        ftag_raw = (row.get("FTAG") or "").strip()

        if not fthg_raw or not ftag_raw:
            continue
        try:
            fthg = int(float(fthg_raw))
            ftag = int(float(ftag_raw))
        except ValueError:
            continue

        if home in home_matches:
            home_matches[home].append((fthg, ftag))

        if away in away_matches:
            away_matches[away].append((ftag, fthg))

    def _build_venue_stats(matches_by_team: dict) -> tuple[list, dict]:
        stats_list = []
        total_games = 0
        total_scored = 0
        total_conceded = 0
        total_weight = 0.0
        total_weighted_scored = 0.0
        total_weighted_conceded = 0.0

        for team in sorted_teams:
            recent = (
                matches_by_team[team][-max_matches:]
                if max_matches
                else matches_by_team[team]
            )
            n = len(recent)
            gp = n
            raw_gf = sum(m[0] for m in recent)
            raw_ga = sum(m[1] for m in recent)

            weights = [decay_rate ** (n - 1 - idx) for idx in range(n)]
            w_sum = sum(weights)
            w_gf = sum(w * m[0] for w, m in zip(weights, recent))
            w_ga = sum(w * m[1] for w, m in zip(weights, recent))

            w_avg_gf = (w_gf / w_sum) if w_sum > 0 else 0.0
            w_avg_ga = (w_ga / w_sum) if w_sum > 0 else 0.0

            total_games += gp
            total_scored += raw_gf
            total_conceded += raw_ga
            total_weight += w_sum
            total_weighted_scored += w_gf
            total_weighted_conceded += w_ga

            stats_list.append(
                {
                    "team": team,
                    "games_played": gp,
                    "goals_scored": raw_gf,
                    "goals_conceded": raw_ga,
                    "avg_goals_scored": round(raw_gf / gp, 4) if gp > 0 else 0.0,
                    "avg_goals_conceded": round(raw_ga / gp, 4) if gp > 0 else 0.0,
                    "weighted_avg_scored": round(w_avg_gf, 4),
                    "weighted_avg_conceded": round(w_avg_ga, 4),
                    "_w_avg_gf": w_avg_gf,
                    "_w_avg_ga": w_avg_ga,
                }
            )

        league_w_avg_scored = (
            (total_weighted_scored / total_weight) if total_weight > 0 else 0.0
        )
        league_w_avg_conceded = (
            (total_weighted_conceded / total_weight) if total_weight > 0 else 0.0
        )

        for item in stats_list:
            item["attack_strength"] = (
                round(item["_w_avg_gf"] / league_w_avg_scored, 4)
                if league_w_avg_scored > 0
                else 0.0
            )
            item["defense_strength"] = (
                round(item["_w_avg_ga"] / league_w_avg_conceded, 4)
                if league_w_avg_conceded > 0
                else 0.0
            )
            del item["_w_avg_gf"]
            del item["_w_avg_ga"]

        summary = {
            "total_games": total_games,
            "total_goals_scored": total_scored,
            "total_goals_conceded": total_conceded,
            "avg_goals_scored": round(league_w_avg_scored, 4),
            "avg_goals_conceded": round(league_w_avg_conceded, 4),
            "raw_avg_goals_scored": (
                round(total_scored / total_games, 4) if total_games > 0 else 0.0
            ),
            "raw_avg_goals_conceded": (
                round(total_conceded / total_games, 4) if total_games > 0 else 0.0
            ),
            "decay_rate": decay_rate,
        }
        return stats_list, summary

    home_stats, home_summary = _build_venue_stats(home_matches)
    away_stats, away_summary = _build_venue_stats(away_matches)

    return {
        "league_code": league_code,
        "league_name": league_cfg["name"],
        "short_name": league_cfg["short_name"],
        "teams": sorted_teams,
        "home": home_stats,
        "away": away_stats,
        "home_summary": home_summary,
        "away_summary": away_summary,
        "max_matches": max_matches,
        "decay_rate": decay_rate,
    }


def get_all_leagues_stats(max_matches: int = 15, decay_rate: float = 0.90) -> dict:
    leagues_data = {}
    for code in LEAGUES:
        leagues_data[code] = get_league_team_stats(
            league_code=code, max_matches=max_matches, decay_rate=decay_rate
        )
    return {
        "leagues": leagues_data,
        "default_league": "E0",
        # Keep top-level E0 keys for backwards compatibility
        **leagues_data["E0"],
    }


def get_team_stats(max_matches: int = 15, decay_rate: float = 0.90) -> dict:
    return get_all_leagues_stats(max_matches=max_matches, decay_rate=decay_rate)


def poisson_pmf(k: int, lam: float) -> float:
    if lam < 0 or k < 0:
        return 0.0
    if lam == 0:
        return 1.0 if k == 0 else 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def _fair_odds(prob: float) -> float:
    return round(1.0 / prob, 2) if prob > 0 else 0.0


def calculate_asian_handicaps(
    matrix: list, home_team: str, away_team: str, max_goals: int = 7
) -> dict:
    lines = [round(-2.5 + 0.25 * k, 2) for k in range(21)]

    def _eval_single_line(diff: int, hcap: float) -> float:
        val = diff + hcap
        if val > 1e-9:
            return 1.0
        elif val < -1e-9:
            return -1.0
        return 0.0

    def _eval_side(is_home: bool, line: float) -> dict:
        rem = round(abs(line) % 0.5, 2)
        if abs(rem - 0.25) < 1e-6:
            sub_lines = [round(line - 0.25, 2), round(line + 0.25, 2)]
        else:
            sub_lines = [line]

        win_weight = 0.0
        loss_weight = 0.0
        push_prob = 0.0

        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                p = matrix[h][a]
                diff = (h - a) if is_home else (a - h)
                outcomes = [_eval_single_line(diff, sl) for sl in sub_lines]
                avg_outcome = sum(outcomes) / len(outcomes)
                if avg_outcome > 0:
                    win_weight += p * avg_outcome
                elif avg_outcome < 0:
                    loss_weight += p * (-avg_outcome)
                else:
                    push_prob += p

        denom = win_weight + loss_weight
        eff_win_prob = (win_weight / denom) if denom > 0 else 0.0
        fair_odds = round(1.0 / eff_win_prob, 2) if eff_win_prob > 0 else 0.0
        fmt_line = f"{line:+g}" if line != 0 else "0.0"

        return {
            "team": home_team if is_home else away_team,
            "side": "Home" if is_home else "Away",
            "line": line,
            "line_str": fmt_line,
            "label": f"{home_team if is_home else away_team} {fmt_line}",
            "eff_win_prob": round(eff_win_prob, 4),
            "push_prob": round(push_prob, 4),
            "fair_odds": fair_odds,
        }

    all_options = []
    for ln in lines:
        all_options.append(_eval_side(True, ln))
        all_options.append(_eval_side(False, ln))

    favored_options = [opt for opt in all_options if opt["eff_win_prob"] >= 0.50]
    best_balanced = min(
        favored_options if favored_options else all_options,
        key=lambda x: abs(x["eff_win_prob"] - 0.52),
    )

    confident_candidates = [
        opt for opt in all_options if 0.56 <= opt["eff_win_prob"] <= 0.68
    ]
    if confident_candidates:
        best_safe = max(confident_candidates, key=lambda x: x["eff_win_prob"])
    else:
        best_safe = min(all_options, key=lambda x: abs(x["eff_win_prob"] - 0.60))

    return {
        "best_balanced": best_balanced,
        "best_safe": best_safe,
        "table": [
            {
                "home_line": f"{ln:+g}" if ln != 0 else "0.0",
                "home": _eval_side(True, ln),
                "away_line": f"{-ln:+g}" if ln != 0 else "0.0",
                "away": _eval_side(False, -ln),
            }
            for ln in lines
        ],
    }


def calculate_poisson_matrix(
    home_xg: float,
    away_xg: float,
    home_team: str = "Home",
    away_team: str = "Away",
    max_goals: int = 7,
) -> dict:
    home_probs = [poisson_pmf(i, home_xg) for i in range(max_goals + 1)]
    away_probs = [poisson_pmf(j, away_xg) for j in range(max_goals + 1)]

    matrix = []
    scorelines = []
    home_win_prob = 0.0
    draw_prob = 0.0
    away_win_prob = 0.0
    over_25_prob = 0.0
    under_25_prob = 0.0
    btts_yes_prob = 0.0
    btts_no_prob = 0.0

    for i in range(max_goals + 1):
        row = []
        for j in range(max_goals + 1):
            p = home_probs[i] * away_probs[j]
            row.append(p)
            scorelines.append(
                {
                    "home_goals": i,
                    "away_goals": j,
                    "score": f"{i}-{j}",
                    "prob": p,
                    "fair_odds": _fair_odds(p),
                }
            )
            if i > j:
                home_win_prob += p
            elif i == j:
                draw_prob += p
            else:
                away_win_prob += p

            if (i + j) > 2.5:
                over_25_prob += p
            else:
                under_25_prob += p

            if i >= 1 and j >= 1:
                btts_yes_prob += p
            else:
                btts_no_prob += p
        matrix.append(row)

    top_3_scorelines = sorted(scorelines, key=lambda x: x["prob"], reverse=True)[:3]
    asian_handicap = calculate_asian_handicaps(
        matrix, home_team=home_team, away_team=away_team, max_goals=max_goals
    )

    return {
        "max_goals": max_goals,
        "home_goal_probs": home_probs,
        "away_goal_probs": away_probs,
        "matrix": matrix,
        "home_win_prob": home_win_prob,
        "home_win_fair_odds": _fair_odds(home_win_prob),
        "draw_prob": draw_prob,
        "draw_fair_odds": _fair_odds(draw_prob),
        "away_win_prob": away_win_prob,
        "away_win_fair_odds": _fair_odds(away_win_prob),
        "over_25_prob": over_25_prob,
        "over_25_fair_odds": _fair_odds(over_25_prob),
        "under_25_prob": under_25_prob,
        "under_25_fair_odds": _fair_odds(under_25_prob),
        "btts_yes_prob": btts_yes_prob,
        "btts_yes_fair_odds": _fair_odds(btts_yes_prob),
        "btts_no_prob": btts_no_prob,
        "btts_no_fair_odds": _fair_odds(btts_no_prob),
        "top_3_scorelines": top_3_scorelines,
        "asian_handicap": asian_handicap,
        "total_prob": home_win_prob + draw_prob + away_win_prob,
    }


def calculate_match_xg(
    home_team: str,
    away_team: str,
    league_code: str = "E0",
    stats: dict = None,
) -> dict:
    if stats is None:
        stats = get_league_team_stats(league_code)
    elif "leagues" in stats and league_code in stats["leagues"]:
        stats = stats["leagues"][league_code]

    home_map = {item["team"]: item for item in stats.get("home", [])}
    away_map = {item["team"]: item for item in stats.get("away", [])}

    if home_team not in home_map or away_team not in away_map:
        raise ValueError(f"Invalid home or away team selection for league {league_code}.")

    h_row = home_map[home_team]
    a_row = away_map[away_team]
    league_home_scored = stats["home_summary"]["avg_goals_scored"]
    league_away_scored = stats["away_summary"]["avg_goals_scored"]

    home_xg = h_row["attack_strength"] * a_row["defense_strength"] * league_home_scored
    away_xg = a_row["attack_strength"] * h_row["defense_strength"] * league_away_scored
    poisson_data = calculate_poisson_matrix(
        home_xg, away_xg, home_team=home_team, away_team=away_team, max_goals=7
    )

    league_cfg = LEAGUES.get(league_code, LEAGUES["E0"])
    return {
        "league_code": league_code,
        "league_name": league_cfg["name"],
        "league_short": league_cfg["short_name"],
        "home_team": home_team,
        "away_team": away_team,
        "home_xg": round(home_xg, 4),
        "away_xg": round(away_xg, 4),
        "components": {
            "home_attack_strength": h_row["attack_strength"],
            "home_defense_strength": h_row["defense_strength"],
            "away_attack_strength": a_row["attack_strength"],
            "away_defense_strength": a_row["defense_strength"],
            "league_avg_home_goals": league_home_scored,
            "league_avg_away_goals": league_away_scored,
        },
        "poisson": poisson_data,
    }


def evaluate_match_markets(match_res: dict, market_odds: dict) -> dict:
    p_data = match_res["poisson"]
    home_team = match_res["home_team"]
    away_team = match_res["away_team"]
    ah_data = p_data.get("asian_handicap", {})
    ah_bal = ah_data.get("best_balanced", {})
    ah_safe = ah_data.get("best_safe", {})

    dynamic_markets = [
        ("home_win", f"{home_team} Win (1)", p_data["home_win_prob"], p_data["home_win_fair_odds"]),
        ("draw", "Draw (X)", p_data["draw_prob"], p_data["draw_fair_odds"]),
        ("away_win", f"{away_team} Win (2)", p_data["away_win_prob"], p_data["away_win_fair_odds"]),
        ("over_25", "Over 2.5 Goals", p_data["over_25_prob"], p_data["over_25_fair_odds"]),
        ("under_25", "Under 2.5 Goals", p_data["under_25_prob"], p_data["under_25_fair_odds"]),
        ("btts_yes", "BTTS - Yes", p_data["btts_yes_prob"], p_data["btts_yes_fair_odds"]),
        ("btts_no", "BTTS - No", p_data["btts_no_prob"], p_data["btts_no_fair_odds"]),
        (
            "ah_balanced",
            f"AH {ah_bal.get('label', 'Balanced')}",
            ah_bal.get("eff_win_prob", 0.0),
            ah_bal.get("fair_odds", 0.0),
        ),
        (
            "ah_safe",
            f"AH {ah_safe.get('label', 'Safe')}",
            ah_safe.get("eff_win_prob", 0.0),
            ah_safe.get("fair_odds", 0.0),
        ),
    ]

    evaluated = {}
    candidates = []

    for key, display_label, prob, fair in dynamic_markets:
        raw_odd = (market_odds or {}).get(key)
        bookie_odd = None
        if raw_odd not in (None, ""):
            try:
                val = float(raw_odd)
                if val > 1.0:
                    bookie_odd = val
            except (ValueError, TypeError):
                bookie_odd = None

        if bookie_odd is not None and prob > 0:
            ev = (prob * bookie_odd) - 1.0
            kelly = ev / (bookie_odd - 1.0)
            entry = {
                "market_key": key,
                "market_label": display_label,
                "prob": round(prob, 4),
                "fair_odds": fair,
                "bookie_odds": round(bookie_odd, 2),
                "ev": round(ev, 4),
                "ev_pct": round(ev * 100, 2),
                "kelly_fraction": round(kelly, 4),
                "kelly_pct": round(max(0.0, kelly) * 100, 2),
                "is_value": ev > 0,
            }
            evaluated[key] = entry
            candidates.append(entry)
        else:
            evaluated[key] = {
                "market_key": key,
                "market_label": display_label,
                "prob": round(prob, 4),
                "fair_odds": fair,
                "bookie_odds": None,
                "ev": None,
                "ev_pct": None,
                "kelly_fraction": None,
                "kelly_pct": None,
                "is_value": False,
            }

    best_bet = None
    if candidates:
        candidates.sort(key=lambda x: (x["kelly_fraction"], x["ev"]), reverse=True)
        best_bet = candidates[0]

    return {
        "markets": evaluated,
        "best_bet": best_bet,
        "has_odds_entered": len(candidates) > 0,
    }


def calculate_round_matches(
    matchups: list,
    stats: dict = None,
    bankroll: float = 1000.0,
    kelly_multiplier: float = 0.25,
) -> dict:
    if stats is None:
        stats = get_all_leagues_stats()
    elif "leagues" not in stats:
        stats = {"leagues": {"E0": stats}}

    results = []
    for idx, pair in enumerate(matchups[:30]):
        league_code = (pair.get("league_code") or "E0").strip().upper()
        if league_code not in LEAGUES:
            league_code = "E0"
        home_team = (pair.get("home_team") or "").strip()
        away_team = (pair.get("away_team") or "").strip()
        market_odds = pair.get("market_odds") or {}
        if not home_team or not away_team:
            continue
        try:
            league_stats = stats["leagues"].get(league_code) or get_league_team_stats(league_code)
            match_res = calculate_match_xg(
                home_team, away_team, league_code=league_code, stats=league_stats
            )
            match_res["match_index"] = idx + 1
            analysis = evaluate_match_markets(match_res, market_odds)
            match_res["betting_analysis"] = analysis
            results.append(match_res)
        except ValueError:
            continue

    ranked_candidates = [
        r for r in results if r["betting_analysis"]["best_bet"] is not None
    ]
    ranked_candidates.sort(
        key=lambda r: (
            r["betting_analysis"]["best_bet"]["kelly_fraction"],
            r["betting_analysis"]["best_bet"]["ev"],
        ),
        reverse=True,
    )

    rank_map = {}
    for rank_idx, r in enumerate(ranked_candidates, start=1):
        rank_map[r["match_index"]] = rank_idx
        r["betting_analysis"]["rank"] = rank_idx

    for r in results:
        if r["match_index"] not in rank_map:
            r["betting_analysis"]["rank"] = None

    top_3 = []
    tier_multipliers = [1.0, 0.75, 0.50]

    raw_top_3 = ranked_candidates[:3]
    raw_stakes = []
    for i, r in enumerate(raw_top_3):
        best = r["betting_analysis"]["best_bet"]
        pos_kelly = max(0.0, best["kelly_fraction"])
        stake = bankroll * kelly_multiplier * pos_kelly * tier_multipliers[i]
        raw_stakes.append(stake)

    for i in range(1, len(raw_stakes)):
        if raw_stakes[i] > 0 and raw_stakes[i] >= raw_stakes[i - 1]:
            raw_stakes[i] = round(raw_stakes[i - 1] * 0.80, 2)

    total_allocated = sum(raw_stakes)

    for i, r in enumerate(raw_top_3):
        best = r["betting_analysis"]["best_bet"]
        stake = round(raw_stakes[i], 2)
        stake_pct_bankroll = round((stake / bankroll) * 100, 2) if bankroll > 0 else 0.0
        share_of_pool = (
            round((stake / total_allocated) * 100, 1) if total_allocated > 0 else 0.0
        )
        ah_best = r["poisson"]["asian_handicap"]["best_balanced"]

        top_3.append(
            {
                "rank": i + 1,
                "match_index": r["match_index"],
                "league_code": r["league_code"],
                "league_short": r["league_short"],
                "home_team": r["home_team"],
                "away_team": r["away_team"],
                "matchup_label": f"{r['home_team']} vs {r['away_team']}",
                "recommended_market": best["market_label"],
                "prob": best["prob"],
                "fair_odds": best["fair_odds"],
                "bookie_odds": best["bookie_odds"],
                "ev_pct": best["ev_pct"],
                "kelly_pct": best["kelly_pct"],
                "tier_weight": tier_multipliers[i],
                "recommended_stake": stake,
                "stake_pct_bankroll": stake_pct_bankroll,
                "share_of_top3_stakes_pct": share_of_pool,
                "is_positive_ev": best["ev"] > 0,
                "best_asian_handicap": ah_best,
            }
        )

    return {
        "count": len(results),
        "bankroll": bankroll,
        "kelly_multiplier": kelly_multiplier,
        "results": results,
        "top_3_bets": top_3,
    }


def update_data_files() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    errors = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PoissonSoccerBetting/1.0"
    }

    for source in DATA_SOURCES:
        file_path = DATA_DIR / source["filename"]
        try:
            response = requests.get(source["url"], headers=headers, timeout=30)
            response.raise_for_status()
            file_path.write_bytes(response.content)
            meta = get_file_metadata(source)
            meta["status"] = "updated"
            results.append(meta)
        except Exception as exc:
            meta = get_file_metadata(source)
            meta["status"] = "error"
            meta["error"] = str(exc)
            results.append(meta)
            errors.append(f"{source['league']} ({source['season']}): {exc}")

    return {
        "success": len(errors) == 0,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "files": results,
        "team_stats": get_all_leagues_stats(),
        "errors": errors,
    }


class AppRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def _send_json(self, status_code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/data-status":
            files = [get_file_metadata(src) for src in DATA_SOURCES]
            self._send_json(200, {"files": files, "team_stats": get_all_leagues_stats()})
            return
        if self.path == "/api/team-stats":
            self._send_json(200, get_all_leagues_stats())
            return
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/update-data":
            result = update_data_files()
            status_code = 200 if result["success"] else 207
            self._send_json(status_code, result)
            return
        if self.path == "/api/calculate-round":
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(raw_body.decode("utf-8"))
                matchups = payload.get("matchups", [])
                bankroll = float(payload.get("bankroll", 1000.0) or 1000.0)
                kelly_multiplier = float(
                    payload.get("kelly_multiplier", 0.25) or 0.25
                )
                round_data = calculate_round_matches(
                    matchups,
                    bankroll=bankroll,
                    kelly_multiplier=kelly_multiplier,
                )
                self._send_json(200, round_data)
            except Exception as exc:
                self._send_json(400, {"error": str(exc)})
            return
        self._send_json(404, {"error": "Endpoint not found"})


def run_server(host: str = "127.0.0.1", port: int = 8000):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), AppRequestHandler)
    print(f"Server running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
