import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiUrl = env.VITE_API_URL || 'http://localhost:8000'

  return {
    plugins: [
      react(),
      tailwindcss(),
    ],
    resolve: {
      alias: {
        '@': path.resolve(import.meta.dirname, './src')
      }
    },
    server: {
      port: 5173,
      host: '0.0.0.0', // Required to expose port outside of the Docker container
      proxy: {
        '/api': {
          target: apiUrl,
          changeOrigin: true,
          secure: false
        }
      }
    },
    build: {
      modulePreload: false,
      chunkSizeWarningLimit: 850,
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom', 'react-router-dom'],
            'react-query': ['@tanstack/react-query'],
            // Only the shiki core + JS regex engine ship in the initial bundle;
            // language grammars are dynamic imports loaded on first use.
            shiki: ['shiki/core', 'shiki/engine/javascript']
          }
        }
      }
    }
  }
})
