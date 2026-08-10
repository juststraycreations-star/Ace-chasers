import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    build: {
      // Route-level code splitting via React.lazy() is the main perf win.
      // The vendor splits below are ONLY for truly leaf packages (no
      // other vendor imports them) — anything that transitively depends
      // on React MUST NOT be extracted into its own chunk or we hit
      // "Cannot read properties of undefined (reading 'useState')" at
      // runtime due to circular-init between vendor chunks.
      chunkSizeWarningLimit: 900,
      rollupOptions: {
        output: {
          manualChunks: (id) => {
            if (!id.includes('node_modules')) return undefined;
            // Firebase is a self-contained SDK — safe to split.
            if (id.includes('/firebase/') || id.includes('@firebase/')) {
              return 'vendor-firebase';
            }
            // Recharts + D3 pull ~80KB gz and are ONLY used on chart
            // pages. Safe to split because they are React consumers but
            // are lazy-imported through React.lazy pages, so their
            // vendor chunk only loads when their consumer route loads.
            if (id.includes('/recharts/') || id.includes('/d3-')) {
              return 'vendor-charts';
            }
            // Everything else (React, react-dom, react-router, radix,
            // phosphor, lucide, zustand, sonner, zod, axios, etc.) stays
            // in ONE vendor chunk so the React init order is preserved.
            return 'vendor';
          },
        },
      },
    },
    optimizeDeps: {
      // Recharts imports `react-is` at bundle time; forcing it in
      // optimizeDeps ensures esbuild can resolve it from node_modules.
      include: ['react-is'],
      esbuildOptions: {
        alias: {
          '@': path.resolve(__dirname, './src'),
        },
      },
    },
    server: {
      host: '0.0.0.0',
      port: 3000,
      strictPort: true,
      allowedHosts: true,
      hmr: { clientPort: 443 },
    },
    define: {
      // Baked-in build stamp used by the auto-cache-bust check on the
      // frontend. Prod builds should pass `ACE_BUILD_ID` at build time
      // (git sha, timestamp, etc). In `vite dev` it collapses to 'dev'
      // and the version-mismatch prompt is skipped.
      '__ACE_BUILD_ID__': JSON.stringify(env.ACE_BUILD_ID || process.env.ACE_BUILD_ID || 'dev'),
      'process.env.REACT_APP_BACKEND_URL': JSON.stringify(env.REACT_APP_BACKEND_URL || ''),
      'process.env.REACT_APP_FIREBASE_API_KEY': JSON.stringify(env.REACT_APP_FIREBASE_API_KEY || ''),
      'process.env.REACT_APP_FIREBASE_PROJECT_ID': JSON.stringify(env.REACT_APP_FIREBASE_PROJECT_ID || ''),
      'process.env.REACT_APP_FIREBASE_STORAGE_BUCKET': JSON.stringify(env.REACT_APP_FIREBASE_STORAGE_BUCKET || ''),
      'process.env.REACT_APP_FIREBASE_AUTH_DOMAIN': JSON.stringify(env.REACT_APP_FIREBASE_AUTH_DOMAIN || ''),
      'process.env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID': JSON.stringify(env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID || ''),
      'process.env.REACT_APP_FIREBASE_APP_ID': JSON.stringify(env.REACT_APP_FIREBASE_APP_ID || ''),
    },
  }
})
