# homebrain

Homebrain is a LAN-first smart-home server entrypoint designed to run on a MacBook and host pluggable modules.

## What this repository now provides

- A minimal web GUI at `/`.
- A JSON API for health, module discovery, and third-party AI bridge requests.
- A default module registry for:
  - Local LLM runtime (llama.cpp endpoint)
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
- `8080` Local LLM (llama.cpp OpenAI-compatible API)
- `8096` Jellyfin
- `8081` Pi-hole admin UI (`/admin`)
- `53/tcp` and `53/udp` Pi-hole DNS

## Local LLM model

The llama.cpp server loads a GGUF model from `./models/model.gguf` on the host.
Create the `models` directory, place a compatible GGUF model there with that
filename, then start the stack. The directory is mounted read-only in the
container. The model endpoint is available at `http://<your-macbook-lan-ip>:8080/v1`.
The selected default is [Qwen3-4B-Instruct-2507 Q4_K_M](https://huggingface.co/bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF), approximately 2.5 GB, served with an 8,192-token context to limit memory use.

## VS Code coding assistance

The llama.cpp API uses the stable model ID `homebrain-coder`. In Continue for
VS Code or Cursor, configure `~/.continue/config.yaml` with:

```yaml
name: Homebrain local coding assistant
version: 0.0.1
schema: v1

models:
  - name: Homebrain Qwen3 4B
    provider: openai
    model: homebrain-coder
    apiBase: http://localhost:8080/v1
    apiKey: not-needed
    roles:
      - chat
      - edit
      - apply
```

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
