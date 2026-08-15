"""
GenAI layer, powered by Groq (OpenAI-compatible chat completions API).

Two jobs:
  1. generate_business_insights() - one-shot: turns the statistical profile
     into narrative insights + business recommendations (structured JSON).
  2. chat() - persistent multi-turn assistant with three tools:
       - generate_chart: draws a new Plotly chart from real columns (including
         correlation heatmaps and pairwise/pairplot scatter matrices)
       - run_sql_query: runs a real, read-only SQL SELECT against the actual
         uploaded dataset (via DuckDB) and returns real numbers
       - compare_columns: real correlation/regression stats between columns

Critically, chat() does the full two-step tool-calling round trip: when the
model calls a tool, we execute it, feed the *result* back to the model, and
only then take its final answer. Skipping that second step is what caused
the assistant to reply with only a generic caption like "here's the chart
you asked for" instead of an answer grounded in the actual data.

Some (especially smaller/faster) Groq models occasionally emit a tool call as
literal text instead of using the structured tool_calls field the SDK expects
— e.g. `<function=run_sql_query>{"sql": "..."}</function>`, or even bare
`generate_chart{"chart_type": "scatter", ...}` with no wrapper, sometimes
inside a stray ```sql code fence, sometimes several calls back-to-back. The
`_extract_inline_tool_calls` scanner below recovers *all* of those forms so
they can still be executed for real, and the raw markup never reaches the UI.
"""
import time
import json
import re
from typing import Optional

import duckdb
import numpy as np
import pandas as pd
from groq import Groq, APITimeoutError, APIConnectionError, APIError, APIStatusError, RateLimitError

from core.config import settings
from services.eda import build_chart_from_request

client = Groq(api_key=settings.GROQ_API_KEY)


class AssistantTimeoutError(Exception):
    """Raised when the Groq API doesn't respond within GROQ_TIMEOUT_SECONDS.
    Routers catch this and return HTTP 504 instead of letting the request
    hang until something upstream (nginx, the Vite proxy, etc.) kills the
    connection and surfaces a bare, unhelpful 502."""


class AssistantOverloadedError(Exception):
    """Raised for Groq 413 (request too large for the model's token limit)
    and 429 (rate limit exceeded) responses. These are request-shape/quota
    problems, not timeouts — routers map this to HTTP 429 with a friendly,
    actionable message instead of the raw 'Limit 6000 TPM, Requested 6238'
    text Groq returns."""


def _create_completion(**kwargs):
    """Thin wrapper around client.chat.completions.create that always sets
    a request timeout and translates Groq's own timeout/connection/overload
    errors into our own exception types. Every completion call in this file
    goes through here so error handling is consistent everywhere."""
    kwargs.setdefault("timeout", settings.GROQ_TIMEOUT_SECONDS)
        max_retries = 3

    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(**kwargs)

        except APITimeoutError as e:
            raise AssistantTimeoutError(
                f"Groq request timed out after {settings.GROQ_TIMEOUT_SECONDS} seconds."
            ) from e

        except APIConnectionError as e:
            # Network-level failure reaching Groq behaves the same as a timeout
            # from the caller's point of view: no usable response can come back.
            raise AssistantTimeoutError(
                f"Could not reach Groq: {e}"
            ) from e

        except RateLimitError as e:
            if attempt < max_retries - 1:
                wait_seconds = 2 ** attempt
                time.sleep(wait_seconds)
                continue

            raise AssistantOverloadedError(
                "The assistant is getting a lot of requests right now (rate limit reached). "
                "Please wait a few seconds and try again."
            ) from e
    except APIStatusError as e:
        if e.status_code == 413:
            raise AssistantOverloadedError(
                "That conversation has grown too long for one request. Starting a new chat, or "
                "asking a shorter/more specific question, will fix this."
            ) from e
        if e.status_code == 429:
            raise AssistantOverloadedError(
                "The assistant is getting a lot of requests right now (rate limit reached). "
                "Please wait a few seconds and try again."
            ) from e
        raise
    except APIError:
        # Real API errors (bad request, auth, 5xx from Groq itself, etc.)
        # are left to propagate as-is; the router maps these to HTTP 502
        # since they're a genuine upstream failure, not a timeout/overload.
        raise


