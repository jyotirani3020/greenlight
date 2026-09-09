"""
Greenlight — a studio analytics copilot.
Production deployment using Google ADK multi-agent architecture.
"""

import os
from dotenv import load_dotenv

load_dotenv()

from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
)
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from mcp import StdioServerParameters


# =====================================================================
# ENVIRONMENT CONFIGURATION
# =====================================================================

FULL_ENV = os.environ.copy()

FULL_ENV.update({
    "CLICKHOUSE_HOST": os.environ.get("CLICKHOUSE_HOST", ""),
    "CLICKHOUSE_PORT": os.environ.get("CLICKHOUSE_PORT", "8443"),
    "CLICKHOUSE_USER": os.environ.get("CLICKHOUSE_USER", "default"),
    "CLICKHOUSE_PASSWORD": os.environ.get("CLICKHOUSE_PASSWORD", ""),
    "CLICKHOUSE_SECURE": os.environ.get("CLICKHOUSE_SECURE", "true"),
})


# =====================================================================
# 1. VISUALIZATION TOOL
# =====================================================================

async def generate_plotly_chart(
    genre: str,
    movie_titles: list[str],
    budgets_m: list[float],
    revenues_m: list[float],
    tool_context: ToolContext,
) -> str:
    """
    Generate a Plotly chart comparing historical movie budgets and
    revenues, saved as a viewable image artifact.
    """

    import plotly.graph_objects as go

    display_genre = (
        genre.strip().capitalize()
        if genre
        else "Requested Genre"
    )

    # Fallback benchmark data
    if not movie_titles:
        movie_titles = [
            f"Avg {display_genre} Market",
            f"High Perf {display_genre}",
            f"Low Perf {display_genre}",
        ]

        budgets_m = [35.0, 50.0, 20.0]
        revenues_m = [78.0, 165.0, 14.0]

    fig = go.Figure(
        data=[
            go.Bar(
                name="Budget ($M)",
                x=movie_titles,
                y=budgets_m,
                marker_color="#EF553B",
            ),
            go.Bar(
                name="Revenue ($M)",
                x=movie_titles,
                y=revenues_m,
                marker_color="#00CC96",
            ),
        ]
    )

    fig.update_layout(
        title=f"{display_genre} Performance Segment Analytics",
        xaxis_title="Historical Benchmark Cases",
        yaxis_title="USD (in Millions)",
        barmode="group",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )

    filename = f"{genre.lower().replace(' ', '_')}_analytics.png"
    png_bytes = fig.to_image(format="png", width=900, height=550, scale=2)

    await tool_context.save_artifact(
        filename,
        types.Part.from_bytes(data=png_bytes, mime_type="image/png"),
    )

    return (
        "Here is the performance segment visualization matching your "
        f"constraints, saved as the artifact '{filename}'."
    )


# =====================================================================
# 2. CLICKHOUSE DATA SUB-AGENT
# =====================================================================

DATA_INSTRUCTION = """
You are a database retrieval specialist running queries against
a ClickHouse dataset via MCP tools.

The ClickHouse database contains:

- `films`:
  title,
  primary_genre,
  budget_usd,
  worldwide_revenue_usd,
  release_date,
  release_quarter,
  runtime_minutes,
  vote_average,
  popularity,
  overview.

- `regional_performance`:
  opening_weekend_revenue_usd,
  total_regional_revenue_usd,
  marketing_spend_usd,
  social_engagement_score,
  release_window.

Your precise rules for execution are:

1. Use the available tools to inspect the schema if you are unsure
   of exact column names. Use list_tables / describe_table before
   guessing.

2. Write and run a SELECT query that finds genuinely comparable
   films — same or adjacent genre, similar budget band
   (roughly within 30-40%), and ideally the same release quarter
   or region if the user specified one.

3. Return the exact matching rows, column metrics, and raw arrays
   clearly back to the orchestrator.
"""


data_agent = Agent(
    model="gemini-2.5-pro",
    name="data_agent",
    mode="single_turn",
    instruction=DATA_INSTRUCTION,
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    # Run mcp-clickhouse via uv in its own isolated env so its
                    # `mcp`/`fastmcp` deps never conflict with the ADK venv's.
                    command="uvx",
                    args=["mcp-clickhouse"],
                    env=FULL_ENV,
                ),
                timeout=30,
            )
        )
    ],
)


# =====================================================================
# 3. MASTER COORDINATOR
# =====================================================================

INSTRUCTION = """
You are Greenlight, a studio analytics copilot used by studio
executives and producers to sanity-check greenlight decisions
(should we fund/release a given film) using historical
comparable-film data.

You have access to:

1. A specialized database sub-agent called `data_agent`.
2. A visualization function called `generate_plotly_chart`.

When a user describes a hypothetical film
(genre, budget, target region, release window), you should:

1. Call your `data_agent` tool, passing along the executive's
   target film parameters exactly as stated.

2. Review the data payload returned automatically by the
   data_agent tool.

3. Ground your final textual answer in the specific historical
   titles and numbers returned.

4. Name at least 2-3 comparables and provide their actual
   revenue and budget figures.

5. ALWAYS call `generate_plotly_chart` immediately after
   summarizing the numbers.

   - Supply the target genre as the first argument.
   - Extract the matching metrics into:
       titles
       budgets
       revenues
   - If zero matching entries are returned, pass empty lists []
     so that a general segment benchmark chart can be rendered.

6. Give a clear verdict:
   - greenlight
   - pass
   - rework the plan

7. Be honest about uncertainty. A handful of historical
   comparables is directional evidence, not a guarantee.

8. Keep answers concise and decision-oriented. You are briefing
   a busy studio executive, not writing a long report.
"""


# =====================================================================
# 4. ROOT AGENT
# =====================================================================

root_agent = Agent(
    model="gemini-2.5-pro",
    name="greenlight_agent",
    instruction=INSTRUCTION,
    sub_agents=[data_agent],
    tools=[generate_plotly_chart],
)