@AGENTS.md

## web/ — the Next.js side of the platform

Read `../CLAUDE.md` (monorepo) and `../docs/ROADMAP.md` (web tracks B0–B6)
first. One session and one branch per track.

- **Stack:** Next.js 16 (App Router, `src/`), React 19, Tailwind CSS v4,
  TypeScript strict, npm. Next.js 16 differs from older versions (typed
  `PageProps<'/route'>` / `LayoutProps`, `params` is a Promise, middleware is
  `proxy`): check `node_modules/next/dist/docs/` before using an API you are
  not sure about.
- **Commands:** `npm run dev`, `npm run lint`, `npm run typecheck`,
  `npm run build`. All three checks must pass before a commit.
- **Routes:** `(marketing)` → `/`, `/blog`, `/blog/[slug]`, `/about`,
  `/privacy`, `/terms`; `(auth)` → `/login`; `(cabinet)` → `/app`; `/admin`
  (operator-only; 404 until track B5, then Google sign-in + `ADMIN_EMAILS`);
  `/api/health` (Railway health check).
- **Design:** minimal, white + jade + mint accents (palette "A · Jade"),
  short copy. Use the semantic tokens from `src/app/globals.css` (`ink`,
  `ink-muted`, `line`, `line-strong`, `surface`, `primary`,
  `primary-hover`, `accent`, `accent-soft`, `tint`) and the shared classes
  in `src/components/ui.ts` (`buttonPrimary`, `buttonSecondary`, `badge`,
  `textLink`); never raw hex values. Hover states get darker, never lighter;
  the bright mint accent is never a background behind text.
- **Indexing** is off (`robots.txt` disallow + `noindex`) until
  `ALLOW_INDEXING=true`: the current domain `ads.vtrata.com` is temporary.
- **Database:** from track B1 this app owns the Postgres schema and every
  migration (Drizzle), including tables the Python MCP server writes to
  (`../openspec/changes/platform-db-and-cabinet/`).
- **Secrets:** never commit `.env*`; `.env.example` documents every variable.
