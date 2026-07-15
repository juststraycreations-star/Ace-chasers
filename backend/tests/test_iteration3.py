"""Iteration 3 backend tests for Ace Chasers.

Covers:
- League model entry_fee, divisions[], payout_split
- POST /api/leagues/{id}/entry-fees/collect (director + 403 + 400 zero fee + split)
- PATCH /api/rounds/{id}/director-notes (director + WS broadcast + persist)
- PATCH /api/league-members/{id}/division (director / self / other 403)
- POST/GET/DELETE /api/rounds/{id}/ctp (validation + broadcast)
- GET /api/rounds/{id}/payout (pool_available reflects credits)
- POST /api/rounds/{id}/finalize-payout (creates debits)
"""
import json as _json
import os
import time
import threading
import pytest
import requests
import websocket as wsclient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
WS_BASE = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/api/ws"

DIRECTOR = "test_session_director_2026"
ALPHA = "test_session_alpha_2026"
BRAVO = "test_session_bravo_2026"


def _h(t):
    return {"Authorization": f"Bearer {t}"}


STATE = {}


@pytest.fixture(scope="module", autouse=True)
def setup_league():
    payload = {
        "name": "TEST_IT3_League",
        "location": "Test Park 3",
        "format": "Singles",
        "win_points": 10, "points_step": 2,
        "entry_fee": 10.0,
        "divisions": ["Open", "MPO"],
        "schedule": {"weeks": 2, "start_date": "2026-03-01T00:00:00+00:00",
                     "weekday": "Sunday", "course_rating": 54},
    }
    r = requests.post(f"{API}/leagues", json=payload, headers=_h(DIRECTOR))
    assert r.status_code == 200, r.text
    lg = r.json()
    STATE["league"] = lg
    lid = lg["id"]
    STATE["league_id"] = lid

    r_a = requests.post(f"{API}/leagues/{lid}/join", headers=_h(ALPHA))
    r_b = requests.post(f"{API}/leagues/{lid}/join", headers=_h(BRAVO))
    assert r_a.status_code == 200, r_a.text
    assert r_b.status_code == 200, r_b.text
    STATE["alpha_member_id"] = r_a.json()["id"]
    STATE["bravo_member_id"] = r_b.json()["id"]

    mems = requests.get(f"{API}/leagues/{lid}/members", headers=_h(DIRECTOR)).json()
    STATE["director_member_id"] = next(m["id"] for m in mems if m["user_id"] == "test-user-director")

    rounds = requests.get(f"{API}/leagues/{lid}/rounds", headers=_h(DIRECTOR)).json()
    STATE["rounds"] = rounds
    STATE["round_id"] = rounds[0]["id"]

    # Zero-fee league for negative test
    r_zero = requests.post(f"{API}/leagues", json={
        "name": "TEST_IT3_ZeroFee",
        "location": "X",
        "format": "Singles",
        "win_points": 10, "points_step": 2,
        "entry_fee": 0.0,
        "schedule": {"weeks": 1, "start_date": "2026-03-01T00:00:00+00:00", "weekday": "Sunday"},
    }, headers=_h(DIRECTOR))
    assert r_zero.status_code == 200
    STATE["zero_league_id"] = r_zero.json()["id"]
    requests.post(f"{API}/leagues/{STATE['zero_league_id']}/join", headers=_h(ALPHA))
    yield


# ---------- League model fields ----------
class TestLeagueModel:
    def test_entry_fee_persisted(self):
        assert STATE["league"]["entry_fee"] == 10.0

    def test_divisions_persisted(self):
        assert STATE["league"]["divisions"] == ["Open", "MPO"]

    def test_payout_split_default(self):
        split = STATE["league"]["payout_split"]
        assert abs(split["pool"] - 0.7) < 1e-6
        assert abs(split["ace"] - 0.2) < 1e-6
        assert abs(split["club"] - 0.1) < 1e-6

    def test_round_has_director_notes_and_ctp_fields(self):
        r = STATE["rounds"][0]
        assert "director_notes" in r
        assert "ctp_holes" in r
        assert r["ctp_holes"] == []

    def test_league_member_has_division(self):
        lid = STATE["league_id"]
        mems = requests.get(f"{API}/leagues/{lid}/members", headers=_h(DIRECTOR)).json()
        assert all("division" in m for m in mems)
        assert all(m.get("division") == "Open" for m in mems)  # default


