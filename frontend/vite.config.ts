/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    svelte(),
    // The service worker opens the app with the Pi out of reach. Pieces waiting to be
    // judged and the hoard's pictures come from its 'art' cache; the queue, the outbox
    // and the last copy of the hoard live in localStorage, kept by the app itself.
    VitePWA({
      registerType: 'autoUpdate',
      // public/manifest.webmanifest is the manifest; index.html links it.
      manifest: false,
      workbox: {
        globPatterns: ['**/*.{js,css,html,png,svg,woff2,webmanifest}'],
        // Latin only: the Greek, Cyrillic and Vietnamese cuts of the fonts are never shown.
        globIgnores: ['**/*-{cyrillic,cyrillic-ext,greek,greek-ext,vietnamese}-*.woff2'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            // A piece's picture never changes under the same key.
            urlPattern: ({ url }) => /^\/api\/art\/[a-z]+-\d+\/(image|thumb)$/.test(url.pathname),
            handler: 'CacheFirst',
            options: {
              cacheName: 'art',
              expiration: { maxEntries: 3000 },
              cacheableResponse: { statuses: [200] }
            }
          }
        ]
      }
    })
  ],
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8060'
    }
  },
  test: {
    environment: 'node'
  }
});
