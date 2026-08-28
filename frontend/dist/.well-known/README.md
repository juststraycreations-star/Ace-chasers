# Digital Asset Links — TWA / Android verification

Before Google Play will accept the Trusted Web Activity, it needs to verify that
`acechasers.net` is officially linked to your Android app. That's done by
serving a JSON file at:

    https://acechasers.net/.well-known/assetlinks.json

The file in this folder is a **template**. It needs two values filled in:

## Values to substitute

1. **`package_name`** — This is the Android package identifier PWABuilder
   assigns to your app. It looks like `net.acechasers.twa` by default, but
   PWABuilder shows you the exact one during the "Package for Stores" step.
   Update it if PWABuilder chose a different name.

2. **`sha256_cert_fingerprints`** — The SHA-256 fingerprint of the signing
   key that PWABuilder generates for your app. It looks like:

   `AB:CD:EF:12:34:...`  (64 hex pairs separated by colons)

   PWABuilder prints this after generating the Android package. You can also
   pull it from Google Play Console → Setup → App signing.

## Publishing steps

1. Generate the Android AAB in PWABuilder → download the ZIP → open the
   included `assetlinks.json` PWABuilder ships in the ZIP.
2. Copy the two values above from PWABuilder's version into
   `/app/frontend/public/.well-known/assetlinks.json` in this repo.
3. Redeploy so the file is live at `https://acechasers.net/.well-known/assetlinks.json`.
4. Verify:
       curl https://acechasers.net/.well-known/assetlinks.json
   Should return the JSON with correct values.
5. Upload the AAB to Play Console. Play verifies the assetlinks file
   automatically during review — if it matches, the TWA is approved.

## Common gotchas

- The file MUST be served with `Content-Type: application/json` (Vite does
  this automatically for `.json` in `/public`).
- No redirect: `acechasers.net/.well-known/assetlinks.json` must return 200
  directly (not a redirect to `www` or vice versa).
- No trailing whitespace or BOM in the file.
- After Play publishes the app, you can also use Google's verifier tool:
  https://developers.google.com/digital-asset-links/tools/generator
