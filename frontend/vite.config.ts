import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const assetVersion = new Date().toISOString().replace(/[^0-9]/g, '').slice(0, 14)

export default defineConfig({
  base: '/assets/',
  plugins: [
    vue(),
    {
      name: 'version-static-assets',
      transformIndexHtml(html) {
        return html
          .replace('src="/assets/app.js"', `src="/assets/app.js?v=${assetVersion}"`)
          .replace('href="/assets/styles.css"', `href="/assets/styles.css?v=${assetVersion}"`)
      },
    },
  ],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
  build: {
    emptyOutDir: false,
    rollupOptions: {
      output: {
        entryFileNames: 'app.js',
        chunkFileNames: '[name].js',
        assetFileNames: (asset) => asset.name?.endsWith('.css') ? 'styles.css' : '[name][extname]',
      },
    },
  },
})
