# homebrain

Homebrain is a LAN-first smart-home server entrypoint designed to run on a MacBook and host pluggable modules.

## What this repository now provides

- A minimal web GUI at `/`.
- A JSON API for health, module discovery, and third-party AI bridge requests.
- A default module registry for:
  - Local LLM runtime (Ollama endpoint)
  - Jellyfin
  - Pi-hole
- A `docker-compose.yml` stack to run all core services on the same LAN host.

## Run locally

```bash
python -m homebrain.server
```

Then open `http://<your-macbook-lan-ip>:8787` from devices on your Wi-Fi LAN.

## Run full stack with Docker

```bash
docker compose up -d
```

Exposed ports:

- `8787` Homebrain web/API gateway
- `11434` Local LLM (Ollama)
- `8096` Jellyfin
- `8081` Pi-hole admin UI (`/admin`)
- `53/tcp` and `53/udp` Pi-hole DNS

## API for third-party AI tools

- `GET /api/v1/health`
- `GET /api/v1/modules`
- `POST /api/v1/bridge`

Bridge payload:

```json
{
  "target": "llm",
  "message": "Summarize today's camera alerts"
}
```

If you set `HOMEBRAIN_API_TOKEN`, include `X-Homebrain-Token: <token>` for `POST /api/v1/bridge`.

## SSH access and server configuration

On macOS host:

1. Enable **Remote Login** (System Settings → General → Sharing → Remote Login).
2. Restrict access to allowed users only.
3. SSH in from LAN:

```bash
ssh <mac-username>@<macbook-lan-ip>
```

Use environment variable `HOMEBRAIN_MODULES_JSON` (JSON list) to add customized submodules without changing code.
