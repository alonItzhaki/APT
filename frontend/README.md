# APT Frontend

Hebrew RTL React SPA (Vite + TypeScript, pnpm).

## Development

```bash
pnpm install
pnpm dev        # expects the API at http://localhost:8000 (proxied /api)
pnpm test
pnpm build      # outputs dist/
```

Production: the backend serves `dist/` when started with
`APT_FRONTEND_DIST=frontend/dist` (see backend/README.md). Routing is
hash-based (#/, #/alerts, #/admin), so no server-side fallback is needed.
