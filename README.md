# Greenlight — a studio analytics copilot (ClickHouse track)

A conversational agent for the "should we greenlight this film" question. A studio
exec asks in plain English ("should we greenlight a $40M psychological thriller for
a Q2 APAC release?"), the agent writes and runs SQL against a ClickHouse dataset of
comparable films via the official ClickHouse MCP server, and answers with a
recommendation grounded in the data — not just a number dump.

Architecture:

```
User → ADK Agent (Gemini) → McpToolset → mcp-clickhouse (MCP server) → ClickHouse Cloud
                                                                          (films + regional_performance tables)
```

This satisfies the ClickHouse track requirement directly: the agent calls
`run_select_query` (and friends) on the official `mcp-clickhouse` server at
runtime — not just a README mention.

---

## Before you start: accounts (do these first, they're all free/instant)

1. **ClickHouse Cloud** — sign up, redeem the $400 hackathon credit link from the
   resources page, spin up a service. Note down: host, port (usually 8443 for
   HTTPS), username (default), password.
2. **TMDb API key** — free, instant, at https://www.themoviedb.org/settings/api.
   This is your real-data seed (budgets, revenue, genres, release dates for
   thousands of films). It does NOT have per-region box office or marketing
   spend — you'll synthesize those on top, which is a reasonable and defensible
   thing to do for a hackathon demo as long as you say so plainly in your
   submission text.
3. **Google AI Studio API key** — free, instant, at https://aistudio.google.com/apikey.
   Use this for fast local iteration (Days 1–2). You'll likely switch to a real
   Google Cloud project + Vertex AI when you deploy to Cloud Run (Day 3), since
   Cloud Run needs a GCP project anyway — that's also where you apply the $100
   hackathon Cloud credit if you want it.
4. **`uv`** installed locally (https://docs.astral.sh/uv/) — this is how the
   ClickHouse MCP server and some ADK tool servers get run without a manual
   virtualenv dance. `pip install uv` or the install script on that page both work.

---

## Day 1 — Data

**Goal:** real ClickHouse tables with real (TMDb) + synthetic (regional/marketing)
data, queryable.

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in your ClickHouse + TMDb credentials.
3. Run `schema.sql` against your ClickHouse service (ClickHouse Cloud's SQL
   console, or via `clickhouse-connect` — see comment at top of the file) to
   create the `films` and `regional_performance` tables.
4. Run `python fetch_data.py` — pulls ~300 films from TMDb with real budget/genre/
   release-date data, synthesizes a plausible regional revenue + marketing split
   per film, and loads both tables directly into ClickHouse.
5. Sanity check: query `SELECT count() FROM films` and eyeball a few rows. This
   is the single riskiest step to get wrong silently (e.g. TMDb returns a lot of
   films with `budget=0`/`revenue=0` — the script filters those out, but check
   your final row count is a few hundred, not a handful).

**De-risk this first, before touching the agent.** If your data isn't queryable,
nothing downstream matters.

## Day 2 — Agent

**Goal:** a working ADK agent, running locally via `adk web`, that can answer a
real greenlight question end-to-end.

1. Confirm `uvx mcp-clickhouse` runs standalone first (with your `.env` vars
   exported in your shell) — you want to isolate "is the MCP server working" from
   "is the agent working" as two separate checks.
2. Open `greenlight_agent/agent.py`. It's wired with an `McpToolset` pointed at
   `mcp-clickhouse` and an instruction that frames the agent as a studio analyst.
   Adjust the instruction/persona to taste — this is genuinely where your
   analytics background is an edge: write the system prompt the way you'd brief
   a junior analyst on what "good" looks like (compare on genre + budget band +
   season, don't overclaim causality, always show the numbers behind a verdict).
3. From the **parent directory** of `greenlight_agent/` (i.e. from
   `greenlight-hackathon/`), run:
   ```
   adk web
   ```
   This opens a local chat UI — ADK's dev UI ships built in, so you don't need to
   build a frontend to demo this locally. Ask it something like: *"Should we
   greenlight a $35M horror film for an October APAC release?"* and watch whether
   it actually queries ClickHouse (you'll see the tool call in the UI) rather than
   guessing from its own knowledge.
4. Iterate on the instruction text until answers consistently (a) run a real
   query, (b) cite specific comparable films and numbers, (c) give a clear
   verdict with a stated confidence/caveat rather than false certainty.

**Note on the code:** ADK's MCP integration (`McpToolset`, `StdioConnectionParams`)
has changed shape across recent versions (an older `MCPToolset.from_server()`
pattern was replaced). The pattern in `agent.py` reflects the current
constructor-based API as of mid-2026 — if you hit an import or attribute error,
check `google.github.io/adk-docs/tools/mcp-tools/` for the exact current
signature before assuming your setup is wrong; this library moves fast.

## Day 3 — Deploy

**Goal:** a public URL judges can actually open.

1. Set up (or reuse) a GCP project, enable billing (apply your $100 hackathon
   credit if you got one), install `gcloud`, run `gcloud auth login`.
2. Switch your agent's env to Vertex AI mode (`GOOGLE_GENAI_USE_VERTEXAI=1`,
   `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` — see `.env.example`).
3. From `greenlight-hackathon/`, deploy with the dev UI included:
   ```
   adk deploy cloud_run --project=<your-project> --region=<your-region> --with_ui greenlight_agent
   ```
   ADK builds and pushes the container and gives you back a `*.run.app` URL.
4. Make it public:
   ```
   gcloud run services add-iam-policy-binding <service-name> --region=<region> --member="allUsers" --role="roles/run.invoker"
   ```
5. Open the URL, re-run your test questions against the deployed version —
   don't assume local behavior survives deployment (env vars are the usual
   culprit).

## Day 4 — Demo + submission

1. Script the 3-minute video before recording it. Suggested beats:
   - 15s: the problem (greenlighting is slow, gut-feel, and analysts are a
     bottleneck)
   - 90s: live demo — ask 2 genuinely different greenlight questions, show it
     querying ClickHouse (not just answering), show the verdict + numbers
   - 30s: brief architecture callout (Gemini + ADK + ClickHouse MCP server) —
     judges are explicitly scoring technical implementation, say the words
   - 15s: close on the audience/impact (studio crews making faster, evidence-backed
     calls)
2. Push the repo public with an **OSS license file visible in the GitHub "About"
   section** (add a `LICENSE` file — MIT is simplest — before you push, GitHub
   detects it automatically).
3. Double check: is `mcp-clickhouse` actually imported/invoked in your code path
   (yes, via `McpToolset`), not just named in your README? This is explicitly
   screened for.
4. Write your submission text: what it does, tech used, and — genuinely worth
   including — a line noting which parts of the data are real (TMDb) vs
   synthesized (regional splits, marketing spend), since honesty about that is a
   feature not a bug for the "quality of idea" criterion.
5. Select the ClickHouse partner track on the submission form. Submit before
   2:00 PM PT, Sept 9, 2026 — don't cut it to the wire given deploy/demo steps
   above.
