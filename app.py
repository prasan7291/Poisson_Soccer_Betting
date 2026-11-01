import csv
import io
import json
import math
import os
import uuid
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
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
    league_code: str = "E0",
    max_matches: int = 15,
    include_last_season: bool = True,
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
            "standings": [],
            "max_matches": max_matches,
            "include_last_season": include_last_season,
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
    if include_last_season and file_2526.exists():
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

        for team in sorted_teams:
            recent = (
                matches_by_team[team][-max_matches:]
                if max_matches
                else matches_by_team[team]
            )
            gp = len(recent)
            raw_gf = sum(m[0] for m in recent)
            raw_ga = sum(m[1] for m in recent)

            avg_gf = (raw_gf / gp) if gp > 0 else 0.0
            avg_ga = (raw_ga / gp) if gp > 0 else 0.0

            total_games += gp
            total_scored += raw_gf
            total_conceded += raw_ga

            stats_list.append(
                {
                    "team": team,
                    "games_played": gp,
                    "goals_scored": raw_gf,
                    "goals_conceded": raw_ga,
                    "avg_goals_scored": round(avg_gf, 4),
                    "avg_goals_conceded": round(avg_ga, 4),
                    "_avg_gf": avg_gf,
                    "_avg_ga": avg_ga,
                }
            )

        league_avg_scored = (total_scored / total_games) if total_games > 0 else 0.0
        league_avg_conceded = (total_conceded / total_games) if total_games > 0 else 0.0

        for item in stats_list:
            item["attack_strength"] = (
                round(item["_avg_gf"] / league_avg_scored, 4)
                if league_avg_scored > 0
                else 0.0
            )
            item["defense_strength"] = (
                round(item["_avg_ga"] / league_avg_conceded, 4)
                if league_avg_conceded > 0
                else 0.0
            )
            del item["_avg_gf"]
            del item["_avg_ga"]

        summary = {
            "total_games": total_games,
            "total_goals_scored": total_scored,
            "total_goals_conceded": total_conceded,
            "avg_goals_scored": round(league_avg_scored, 4),
            "avg_goals_conceded": round(league_avg_conceded, 4),
        }
        return stats_list, summary

    home_stats, home_summary = _build_venue_stats(home_matches)
    away_stats, away_summary = _build_venue_stats(away_matches)

    # Calculate 2026-2027 Current Season League Standings, Goal Difference & Recent Form
    sorted_2627 = [
        row
        for _, row in sorted(
            enumerate(rows_2627),
            key=lambda item: _parse_match_datetime(item[1], item[0]),
        )
    ]

    standings_map = {
        team: {
            "team": team,
            "mp": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "gf": 0,
            "ga": 0,
            "gd": 0,
            "points": 0,
            "recent_results": [],  # list of (result_char, pts, gd_in_match)
        }
        for team in sorted_teams
    }

    for row in sorted_2627:
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

        if home in standings_map:
            st = standings_map[home]
            st["mp"] += 1
            st["gf"] += fthg
            st["ga"] += ftag
            st["gd"] = st["gf"] - st["ga"]
            if fthg > ftag:
                st["wins"] += 1
                st["points"] += 3
                st["recent_results"].append(("W", 3, fthg - ftag))
            elif fthg == ftag:
                st["draws"] += 1
                st["points"] += 1
                st["recent_results"].append(("D", 1, 0))
            else:
                st["losses"] += 1
                st["recent_results"].append(("L", 0, fthg - ftag))

        if away in standings_map:
            st = standings_map[away]
            st["mp"] += 1
            st["gf"] += ftag
            st["ga"] += fthg
            st["gd"] = st["gf"] - st["ga"]
            if ftag > fthg:
                st["wins"] += 1
                st["points"] += 3
                st["recent_results"].append(("W", 3, ftag - fthg))
            elif ftag == fthg:
                st["draws"] += 1
                st["points"] += 1
                st["recent_results"].append(("D", 1, 0))
            else:
                st["losses"] += 1
                st["recent_results"].append(("L", 0, ftag - fthg))

    # Sort standings by Points DESC, Goal Difference DESC, Goals For DESC, Team ASC
    standings_list = sorted(
        standings_map.values(),
        key=lambda x: (-x["points"], -x["gd"], -x["gf"], x["team"]),
    )

    n_teams = len(standings_list)
    # Compute last-5 form stats and composite Form/Position/GD multiplier for xG
    for idx, st in enumerate(standings_list):
        pos = idx + 1
        st["position"] = pos
        last_5 = st["recent_results"][-5:]
        st["form_last5"] = [r[0] for r in last_5]
        st["form_str"] = "-".join(st["form_last5"]) if st["form_last5"] else "—"
        st["form_points"] = sum(r[1] for r in last_5)
        st["form_gd"] = sum(r[2] for r in last_5)
        form_ppg = (st["form_points"] / len(last_5)) if last_5 else 1.35
        st["form_ppg"] = round(form_ppg, 2)

        # Normalized scores in [-1, +1]
        pos_score = (
            (((n_teams + 1) / 2.0) - pos) / ((n_teams - 1) / 2.0)
            if n_teams > 1
            else 0.0
        )
        form_score = max(-1.0, min(1.0, (form_ppg - 1.35) / 1.65))
        gd_per_game = (st["gd"] / st["mp"]) if st["mp"] > 0 else 0.0
        gd_score = max(-1.0, min(1.0, gd_per_game / 2.0))

        # Composite multiplier combining Recent Form (6%), League Position (5%), and Goal Difference (4%)
        multiplier = 1.0 + (0.06 * form_score) + (0.05 * pos_score) + (0.04 * gd_score)
        st["form_position_multiplier"] = round(multiplier, 4)
        del st["recent_results"]

    return {
        "league_code": league_code,
        "league_name": league_cfg["name"],
        "short_name": league_cfg["short_name"],
        "teams": sorted_teams,
        "home": home_stats,
        "away": away_stats,
        "home_summary": home_summary,
        "away_summary": away_summary,
        "standings": standings_list,
        "max_matches": max_matches,
        "include_last_season": include_last_season,
    }


