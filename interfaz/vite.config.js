import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// /api goes to the search server (API.md). Change the target if it runs elsewhere.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
});
