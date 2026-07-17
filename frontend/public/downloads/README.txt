Ace Chasers — Android release bundle package
=============================================

Files in this folder:

1) AceChasers-release-1.0.0.aab   ← THIS IS WHAT YOU UPLOAD TO PLAY CONSOLE
   Signed Android App Bundle, v1 (versionCode 1, versionName 1.0.0)
   Package ID: net.acechasers.twa
   Target: API 34 (Android 14), min SDK 21 (Android 5.0)

2) AceChasers-release-1.0.0.apk
   Same TWA as an APK. NOT used for Play submission. Useful if you want to
   sideload onto your own device for a quick test before submitting.

3) android.keystore + KEYSTORE_PASSWORD.txt   ← KEEP THESE FOREVER
   Your upload signing key. If you lose these you can never publish an
   update to this app (you'd have to re-request an upload key reset in
   Play Console, which takes 2-3 business days).
   Move both files to 1Password / Bitwarden / a hardware security key.

Fingerprints:
- Upload key SHA-256:  22:F8:BD:A0:06:2D:A3:C5:57:28:00:86:32:F9:F3:80:7D:41:C4:92:09:EF:8F:4D:DF:7B:9A:D8:C4:0B:39:9F
- App Signing SHA-256: 7D:63:D0:21:DD:83:A3:54:DF:0D:FB:BD:3A:A9:D1:51:00:E1:A8:FA:CD:0E:75:1B:1C:2D:1F:75:AF:7C:97:7A
Both are now present in /.well-known/assetlinks.json.