def get_all_leagues_stats(
    max_matches: int = 15,
    include_last_season: bool = True,
) -> dict:
    leagues_data = {}
    for code in LEAGUES:
        leagues_data[code] = get_league_team_stats(
            league_code=code,
            max_matches=max_matches,
            include_last_season=include_last_season,
        )
    return {
        "leagues": leagues_data,
        "default_league": "E0",
        "include_last_season": include_last_season,
        **leagues_data["E0"],
    }


def get_team_stats(
    max_matches: int = 15,
    include_last_season: bool = True,
) -> dict:
    return get_all_leagues_stats(
        max_matches=max_matches,
        include_last_season=include_last_season,
    )


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
    standings_map = {item["team"]: item for item in stats.get("standings", [])}

    if home_team not in home_map or away_team not in away_map:
        raise ValueError(f"Invalid home or away team selection for league {league_code}.")

    h_row = home_map[home_team]
    a_row = away_map[away_team]
    h_st = standings_map.get(home_team, {})
    a_st = standings_map.get(away_team, {})

    league_home_scored = stats["home_summary"]["avg_goals_scored"]
    league_away_scored = stats["away_summary"]["avg_goals_scored"]

    base_home_xg = h_row["attack_strength"] * a_row["defense_strength"] * league_home_scored
    base_away_xg = a_row["attack_strength"] * h_row["defense_strength"] * league_away_scored

    h_mult = h_st.get("form_position_multiplier", 1.0) or 1.0
    a_mult = a_st.get("form_position_multiplier", 1.0) or 1.0

    # Apply Recent Form, League Position & Goal Difference factor to xG
    home_xg = base_home_xg * (h_mult / a_mult)
    away_xg = base_away_xg * (a_mult / h_mult)

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
        "base_home_xg": round(base_home_xg, 4),
        "base_away_xg": round(base_away_xg, 4),
        "home_standing": {
            "position": h_st.get("position"),
            "points": h_st.get("points", 0),
            "gd": h_st.get("gd", 0),
            "form_str": h_st.get("form_str", "—"),
            "multiplier": h_mult,
        },
        "away_standing": {
            "position": a_st.get("position"),
            "points": a_st.get("points", 0),
            "gd": a_st.get("gd", 0),
            "form_str": a_st.get("form_str", "—"),
            "multiplier": a_mult,
        },
        "components": {
            "home_attack_strength": h_row["attack_strength"],
            "home_defense_strength": h_row["defense_strength"],
            "away_attack_strength": a_row["attack_strength"],
            "away_defense_strength": a_row["defense_strength"],
            "league_avg_home_goals": league_home_scored,
            "league_avg_away_goals": league_away_scored,
            "home_form_pos_multiplier": h_mult,
            "away_form_pos_multiplier": a_mult,
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
        # Sort by Expected Value (EV) descending first, then Kelly fraction descending
        candidates.sort(key=lambda x: (x["ev"], x["kelly_fraction"]), reverse=True)
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
    include_last_season: bool = True,
) -> dict:
    if stats is None:
        stats = get_all_leagues_stats(include_last_season=include_last_season)
    elif "leagues" not in stats:
        stats = {"leagues": {"E0": stats}}

    results = []
    for idx, pair in enumerate(matchups[:50]):
        league_code = (pair.get("league_code") or "E0").strip().upper()
        if league_code not in LEAGUES:
            league_code = "E0"
        home_team = (pair.get("home_team") or "").strip()
        away_team = (pair.get("away_team") or "").strip()
        market_odds = pair.get("market_odds") or {}
        if not home_team or not away_team:
            continue
        try:
            league_stats = stats["leagues"].get(league_code) or get_league_team_stats(
                league_code, include_last_season=include_last_season
            )
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
            r["betting_analysis"]["best_bet"]["ev"],
            r["betting_analysis"]["best_bet"]["kelly_fraction"],
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
                "market_key": best["market_key"],
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


