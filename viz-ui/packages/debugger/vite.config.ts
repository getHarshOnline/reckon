import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { resolve } from 'path';

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    sourcemap: true,
    // Plotly.js is inherently ~5MB; suppress warning for vendor chunks
    chunkSizeWarningLimit: 5000,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
      },
      output: {
        manualChunks(id) {
          // Split large vendor libraries into separate chunks
          if (id.includes('node_modules')) {
            if (id.includes('plotly')) {
              return 'vendor-plotly';
            }
            if (id.includes('@xyflow') || id.includes('reactflow')) {
              return 'vendor-reactflow';
            }
            if (id.includes('react-dom')) {
              return 'vendor-react';
            }
            if (id.includes('zustand')) {
              return 'vendor-zustand';
            }
          }
        },
      },
    },
  },
});
