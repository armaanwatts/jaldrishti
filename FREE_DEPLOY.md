# Free-tier deployment — supersedes the earlier paid Blueprint

Use Vercel frontend, Render Free backend, Supabase Free Postgres and a quota-limited hosted open-weight model endpoint. The project does not need your laptop once these are configured. Free backend sleeps and database inactivity policies still apply. No 24/7 delivery guarantee is made. Do not create the earlier paid service/disk.

## 1. Apply the update in your existing Git repository

Copy the files from this patch into the root of your existing JalDrishti_Cloud repository, replacing matching code files only. No .git or secrets are included. Verify `render.yaml` is directly at the GitHub repository root, NOT inside another JalDrishti_Cloud folder. Run `git ls-files render.yaml` locally; it must print render.yaml. Commit and push changed files. Render's "Blueprint file not found on main" means it has not found that file on the selected branch/path; check GitHub before retrying.

## 2. Create Supabase Free project

Use https://supabase.com/dashboard → New project, choose Free organization, enter a new strong DATABASE password and wait for the project to be ready. Save that password privately.

Click Connect → Session pooler → URI, normally port 5432. Copy the actual connection string; replace the password placeholder and URL-encode reserved characters in the password. Do NOT use a frontend API key as DATABASE_URL. Never paste the connection string into chat, GitHub, or Vercel browser variables. Set it only as the Render secret DATABASE_URL.

The app creates a `jaldrishti_private` schema, with row-level security enabled and no grants to anonymous/authenticated browser roles. It stores subscriptions, alert inbox/outbox, and push keys there. The backend connects using the server's privileged Postgres credentials; no browser connects directly to these tables. The pg advisory lock serialises short transactions to preserve preview/publish and queue claim semantics. Keep one backend instance.

## 3. Render Free

Render → New → Blueprint → your GitHub repository → main → render.yaml. Review the new configuration: plan must be FREE and no persistent disk must be requested. Set these secret/environment values:

- DATABASE_URL: Supabase Session pooler URI.
- ADMIN_PASSWORD: strong password, at least 12 characters; persisted in the Render secret settings and hashed locally on boot. Changing this environment secret takes effect after backend restarts on ephemeral hosting.
- PUSH_CONTACT_EMAIL: your real email, no mailto prefix.
- PUBLIC_ORIGINS: `https://jaldrishti.theinnovationcircle.online` initially; add your exact Vercel hostname, comma-separated, once created.
- LLM_BASE_URL: hosted OpenAI-compatible model API base ending in /v1.
- LLM_MODEL: exact hosted open-weight model ID.
- LLM_API_KEY: server-only provider key.

For a free inference trial, create a Groq Free account at https://console.groq.com and choose an open-weight chat model currently available to that account. Base URL: https://api.groq.com/openai/v1 . Check the provider's model list and quotas; no specific model is assumed prevalidated for Marathi/Hindi or the app's JSON/evidence rules. Model questions and retrieved public evidence go to the provider. Rate-limit errors are possible. Leave AI variables blank if testing maps first; AI-generated answers will be unavailable rather than fabricated.

Original reviewed observation files and historical output files ship in Git. CLOUD CSV UPLOAD/PUBLISH IS DISABLED to prevent claiming persistence on an ephemeral disk. Update reviewed public datasets in Git and redeploy. Regional alert composition/publication remains available and is persisted in Postgres. This is an explicit limitation of the free demo update.

## 4. Vercel and domain

After Render's /api/health responds successfully, run `python3 configure_vercel.py` in your Git repository and enter its actual HTTPS backend URL. Commit vercel.json and push. Import repository in Vercel with root directory set to the repository root, framework Other; the supplied build and output configuration handles frontend. Add exact Vercel URL to Render PUBLIC_ORIGINS.

Vercel → Settings → Domains → add jaldrishti.theinnovationcircle.online. In Cloudflare DNS, replace ONLY the existing jaldrishti tunnel record with the exact record Vercel requests. Start DNS only. Preserve all website/email records and other hostnames. Wait for Vercel's certificate/domain validation.

## 5. Verify

Test on mobile data while your Mac is switched off. Load district map and graph; save farmer profile; enable push on the new HTTPS domain; send an own-device test; create a TEST broadcast to the subscribed region. Restart backend and verify profile and VAPID public key remain the same. Acceptance by push service does not confirm a visible phone notification.

Render Free sleeps after inactivity. While sleeping, its background sender cannot process alerts; processing resumes after the backend wakes and only sends unexpired messages. Initial loading can be slow. Supabase Free may pause inactive projects. No artificial keep-alive or payment bypass is implemented. This is a hackathon/demo deployment, not a dependable emergency notification service.

## Validation

Existing backend checks plus storage adapter tests are included. Actual Supabase/Vercel/Render connections, free-tier capacity, hosted-model language quality and phone delivery must be tested with your accounts. Historical results remain research, not validated current crisis warnings.
