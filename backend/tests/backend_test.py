"""End-to-end backend test suite for Ace Chasers Disc Golf platform.

Tests auth, leagues, members, rounds, scoring, ledger, clubhouse, files, stories.
Uses pre-seeded session tokens (see /app/memory/test_credentials.md).
"""
import io
import os
import time
import struct
import zlib
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://disc-league-ops.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DIRECTOR_TOKEN = "test_session_director_2026"
ALPHA_TOKEN = "test_session_alpha_2026"
BRAVO_TOKEN = "test_session_bravo_2026"


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _mkpng():
    # Minimal 1x1 red PNG
    sig = b"\x89PNG\r\n\x1a\n"
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00" + b"\xff\x00\x00"
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


# Shared state across tests
STATE = {}


# ---------- AUTH ----------
class TestAuth:
    def test_me_unauth_401(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_director_200(self):
        r = requests.get(f"{API}/auth/me", headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200
        data = r.json()
        assert data["user_id"] == "test-user-director"
        assert data["email"] == "test.player.director@example.com"

    def test_me_alpha_200(self):
        r = requests.get(f"{API}/auth/me", headers=_h(ALPHA_TOKEN))
        assert r.status_code == 200
        assert r.json()["user_id"] == "test-user-alpha"


# ---------- LEAGUES ----------
class TestLeagues:
    def test_create_league_with_schedule(self):
        payload = {
            "name": "TEST_League_QA",
            "location": "Test Park",
            "format": "Singles",
            "description": "QA test league",
            "win_points": 10, "points_step": 2,
            "schedule": {"weeks": 4, "start_date": "2026-02-01T00:00:00+00:00", "weekday": "Sunday"},
        }
        r = requests.post(f"{API}/leagues", json=payload, headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200, r.text
        lg = r.json()
        assert lg["name"] == "TEST_League_QA"
        assert lg["director_id"] == "test-user-director"
        assert "id" in lg
        STATE["league_id"] = lg["id"]

    def test_get_league_director_flag(self):
        lid = STATE["league_id"]
        r = requests.get(f"{API}/leagues/{lid}", headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200
        d = r.json()
        assert d["is_director"] is True
        assert d["is_member"] is True
        assert d["my_bag_tag"] == 1

    def test_get_league_non_member(self):
        lid = STATE["league_id"]
        r = requests.get(f"{API}/leagues/{lid}", headers=_h(BRAVO_TOKEN))
        assert r.status_code == 200
        d = r.json()
        assert d["is_director"] is False
        assert d["is_member"] is False

    def test_list_leagues_director(self):
        r = requests.get(f"{API}/leagues", headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200
        ids = [l["id"] for l in r.json()]
        assert STATE["league_id"] in ids

    def test_browse_leagues(self):
        r = requests.get(f"{API}/leagues/browse", headers=_h(ALPHA_TOKEN))
        assert r.status_code == 200
        assert any(l["id"] == STATE["league_id"] for l in r.json())

    def test_rounds_generated(self):
        lid = STATE["league_id"]
        r = requests.get(f"{API}/leagues/{lid}/rounds", headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200
        rounds = r.json()
        assert len(rounds) == 4
        STATE["round_id"] = rounds[0]["id"]
        STATE["round_id_2"] = rounds[1]["id"]


# ---------- JOIN / MEMBERS ----------
class TestMembers:
    def test_alpha_joins(self):
        lid = STATE["league_id"]
        r = requests.post(f"{API}/leagues/{lid}/join", headers=_h(ALPHA_TOKEN))
        assert r.status_code == 200
        m = r.json()
        assert m["bag_tag"] > 1
        STATE["alpha_member_id"] = m["id"]

    def test_alpha_join_idempotent(self):
        lid = STATE["league_id"]
        r = requests.post(f"{API}/leagues/{lid}/join", headers=_h(ALPHA_TOKEN))
        assert r.status_code == 200
        # Same member id
        assert r.json()["id"] == STATE["alpha_member_id"]

    def test_bravo_joins(self):
        lid = STATE["league_id"]
        r = requests.post(f"{API}/leagues/{lid}/join", headers=_h(BRAVO_TOKEN))
        assert r.status_code == 200
        STATE["bravo_member_id"] = r.json()["id"]

    def test_list_members_ok(self):
        lid = STATE["league_id"]
        r = requests.get(f"{API}/leagues/{lid}/members", headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200
        members = r.json()
        assert len(members) == 3
        # director bag_tag=1 first
        assert members[0]["bag_tag"] == 1
        # find director member id
        director = next(m for m in members if m["user_id"] == "test-user-director")
        STATE["director_member_id"] = director["id"]

    def test_list_members_non_member_403(self):
        # Create another league with alpha not joined -- reuse: bravo left? bravo joined too.
        # Test with an unrelated new league by director, alpha not joined yet.
        payload = {"name": "TEST_Private", "location": "X", "format": "Singles"}
        r = requests.post(f"{API}/leagues", json=payload, headers=_h(DIRECTOR_TOKEN))
        priv_id = r.json()["id"]
        r2 = requests.get(f"{API}/leagues/{priv_id}/members", headers=_h(ALPHA_TOKEN))
        assert r2.status_code == 403


# ---------- ROUNDS / CARDS / SCORING ----------
class TestScoring:
    def test_round_status_non_director_403(self):
        rid = STATE["round_id"]
        r = requests.patch(f"{API}/rounds/{rid}/status", json={"status": "active"},
                           headers=_h(ALPHA_TOKEN))
        assert r.status_code == 403

    def test_round_status_director(self):
        rid = STATE["round_id"]
        r = requests.patch(f"{API}/rounds/{rid}/status", json={"status": "active"},
                           headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200

    def test_create_card(self):
        rid = STATE["round_id"]
        payload = {
            "label": "Card A",
            "player_ids": [STATE["director_member_id"], STATE["alpha_member_id"], STATE["bravo_member_id"]],
        }
        r = requests.post(f"{API}/rounds/{rid}/cards", json=payload, headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200, r.text
        # Scorecards auto-created
        rd = requests.get(f"{API}/rounds/{rid}", headers=_h(DIRECTOR_TOKEN)).json()
        assert len(rd["scorecards"]) == 3
        # Track scorecards by member
        for sc in rd["scorecards"]:
            STATE[f"sc_{sc['member_id']}"] = sc["id"]

    def test_score_update_and_proof(self):
        sc_id = STATE[f"sc_{STATE['director_member_id']}"]
        r = requests.patch(f"{API}/scorecards/{sc_id}/score",
                           json={"hole": 1, "strokes": 4}, headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 4
        assert data["plus_minus"] == 1  # 4 vs par 3
        # Proof log
        p = requests.get(f"{API}/scorecards/{sc_id}/proof", headers=_h(DIRECTOR_TOKEN))
        assert p.status_code == 200
        logs = p.json()
        assert len(logs) >= 1
        assert logs[0]["new_value"] == 4

    def test_fill_scorecards_all_players(self):
        # Complete all 18 holes for director (par), alpha (par+1 each), bravo (par-1 each)
        for member_key, offset in [
            ("director_member_id", 0),  # par
            ("alpha_member_id", 1),
            ("bravo_member_id", -1 if False else 1),  # avoid net-zero surprise; both +1
        ]:
            sc_id = STATE[f"sc_{STATE[member_key]}"]
            for hole in range(1, 19):
                strokes = 3 + offset
                # Skip if director hole 1 already set
                if member_key == "director_member_id" and hole == 1:
                    strokes = 3
                r = requests.patch(f"{API}/scorecards/{sc_id}/score",
                                   json={"hole": hole, "strokes": strokes},
                                   headers=_h(DIRECTOR_TOKEN))
                assert r.status_code == 200


# ---------- HANDICAP ----------
class TestHandicap:
    def test_second_round_and_handicap(self):
        # Create card in round 2 and score all holes so we have 2 scorecards per player
        rid2 = STATE["round_id_2"]
        payload = {
            "label": "Card A",
            "player_ids": [STATE["director_member_id"], STATE["alpha_member_id"]],
        }
        r = requests.post(f"{API}/rounds/{rid2}/cards", json=payload, headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200
        rd = requests.get(f"{API}/rounds/{rid2}", headers=_h(DIRECTOR_TOKEN)).json()
        for sc in rd["scorecards"]:
            for hole in range(1, 19):
                requests.patch(f"{API}/scorecards/{sc['id']}/score",
                               json={"hole": hole, "strokes": 4}, headers=_h(DIRECTOR_TOKEN))

        lid = STATE["league_id"]
        r = requests.get(f"{API}/leagues/{lid}/handicaps", headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200
        hcs = r.json()
        # Director played 2 rounds
        director_h = next(h for h in hcs if h["member_id"] == STATE["director_member_id"])
        assert director_h["rounds_played"] >= 2
        assert isinstance(director_h["handicap"], (int, float))


# ---------- FINALIZE ROUND ----------
class TestFinalize:
    def test_complete_round_awards_and_recap(self):
        rid = STATE["round_id"]
        lid = STATE["league_id"]
        # Get pre-completion bag tags
        pre_members = {m["id"]: m for m in requests.get(f"{API}/leagues/{lid}/members",
                                                        headers=_h(DIRECTOR_TOKEN)).json()}
        r = requests.patch(f"{API}/rounds/{rid}/status", json={"status": "completed"},
                           headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200
        # Standings check
        st = requests.get(f"{API}/leagues/{lid}/standings", headers=_h(DIRECTOR_TOKEN)).json()
        assert any(s["total_points"] > 0 for s in st)
        # Recap feed post
        feed = requests.get(f"{API}/leagues/{lid}/feed", headers=_h(DIRECTOR_TOKEN)).json()
        recap = next((p for p in feed if p.get("kind") == "recap"), None)
        assert recap is not None
        assert recap.get("meta", {}).get("hot_round") is not None


# ---------- LEDGER ----------
class TestLedger:
    def test_add_ace_pool_credit(self):
        lid = STATE["league_id"]
        r = requests.post(f"{API}/leagues/{lid}/ledger",
                          json={"kind": "credit", "category": "Ace Pool", "amount": 25, "note": "week 1"},
                          headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200
        # League ace_pool incremented
        lg = requests.get(f"{API}/leagues/{lid}", headers=_h(DIRECTOR_TOKEN)).json()
        assert lg["ace_pool"] >= 25

    def test_list_ledger(self):
        lid = STATE["league_id"]
        r = requests.get(f"{API}/leagues/{lid}/ledger", headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200
        d = r.json()
        assert "entries" in d and "totals" in d and "balance" in d
        assert d["totals"].get("Ace Pool", {}).get("credit", 0) >= 25
        assert d["balance"] >= 25

    def test_non_director_cannot_add(self):
        lid = STATE["league_id"]
        r = requests.post(f"{API}/leagues/{lid}/ledger",
                          json={"kind": "credit", "category": "Ace Pool", "amount": 10},
                          headers=_h(ALPHA_TOKEN))
        assert r.status_code == 403


# ---------- CLUBHOUSE ----------
class TestClubhouse:
    def test_announcement_director(self):
        lid = STATE["league_id"]
        r = requests.post(f"{API}/leagues/{lid}/announcements",
                          json={"title": "TEST_Ann", "body": "hello", "urgent": False},
                          headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200
        STATE["ann_id"] = r.json()["id"]

    def test_announcement_non_director_403(self):
        lid = STATE["league_id"]
        r = requests.post(f"{API}/leagues/{lid}/announcements",
                          json={"title": "no", "body": "no"}, headers=_h(ALPHA_TOKEN))
        assert r.status_code == 403

    def test_list_announcements(self):
        lid = STATE["league_id"]
        r = requests.get(f"{API}/leagues/{lid}/announcements", headers=_h(ALPHA_TOKEN))
        assert r.status_code == 200
        assert any(a["id"] == STATE["ann_id"] for a in r.json())

    def test_feed_post_member(self):
        lid = STATE["league_id"]
        r = requests.post(f"{API}/leagues/{lid}/feed",
                          json={"body": "TEST_message"}, headers=_h(ALPHA_TOKEN))
        assert r.status_code == 200
        r2 = requests.get(f"{API}/leagues/{lid}/feed", headers=_h(ALPHA_TOKEN))
        assert any(p["body"] == "TEST_message" for p in r2.json())

    def test_lost_found_create_and_resolve(self):
        lid = STATE["league_id"]
        r = requests.post(f"{API}/leagues/{lid}/lost-found",
                          json={"title": "TEST_disc", "description": "lost on hole 4"},
                          headers=_h(ALPHA_TOKEN))
        assert r.status_code == 200
        item_id = r.json()["id"]
        r2 = requests.patch(f"{API}/lost-found/{item_id}/resolve", headers=_h(DIRECTOR_TOKEN))
        assert r2.status_code == 200
        lst = requests.get(f"{API}/leagues/{lid}/lost-found", headers=_h(DIRECTOR_TOKEN)).json()
        found = next(x for x in lst if x["id"] == item_id)
        assert found["resolved"] is True


# ---------- FILES & STORIES ----------
class TestFilesAndStories:
    def test_upload_download(self):
        png = _mkpng()
        files = {"file": ("test.png", png, "image/png")}
        r = requests.post(f"{API}/files/upload", files=files, headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200, r.text
        path = r.json()["path"]
        STATE["file_path"] = path
        # Unauth
        r2 = requests.get(f"{API}/files/{path}")
        assert r2.status_code == 401
        # Authed
        r3 = requests.get(f"{API}/files/{path}", headers=_h(DIRECTOR_TOKEN))
        assert r3.status_code == 200
        assert r3.headers.get("content-type", "").startswith("image/")
        assert len(r3.content) > 0

    def test_create_and_list_story(self):
        lid = STATE["league_id"]
        r = requests.post(f"{API}/leagues/{lid}/stories",
                          json={"image_path": STATE["file_path"], "caption": "TEST_story"},
                          headers=_h(DIRECTOR_TOKEN))
        assert r.status_code == 200
        r2 = requests.get(f"{API}/leagues/{lid}/stories", headers=_h(ALPHA_TOKEN))
        assert r2.status_code == 200
        assert any(s["caption"] == "TEST_story" for s in r2.json())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