def _parse_bool(val, default: bool = True) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    s = str(val).strip().lower()
    if s in ("false", "0", "no"):
        return False
    if s in ("true", "1", "yes"):
        return True
    return default


def update_data_files(include_last_season: bool = True) -> dict:
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
        "team_stats": get_all_leagues_stats(include_last_season=include_last_season),
        "errors": errors,
    }


BETS_FILE = DATA_DIR / "bet_history.json"

BET_TYPE_CATEGORIES = [
    "Home Win (1)",
    "Draw (X)",
    "Away Win (2)",
    "Over 2.5 Goals",
    "Under 2.5 Goals",
    "BTTS - Yes",
    "BTTS - No",
    "Asian Handicap",
    "Correct Score / Other",
]

ODDS_BUCKETS = [
    ("1.01 - 1.49 (Heavy Fav)", 1.00, 1.50),
    ("1.50 - 1.89 (Short Odds)", 1.50, 1.90),
    ("1.90 - 2.39 (Value / Even)", 1.90, 2.40),
    ("2.40 - 3.49 (Plus Money)", 2.40, 3.50),
    ("3.50+ (Longshot)", 3.50, 9999.0),
]

EV_BUCKETS = [
    ("< 0% (Negative EV)", -9999.0, 0.0),
    ("0.0% - 4.9% (Low Edge)", 0.0, 5.0),
    ("5.0% - 9.9% (Medium Edge)", 5.0, 10.0),
    ("10.0%+ (High Edge)", 10.0, 9999.0),
]


def normalize_bet_type(market_label: str = "", bet_type: str = "", market_key: str = "") -> str:
    key = (market_key or "").strip().lower()
    if key == "home_win":
        return "Home Win (1)"
    if key == "draw":
        return "Draw (X)"
    if key == "away_win":
        return "Away Win (2)"
    if key == "over_25":
        return "Over 2.5 Goals"
    if key == "under_25":
        return "Under 2.5 Goals"
    if key == "btts_yes":
        return "BTTS - Yes"
    if key == "btts_no":
        return "BTTS - No"
    if key in ("ah_balanced", "ah_safe"):
        return "Asian Handicap"

    bt = (bet_type or "").strip()
    if bt in BET_TYPE_CATEGORIES:
        return bt

    lbl = (market_label or bt).strip()
    lbl_low = lbl.lower()
    if "(1)" in lbl_low or "home win" in lbl_low:
        return "Home Win (1)"
    if "(x)" in lbl_low or lbl_low == "draw" or "draw (x)" in lbl_low:
        return "Draw (X)"
    if "(2)" in lbl_low or "away win" in lbl_low:
        return "Away Win (2)"
    if "over 2.5" in lbl_low or "o2.5" in lbl_low or "over " in lbl_low:
        return "Over 2.5 Goals"
    if "under 2.5" in lbl_low or "u2.5" in lbl_low or "under " in lbl_low:
        return "Under 2.5 Goals"
    if "btts - yes" in lbl_low or "btts yes" in lbl_low:
        return "BTTS - Yes"
    if "btts - no" in lbl_low or "btts no" in lbl_low:
        return "BTTS - No"
    if lbl_low.startswith("ah ") or "asian handicap" in lbl_low or "handicap" in lbl_low:
        return "Asian Handicap"
    return "Correct Score / Other"


