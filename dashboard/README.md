# Somnia dashboard

Next.js 15 App Router + shadcn/ui. Users sign in with GitHub via Supabase Auth (PKCE). The dashboard verifies the user with Supabase and sends the user's Supabase access JWT to the Somnia FastAPI service as a server-to-server bearer token. The API must be configured to accept JWTs from the same Supabase project and authorize dashboard access. There is no shared dashboard credential or fallback.

## Configure GitHub and Supabase

1. Create a [GitHub OAuth app](https://github.com/settings/developers). Set its **Authorization callback URL** to the OAuth callback shown in Supabase under **Authentication → Sign In / Providers → GitHub** (typically `https://<project-ref>.supabase.co/auth/v1/callback`). Enter the GitHub client ID and secret there and enable GitHub. Do not put the secret in Next.js or Vercel env.
2. In Supabase **Authentication → URL Configuration**, set **Site URL** to the production dashboard origin. Add the exact dashboard callback URLs under **Redirect URLs**, e.g. `http://localhost:3000/auth/callback` and `https://dashboard.example.com/auth/callback`. For Vercel Preview, add the callback for each trusted preview domain you use (or use a stable preview domain). Use the same origin to start and complete OAuth so the browser retains the PKCE cookie.

## Configure the dashboard

From `dashboard/`, copy `.env.example` to `.env.local` if you don't have one, then set:

| Variable | Value |
| --- | --- |
| `SUPABASE_URL` | Server-only URL of the Supabase project used for GitHub sign-in |
| `SUPABASE_PUBLISHABLE_KEY` | Server-only publishable key from that project; not a secret or service-role key |
| `SOMNIA_API_URL` | Server-only base URL of the Somnia FastAPI service, without `/v1`; use `http://127.0.0.1:8000` locally |

Use Node.js 22 or later for the dashboard runtime. Run `npm ci` and `npm run dev`, then open `http://localhost:3000`. All three variables are server-only and are not bundled into browser code. For local development, run the FastAPI service on `127.0.0.1:8000` and keep `SOMNIA_API_URL=http://127.0.0.1:8000`. For Vercel, set the project root directory to `dashboard`, select Node.js 22 or later, and set the same three variables for each intended environment. The deployed API must be reachable from Vercel (not `localhost`).

The app can build without these values. `/login` starts GitHub sign-in; `/auth/error` shows recovery steps for an unconfigured deployment, cancelled or failed OAuth, service outages, rejected sessions, denied access, and failed sign-out. For callback failures, retry from `/login` in the same browser and check the exact Supabase redirect allowlist. If the API rejects a signed-in user, check that it trusts the same project and that the account has access.

Checks: `npm run lint`, `npm run typecheck`, `npm run build` (the existing `next/font/google` setup needs network access to Google Fonts on a clean build).