# --- Context/token management ------------------------------------------------
# Sending the *entire* raw conversation on every turn is what caused
# "413 Request too large" / "429 ... Limit 6000 TPM, Requested 6238" on long
# conversations. Chart/table JSON is never part of `history` in the first
# place (chat.py only stores role+content text for model context — charts
# and tables are attached separately and rendered client-side), so the fix
# here is specifically about unbounded *text* growth over a long chat.
MAX_HISTORY_MESSAGES = 12   # last 6 user/assistant exchanges kept in full
MAX_MESSAGE_CHARS = 2000    # caps any single turn so one long reply can't blow the budget alone


def _prepare_history_for_model(history: list[dict]) -> list[dict]:
    """Keeps only the most recent exchanges in full, each capped in length,
    and collapses everything older into one short, deterministic summary
    line (no extra LLM call — so this never adds latency or its own token
    risk) so token usage stays bounded no matter how long the conversation
    has run."""
    if not history:
        return history

    def _cap(m: dict) -> dict:
        content = m.get("content") or ""
        if len(content) > MAX_MESSAGE_CHARS:
            content = content[:MAX_MESSAGE_CHARS] + " …[truncated]"
        return {"role": m["role"], "content": content}

    capped = [_cap(m) for m in history]
    if len(capped) <= MAX_HISTORY_MESSAGES:
        return capped

    older, recent = capped[:-MAX_HISTORY_MESSAGES], capped[-MAX_HISTORY_MESSAGES:]
    earlier_questions = [m["content"][:100] for m in older if m["role"] == "user"][:8]
    summary = (
        f"[This conversation has {len(older) // 2} earlier exchange(s) not shown verbatim to save "
        f"context space. Topics already discussed: {'; '.join(earlier_questions) or 'general dataset questions'}. "
        f"Stay consistent with anything already established, but you don't need to re-explain it.]"
    )
    return [{"role": "user", "content": summary}] + recent

GENERATE_CHART_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_chart",
        "description": "Draw a new chart from the dataset to answer the user's question visually. "
                        "Only call this when the user explicitly asks to see, plot, chart, or visualize "
                        "something — not for plain descriptive or explanatory questions. Use 'heatmap' "
                        "for a correlation matrix / correlation heatmap request, and 'pairplot' for a "
                        "'pairwise relationship chart' / 'scatter matrix' / 'plot all variables against "
                        "each other' request — for both of those, call this ONCE (not once per pair).",
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {"type": "string", "enum": ["bar", "line", "scatter", "histogram", "box",
                                                            "pie", "heatmap", "pairplot"]},
                "x_column": {"type": ["string", "null"],
                             "description": "Column name for the x-axis / categories / grouping. Not used "
                                             "for 'heatmap' or 'pairplot'. For 'box', this is optional — "
                                             "pass null (or omit) for a single-column box plot of "
                                             "y_column, or a categorical column here to group the box "
                                             "plot of y_column by category."},
                "y_column": {"type": ["string", "null"],
                             "description": "Column name for the y-axis / values. Optional for "
                                             "histogram/pie; not used for 'heatmap' or 'pairplot'. For "
                                             "'box', this is the numeric column being plotted — required "
                                             "unless x_column is given instead."},
                "columns": {"type": "array", "items": {"type": "string"},
                            "description": "For 'heatmap' or 'pairplot' only: the numeric columns to "
                                            "include. Omit to use every numeric column in the dataset."},
                "title": {"type": "string"},
            },
            "required": ["chart_type", "title"],
        },
    },
}

RUN_SQL_TOOL = {
    "type": "function",
    "function": {
        "name": "run_sql_query",
        "description": "Run a read-only SQL SELECT query against the dataset (table name: data) to get "
                        "exact numbers — totals, averages, counts, filters, group-bys, top-N/LIMIT, etc. "
                        "Use this whenever the user asks a specific data question that needs a precise "
                        "computed answer, or explicitly asks you to write/run a SQL query. ALWAYS call this "
                        "tool for such requests — never just type SQL text into your reply. Only reference "
                        "columns that actually exist in the dataset — never invent a grouping column (e.g. "
                        "a 'channel' or 'category' column) that isn't listed in the dataset profile.",
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A single SELECT statement over the table `data`, using the exact "
                                    "column names given in the dataset profile.",
                }
            },
            "required": ["sql"],
        },
    },
}

