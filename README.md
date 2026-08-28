# Relay

Track a GitHub **account** (every repo, including ones created later) and mirror each one onto a destination GitHub account. Discord gets one compact note when something actually moved.

## Run

```bash
cp .env.example .env
# DEST_GITHUB_ACCOUNT=your-user
# DEST_GITHUB_TOKEN=ghp_...     # create repos + push
# DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
# GITHUB_TOKEN=                 # optional, private origin repos

./dev.sh
```

Open **http://169.58.173.136:6001** (bound on `0.0.0.0:6001`).

## Environment

| Variable | Purpose |
| --- | --- |
| `DEST_GITHUB_ACCOUNT` | Default dest login. Same repo names as origin. Not typed in the UI. |
| `DEST_GITHUB_TOKEN` | PAT that can create repos and push on that account. |
| `DISCORD_WEBHOOK_URL` | Channel webhook. |
| `GITHUB_TOKEN` | Optional. Needed to see private origin repos. |
| `HOST` | Bind address. `0.0.0.0` for external access. |
| `PORT` | Default `6001`. |

## How a cycle works

1. List origin repos. First pass only records names and HEAD — dest is left alone.
2. A **new** origin repo → create it on dest (empty if origin is empty).
3. A **new commit** (pushed_at / SHA moved) → create dest if needed and push those commits.
4. Idle repos are never copied. Discord stays quiet unless something actually moved.

Destination repos are created under `DEST_GITHUB_ACCOUNT`. Fast-forward refuses to overwrite a diverged dest branch.
