import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backend = 'http://127.0.0.1:8000'

const httpProxy = {
  target: backend,
  changeOrigin: true,
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/users': httpProxy,
      '/passengers': httpProxy,
      '/drivers': httpProxy,
      '/vehicles': httpProxy,
      '/rides': httpProxy,
      '/trips': httpProxy,
      '/internal': httpProxy,
      '/payments': httpProxy,
      '/ws': {
        target: backend,
        changeOrigin: true,
        ws: true,
      },
    },
  },
})

