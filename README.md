# JalDrishti — groundwater decision-support prototype

React dashboard, FastAPI backend, historical CGWB observations, rainfall pilot, evidence-grounded multilingual explanations and regional notifications.

**Start with [FREE_DEPLOY.md](FREE_DEPLOY.md)** for GitHub, Render, Vercel and custom-domain deployment. The hosted setup does not require the developer laptop.

- Frontend: Vercel, repository root configuration in vercel.json.
- Backend: Render Free Docker service with Supabase Postgres, render.yaml. Cloud CSV uploads are disabled; update reviewed datasets in Git.
- AI: configurable hosted OpenAI-compatible endpoint serving an open-weight model. No endpoint/account/model compute is bundled.
- Local development: existing start.py + Ollama remains available; use npm --prefix frontend ci for frontend build dependencies.
- Tests: python -m unittest discover -s backend/tests after installing backend/requirements.txt and backend/requirements-dev.txt.

No admin password, push private keys, device profiles or private logs are shipped. Set secrets in the backend host.

This is a research prototype. Historical colours are not current crisis classifications. Current-season warnings remain disabled pending scientific validation. Third-party source provenance and notices are retained.
