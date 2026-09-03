import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { resolve } from 'path';

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api/v1': {
        target: 'http://localhost:3000',  // Node 后端
        changeOrigin: true,
      },
      '/api/python': {
        target: 'http://localhost:8000',  // Python 后端
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/python/, '/api/v1'),
      },
    },
  },
});