def compute_bet_settlement(stake: float, bookie_odds: float, status: str) -> dict:
    st = (status or "Pending").strip()
    stake_val = max(0.0, float(stake or 0.0))
    odds_val = max(1.01, float(bookie_odds or 1.01))

    if st == "Won":
        profit = stake_val * (odds_val - 1.0)
        payout = stake_val * odds_val
        win_weight = 1.0
        settled = True
    elif st == "Half Won":
        profit = 0.5 * stake_val * (odds_val - 1.0)
        payout = stake_val + profit
        win_weight = 0.5
        settled = True
    elif st == "Lost":
        profit = -stake_val
        payout = 0.0
        win_weight = 0.0
        settled = True
    elif st == "Half Lost":
        profit = -0.5 * stake_val
        payout = 0.5 * stake_val
        win_weight = 0.0
        settled = True
    elif st == "Push":
        profit = 0.0
        payout = stake_val
        win_weight = 0.0
        settled = True
    else:
        st = "Pending"
        profit = 0.0
        payout = 0.0
        win_weight = 0.0
        settled = False

    return {
        "status": st,
        "profit": round(profit, 2),
        "payout": round(payout, 2),
        "win_weight": win_weight,
        "settled": settled,
    }


def enrich_bet_record(raw: dict) -> dict:
    bet_id = str(raw.get("id") or uuid.uuid4().hex[:10])
    date_str = str(raw.get("date") or datetime.now().strftime("%Y-%m-%d")).strip()
    league_code = str(raw.get("league_code") or "E0").strip().upper()
    league_meta = LEAGUES.get(league_code, {"name": league_code, "short_name": league_code})
    matchup = str(raw.get("matchup") or "Unknown Match").strip()
    selection = str(raw.get("selection") or raw.get("recommended_market") or raw.get("bet_type") or "Selection").strip()
    bet_type = normalize_bet_type(
        market_label=selection,
        bet_type=str(raw.get("bet_type") or ""),
        market_key=str(raw.get("market_key") or ""),
    )

    try:
        bookie_odds = round(max(1.01, float(raw.get("bookie_odds") or 1.90)), 2)
    except (ValueError, TypeError):
        bookie_odds = 1.90

    fair_odds_raw = raw.get("fair_odds")
    fair_odds = None
    if fair_odds_raw not in (None, "", 0, "0"):
        try:
            fo = float(fair_odds_raw)
            if fo > 1.0:
                fair_odds = round(fo, 2)
        except (ValueError, TypeError):
            fair_odds = None

    prob_raw = raw.get("model_prob")
    model_prob = None
    if prob_raw not in (None, "", 0, "0"):
        try:
            mp = float(prob_raw)
            if mp > 1.0:
                mp = mp / 100.0
            if 0.0 < mp <= 1.0:
                model_prob = round(mp, 4)
        except (ValueError, TypeError):
            model_prob = None

    if model_prob is None and fair_odds is not None and fair_odds > 1.0:
        model_prob = round(1.0 / fair_odds, 4)
    elif fair_odds is None and model_prob is not None and model_prob > 0.0:
        fair_odds = round(1.0 / model_prob, 2)

    ev_pct_raw = raw.get("ev_pct")
    ev_pct = None
    if ev_pct_raw not in (None, ""):
        try:
            ev_pct = round(float(ev_pct_raw), 2)
        except (ValueError, TypeError):
            ev_pct = None
    if ev_pct is None and model_prob is not None:
        ev_pct = round(((model_prob * bookie_odds) - 1.0) * 100.0, 2)

    try:
        stake = round(max(0.0, float(raw.get("stake") or 25.0)), 2)
    except (ValueError, TypeError):
        stake = 25.0

    settlement = compute_bet_settlement(stake, bookie_odds, str(raw.get("status") or "Pending"))

    return {
        "id": bet_id,
        "date": date_str,
        "league_code": league_code,
        "league_short": league_meta.get("short_name", league_code),
        "matchup": matchup,
        "bet_type": bet_type,
        "selection": selection,
        "bookie_odds": bookie_odds,
        "fair_odds": fair_odds,
        "model_prob": model_prob,
        "model_prob_pct": round(model_prob * 100.0, 1) if model_prob is not None else None,
        "ev_pct": ev_pct,
        "stake": stake,
        "status": settlement["status"],
        "profit": settlement["profit"],
        "payout": settlement["payout"],
        "settled": settlement["settled"],
        "notes": str(raw.get("notes") or "").strip(),
    }


