import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const backend = new URL(process.env.GEOPULSE_BACKEND_URL ?? 'http://127.0.0.1:8080');
const websocket = new URL(backend);
websocket.protocol = backend.protocol === 'https:' ? 'wss:' : 'ws:';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': backend.origin,
      '/ws': { target: websocket.origin, ws: true },
    },
  },
});