COMPARE_COLUMNS_TOOL = {
    "type": "function",
    "function": {
        "name": "compare_columns",
        "description": "Compare one or more numeric columns against a numeric target column using real "
                        "statistics (Pearson correlation and linear regression slope). Use this whenever the "
                        "user asks to compare numeric fields against each other or against an outcome (e.g. "
                        "'compare TV vs Radio on Sales', 'which channel drives sales most', 'is Newspaper "
                        "effective'). This is a WIDE-format dataset — each variable (TV, Radio, Newspaper, "
                        "etc.) is already its own column, there is no categorical 'channel' column to group by, "
                        "so do NOT use run_sql_query with a GROUP BY for this kind of question — use this tool "
                        "instead.",
        "parameters": {
            "type": "object",
            "properties": {
                "columns": {
                    "type": "array", "items": {"type": "string"},
                    "description": "The numeric columns to compare, e.g. ['TV', 'Radio', 'Newspaper'].",
                },
                "target": {
                    "type": "string",
                    "description": "The numeric outcome column to compare each column against, e.g. 'Sales'.",
                },
            },
            "required": ["columns", "target"],
        },
    },
}

SYSTEM_INSTRUCTION = """You are InsightForge, an expert data analyst and business consultant AI \
embedded in a data analytics dashboard. You are given a statistical PROFILE of a dataset. Be precise, \
cite actual numbers, and prefer concrete, actionable business recommendations over generic advice.

The dataset's exact column names are provided to you in every message context. Never reference, filter \
on, or group by a column that is not in that exact list — in particular, never assume a categorical \
column like 'channel', 'category', 'group', or 'segment' exists unless it is explicitly listed. Many \
datasets are WIDE format, where each variable (e.g. TV, Radio, Newspaper) is already its own numeric \
column rather than rows tagged with a category — for those, use compare_columns, not a SQL GROUP BY.

You have three tools:
- generate_chart: only call this when the user explicitly wants to see/plot/visualize something. Use \
'heatmap' for a correlation matrix, and 'pairplot' for a pairwise/scatter-matrix request — call it ONCE \
for the whole chart, never once per pair of columns. For a 'box' plot of a single numeric column, pass \
that column as y_column and leave x_column null; only set x_column too if the user wants the box plot \
grouped by a categorical column.
- run_sql_query: call this for exact numbers computed from real rows (totals, averages, counts, top-N, \
filters), or any time the user asks you to write/run a SQL query. ALWAYS use the tool for this — never \
type SQL as plain text in your reply. If the user asks for multiple/N SQL queries (e.g. "generate 5 SQL \
queries for sales analysis"), call run_sql_query separately once per query — exactly N calls for N \
queries, each with a different, distinct SELECT statement covering a different angle of the request. \
Never combine multiple queries into a single call, and never answer with fewer calls than requested.
- compare_columns: call this whenever comparing numeric columns' relationship to a target/outcome column \
(e.g. "compare TV vs Radio on Sales", "is Newspaper effective") — not a SQL GROUP BY, since this is a \
wide-format dataset.

For plain descriptive questions ("what is this dataset about", "summarize this data"), answer directly \
in text using the profile — do not call a tool for these.

Tool calls are internal plumbing — NEVER show a tool call, function name, curly-brace arguments, or SQL \
text in your reply; the UI renders the chart, table, or query result on its own. After a tool runs, you \
will receive its real result. Your final reply is ONLY the analysis/explanation of that result in plain \
language — never repeat the SQL query, never redraw a table in your reply, never respond with only a \
generic caption like "here's the chart you asked for," and never echo the tool call itself.

When you were asked for multiple SQL queries, structure your reply as a numbered explanation matching \
the order the queries were run in — "1) ...", "2) ...", etc — one short explanation per query, never one \
combined summary that blurs them together. The UI already shows each query and its own result table \
numbered in that same order; your job is only to explain what each one found.

Write in plain prose only — no markdown (**bold**, headers, code fences, or tables) anywhere in your \
reply, since the chat UI displays your text as-is.

For any analytical question (comparisons, effectiveness, predictions, correlations, "what's driving X"), \
give a genuinely useful answer of about 3-6 sentences that covers: the key finding, the supporting \
number(s)/statistic(s) from the tool result, what that means in plain business terms, and — when it's \
relevant — a concrete recommendation. Skip the recommendation for purely descriptive questions. Avoid \
one-line non-answers; also avoid padding with generic filler that isn't grounded in the actual numbers."""

