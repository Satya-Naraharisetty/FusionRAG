import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiUrl = env.VITE_API_URL || 'http://localhost:8000'

  return {
    plugins: [
      react(),
      tailwindcss(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['favicon.ico', 'apple-touch-icon.png'],
        manifest: {
          name: 'Hybrid RAG Chatbot',
          short_name: 'RAG Chat',
          description: 'AI-powered document chat with hybrid retrieval',
          id: '/',
          start_url: '/',
          scope: '/',
          lang: 'en',
          theme_color: '#0d0d0d',
          background_color: '#0d0d0d',
          display: 'standalone',
          display_override: ['window-controls-overlay', 'standalone', 'fullscreen'],
          orientation: 'any',
          categories: ['productivity', 'utilities'],
          icons: [
            {
              src: 'pwa-192x192.png',
              sizes: '192x192',
              type: 'image/png',
              purpose: 'any'
            },
            {
              src: 'pwa-512x512.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'any'
            },
            {
              src: 'pwa-192-maskable.png',
              sizes: '192x192',
              type: 'image/png',
              purpose: 'maskable'
            },
            {
              src: 'pwa-512-maskable.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'maskable'
            }
          ],
          shortcuts: [
            {
              name: 'New chat',
              short_name: 'Chat',
              url: '/chat',
              icons: [{ src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' }]
            },
            {
              name: 'Documents',
              short_name: 'Docs',
              url: '/documents',
              icons: [{ src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' }]
            },
            {
              name: 'Settings',
              short_name: 'Settings',
              url: '/settings',
              icons: [{ src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' }]
            }
          ]
        },
        workbox: {
          globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
          navigateFallback: '/index.html',
          runtimeCaching: [
            {
              // Never cache API traffic; auth + chat must always hit the network.
              urlPattern: /^\/api\//,
              handler: 'NetworkOnly'
            },
            {
              // Cache Google Fonts so first load is fast and offline installs
              // still render the correct typeface.
              urlPattern: /^https:\/\/fonts\.(googleapis|gstatic)\.com\/.*/i,
              handler: 'CacheFirst',
              options: {
                cacheName: 'google-fonts',
                expiration: {
                  maxEntries: 12,
                  maxAgeSeconds: 60 * 60 * 24 * 365
                },
                cacheableResponse: { statuses: [0, 200] }
              }
            }
          ]
        }
      })
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
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom', 'react-router-dom'],
            'react-query': ['@tanstack/react-query'],
            shiki: ['shiki']
          }
        }
      }
    }
  }
})
