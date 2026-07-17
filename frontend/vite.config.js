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
      // Warn only above 900KB (React + Firebase + Radix vendors alone are
      // dense). Real split targets are enforced by manualChunks below.
      chunkSizeWarningLimit: 900,
      rollupOptions: {
        output: {
          // Vendor chunks let the browser cache the (rarely-changing) 3rd-
          // party JS separately from our app code so shipping a new build
          // only invalidates ~50KB, not 1.3MB.
          manualChunks: (id) => {
            if (!id.includes('node_modules')) return undefined;
            if (id.includes('firebase')) return 'vendor-firebase';
            if (id.includes('@radix-ui')) return 'vendor-radix';
            if (id.includes('recharts') || id.includes('d3-')) return 'vendor-charts';
            if (id.includes('@phosphor-icons') || id.includes('lucide-react')) return 'vendor-icons';
            if (id.includes('react-router') || id.includes('react-dom') || id.includes('/react/')) return 'vendor-react';
            if (id.includes('@tanstack')) return 'vendor-query';
            if (id.includes('date-fns') || id.includes('sonner') || id.includes('cmdk') || id.includes('zod')) return 'vendor-ui';
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
