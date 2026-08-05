ACE CHASERS · v1.0.3 UPLOAD KEY RESET
======================================

Files in this folder:
  * acechasers-net-v1.0.3.aab            → the new signed release bundle
  * upload-keystore.jks                  → NEW upload keystore (save this forever)
  * upload_certificate.pem               → public cert to send Google
  * NEW_UPLOAD_KEYSTORE_PASSWORD.txt     → password for the .jks (save this forever)

WHY: v1.0.3 fixes the Android 15 "deprecated edge-to-edge APIs" warning
(androidbrowserhelper 2.6.2 → 2.7.2). We had to generate a brand-new
upload key because the old keystore password was lost. Your real app-
signing key is still safe with Google (Play App Signing).

WHAT TO DO — in order:
──────────────────────────────────────────────────────────────────────

1) DOWNLOAD ALL 4 FILES to a safe local folder RIGHT NOW.
   Suggested path on your computer:  ~/AceChasers/keys/upload-2026/
   Back this folder up (Google Drive / password manager attachment).

2) REQUEST an upload-key reset with Google Play:
   Play Console → Setup → App integrity → App signing
   → "Change app signing key" section
   → click "Request upload key reset"
   Attach:  upload_certificate.pem
   In the reason box, write:
     "Upload keystore password lost. Generated a new upload key.
      Attaching the new public certificate."
   Submit. Google usually approves within 1-2 business days.

3) WHILE YOU WAIT, tell me here in chat once you've saved the files.
   I will DELETE them from the public /downloads folder immediately
   so nobody else can grab them.

4) After Google confirms the upload key reset, upload
   acechasers-net-v1.0.3.aab to Play Console → Closed testing → Create
   new release. That build:
     * fixes the Android 15 deprecated-API warning
     * bumps versionCode 3 → 4, versionName 1.0.2 → 1.0.3
     * raises minSdk 21 → 23 (Android 6.0+, still 99%+ of devices)

5) FOR FUTURE RELEASES, always sign with upload-keystore.jks using the
   password from NEW_UPLOAD_KEYSTORE_PASSWORD.txt. Never lose it again.

──────────────────────────────────────────────────────────────────────

If Play Console rejects the upload with "signature mismatch," it means
the upload key reset hasn't been approved yet — wait for Google's email.
