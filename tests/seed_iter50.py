"""Seed helper: create director account + finalize a round so the completed
archive has a winner chip to verify in the browser. Prints EMAIL/PASSWORD to stdout."""
import os, uuid, time, sys, json, requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://league-manager-hub-3.preview.emergentagent.com").rstrip("/")
FB_KEY = os.environ.get("REACT_APP_FIREBASE_API_KEY") or "AIzaSyCaW_gJQ6zyUiHrr99VFmUPHvSgC2w2rVA"
SIGNUP = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FB_KEY}"

def H(t): return {"Authorization": f"Bearer {t}"}

def signup():
    for i in range(6):
        email = f"TEST_i50_{uuid.uuid4().hex[:10]}@example.com"
        pw = "demo1234"
        r = requests.post(SIGNUP, json={"email": email, "password": pw, "returnSecureToken": True}, timeout=25)
        if r.status_code == 200:
            tok = r.json()["idToken"]
            requests.post(f"{BASE_URL}/api/auth/sync", json={}, headers=H(tok), timeout=25)
            return email, pw, tok
        time.sleep(10)
    raise RuntimeError("firebase signup ratelimited")

def main():
    email, pw, tok = signup()
    # league
    lg = requests.post(f"{BASE_URL}/api/leagues", json={
        "name": f"i50-{uuid.uuid4().hex[:6]}", "location": "T",
        "format": "Singles", "entry_fee": 0.0}, headers=H(tok), timeout=15).json()
    lid = lg["id"]
    seasons = requests.get(f"{BASE_URL}/api/leagues/{lid}/seasons", headers=H(tok), timeout=15).json()
    # 1) COMPLETED round
    rd = requests.post(f"{BASE_URL}/api/leagues/{lid}/rounds", json={
        "name": "Champ Round", "date": "2026-09-01", "season_id": seasons[0]["id"],
        "holes": 9, "par_per_hole": [3]*9, "publish_announcement": False},
        headers=H(tok), timeout=15).json()
    requests.patch(f"{BASE_URL}/api/rounds/{rd['id']}/status", json={"status": "active"}, headers=H(tok), timeout=15)
    j = requests.post(f"{BASE_URL}/api/rounds/{rd['id']}/join", headers=H(tok), timeout=15).json()
    sc = j["scorecard"]["id"]
    for hole in range(1, 10):
        requests.patch(f"{BASE_URL}/api/scorecards/{sc}/score", json={"hole": hole, "strokes": 3}, headers=H(tok), timeout=15)
    requests.post(f"{BASE_URL}/api/scorecards/{sc}/finalize", json={"certified": True}, headers=H(tok), timeout=15)
    requests.post(f"{BASE_URL}/api/rounds/{rd['id']}/finalize", json={"certified": True}, headers=H(tok), timeout=15)
    # 2) ACTIVE round with a scorecard (for bulk print)
    rd2 = requests.post(f"{BASE_URL}/api/leagues/{lid}/rounds", json={
        "name": "Live Round", "date": "2026-10-15", "season_id": seasons[0]["id"],
        "holes": 9, "par_per_hole": [3]*9, "publish_announcement": False},
        headers=H(tok), timeout=15).json()
    requests.patch(f"{BASE_URL}/api/rounds/{rd2['id']}/status", json={"status": "active"}, headers=H(tok), timeout=15)
    requests.post(f"{BASE_URL}/api/rounds/{rd2['id']}/join", headers=H(tok), timeout=15)

    # verify completed round has winner
    rounds = requests.get(f"{BASE_URL}/api/leagues/{lid}/rounds", headers=H(tok), timeout=15).json()
    completed = next(x for x in rounds if x["id"] == rd["id"])
    print(json.dumps({
        "email": email, "password": pw, "league_id": lid,
        "completed_round_id": rd["id"], "active_round_id": rd2["id"],
        "winner_name": completed.get("winner_name"),
        "winner_id": completed.get("winner_id"),
        "status": completed.get("status"),
    }))

if __name__ == "__main__":
    main()