def load_bets() -> list:
    if not BETS_FILE.exists():
        return []
    try:
        data = json.loads(BETS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [enrich_bet_record(item) for item in data]
    except Exception:
        pass
    return []


def save_bets(bets: list) -> list:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    enriched = [enrich_bet_record(b) for b in bets]
    BETS_FILE.write_text(json.dumps(enriched, indent=2), encoding="utf-8")
    return enriched


def _aggregate_group(group_name: str, items: list, extra: dict = None) -> dict:
    settled = [b for b in items if b["settled"]]
    decisive = [b for b in settled if b["status"] in ("Won", "Half Won", "Lost", "Half Lost")]

    wins = sum(1 for b in settled if b["status"] in ("Won", "Half Won"))
    losses = sum(1 for b in settled if b["status"] in ("Lost", "Half Lost"))
    pushes = sum(1 for b in settled if b["status"] == "Push")
    pending = sum(1 for b in items if not b["settled"])

    win_units = sum(
        1.0 if b["status"] == "Won" else (0.5 if b["status"] == "Half Won" else 0.0)
        for b in decisive
    )
    win_rate_pct = round((win_units / len(decisive)) * 100.0, 1) if decisive else 0.0

    probs = [b["model_prob"] for b in decisive if b.get("model_prob") is not None]
    if not probs:
        probs = [1.0 / b["bookie_odds"] for b in decisive if b.get("bookie_odds", 0) > 1.0]
    model_win_rate_pct = round((sum(probs) / len(probs)) * 100.0, 1) if probs else 0.0
    calibration_diff_pct = round(win_rate_pct - model_win_rate_pct, 1) if decisive else 0.0

    staked = round(sum(b["stake"] for b in settled), 2)
    profit = round(sum(b["profit"] for b in settled), 2)
    roi_pct = round((profit / staked) * 100.0, 2) if staked > 0 else 0.0

    avg_odds = (
        round(sum(b["bookie_odds"] for b in settled) / len(settled), 2)
        if settled
        else (round(sum(b["bookie_odds"] for b in items) / len(items), 2) if items else 0.0)
    )
    ev_vals = [b["ev_pct"] for b in items if b.get("ev_pct") is not None]
    avg_ev_pct = round(sum(ev_vals) / len(ev_vals), 2) if ev_vals else None

    res = {
        "category": group_name,
        "total_bets": len(items),
        "settled_bets": len(settled),
        "pending_bets": pending,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_rate_pct": win_rate_pct,
        "model_win_rate_pct": model_win_rate_pct,
        "calibration_diff_pct": calibration_diff_pct,
        "avg_odds": avg_odds,
        "avg_ev_pct": avg_ev_pct,
        "staked": staked,
        "profit": profit,
        "roi_pct": roi_pct,
    }
    if extra:
        res.update(extra)
    return res


def analyze_bet_history(bets: list) -> dict:
    enriched = [enrich_bet_record(b) for b in bets]
    overall = _aggregate_group("Overall", enriched)

    settled = [b for b in enriched if b["settled"]]
    winning_bets = [b for b in settled if b["status"] in ("Won", "Half Won")]
    avg_winning_odds = (
        round(sum(b["bookie_odds"] for b in winning_bets) / len(winning_bets), 2)
        if winning_bets
        else 0.0
    )

    # 1. Breakdown by Bet Type
    by_bet_type = []
    for cat in BET_TYPE_CATEGORIES:
        cat_items = [b for b in enriched if b["bet_type"] == cat]
        if cat_items:
            by_bet_type.append(_aggregate_group(cat, cat_items))
    by_bet_type.sort(key=lambda x: (x["profit"], x["roi_pct"], x["settled_bets"]), reverse=True)

    # 2. Breakdown by Odds Range
    by_odds_range = []
    for label, low, high in ODDS_BUCKETS:
        bucket_items = [b for b in enriched if low <= b["bookie_odds"] < high]
        if bucket_items:
            by_odds_range.append(_aggregate_group(label, bucket_items, {"min_odds": low, "max_odds": high}))

    # 3. Breakdown by League
    by_league = []
    league_codes_seen = list(LEAGUES.keys()) + [
        c for c in {b["league_code"] for b in enriched} if c not in LEAGUES
    ]
    for code in league_codes_seen:
        lg_items = [b for b in enriched if b["league_code"] == code]
        if lg_items:
            lg_name = LEAGUES.get(code, {}).get("short_name", code)
            by_league.append(_aggregate_group(lg_name, lg_items, {"league_code": code}))
    by_league.sort(key=lambda x: (x["profit"], x["roi_pct"]), reverse=True)

    # 4. Breakdown by Model Edge (EV %)
    by_ev_bucket = []
    for label, low, high in EV_BUCKETS:
        ev_items = [
            b for b in enriched if b.get("ev_pct") is not None and low <= b["ev_pct"] < high
        ]
        if ev_items:
            by_ev_bucket.append(_aggregate_group(label, ev_items))
    no_ev_items = [b for b in enriched if b.get("ev_pct") is None]
    if no_ev_items:
        by_ev_bucket.append(_aggregate_group("Unrated (No Model Odds)", no_ev_items))

    # Cumulative Bankroll / Profit Progression (chronological order of settled bets)
    chronological = sorted(settled, key=lambda b: (b["date"], b["id"]))
    running_profit = 0.0
    running_staked = 0.0
    equity_curve = []
    for idx, b in enumerate(chronological, start=1):
        running_profit = round(running_profit + b["profit"], 2)
        running_staked = round(running_staked + b["stake"], 2)
        equity_curve.append(
            {
                "step": idx,
                "date": b["date"],
                "matchup": b["matchup"],
                "selection": b["selection"],
                "status": b["status"],
                "profit": b["profit"],
                "cumulative_profit": running_profit,
                "cumulative_roi_pct": round((running_profit / running_staked) * 100.0, 2)
                if running_staked > 0
                else 0.0,
            }
        )

    settled_bet_types = [g for g in by_bet_type if g["settled_bets"] > 0]
    best_bet_type = max(settled_bet_types, key=lambda x: (x["profit"], x["roi_pct"])) if settled_bet_types else None
    worst_bet_type = min(settled_bet_types, key=lambda x: (x["profit"], x["roi_pct"])) if settled_bet_types else None

    settled_odds_buckets = [g for g in by_odds_range if g["settled_bets"] > 0]
    best_odds_bucket = max(settled_odds_buckets, key=lambda x: (x["roi_pct"], x["profit"])) if settled_odds_buckets else None

    settled_leagues = [g for g in by_league if g["settled_bets"] > 0]
    best_league = max(settled_leagues, key=lambda x: (x["profit"], x["roi_pct"])) if settled_leagues else None

    # Actionable insights generation
    insights = []
    if best_bet_type:
        insights.append(
            f"Top Market: '{best_bet_type['category']}' is your most profitable bet type with "
            f"${best_bet_type['profit']:+.2f} net profit ({best_bet_type['roi_pct']:+.1f}% ROI, "
            f"{best_bet_type['win_rate_pct']}% win rate across {best_bet_type['settled_bets']} settled bets)."
        )
    if best_odds_bucket:
        insights.append(
            f"Sweet-Spot Odds: '{best_odds_bucket['category']}' yields the strongest return at "
            f"{best_odds_bucket['roi_pct']:+.1f}% ROI (${best_odds_bucket['profit']:+.2f} profit, "
            f"{best_odds_bucket['win_rate_pct']}% actual win rate vs {best_odds_bucket['model_win_rate_pct']}% model expected)."
        )
    if best_league:
        insights.append(
            f"Best League: {best_league['category']} leads with ${best_league['profit']:+.2f} profit "
            f"and {best_league['roi_pct']:+.1f}% ROI ({best_league['wins']}W-{best_league['losses']}L)."
        )
    if overall["settled_bets"] >= 3:
        diff = overall["calibration_diff_pct"]
        if abs(diff) <= 3.5:
            insights.append(
                f"Model Calibration: Well-calibrated! Your actual win rate ({overall['win_rate_pct']}%) "
                f"tracks closely with the Poisson model's expected win probability ({overall['model_win_rate_pct']}%)."
            )
        elif diff > 3.5:
            insights.append(
                f"Model Calibration: Outperforming expectations by {diff:+.1f}% "
                f"({overall['win_rate_pct']}% actual win rate vs {overall['model_win_rate_pct']}% model expected)."
            )
        else:
            insights.append(
                f"Model Calibration: Running {diff:+.1f}% below expected win rate "
                f"({overall['win_rate_pct']}% actual vs {overall['model_win_rate_pct']}% model expected) — check if longshot variance or negative-EV bets are dragging results."
            )

    summary = {
        **overall,
        "total_staked_all": round(sum(b["stake"] for b in enriched), 2),
        "avg_winning_odds": avg_winning_odds,
        "best_bet_type": best_bet_type,
        "worst_bet_type": worst_bet_type,
        "best_odds_bucket": best_odds_bucket,
        "best_league": best_league,
        "insights": insights,
    }

    return {
        "summary": summary,
        "by_bet_type": by_bet_type,
        "by_odds_range": by_odds_range,
        "by_league": by_league,
        "by_ev_bucket": by_ev_bucket,
        "equity_curve": equity_curve,
    }


def get_sample_bets() -> list:
    return [
        {
            "date": "2026-10-18",
            "league_code": "E0",
            "matchup": "Arsenal vs Bournemouth",
            "bet_type": "Home Win (1)",
            "selection": "Arsenal Win (1)",
            "bookie_odds": 1.48,
            "fair_odds": 1.38,
            "stake": 45.0,
            "status": "Won",
        },
        {
            "date": "2026-10-18",
            "league_code": "SP1",
            "matchup": "Barcelona vs Sevilla",
            "bet_type": "Over 2.5 Goals",
            "selection": "Over 2.5 Goals",
            "bookie_odds": 1.72,
            "fair_odds": 1.56,
            "stake": 40.0,
            "status": "Won",
        },
        {
            "date": "2026-10-19",
            "league_code": "I1",
            "matchup": "Inter vs Napoli",
            "bet_type": "BTTS - No",
            "selection": "BTTS - No",
            "bookie_odds": 2.08,
            "fair_odds": 1.86,
            "stake": 35.0,
            "status": "Won",
        },
        {
            "date": "2026-10-20",
            "league_code": "E0",
            "matchup": "Liverpool vs Chelsea",
            "bet_type": "BTTS - Yes",
            "selection": "BTTS - Yes",
            "bookie_odds": 1.66,
            "fair_odds": 1.58,
            "stake": 30.0,
            "status": "Won",
        },
        {
            "date": "2026-10-22",
            "league_code": "I1",
            "matchup": "Juventus vs Lazio",
            "bet_type": "Under 2.5 Goals",
            "selection": "Under 2.5 Goals",
            "bookie_odds": 1.85,
            "fair_odds": 1.71,
            "stake": 35.0,
            "status": "Won",
        },
        {
            "date": "2026-10-24",
            "league_code": "SP1",
            "matchup": "Real Madrid vs Villarreal",
            "bet_type": "Asian Handicap",
            "selection": "AH Real Madrid -1.25",
            "bookie_odds": 1.98,
            "fair_odds": 1.82,
            "stake": 38.0,
            "status": "Won",
        },
        {
            "date": "2026-10-25",
            "league_code": "E0",
            "matchup": "Brighton vs Wolves",
            "bet_type": "Draw (X)",
            "selection": "Draw (X)",
            "bookie_odds": 3.80,
            "fair_odds": 3.45,
            "stake": 18.0,
            "status": "Lost",
        },
        {
            "date": "2026-10-26",
            "league_code": "SP1",
            "matchup": "Atletico Madrid vs Betis",
            "bet_type": "Under 2.5 Goals",
            "selection": "Under 2.5 Goals",
            "bookie_odds": 1.92,
            "fair_odds": 1.76,
            "stake": 32.0,
            "status": "Won",
        },
        {
            "date": "2026-10-27",
            "league_code": "I1",
            "matchup": "Milan vs Roma",
            "bet_type": "Away Win (2)",
            "selection": "Roma Win (2)",
            "bookie_odds": 3.60,
            "fair_odds": 3.30,
            "stake": 20.0,
            "status": "Lost",
        },
        {
            "date": "2026-10-28",
            "league_code": "E0",
            "matchup": "Aston Villa vs Fulham",
            "bet_type": "Home Win (1)",
            "selection": "Aston Villa Win (1)",
            "bookie_odds": 1.95,
            "fair_odds": 1.78,
            "stake": 36.0,
            "status": "Won",
        },
        {
            "date": "2026-10-29",
            "league_code": "I1",
            "matchup": "Atalanta vs Fiorentina",
            "bet_type": "Over 2.5 Goals",
            "selection": "Over 2.5 Goals",
            "bookie_odds": 1.88,
            "fair_odds": 1.74,
            "stake": 30.0,
            "status": "Lost",
        },
        {
            "date": "2026-10-30",
            "league_code": "SP1",
            "matchup": "Sociedad vs Athletic Club",
            "bet_type": "BTTS - No",
            "selection": "BTTS - No",
            "bookie_odds": 1.96,
            "fair_odds": 1.79,
            "stake": 34.0,
            "status": "Won",
        },
    ]


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
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        inc_last = _parse_bool(
            qs.get("include_last_season", ["true"])[0], default=True
        )
        if parsed.path == "/api/data-status":
            files = [get_file_metadata(src) for src in DATA_SOURCES]
            self._send_json(
                200,
                {
                    "files": files,
                    "team_stats": get_all_leagues_stats(include_last_season=inc_last),
                },
            )
            return
        if parsed.path == "/api/team-stats":
            self._send_json(
                200, get_all_leagues_stats(include_last_season=inc_last)
            )
            return
        if parsed.path == "/api/bets":
            bets = load_bets()
            self._send_json(
                200,
                {
                    "bets": bets,
                    "analytics": analyze_bet_history(bets),
                },
            )
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/bets":
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(raw_body.decode("utf-8"))
                bets = load_bets()
                if payload.get("action") == "load_samples":
                    sample_records = [enrich_bet_record(s) for s in get_sample_bets()]
                    bets.extend(sample_records)
                elif isinstance(payload.get("bets"), list):
                    for item in payload["bets"]:
                        bets.insert(0, enrich_bet_record(item))
                else:
                    new_bet = enrich_bet_record(payload)
                    bets.insert(0, new_bet)
                saved = save_bets(bets)
                self._send_json(
                    200,
                    {
                        "bets": saved,
                        "analytics": analyze_bet_history(saved),
                    },
                )
            except Exception as exc:
                self._send_json(400, {"error": str(exc)})
            return
        if parsed.path == "/api/update-data":
            qs = parse_qs(parsed.query)
            inc_last = _parse_bool(
                qs.get("include_last_season", ["true"])[0], default=True
            )
            result = update_data_files(include_last_season=inc_last)
            status_code = 200 if result["success"] else 207
            self._send_json(status_code, result)
            return
        if parsed.path == "/api/calculate-round":
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(raw_body.decode("utf-8"))
                matchups = payload.get("matchups", [])
                bankroll = float(payload.get("bankroll", 1000.0) or 1000.0)
                kelly_multiplier = float(
                    payload.get("kelly_multiplier", 0.25) or 0.25
                )
                inc_last = _parse_bool(
                    payload.get("include_last_season", True), default=True
                )
                round_data = calculate_round_matches(
                    matchups,
                    bankroll=bankroll,
                    kelly_multiplier=kelly_multiplier,
                    include_last_season=inc_last,
                )
                self._send_json(200, round_data)
            except Exception as exc:
                self._send_json(400, {"error": str(exc)})
            return
        self._send_json(404, {"error": "Endpoint not found"})

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/bets":
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(raw_body.decode("utf-8"))
                bet_id = str(payload.get("id") or "").strip()
                if not bet_id:
                    self._send_json(400, {"error": "Missing bet id"})
                    return
                bets = load_bets()
                updated = False
                for idx, b in enumerate(bets):
                    if b["id"] == bet_id:
                        merged = {**b, **payload}
                        bets[idx] = enrich_bet_record(merged)
                        updated = True
                        break
                if not updated:
                    self._send_json(404, {"error": "Bet not found"})
                    return
                saved = save_bets(bets)
                self._send_json(
                    200,
                    {
                        "bets": saved,
                        "analytics": analyze_bet_history(saved),
                    },
                )
            except Exception as exc:
                self._send_json(400, {"error": str(exc)})
            return
        self._send_json(404, {"error": "Endpoint not found"})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/bets":
            qs = parse_qs(parsed.query)
            clear_all = _parse_bool(qs.get("all", ["false"])[0], default=False)
            bet_id = (qs.get("id", [""])[0] or "").strip()
            bets = load_bets()
            if clear_all:
                bets = []
            elif bet_id:
                bets = [b for b in bets if b["id"] != bet_id]
            saved = save_bets(bets)
            self._send_json(
                200,
                {
                    "bets": saved,
                    "analytics": analyze_bet_history(saved),
                },
            )
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
