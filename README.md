# homebrain

Homebrain is a LAN-first smart-home server entrypoint designed to run on a MacBook and host pluggable modules.

## What this repository provides

- A responsive web dashboard with Overview, Assistant, Data sources, Modules, and Activity sections.
- A private chat UI powered by the local llama.cpp model.
- A scheduled analysis agent that fetches enabled data sources, sends bounded snapshots to the local model, and updates a persistent dashboard.
- Optional read-only connectors for Gmail inbox metadata and selected GitHub repository activity.
- A default Austin, TX weather feed from Open-Meteo, refreshed with the scheduled analysis.
- Built-in Austin traffic, market-watch, local-news, and nearby-event sources.
- A JSON API for dashboard data, data-source management, model chat, health, and module discovery.
- A `docker-compose.yml` stack for Homebrain and its local services.

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
- `80` LAN-only Homebrain reverse proxy (`homebrain.home.arpa`)

Open `http://<your-macbook-lan-ip>:8787` to use the dashboard. Built-in weather,
traffic, market, news, and event sources are seeded on first start. Add a text
note, read-only HTTP(S) endpoint, or configure the Gmail/GitHub connectors below in
**Data sources**. The agent analyzes enabled
sources every 15 minutes by default; **Analyze now** starts an on-demand run. Its latest
summary and insights persist across restarts in `./data/homebrain.sqlite3`.

### Open Homebrain and its modules by name

The Compose stack includes a Caddy reverse proxy for the private LAN hostname
`http://homebrain.home.arpa/`. To make that name resolve on your network:

1. Reserve the Mac's LAN address in your router's DHCP settings. The record must
   point to the Mac's current LAN IP, not its Tailscale address.
2. In Pi-hole, open **Local DNS → DNS Records** and add
   `homebrain.home.arpa` with the Mac's reserved LAN IP.
3. Configure the router's DHCP DNS setting to hand out Pi-hole's LAN IP, then
   reconnect clients or renew their DHCP leases. Clients using another DNS
   resolver will not resolve this private name.
4. Start or update the stack with `docker compose up -d`, then open
   `http://homebrain.home.arpa/`.

The proxy serves Homebrain over HTTP on the LAN; it does not configure a public
domain or HTTPS. Do not forward ports 80, 53, or 8081 from the internet. A
registered public domain needs a domain name and a separately secured remote
access design; do not point a public DNS record directly at this Mac.

The dashboard's **Modules** page links to each configured service. Jellyfin,
Pi-hole, and the llama.cpp API still use their separately exposed ports; the
LLM link opens its OpenAI-compatible models endpoint.

The local model serves chat on `http://localhost:8080/v1`. Chat and analysis
requests are sent to the local llama.cpp service, not a hosted AI API. Configure
`HOMEBRAIN_ANALYSIS_INTERVAL_SECONDS` to change the periodic analysis interval
(minimum 60 seconds).