# ---------- Entry Fees collection ----------
class TestEntryFees:
    def test_collect_director_and_split(self):
        lid = STATE["league_id"]
        rid = STATE["round_id"]
        r = requests.post(
            f"{API}/leagues/{lid}/entry-fees/collect",
            json={"round_id": rid,
                  "member_ids": [STATE["alpha_member_id"], STATE["bravo_member_id"]]},
            headers=_h(DIRECTOR),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["collected_from"] == 2
        assert data["total"] == 20.0
        assert data["split"]["weekly_payout"] == 14.0
        assert data["split"]["ace_pool"] == 4.0
        assert data["split"]["club_fund"] == 2.0

    def test_ledger_reflects_split(self):
        lid = STATE["league_id"]
        ledger = requests.get(f"{API}/leagues/{lid}/ledger", headers=_h(DIRECTOR)).json()["entries"]
        # Entry Fee credits: 2 (one per member @ 10)
        ef_credits = [e for e in ledger if e["category"] == "Entry Fee" and e["kind"] == "credit"]
        ef_debits = [e for e in ledger if e["category"] == "Entry Fee" and e["kind"] == "debit"]
        assert len(ef_credits) == 2
        assert sum(e["amount"] for e in ef_credits) == 20.0
        assert sum(e["amount"] for e in ef_debits) == 20.0
        # Buckets
        wp = [e for e in ledger if e["category"] == "Weekly Payout" and e["kind"] == "credit"]
        ap = [e for e in ledger if e["category"] == "Ace Pool" and e["kind"] == "credit"]
        cf = [e for e in ledger if e["category"] == "Club Fund" and e["kind"] == "credit"]
        assert sum(e["amount"] for e in wp) == 14.0
        assert sum(e["amount"] for e in ap) == 4.0
        assert sum(e["amount"] for e in cf) == 2.0

    def test_non_director_403(self):
        lid = STATE["league_id"]
        r = requests.post(
            f"{API}/leagues/{lid}/entry-fees/collect",
            json={"round_id": STATE["round_id"], "member_ids": [STATE["alpha_member_id"]]},
            headers=_h(ALPHA),
        )
        assert r.status_code == 403, r.text

    def test_zero_entry_fee_400(self):
        lid = STATE["zero_league_id"]
        mems = requests.get(f"{API}/leagues/{lid}/members", headers=_h(DIRECTOR)).json()
        r = requests.post(
            f"{API}/leagues/{lid}/entry-fees/collect",
            json={"member_ids": [mems[0]["id"]]},
            headers=_h(DIRECTOR),
        )
        assert r.status_code == 400, r.text


# ---------- Division update ----------
class TestDivision:
    def test_director_updates_any(self):
        r = requests.patch(
            f"{API}/league-members/{STATE['alpha_member_id']}/division",
            json={"division": "MPO"}, headers=_h(DIRECTOR),
        )
        assert r.status_code == 200, r.text
        assert r.json()["division"] == "MPO"

        mems = requests.get(f"{API}/leagues/{STATE['league_id']}/members",
                            headers=_h(DIRECTOR)).json()
        alpha = next(m for m in mems if m["id"] == STATE["alpha_member_id"])
        assert alpha["division"] == "MPO"

    def test_player_updates_self(self):
        r = requests.patch(
            f"{API}/league-members/{STATE['bravo_member_id']}/division",
            json={"division": "MPO"}, headers=_h(BRAVO),
        )
        assert r.status_code == 200, r.text

    def test_player_cannot_update_other(self):
        r = requests.patch(
            f"{API}/league-members/{STATE['alpha_member_id']}/division",
            json={"division": "Open"}, headers=_h(BRAVO),
        )
        assert r.status_code == 403, r.text


# ---------- Director notes ----------
class TestDirectorNotes:
    def test_director_patches_notes_and_ctp_holes(self):
        rid = STATE["round_id"]
        r = requests.patch(
            f"{API}/rounds/{rid}/director-notes",
            json={"director_notes": "Watch for lightning", "ctp_holes": [5, 9]},
            headers=_h(DIRECTOR),
        )
        assert r.status_code == 200, r.text
        # Verify persistence
        rounds = requests.get(f"{API}/leagues/{STATE['league_id']}/rounds",
                              headers=_h(DIRECTOR)).json()
        this_round = next(x for x in rounds if x["id"] == rid)
        assert this_round["director_notes"] == "Watch for lightning"
        assert this_round["ctp_holes"] == [5, 9]

    def test_non_director_403(self):
        rid = STATE["round_id"]
        r = requests.patch(
            f"{API}/rounds/{rid}/director-notes",
            json={"director_notes": "hi"}, headers=_h(ALPHA),
        )
        assert r.status_code == 403

    def test_ws_broadcast_on_notes(self):
        rid = STATE["round_id"]
        url = f"{WS_BASE}/rounds/{rid}?token={DIRECTOR}"
        received = []

        def _run():
            try:
                ws = wsclient.create_connection(url, timeout=8)
                # discard hello
                ws.recv()
                # trigger update in a thread
                def _patch():
                    time.sleep(0.4)
                    requests.patch(
                        f"{API}/rounds/{rid}/director-notes",
                        json={"director_notes": "Storm coming", "ctp_holes": [3, 7]},
                        headers=_h(DIRECTOR),
                    )
                threading.Thread(target=_patch, daemon=True).start()
                deadline = time.time() + 6
                while time.time() < deadline:
                    ws.settimeout(3)
                    try:
                        msg = ws.recv()
                        received.append(msg)
                        if '"director_notes"' in msg and "Storm coming" in msg:
                            break
                    except Exception:
                        break
                ws.close()
            except Exception as e:
                received.append(f"ERR:{e}")
        t = threading.Thread(target=_run)
        t.start()
        t.join(timeout=15)
        assert any("director_notes" in m and "Storm coming" in m for m in received), received


# ---------- CTP ----------
class TestCTP:
    def test_create_ctp_valid(self):
        rid = STATE["round_id"]
        r = requests.post(
            f"{API}/rounds/{rid}/ctp",
            json={"hole": 5, "feet": 12, "inches": 3.5},
            headers=_h(ALPHA),
        )
        assert r.status_code == 200, r.text
        e = r.json()
        assert e["hole"] == 5
        assert e["feet"] == 12
        assert e["inches"] == 3.5
        STATE["ctp_entry_alpha"] = e["id"]

    def test_create_ctp_invalid_inches(self):
        rid = STATE["round_id"]
        r = requests.post(
            f"{API}/rounds/{rid}/ctp",
            json={"hole": 5, "feet": 5, "inches": 12},
            headers=_h(ALPHA),
        )
        assert r.status_code == 400

    def test_create_ctp_invalid_feet(self):
        rid = STATE["round_id"]
        r = requests.post(
            f"{API}/rounds/{rid}/ctp",
            json={"hole": 5, "feet": -1, "inches": 0},
            headers=_h(ALPHA),
        )
        assert r.status_code == 400

    def test_create_ctp_invalid_hole(self):
        rid = STATE["round_id"]
        r = requests.post(
            f"{API}/rounds/{rid}/ctp",
            json={"hole": 99, "feet": 5, "inches": 0},
            headers=_h(ALPHA),
        )
        assert r.status_code == 400

    def test_ctp_leaderboard_sorted(self):
        rid = STATE["round_id"]
        # add a farther entry from bravo
        r = requests.post(f"{API}/rounds/{rid}/ctp",
                          json={"hole": 5, "feet": 20, "inches": 0}, headers=_h(BRAVO))
        assert r.status_code == 200
        STATE["ctp_entry_bravo"] = r.json()["id"]
        # closer bravo entry on hole 9
        requests.post(f"{API}/rounds/{rid}/ctp",
                      json={"hole": 9, "feet": 8, "inches": 6}, headers=_h(BRAVO))

        r = requests.get(f"{API}/rounds/{rid}/ctp", headers=_h(ALPHA))
        assert r.status_code == 200
        data = r.json()
        assert data["ctp_holes"] == [3, 7] or data["ctp_holes"] == [5, 9]  # last patch may vary
        h5 = data["leaderboard"]["5"] if "5" in data["leaderboard"] else data["leaderboard"][5]
        # first is smallest distance
        assert h5[0]["distance_inches"] < h5[1]["distance_inches"]
        assert h5[0]["feet"] == 12

    def test_non_member_ctp_get_403(self):
        # Create a separate league where BRAVO is not a member
        r = requests.post(f"{API}/leagues", json={
            "name": "TEST_IT3_Private", "location": "X", "format": "Singles",
            "win_points": 10, "points_step": 2,
            "schedule": {"weeks": 1, "start_date": "2026-03-01T00:00:00+00:00",
                         "weekday": "Sunday"},
        }, headers=_h(DIRECTOR)).json()
        rid = requests.get(f"{API}/leagues/{r['id']}/rounds", headers=_h(DIRECTOR)).json()[0]["id"]
        resp = requests.get(f"{API}/rounds/{rid}/ctp", headers=_h(BRAVO))
        assert resp.status_code == 403

    def test_delete_own_ctp_entry(self):
        eid = STATE["ctp_entry_alpha"]
        # bravo cannot delete alpha's
        r = requests.delete(f"{API}/ctp/{eid}", headers=_h(BRAVO))
        assert r.status_code == 403
        # alpha can
        r = requests.delete(f"{API}/ctp/{eid}", headers=_h(ALPHA))
        assert r.status_code == 200

    def test_delete_ctp_by_director(self):
        eid = STATE["ctp_entry_bravo"]
        r = requests.delete(f"{API}/ctp/{eid}", headers=_h(DIRECTOR))
        assert r.status_code == 200


# ---------- Payout ----------
class TestPayout:
    def test_payout_pool_reflects_credits(self):
        # Need scorecards with totals >0 for payout distribution
        rid = STATE["round_id"]
        # Create card w/ both players
        card_resp = requests.post(f"{API}/rounds/{rid}/cards",
            json={"label": "Card1",
                  "player_ids": [STATE["alpha_member_id"], STATE["bravo_member_id"]]},
            headers=_h(DIRECTOR))
        assert card_resp.status_code == 200, card_resp.text
        # Get scorecards
        detail = requests.get(f"{API}/rounds/{rid}", headers=_h(DIRECTOR)).json()
        alpha_sc = next(s for s in detail["scorecards"] if s["member_id"] == STATE["alpha_member_id"])
        bravo_sc = next(s for s in detail["scorecards"] if s["member_id"] == STATE["bravo_member_id"])
        # Post one hole score each so totals >0
        for h in range(1, 4):
            requests.patch(f"{API}/scorecards/{alpha_sc['id']}/score",
                           json={"hole": h, "strokes": 3}, headers=_h(ALPHA))
            requests.patch(f"{API}/scorecards/{bravo_sc['id']}/score",
                           json={"hole": h, "strokes": 4}, headers=_h(BRAVO))
        r = requests.get(f"{API}/rounds/{rid}/payout", headers=_h(DIRECTOR))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["pool_available"] == 14.0
        # Both should be MPO now
        assert "MPO" in data["divisions"]
        players = data["divisions"]["MPO"]["players"]
        # winner (alpha, lower total) placement=1 gets 50% of MPO pool
        p1 = next(p for p in players if p["place"] == 1)
        assert p1["member_id"] == STATE["alpha_member_id"]
        # curve 50/30/20 for 2 players -> [0.5, 0.3], remainder 0.2 goes to first -> 0.7
        # div_pool proportional: MPO 2/2 = full 14.0 -> p1 gets 0.7*14 = 9.8
        assert p1["payout"] == 9.8

    def test_finalize_payout_creates_debits(self):
        rid = STATE["round_id"]
        r = requests.post(f"{API}/rounds/{rid}/finalize-payout", headers=_h(DIRECTOR))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["created"] >= 1
        # Verify ledger has Weekly Payout debits
        ledger = requests.get(f"{API}/leagues/{STATE['league_id']}/ledger",
                              headers=_h(DIRECTOR)).json()["entries"]
        wp_debits = [e for e in ledger
                     if e["category"] == "Weekly Payout" and e["kind"] == "debit"
                     and e["round_id"] == rid]
        assert len(wp_debits) >= 1

    def test_finalize_payout_non_director_403(self):
        r = requests.post(f"{API}/rounds/{STATE['round_id']}/finalize-payout",
                          headers=_h(ALPHA))
        assert r.status_code == 403