_KNOWN_TOOLS = ("generate_chart", "run_sql_query", "compare_columns")

# Some models occasionally emit a tool call as literal text instead of using
# the structured tool_calls field the SDK expects — wrapped as
# `<function=run_sql_query>{"sql": "..."}</function>`, or written bare as
# `generate_chart{"chart_type": "scatter", ...}` with no wrapper at all,
# sometimes inside a stray ```sql code fence, sometimes several back-to-back.
# `_extract_inline_tool_calls` recovers every form of that so each call can
# still be executed for real, and none of the raw markup reaches the user.
_FUNCTION_TAG_RE = re.compile(r"<function=([a-zA-Z_]\w*)>")
_BARE_CALL_RE = re.compile(r"(?<![\w.])(" + "|".join(_KNOWN_TOOLS) + r")\b")


def _find_balanced_json(text: str, start: int) -> "tuple[dict, int] | None":
    """Given `text` and the index of an opening '{', walks forward counting
    brace depth (ignoring braces inside quoted strings) to find the matching
    close brace, then parses that span as JSON. Returns (parsed_args, index
    just past the closing brace), or None if it's not valid/balanced JSON."""
    if start >= len(text) or text[start] != "{":
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1]), i + 1
                except json.JSONDecodeError:
                    return None
    return None


def _extract_inline_tool_calls(text: str) -> "list[tuple[int, int, str, dict]]":
    """Scans `text` for every tool call emitted as literal text (either the
    `<function=name>{...}</function>` form or a bare `name{...}` form) and
    returns each as (start_index, end_index, tool_name, args), sorted and
    de-overlapped, so callers can execute them and strip that exact span."""
    if not text:
        return []
    spans = []
    for m in _FUNCTION_TAG_RE.finditer(text):
        j = m.end()
        while j < len(text) and text[j] in " \t\n":
            j += 1
        result = _find_balanced_json(text, j)
        if not result:
            continue
        args, end_idx = result
        if text[end_idx:end_idx + 11] == "</function>":
            end_idx += len("</function>")
        spans.append((m.start(), end_idx, m.group(1), args))
    for m in _BARE_CALL_RE.finditer(text):
        j = m.end()
        while j < len(text) and text[j] in " \t\n`":
            j += 1
        result = _find_balanced_json(text, j)
        if not result:
            continue
        args, end_idx = result
        spans.append((m.start(), end_idx, m.group(1), args))
    spans.sort(key=lambda s: s[0])
    filtered, last_end = [], -1
    for s in spans:
        if s[0] >= last_end:
            filtered.append(s)
            last_end = s[1]
    return filtered


def _compare_columns(df: pd.DataFrame, columns: list[str], target: str) -> dict:
    """Real Pearson correlation + linear regression slope of each column against
    a target column — computed directly from the data, not guessed by the model."""
    if target not in df.columns:
        raise ValueError(f"Column '{target}' not found in dataset.")
    results = []
    for col in columns:
        if col not in df.columns or col == target:
            continue
        sub = df[[col, target]].dropna()
        if len(sub) < 2 or sub[col].nunique() < 2:
            continue
        corr = float(sub[col].corr(sub[target]))
        slope = float(np.polyfit(sub[col], sub[target], 1)[0])
        strength = "strong" if abs(corr) > 0.7 else "moderate" if abs(corr) > 0.4 else "weak"
        results.append({"column": col, "correlation": round(corr, 3),
                         "regression_slope": round(slope, 4), "strength": strength})
    results.sort(key=lambda r: abs(r["correlation"]), reverse=True)
    return {"target": target, "comparisons": results}


