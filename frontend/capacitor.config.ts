import type { CapacitorConfig } from '@capacitor/cli';

/**
 * Capacitor configuration for Ace Chasers.
 *
 * Committed so you can skip `cap init` — after `git pull` the next
 * step is:
 *   yarn add -D @capacitor/cli @capacitor/android
 *   yarn build
 *   npx cap add android      # only the first time on a machine
 *   npx cap sync android
 *   cd ../android && ./gradlew bundleRelease
 *
 * `webDir: "dist"` is the Vite production output (matches
 * frontend/vite.config.ts `build.outDir`). If you ever change that,
 * update this file too.
 */
const config: CapacitorConfig = {
  appId: 'net.acechasers.app',
  appName: 'Ace Chasers',
  webDir: 'dist',
  server: {
    // Native shell talks to production so a bundled build works even
    // if the device is offline from your preview. Change to a
    // preview URL for internal builds.
    androidScheme: 'https',
  },
  plugins: {
    PushNotifications: {
      // Presents heads-up banner + badge + sound when a payload
      // arrives while the app is in the foreground. Matches the
      // in-app JS primer flow in src/components/PushPermissionPrimer.jsx.
      presentationOptions: ['badge', 'sound', 'alert'],
    },
  },
};

export default config;
