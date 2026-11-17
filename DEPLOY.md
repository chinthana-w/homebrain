# Homebrain auto-deployment + private access — DRAFT

**Draft only. Nothing here has been copied into the repo, pushed, or
merged. Review it first, fill in the missing inputs at the bottom,
then apply it to the Mac.**

## What this sets up

- **Auto-deployment:** every push to `main` deploys itself to your Mac
  home server — no manual log-in, no manual restart.
- **Private access:** you can reach Homebrain from your own devices
  when you are away from home, over Tailscale. It is **not** public.
  There is no port forwarding, no public address, and no one on the
  internet can reach it.

## How the two parts work

### 1. Private access with Tailscale

Tailscale makes your devices act as if they are on the same private
network, wherever they are. Only devices signed in to your Tailscale
account can see the Mac.

Tailscale is already set up on the Mac — device name
`chinthanas-macbook-pro` (confirmed 2026-11-16).

1. Install Tailscale on each of your other devices (phone, laptop,
   tablet) and sign in with the same account, if you have not already.
2. From any of your devices, open
   `http://chinthanas-macbook-pro:8787` — that is your Homebrain
   dashboard. The same address works at home and away. If the name
   does not resolve, use the Mac's Tailscale address (starts with `100.`).
5. Do **not** open port 8787 (or 8080, 8096, 8081) on your home router.
   Tailscale replaces port forwarding entirely.

Only the Homebrain port (8787) is for remote use. The llama.cpp port
(8080), Jellyfin (8096) and Pi-hole admin (8081) stay reachable the
same way if you need them, but do not share their addresses.

### 2. Lock it down first — set an API token

Homebrain's API token is currently commented out in
`docker-compose.yml`, which means API calls need no token at all.
Set one **before** you use remote access:

1. On the Mac, in the Homebrain folder, create or edit the `.env`
   file and add a long random token, for example:
   `HOMEBRAIN_API_TOKEN=<a-long-random-token-you-generate>`
2. In `docker-compose.yml`, uncomment the `HOMEBRAIN_API_TOKEN`
   line so it reads the value from `.env`.
3. Restart the stack: `docker compose up -d`
4. Keep that token private — anyone with it can call the API.
   When you call the API from outside, send it as the
   `X-Homebrain-Token` header.

Do not put the real token in GitHub, in the workflow file, or in
any file you commit. It lives only in the Mac's `.env`.

### 3. Auto-deployment — recommended path: self-hosted runner on the Mac

This is the recommended path because it stores **no SSH keys in
GitHub** and opens **no inbound connection**. The Mac itself watches
for pushes and deploys them.

1. On the Mac, clone the repo (or use your existing checkout) at
   `~/projects/homebrain` — that is the checkout path the workflow uses.
2. In GitHub, go to the Homebrain repo → Settings → Actions →
   Runners → New self-hosted runner → macOS, and follow the
   on-screen install steps on the Mac. Give it a clear name and
   labels, and note the labels — that is `<RUNNER_LABELS>`.
3. Start the runner on the Mac (GitHub's instructions include how
   to run it as a service so it survives restarts).
4. Copy the draft files into the repo and push them to `main`:
   - `.github/workflows/deploy.yml` — fill in `<RUNNER_LABELS>` first
     (the checkout path is already set to `~/projects/homebrain`)
   - `scripts/deploy.sh`
   - this `DEPLOY.md`
5. Test it: make a small change on `main` (for example, a comment
   in the README) and push. In GitHub → Actions, watch the
   "Deploy Homebrain to Mac" run. It should end green, and
   `http://chinthanas-macbook-pro:8787/api/v1/health` should
   answer. If the run goes red, the workflow prints the Docker
   status and the last 100 lines of the Homebrain log — fix the
   cause, push again, and it will retry.

What the deploy does on the Mac, every time: pulls `main`
(fast-forward only — it refuses rather than overwriting local
changes), runs `docker compose up -d`, waits up to two minutes
for the health check, and fails loudly if Homebrain does not come
back healthy. It never deletes data, never overwrites `.env`,
and never prunes Docker volumes.

### Alternative path: SSH over Tailscale (only if you do not want a runner)

If you would rather not run a GitHub runner on the Mac, the
workflow file contains a commented-out second job that deploys
over SSH — but only over Tailscale, never over the public
internet. To use it you need: Remote Login (SSH) turned on in
macOS Settings on the Mac, the Mac's Tailscale address, a macOS
username, and an SSH key stored as GitHub secrets
(`MAC_TAILSCALE_HOST`, `MAC_SSH_USER`, `MAC_SSH_KEY`). Enable **one** path only, not both.
The runner path above is recommended because it avoids storing
an SSH key in GitHub at all.

## Roll back

If a deploy makes things worse, roll back from the Mac (or over
Tailscale) — do not edit the running containers by hand:

```bash
cd ~/projects/homebrain
git log --oneline -5          # find the last good commit
git revert <bad-commit>       # or: git reset --hard <last-good-commit>
docker compose up -d
curl http://localhost:8787/api/v1/health
```

`git revert` is the safe option: it creates a new commit that
undoes the bad one, and the next push to `main` will deploy that
fix automatically. Your data in `./data` and the `.env` file are
not touched by a revert or by a deploy.

If Homebrain will not start at all, check the logs first:
`docker compose logs --tail=100 homebrain`

## Missing inputs — needed before this can be finished

| Input | Why it is needed | Where it goes |
|---|---|---|
| Tailscale on the Mac | Set up — device name `chinthanas-macbook-pro` (confirmed 2026-11-16) | Step 1 in "Private access" above |
| Runner labels (`<RUNNER_LABELS>`) | Only needed for the recommended runner path — they tell GitHub which runner is the Mac | `deploy.yml`, `runs-on` |
| Docker on the Mac | Installed (confirmed 2026-11-16) | No action needed |
| HOMEBRAIN_API_TOKEN value | Lock down the API before remote access | Mac's `.env` only — never in GitHub or any committed file |

## What is NOT in this kit

- No port forwarding, no public domain, no public access of any kind.
- No changes to the Homebrain code, the bridge, or the model.
- No secrets are included in these drafts — every secret is a
  placeholder or a GitHub secret you add yourself.