def _run_sql(df: pd.DataFrame, sql: str) -> dict:
    stripped = sql.strip().rstrip(";")
    if not re.match(r"(?is)^\s*(with\b.*?\bselect|select)\b", stripped):
        raise ValueError("Only SELECT queries are allowed.")
    forbidden = r"\b(insert|update|delete|drop|alter|attach|create|copy|pragma|call)\b"
    if re.search(forbidden, stripped, re.IGNORECASE):
        raise ValueError("Only read-only SELECT queries are allowed.")

    con = duckdb.connect(database=":memory:")
    try:
        con.register("data", df)
        result_df = con.execute(stripped).df()
    finally:
        con.close()

    result_df = result_df.head(50)
    return {
        "columns": [str(c) for c in result_df.columns],
        "rows": json.loads(result_df.to_json(orient="values", date_format="iso")),
        "row_count": int(len(result_df)),
        "sql": stripped,
    }


def _clean_reply_text(text: str) -> str:
    """Defensive final cleanup: strips any tool-call markup, markdown bold,
    and stray code fences that might otherwise leak into what the user sees,
    even if a model slips one into an ostensibly normal reply."""
    if not text:
        return text
    for start, end, _name, _args in reversed(_extract_inline_tool_calls(text)):
        text = text[:start] + text[end:]
    text = re.sub(r"```[a-zA-Z]*\n?", "", text)
    text = text.replace("```", "")
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


INSIGHTS_SYSTEM_INSTRUCTION = """You are InsightForge, an expert data analyst and business consultant AI. \
You are given a COMPACT statistical summary of a dataset (already computed with pandas — row/column \
counts, missing/duplicate counts, per-column stats, and the strongest correlations). You do not have \
the raw rows and must never invent numbers that aren't in the summary. Be precise, cite the actual \
figures given, and prefer concrete, actionable business recommendations over generic advice. Respond \
with ONLY a raw JSON object — no markdown fences, no preamble."""

# --- Compact context for AI Insights ----------------------------------------
# generate_business_insights() must NEVER send the full profile (it can carry
# a top-5-values block and full skew/kurtosis/outlier stats per column, plus
# an NxN correlation matrix) or the raw dataset as text — that unbounded
# growth on wide datasets was the actual cause of the "conversation has grown
# too long" / 413 error, not chat history (this endpoint never touches chat
# history at all). Instead we build a small, bounded JSON summary directly
# from the stats profiler.py already computed with pandas, so the LLM is
# never asked to (re-)calculate anything from raw data. `_build_insights_context`
# is also the hard safety limit from requirement #12: it always returns a
# string capped at `max_chars`, regardless of how wide/large the dataset is.
INSIGHTS_CONTEXT_MAX_CHARS = 6000


def _compact_column_entry(col: dict) -> dict:
    """Keeps only what a business-insights narrative actually needs from one
    column's profile entry, rounded and trimmed (e.g. top 3 categories, not
    top 5; no kurtosis) to keep per-column size small."""
    entry = {
        "name": col.get("name"),
        "type": col.get("type"),
        "missing_pct": col.get("missing_pct"),
        "unique_count": col.get("unique_count"),
    }
    if col.get("type") == "numeric":
        for key in ("mean", "median", "std", "min", "max", "skew", "outlier_count"):
            val = col.get(key)
            if val is None:
                continue
            entry[key] = round(val, 3) if isinstance(val, float) else val
    elif col.get("type") in ("categorical", "boolean", "identifier"):
        top_values = col.get("top_values") or {}
        entry["top_values"] = dict(list(top_values.items())[:3])
    elif col.get("type") == "datetime":
        entry["min_date"] = col.get("min_date")
        entry["max_date"] = col.get("max_date")
    return entry


def _top_correlations(correlation_matrix: "dict | None", limit: int = 8) -> list:
    """Reduces a full NxN correlation matrix (which grows quadratically with
    the number of numeric columns) down to just the strongest, de-duplicated
    pairs — plenty for narrative insights, without shipping the whole grid."""
    if not correlation_matrix:
        return []
    seen, pairs = set(), []
    for a, row in correlation_matrix.items():
        for b, v in (row or {}).items():
            if a == b or v is None:
                continue
            key = tuple(sorted((a, b)))
            if key in seen:
                continue
            seen.add(key)
            pairs.append({"columns": list(key), "correlation": round(v, 3)})
    pairs.sort(key=lambda p: abs(p["correlation"]), reverse=True)
    return pairs[:limit]


