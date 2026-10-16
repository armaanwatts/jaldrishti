# GitHub → backend → Vercel → custom domain

This is a complete source copy of the current JalDrishti prototype, with public data, map boundaries, local map assets and historical model outputs. No laptop, tunnel, old credentials or farmer subscriptions are needed. Production services still need to be provisioned. Current-season scientific validation remains pending.

## 1. Create the GitHub repository

Create an EMPTY private repository named `jaldrishti` on GitHub. Unzip this folder outside your existing application; do not copy the entire old project into it. In Terminal, enter the extracted JalDrishti_Cloud folder. Run:

```bash
git init
git add .
git status --short
git commit -m "Prepare JalDrishti cloud deployment"
git branch -M main
```

Then copy the exact `git remote add origin ...` and `git push -u origin main` commands provided by YOUR GitHub repository. Do not invent the username. GitHub authentication uses its browser/credential flow or a token locally, not your account password. Never paste a token into chat.

Public-source observations and dataset excerpts are included with existing provenance and notices. Review source terms before making the repository public. No license granting ownership of government data is asserted.

## 2. Deploy the backend on Render

Connect the GitHub repository in Render → New → Blueprint. It reads `render.yaml` and creates one Docker web service with a persistent disk. Review charges BEFORE confirming. This configuration is paid; a sleeping free service with disposable storage does not provide reliable alert delivery. Do not scale above one instance with this SQLite architecture.

Set these BACKEND environment variables:

| Variable | Value |
|---|---|
| PUBLIC_ORIGINS | `https://jaldrishti.theinnovationcircle.online,https://YOUR-PROJECT.vercel.app` (replace the second hostname when known) |
| ADMIN_PASSWORD | A new strong password of at least 12 characters |
| PUSH_CONTACT_EMAIL | Your real contact email, without `mailto:` |
| LLM_BASE_URL | Your hosted open-weight model's OpenAI-compatible HTTPS API base ending in `/v1` |
| LLM_MODEL | The exact open-weight model identifier served by that endpoint |
| LLM_API_KEY | The endpoint API key; leave empty only for an endpoint that requires none |

Use an endpoint supporting JSON-object responses and chat completions. Qwen is an intended open-weight option, but this package does not provision a GPU or model account. Verify the chosen model's license, availability and provider's data policy. Hosting a model, even an open-weight model, can cost money. The configured provider receives the submitted question and retrieved public evidence. No device subscription or password is sent to it.

If AI variables are blank, maps, charts and inboxes still work; generated answers remain unavailable. No results are fabricated as an AI fallback. The existing evidence and language checks still apply. Cloud inference uses a 45-second request timeout and can retry once after evidence validation failure; proxy limits can still interrupt slow calls.

Persistent disk boot seeds bundled public data once, then preserves uploads, subscriptions, admin hash and generated push keys there. Later Git commits to bundled data do NOT silently overwrite runtime data. Publish reviewed observations through the admin workflow or perform a reviewed disk migration. Existing local farmers need to register again on the new domain. ADMIN_PASSWORD initializes only on first boot; later password changes must use the backend's admin setup command with the persistent directory linked, not an environment edit alone.

After backend is healthy, copy its actual HTTPS URL. Open `/api/health` on that URL and verify success.

## 3. Connect Vercel to the backend

In the repository folder run:

```bash
python3 configure_vercel.py
```

Paste the backend HTTPS URL when prompted. Then:

```bash
git add vercel.json
git commit -m "Connect hosted backend"
git push
```

In Vercel → Add New Project → Import this repository. Root directory: repository root. Framework preset: Other. Build/output settings come from `vercel.json`. Do NOT set the root directory to frontend. The dashboard proxies `/api/*` to the backend, so cookies and phone subscriptions stay on the dashboard origin. Vercel and backend caching must not override API `no-store` responses. Keep the backend URL out of browser fetch calls; use the supplied same-origin proxy.

Update PUBLIC_ORIGINS on Render with the EXACT production Vercel hostname. Preview deployment hosts are deliberately not automatically allowed. Administrative mutations from unknown origins are rejected. Keep backend and frontend on HTTPS. Render's proxy headers are trusted in the supplied deployment; do not reuse its wildcard trust setting on a directly exposed unmanaged server.

## 4. Add your domain to Vercel

Vercel → project → Settings → Domains → add `jaldrishti.theinnovationcircle.online`. Copy the EXACT DNS target Vercel displays. Cloudflare now manages DNS for this domain, even though GoDaddy remains its registrar. In Cloudflare DNS, remove/replace only the existing `jaldrishti` tunnel record and add Vercel's requested record. Initially use DNS only. Do not modify apex, www, mail, DKIM, SPF or other records. Wait for Vercel to confirm domain and certificate readiness.

Cloudflare Tunnel and your Mac are no longer needed AFTER both hosted services and the domain have been verified. Do not remove them during migration.

## 5. Acceptance checks

- Farmer and admin pages open on the public domain using mobile data, with the Mac shut down.
- District directory, selected-well map, historical graph and languages work.
- POST `/api/admin/login` works from the approved HTTPS origin; invalid credentials fail.
- Farmer saves a region and permission is requested only after tapping Enable notifications.
- Personal test reaches inbox and phone push; provider acceptance alone is not proof of delivery.
- New admin test broadcast reaches only selected-region subscribers.
- Restart/redeploy backend, then verify the same profile, keys and subscriptions remain.
- Ask a source-based question with hosted AI configured; check language and cited facts.

Current forecasts and crisis classifications remain disabled, as in the prototype. Do not label historical colours as current safety or crisis.

## Verification performed during preparation

Python compilation, automated backend tests and React build. Actual Render/Vercel deployment, provider inference and real phone delivery require accounts and secrets and have not been verified here. No production URL is claimed to be deployed by this archive.