Weather uses the free, no-key [Open-Meteo Forecast API](https://open-meteo.com/en/docs)
with Austin city-center coordinates (30.2672, -97.7431), local Central time, and
Fahrenheit units. It includes current conditions, the next 12 hours, and a
three-day outlook. Change `HOMEBRAIN_WEATHER_LOCATION`, `HOMEBRAIN_WEATHER_LATITUDE`,
`HOMEBRAIN_WEATHER_LONGITUDE`, and `HOMEBRAIN_WEATHER_TIMEZONE` in Compose to use
a more precise home location. The free API is for non-commercial use; Open-Meteo
lists a 10,000-call/day limit, while Homebrain's 15-minute default uses about
96 calls/day. Weather attribution is shown in Data sources.

### Traffic, stocks, news, and events

The local news feed uses Google News RSS to search the configured home location
for recent headlines; no key is needed. Traffic samples
one road segment near the configured home coordinates through the
[TomTom Traffic Flow API](https://developer.tomtom.com/traffic-api/documentation/traffic-flow/flow-segment-data).
Market quotes use the [Finnhub quote API](https://finnhub.io/); set
`HOMEBRAIN_STOCK_SYMBOLS` in `.env` to change the default `SPY,QQQ,DIA`
watchlist. Nearby events use the [Ticketmaster Discovery API](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/).
Get API keys from the linked providers and add these entries to `.env`:

```dotenv
HOMEBRAIN_TRAFFIC_API_KEY=your-tomtom-key
HOMEBRAIN_STOCKS_API_KEY=your-finnhub-key
HOMEBRAIN_STOCK_SYMBOLS=SPY,QQQ,DIA
HOMEBRAIN_TICKETMASTER_API_KEY=your-ticketmaster-key
```

Recreate Homebrain after editing `.env`:

```bash
docker compose up -d --force-recreate homebrain
```

The four new feeds are enabled by default and analyzed on the same 15-minute
schedule. Missing keys show as source errors in Activity; the local model still
analyzes snapshots from sources that did load. Traffic covers a single nearby
road segment, not a citywide route. Finnhub's free plan may return delayed
quotes; these are informational and not financial advice. News headlines are
unverified reports, and Ticketmaster results or availability may change.

Data source URLs are fetched with GET only, without authorization headers or
redirects, and response size is capped. Embedded username/password credentials
are rejected; URL query parameters are passed to the configured endpoint but
omitted from the source list shown in the UI. Treat connected source content as
untrusted: the agent summarizes it and does not execute instructions or take
actions. Set
`HOMEBRAIN_API_TOKEN` on the Homebrain service to require `X-Homebrain-Token` on
chat, source changes, manual analysis, and bridge POST requests. Enter the same
token in the dashboard’s **Settings** section. This is recommended when the
dashboard is reachable by other devices on your LAN.

## Gmail and GitHub connectors

Provider credentials are read from the local `.env` file and are never saved in
Homebrain's source records or returned by its source API. Keep `.env` private,
do not commit it, and do not send its values in chat. Start with the ignored
template and restrict local file permissions:

```bash
cp .env.example .env
chmod 600 .env
```

Docker Compose passes these `.env` values to Homebrain. If you run
`python -m homebrain.server` directly instead, set the same variables in that
process's environment.

### Gmail: inbox metadata only

Homebrain uses Google's `gmail.metadata` scope. It reads sender, subject, date,
and labels for at most the 20 most recent Inbox messages. It does not fetch
message bodies, send mail, or modify messages.

1. In [Google Cloud Console](https://console.cloud.google.com/), create/select a
   project and enable the [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com).
2. Configure the OAuth consent screen. For a personal setup, choose **External**,
   keep the app in **Testing**, and add your Google account as a test user in
   [Google Auth Platform](https://console.cloud.google.com/auth/overview).
3. Create an OAuth client ID of type **Web application**. Add this exact
   authorized redirect URI: `http://localhost:8765/callback` in
   [Clients](https://console.cloud.google.com/auth/clients).
4. Put the client ID and client secret in `.env`:

   ```dotenv
   HOMEBRAIN_GMAIL_CLIENT_ID=your-client-id
   HOMEBRAIN_GMAIL_CLIENT_SECRET=your-client-secret
   ```

5. From the repository directory, run `python3 -m homebrain.gmail_auth`. Approve
   access in the browser opened on this Mac. The local callback listens only on
   `127.0.0.1`; the script prints a refresh token in your terminal.
6. Copy that token into `.env` as `HOMEBRAIN_GMAIL_REFRESH_TOKEN=...`. Treat it
   like a password; never paste it into chat or commit it.
7. Add a source in **Data sources** with type **Gmail inbox metadata** and
   mailbox `inbox`.

Google refresh tokens for an External app left in **Testing** expire after
seven days when Gmail scopes are used. You may need to rerun the authorization
command weekly; a production/published app with Gmail scopes can require Google
verification.

### GitHub: selected repositories, read-only

Public repositories can be read without a token, subject to GitHub's lower
unauthenticated rate limit. For private repositories or higher rate limits,
create a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new)
in GitHub **Settings → Developer settings**:

1. Restrict **Repository access** to only the repositories Homebrain should
   analyze and set an expiration.
2. Grant **Contents: read-only**, **Issues: read-only**, and **Pull requests:
   read-only**. Contents permission is needed by GitHub's releases endpoint;
   Homebrain reads release metadata only and never downloads source code.
3. Put the token in `.env` as `HOMEBRAIN_GITHUB_TOKEN=...`.
4. Add a source in **Data sources** with type **GitHub repositories** and a
   comma-separated list of one to five `owner/repository` names.

The connector fetches only issue, pull-request, and release metadata. It makes
no writes. After changing `.env`, recreate Homebrain so Docker passes the new
environment values to the container:

```bash
docker compose up -d --force-recreate homebrain
```

Then use **Analyze now** to verify the connectors. Credential or provider
errors are shown in the Activity section. These connectors send requests only
to Google's OAuth/Gmail APIs or GitHub's API; analysis is performed by the
local llama.cpp model.

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
- `GET /api/v1/dashboard`
- `GET /api/v1/sources`
- `GET /api/v1/agent/status`
- `GET /api/v1/agent/runs`
- `POST /api/v1/chat` (`messages`: user/assistant message list)
- `POST /api/v1/sources` (`name`, `type`: `text`, `url`, `gmail`, `github`, `traffic`, `stocks`, `news`, or `events`, `value`)
- `PATCH /api/v1/sources/<id>` (`enabled`: boolean)
- `DELETE /api/v1/sources/<id>`
- `POST /api/v1/agent/run`
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