def _build_insights_context(profile: dict, max_chars: int = INSIGHTS_CONTEXT_MAX_CHARS) -> str:
    """Builds a compact JSON string describing the dataset for the LLM.
    Tries progressively smaller column caps until the serialized result fits
    under `max_chars`; the final attempt is also hard-truncated, so the
    return value is *always* bounded no matter how wide the dataset is."""
    columns = profile.get("columns", [])
    correlations = _top_correlations(profile.get("correlation_matrix"))
    text = "{}"
    for col_cap in (30, 15, 8, 4, 0):
        compact = {
            "n_rows": profile.get("n_rows"),
            "n_cols": profile.get("n_cols"),
            "duplicate_rows": profile.get("duplicate_rows"),
            "total_missing_cells": profile.get("total_missing_cells"),
            "columns": [_compact_column_entry(c) for c in columns[:col_cap]],
            "top_correlations": correlations,
        }
        if len(columns) > col_cap:
            compact["other_columns"] = [c.get("name") for c in columns[col_cap:]]
        text = json.dumps(compact, default=str)
        if len(text) <= max_chars:
            return text
    # Hard safety net (requirement #12): even the smallest summary above was
    # too large (e.g. an extreme number of columns) — truncate outright
    # rather than ever sending an unbounded request to Groq.
    return text[:max_chars]


