# Auth Testing Playbook

Emergent Google Auth: users authenticate via https://auth.emergentagent.com and land at `{redirect_url}#session_id=...`. Backend exchanges session_id at `https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data` and stores session_token in DB + httpOnly cookie (7 day expiry).

## Test User Setup
```
mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'test.user.' + Date.now() + '@example.com',
  name: 'Test User',
  picture: 'https://via.placeholder.com/150',
  created_at: new Date()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"
```

## API Auth
- Cookie `session_token` OR `Authorization: Bearer <session_token>`
- `/api/auth/me` returns user data if authenticated

## Test in browser
```
await page.context.add_cookies([{
    "name": "session_token",
    "value": "<TOKEN>",
    "domain": "<host>",
    "path": "/",
    "httpOnly": True,
    "secure": True,
    "sameSite": "None"
}]);
```