def generate_business_insights(profile: dict) -> dict:
    """AI Insights tab — one-shot, STATELESS Groq call (same Groq client/
    service as chat, via _create_completion below). It never sees chat
    history or previous AI Insights output — every call (including "Try
    again") builds a fresh compact summary from the dataset's statistical
    profile only, so it can't hit "conversation has grown too long" and
    stays fully independent of the Assistant/chat tab. Uses its own model/
    token budget (GROQ_INSIGHTS_*) so this never changes the existing chat
    assistant's model or token usage."""
    context_json = _build_insights_context(profile)

    prompt = f"""Here is a compact statistical summary of a dataset (already computed with pandas, JSON):

{context_json}

Return a JSON object with exactly these keys:
- "key_insights": array of 4-6 strings, each a specific, numbers-backed observation
- "business_recommendations": array of 3-5 strings, each a concrete, actionable recommendation
- "risk_flags": array of 0-3 strings noting data quality or business risks worth attention
- "executive_summary": one 2-3 sentence paragraph summarizing the dataset's story

Respond with ONLY the raw JSON object, no markdown fences, no preamble."""

    try:
        response = _create_completion(
            model=settings.GROQ_INSIGHTS_MODEL,
            temperature=settings.GROQ_INSIGHTS_TEMPERATURE,
            max_tokens=settings.GROQ_INSIGHTS_MAX_TOKENS,
            messages=[
                {"role": "system", "content": INSIGHTS_SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
        )
    except AssistantOverloadedError as e:
        # _create_completion's message is written for the chat tab ("start a
        # new chat"); AI Insights has no conversation to reset, so reword it
        # here rather than editing that shared chat-facing message.
        if "rate limit" in str(e).lower():
            raise
        raise AssistantOverloadedError(
            "This dataset's statistics were too large to summarize in one request. "
            "Please try again — if it keeps happening, it likely has an unusually "
            "large number of columns."
        ) from e
    text = (response.choices[0].message.content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "key_insights": [text[:500]] if text else ["The AI response could not be parsed."],
            "business_recommendations": [],
            "risk_flags": [],
            "executive_summary": "Auto-generated summary parsing failed; showing raw model output above.",
        }


def _execute_tool(name: str, args: dict, df: pd.DataFrame) -> "tuple[str, dict | None, dict | None]":
    """Runs one tool call against the real dataframe. Returns
    (tool_output_text_for_model, chart_result, table_result)."""
    if name == "generate_chart":
        try:
            chart_result = build_chart_from_request(df, **args)
            return f"Chart created successfully: '{args.get('title')}' ({args.get('chart_type')}).", chart_result, None
        except Exception as e:
            return f"Could not build that chart: {e}", None, None

    if name == "run_sql_query":
        try:
            result = _run_sql(df, args.get("sql", ""))
            tool_output = (
                f"Query executed successfully, {result['row_count']} row(s) returned. "
                f"Columns: {result['columns']}. Data: {json.dumps(result['rows'][:20])}"
            )
            return tool_output, None, result
        except Exception as e:
            return f"SQL error: {e}", None, None

    if name == "compare_columns":
        try:
            result = _compare_columns(df, args.get("columns", []), args.get("target", ""))
            tool_output = f"Comparison computed successfully: {json.dumps(result)}"
            return tool_output, None, result
        except Exception as e:
            return f"Comparison error: {e}", None, None

    return "Unknown tool.", None, None


_N_QUERIES_RE = re.compile(r"\b(\d{1,2})\b\s+(?:distinct\s+|different\s+|separate\s+)?sql\s+quer", re.IGNORECASE)


def _detect_requested_query_count(user_message: str) -> "int | None":
    """Looks for phrasing like 'generate 5 SQL queries' / '5 different SQL
    queries' and returns the requested count (capped at 10) so we can inject
    an explicit, hard-to-miss reminder — relying on the system prompt alone
    was not reliable enough in practice and was the root cause of "asked
    for 5, got 1"."""
    m = _N_QUERIES_RE.search(user_message)
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 < n <= 10 else None


def chat(profile: dict, history: list[dict], user_message: str, df: pd.DataFrame) -> dict:
    """
    history: [{"role": "user"|"assistant", "content": str}, ...]
    Returns: {"reply": str, "chart": dict|None, "table": dict|None}
    """
    if len(user_message) > 4000:
        user_message = user_message[:4000] + " …[truncated — please ask a shorter/more specific question]"

    messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]

    columns_note = (
        f"[Exact dataset columns — use ONLY these, never invent others: {list(df.columns)}. "
        f"This is a WIDE-format dataset: each variable is its own column, not a category to group by, "
        f"unless a column is explicitly listed above as categorical.]"
    )

    if not history:
        context = (
            f"{columns_note}\n"
            f"[Dataset profile for reference — {profile['n_rows']} rows, {profile['n_cols']} columns. "
            f"Numeric columns: {profile['numeric_columns']}. Categorical columns: {profile['categorical_columns']}. "
            f"Full profile JSON: {json.dumps(profile, default=str)[:8000]}]"
        )
        final_user_turn = f"{context}\n\nUser question: {user_message}"
    else:
        messages.extend(_prepare_history_for_model(history))
        final_user_turn = f"{columns_note}\n\nUser question: {user_message}"

    requested_n = _detect_requested_query_count(user_message)
    if requested_n:
        final_user_turn += (
            f"\n\n[SYSTEM REMINDER: The user explicitly asked for {requested_n} SQL queries. You must "
            f"call the run_sql_query tool exactly {requested_n} separate times in this turn — one "
            f"distinct, meaningfully different query per call, each covering a different angle of the "
            f"analysis. Do not stop after fewer calls, and do not put more than one query in a single "
            f"call.]"
        )
    messages.append({"role": "user", "content": final_user_turn})

    tools = [GENERATE_CHART_TOOL, RUN_SQL_TOOL, COMPARE_COLUMNS_TOOL]
    chart_results: list[dict] = []
    table_results: list[dict] = []

    response = _create_completion(
        model=settings.GROQ_MODEL,
        temperature=settings.GROQ_TEMPERATURE,
        max_tokens=settings.GROQ_MAX_TOKENS,
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )
    msg = response.choices[0].message

    # Tool-calling loop. Every round keeps `tools` in the request — this is
    # what actually fixes "tool generate_chart was not in request.tools":
    # once a message with tool_calls is in the conversation, Groq validates
    # any *later* request in the same exchange against that request's own
    # `tools` list, so a follow-up call made without `tools` would fail
    # that validation. Looping (instead of one fixed follow-up) also lets
    # the model make several run_sql_query calls across rounds if it
    # doesn't batch them all into one response — the actual cause of
    # "asked for 5 queries, got 1".
    MAX_TOOL_ROUNDS = 3
    rounds = 0
    while msg.tool_calls and rounds < MAX_TOOL_ROUNDS:
        rounds += 1
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            try:
                tool_output, chart, table = _execute_tool(tc.function.name, args, df)
            except Exception as e:  # noqa: BLE001 - never let one bad tool call kill the whole turn
                tool_output, chart, table = f"Tool '{tc.function.name}' failed unexpectedly: {e}", None, None
            if chart:
                chart_results.append(chart)
            if table:
                table_results.append(table)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_output})

        remaining_hint = ""
        if requested_n and len(table_results) < requested_n:
            remaining_hint = (
                f"\n\n[SYSTEM REMINDER: {len(table_results)} of {requested_n} requested SQL queries have "
                f"been run so far. Call run_sql_query again for each remaining distinct query before "
                f"writing your final answer.]"
            )
        response = _create_completion(
            model=settings.GROQ_MODEL,
            temperature=settings.GROQ_TEMPERATURE,
            max_tokens=settings.GROQ_MAX_TOKENS,
            messages=messages + ([{"role": "user", "content": remaining_hint}] if remaining_hint else []),
            tools=tools,
            tool_choice="auto" if rounds < MAX_TOOL_ROUNDS else "none",
        )
        msg = response.choices[0].message

    if rounds > 0:
        # Loop ran at least once: `msg` is the model's final, tool-free answer.
        reply_text = (msg.content or "").strip()
        if not reply_text:
            reply_text = "Here's what I found." if (chart_results or table_results) else "I wasn't able to generate a response."
    else:
        # Fallback path: the very first response had no structured tool_calls
        # at all. Some models emit the call as literal text instead — one
        # call or several, wrapped or bare, maybe inside a code fence.
        # Recover every one, execute them for real, and re-ask for a clean
        # explanation — never show the raw markup.
        inline_calls = _extract_inline_tool_calls(msg.content or "")
        if inline_calls:
            tool_outputs = []
            for _start, _end, name, args in inline_calls:
                try:
                    tool_output, chart, table = _execute_tool(name, args, df)
                except Exception as e:  # noqa: BLE001
                    tool_output, chart, table = f"Tool '{name}' failed unexpectedly: {e}", None, None
                if chart:
                    chart_results.append(chart)
                if table:
                    table_results.append(table)
                tool_outputs.append(f"Tool '{name}' result: {tool_output}")
            messages.append({"role": "assistant", "content": "(internal tool call)"})
            messages.append({"role": "user", "content": "\n".join(tool_outputs) +
                                                          "\n\nAnswer the original question in plain "
                                                          "language using these results. Do not mention "
                                                          "any tool, function name, or SQL/JSON syntax."})
            follow_up = _create_completion(
                model=settings.GROQ_MODEL,
                temperature=settings.GROQ_TEMPERATURE,
                max_tokens=settings.GROQ_MAX_TOKENS,
                messages=messages,
                tools=tools,
                tool_choice="none",
            )
            reply_text = (follow_up.choices[0].message.content or "").strip()
            if not reply_text:
                reply_text = "Here's what I found."
        else:
            reply_text = (msg.content or "").strip()

    for i, t in enumerate(table_results, start=1):
        t["query_number"] = i

    chart_result = chart_results[0] if chart_results else None
    table_result = table_results[0] if table_results else None
    suggestions = _build_suggestions(chart_result, table_result, df)

    return {
        "reply": _clean_reply_text(reply_text),
        # Singular "chart"/"table" are kept for backward compatibility —
        # each is just the first entry of the corresponding list below.
        "chart": chart_result,
        "table": table_result,
        # Plural keys carry every result — this is what lets "generate 5
        # SQL queries" return 5 separate, individually-numbered tables
        # instead of collapsing down to just one.
        "charts": chart_results,
        "tables": table_results,
        "kpis": None,
        "suggestions": suggestions,
    }


def _build_suggestions(chart_result: dict | None, table_result: dict | None, df: pd.DataFrame) -> list[str]:
    """Cheap, deterministic follow-up prompts based on what just happened —
    no extra model call, so this never adds latency or another timeout
    risk. Purely additive: the current frontend doesn't render this yet."""
    if table_result:
        return ["Explain this result in more detail", "Show this as a chart", "What should I do about this?"]
    if chart_result:
        return ["What's driving this trend?", "Break this down by another column", "Summarize the key takeaway"]
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if len(numeric_cols) >= 2:
        return [f"Compare {numeric_cols[0]} vs {numeric_cols[1]}", "Show me a correlation heatmap",
                "What's the overall summary of this data?"]
    return ["Summarize this dataset", "What stands out in this data?"]
