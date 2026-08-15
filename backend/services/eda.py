"""
Generates a gallery of EDA charts automatically based on detected column types,
each returned as Plotly JSON (frontend renders with Plotly.js) plus a short
auto-written description — this is the "dashboard" content.

Chart style follows a clean, Colab/Power-BI-style "plotly_white" look:
white background, no borders, no modebar, subtle y-axis-only gridlines,
labeled bars, and a consistent brand colorway across every chart type.
"""
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import json

# Global color palette used consistently across every chart type
PRIMARY_COLOR = "#636EFA"
PALETTE = ["#636EFA", "#00CC96", "#EF553B", "#AB63FA", "#FFA15A"]
DIVERGING_COLORSCALE = [[0, "#EF553B"], [0.5, "#F5F5F5"], [1, "#636EFA"]]

CHART_FONT = "Inter, Arial, sans-serif"


def _fig_to_dict(fig, title, description, chart_type):
    fig.update_layout(
        template="plotly_white",
        title=dict(text=title, font=dict(size=22, family=CHART_FONT, color="#1A1A2E"), x=0.02, xanchor="left"),
        font=dict(family=CHART_FONT, size=13, color="#333333"),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        margin=dict(l=60, r=30, t=64, b=60),
        colorway=PALETTE,
        hoverlabel=dict(bgcolor="#FFFFFF", font_size=13, font_family=CHART_FONT, bordercolor="#DDDDDD"),
        hovermode="closest",
        bargap=0.25,
        showlegend=False,
        xaxis=dict(
            title_font=dict(size=16, family=CHART_FONT),
            tickfont=dict(size=13, family=CHART_FONT),
            showgrid=False,
            showline=True,
            linecolor="#E2E2E2",
            zeroline=False,
        ),
        yaxis=dict(
            title_font=dict(size=16, family=CHART_FONT),
            tickfont=dict(size=13, family=CHART_FONT),
            showgrid=True,
            gridcolor="rgba(0,0,0,0.08)",
            showline=False,
            zeroline=False,
        ),
    )
    fig.update_traces(marker_line_width=0, selector=dict(type="bar"))
    if chart_type == "bar":
        fig.update_traces(texttemplate="%{y:,.0f}", textposition="outside",
                           textfont=dict(size=12, family=CHART_FONT), selector=dict(type="bar"))
    return {
        "title": title,
        "type": chart_type,
        "description": description,
        "figure": json.loads(fig.to_json()),
    }


def _try_add(charts: list, label: str, builder, *args, **kwargs):
    """Runs a single chart builder in isolation. If it throws (bad data, degenerate
    column, etc.) we log and skip that one chart rather than letting one failure
    take out the whole dashboard — every other card still renders normally."""
    try:
        entry = builder(*args, **kwargs)
        if entry:
            charts.append(entry)
    except Exception as e:  # noqa: BLE001 - intentionally broad, this is a best-effort gallery
        print(f"[eda] skipped chart '{label}': {e}")


def _sample_df(df: pd.DataFrame, n: int = 3000) -> pd.DataFrame:
    """Downsamples large datasets before feeding them into heavier chart types
    (scatter matrix, scatter plots) so the dashboard stays responsive."""
    return df.sample(n, random_state=42) if len(df) > n else df


def _zero_diagonal(corr_df: pd.DataFrame, fill=0.0) -> pd.DataFrame:
    """Returns a copy of a correlation matrix with the diagonal replaced.
    Goes through a plain numpy array rather than `.copy(); .values[...] = ...`
    because pandas' copy-on-write mode can hand back a read-only view from
    `.values` even after `.copy()`, which raises at chart-build time — this
    was, in fact, one real cause of the heatmap silently failing to render."""
    arr = corr_df.to_numpy(copy=True)
    np.fill_diagonal(arr, fill)
    return pd.DataFrame(arr, index=corr_df.index, columns=corr_df.columns)


def _pick_target_column(corr_df: pd.DataFrame) -> "str | None":
    """Picks the numeric column most representative of the dataset's relationships —
    the one with the highest average correlation to every other numeric column.
    For an Advertising-style dataset (TV/Radio/Newspaper/Sales) this reliably
    lands on 'Sales', without hardcoding any column names."""
    if corr_df.shape[0] < 2:
        return None
    arr = np.abs(corr_df.to_numpy(copy=True))
    np.fill_diagonal(arr, np.nan)
    avg_corr = pd.Series(np.nanmean(arr, axis=1), index=corr_df.index)
    if avg_corr.isna().all():
        return None
    return avg_corr.idxmax()


def _trendline_figure(df: pd.DataFrame, x: str, y: str) -> go.Figure:
    """Scatter + linear trendline, computed with numpy.polyfit so we don't need
    the statsmodels dependency that plotly express's trendline='ols' requires."""
    sub = df[[x, y]].dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sub[x], y=sub[y], mode="markers", name=y,
                              marker=dict(color=PALETTE[0], size=7, opacity=0.7)))
    if len(sub) >= 2 and sub[x].nunique() > 1:
        slope, intercept = np.polyfit(sub[x], sub[y], 1)
        xs = np.linspace(sub[x].min(), sub[x].max(), 50)
        fig.add_trace(go.Scatter(x=xs, y=slope * xs + intercept, mode="lines",
                                  name="Trend", line=dict(color=PALETTE[2], width=2)))
    fig.update_layout(xaxis_title=x, yaxis_title=y)
    return fig


def _correlation_fallback_items(corr_df: pd.DataFrame, top_n: int = 6) -> list[dict]:
    """Compact summary of the strongest correlation pairs, used as the fallback
    view when the heatmap itself can't be rendered (and sent alongside a
    successfully-rendered heatmap too, so the frontend always has it on hand)."""
    c = _zero_diagonal(corr_df)
    pairs = c.abs().stack().sort_values(ascending=False)
    seen, items = set(), []
    for (a, b), _ in pairs.items():
        key = tuple(sorted((a, b)))
        if key in seen or a == b:
            continue
        seen.add(key)
        val = corr_df.loc[a, b]
        items.append({"label": f"{a} & {b}", "value": round(float(val), 3)})
        if len(items) >= top_n:
            break
    return items


def generate_eda_charts(df: pd.DataFrame, profile: dict, max_charts: int = 26) -> list[dict]:
    charts: list[dict] = []
    numeric_cols = profile["numeric_columns"]
    cat_cols = profile["categorical_columns"]
    date_cols = profile["datetime_columns"]
    sampled = _sample_df(df)

    corr_df = None
    target_col = None
    if profile.get("correlation_matrix") and len(numeric_cols) >= 2:
        corr_df = df[numeric_cols].corr(numeric_only=True)
        target_col = _pick_target_column(corr_df)

    # 1. Missing values overview
    def _missing_chart():
        miss = df.isna().sum()
        miss = miss[miss > 0].sort_values(ascending=False)
        if len(miss) == 0:
            return None
        fig = px.bar(x=miss.index, y=miss.values, labels={"x": "Column", "y": "Missing count"})
        return _fig_to_dict(
            fig, "Missing Values by Column",
            f"{len(miss)} column(s) contain missing data. '{miss.index[0]}' has the most, "
            f"with {int(miss.iloc[0])} missing entries — worth checking your collection process there.",
            "bar",
        )
    _try_add(charts, "missing_values", _missing_chart)

    # 2. Distribution (histogram) for each numeric column — covers "Sales distribution"
    # and "advertising spend distributions" automatically for any dataset shape.
    for col in numeric_cols[:6]:
        def _hist_chart(col=col):
            fig = px.histogram(df, x=col, nbins=30, marginal="box")
            skew = df[col].skew()
            shape = "right-skewed" if skew > 0.5 else "left-skewed" if skew < -0.5 else "roughly symmetric"
            return _fig_to_dict(
                fig, f"Distribution of {col}",
                f"'{col}' ranges from {df[col].min():.2f} to {df[col].max():.2f} with a mean of "
                f"{df[col].mean():.2f}. The distribution is {shape} (skew={skew:.2f}).",
                "histogram",
            )
        _try_add(charts, f"histogram_{col}", _hist_chart)

    # 3. Correlation heatmap — always carries a `fallback` summary of the strongest
    # pairs so the frontend can render a graceful summary instead of a blank card,
    # whether the failure happens here (server) or during client-side Plotly render.
    if corr_df is not None:
        def _heatmap_chart():
            # Computed defensively, outside the figure-building try/except below,
            # so a failure in the correlation summary itself can never take the
            # whole card down — worst case it's an empty fallback list.
            try:
                fallback_items = _correlation_fallback_items(corr_df)
            except Exception as e:  # noqa: BLE001
                print(f"[eda] correlation fallback summary failed: {e}")
                fallback_items = []
            entry = None
            try:
                fig = px.imshow(corr_df, text_auto=".2f", color_continuous_scale=DIVERGING_COLORSCALE,
                                 zmin=-1, zmax=1)
                c = _zero_diagonal(corr_df)
                max_pair = c.abs().stack().idxmax()
                max_val = corr_df.loc[max_pair]
                entry = _fig_to_dict(
                    fig, "Correlation Heatmap",
                    f"The strongest relationship is between '{max_pair[0]}' and '{max_pair[1]}' "
                    f"(correlation = {max_val:.2f}), suggesting they move together"
                    f"{' strongly' if abs(max_val) > 0.7 else ' moderately'}.",
                    "heatmap",
                )
            except Exception as e:  # noqa: BLE001
                print(f"[eda] heatmap figure failed, falling back to summary: {e}")
                entry = {
                    "title": "Correlation Heatmap",
                    "type": "heatmap",
                    "description": "Showing the strongest correlations as a summary instead.",
                    "figure": None,
                }
            entry["fallback"] = {"items": fallback_items}
            return entry
        _try_add(charts, "correlation_heatmap", _heatmap_chart)

    # 4. Pairwise relationship matrix (scatter matrix) — feasible for a moderate
    # number of numeric columns; skipped otherwise to avoid an unreadable, heavy chart.
    if 3 <= len(numeric_cols) <= 6:
        def _scatter_matrix_chart():
            dims = numeric_cols[:5]
            fig = px.scatter_matrix(sampled, dimensions=dims)
            fig.update_traces(diagonal_visible=False, marker=dict(size=4, opacity=0.6, color=PALETTE[0]))
            return _fig_to_dict(
                fig, "Pairwise Relationships",
                f"Scatter matrix across {', '.join(dims)}, useful for spotting relationships "
                "and clusters across every numeric field at once.",
                "scatter_matrix",
            )
        _try_add(charts, "scatter_matrix", _scatter_matrix_chart)

    # 5. Bar chart for top categorical columns
    for col in cat_cols[:5]:
        def _cat_bar_chart(col=col):
            vc = df[col].value_counts().head(10)
            fig = px.bar(x=vc.index.astype(str), y=vc.values, labels={"x": col, "y": "Count"},
                         color=vc.index.astype(str), color_discrete_sequence=PALETTE)
            fig.update_layout(showlegend=False)
            top_pct = vc.iloc[0] / len(df) * 100
            return _fig_to_dict(
                fig, f"Top Categories in {col}",
                f"'{vc.index[0]}' is the most common value in '{col}', making up {top_pct:.1f}% of records.",
                "bar",
            )
        _try_add(charts, f"cat_bar_{col}", _cat_bar_chart)

    # 5b. Pie/donut for low-cardinality categoricals only — a 30-slice pie isn't meaningful.
    for col in cat_cols[:5]:
        def _pie_chart(col=col):
            if df[col].nunique() > 6:
                return None
            vc = df[col].value_counts()
            fig = px.pie(names=vc.index.astype(str), values=vc.values, hole=0.45,
                         color_discrete_sequence=PALETTE)
            return _fig_to_dict(
                fig, f"Share of {col}",
                f"'{col}' has {vc.shape[0]} distinct values; '{vc.index[0]}' makes up "
                f"{vc.iloc[0]/len(df)*100:.1f}% of records.",
                "pie",
            )
        _try_add(charts, f"pie_{col}", _pie_chart)

    # 6. Boxplots per numeric column (outlier view)
    for col in numeric_cols[:6]:
        def _box_chart(col=col):
            fig = px.box(df, y=col, points="outliers")
            q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
            iqr = q3 - q1
            outliers = df[(df[col] < q1 - 1.5 * iqr) | (df[col] > q3 + 1.5 * iqr)]
            return _fig_to_dict(
                fig, f"Outlier Detection: {col}",
                f"{len(outliers)} outlier(s) detected in '{col}' using the IQR method "
                f"({len(outliers)/len(df)*100:.1f}% of rows).",
                "box",
            )
        _try_add(charts, f"box_{col}", _box_chart)

    # 6b. Violin plots — Plotly's density-shape equivalent to a KDE plot, and a
    # natural complement to the boxplots above (same columns, distribution shape view).
    for col in numeric_cols[:4]:
        def _violin_chart(col=col):
            fig = px.violin(df, y=col, box=True, points=False)
            return _fig_to_dict(
                fig, f"Density Shape: {col}",
                f"Violin plot of '{col}' showing where values concentrate, beyond what the "
                "box plot alone shows.",
                "violin",
            )
        _try_add(charts, f"violin_{col}", _violin_chart)

    # 6c. Distribution comparison — overlaid density histograms for the non-target
    # numeric columns (e.g. comparing TV/Radio/Newspaper spend on one chart).
    other_numeric = [c for c in numeric_cols if c != target_col]
    if len(other_numeric) >= 2:
        def _dist_compare_chart():
            cols = other_numeric[:4]
            fig = go.Figure()
            for i, col in enumerate(cols):
                fig.add_trace(go.Histogram(x=df[col], name=col, opacity=0.6,
                                            histnorm="probability density",
                                            marker_color=PALETTE[i % len(PALETTE)]))
            fig.update_layout(barmode="overlay", showlegend=True, xaxis_title="Value",
                               yaxis_title="Density")
            return _fig_to_dict(
                fig, "Distribution Comparison",
                f"Overlaid distributions for {', '.join(cols)}, making it easy to compare "
                "spread and shape side by side.",
                "distribution_comparison",
            )
        _try_add(charts, "distribution_comparison", _dist_compare_chart)

    # 7. Time series (line) + cumulative area if a datetime column exists
    if date_cols and numeric_cols:
        dcol, ncol = date_cols[0], numeric_cols[0]

        def _line_chart():
            ts = df[[dcol, ncol]].dropna().sort_values(dcol)
            if len(ts) <= 1:
                return None
            ts_grouped = ts.groupby(pd.Grouper(key=dcol, freq="ME"))[ncol].mean().dropna()
            fig = px.line(x=ts_grouped.index, y=ts_grouped.values, labels={"x": dcol, "y": f"Avg {ncol}"})
            trend = "increasing" if ts_grouped.iloc[-1] > ts_grouped.iloc[0] else "decreasing"
            return _fig_to_dict(
                fig, f"{ncol} Over Time",
                f"Average '{ncol}' shows a {trend} trend over the observed period "
                f"(from {ts_grouped.iloc[0]:.2f} to {ts_grouped.iloc[-1]:.2f}).",
                "line",
            )
        _try_add(charts, "time_series_line", _line_chart)

        def _area_chart():
            ts = df[[dcol, ncol]].dropna().sort_values(dcol)
            if len(ts) <= 1:
                return None
            ts_grouped = ts.groupby(pd.Grouper(key=dcol, freq="ME"))[ncol].sum().dropna()
            fig = px.area(x=ts_grouped.index, y=ts_grouped.values, labels={"x": dcol, "y": f"Cumulative {ncol}"})
            return _fig_to_dict(
                fig, f"{ncol} Accumulated Over Time",
                f"Running monthly total of '{ncol}' across the observed period.",
                "area",
            )
        _try_add(charts, "time_series_area", _area_chart)

    # 8. Scatter-with-trendline of every numeric column against the detected target
    # column. For an Advertising dataset this yields TV vs Sales, Radio vs Sales,
    # Newspaper vs Sales automatically, since 'Sales' is the column most correlated
    # with the others — no column names are hardcoded.
    if target_col:
        for col in other_numeric[:5]:
            def _trend_scatter_chart(col=col):
                fig = _trendline_figure(sampled, col, target_col)
                corr_val = corr_df.loc[col, target_col] if corr_df is not None else None
                corr_txt = f" (correlation = {corr_val:.2f})" if corr_val is not None else ""
                return _fig_to_dict(
                    fig, f"{col} vs {target_col}",
                    f"Relationship between '{col}' and '{target_col}'{corr_txt}, with a linear "
                    "trend line fitted across all records.",
                    "scatter",
                )
            _try_add(charts, f"trend_scatter_{col}", _trend_scatter_chart)
    elif len(numeric_cols) >= 2 and corr_df is not None:
        # Fallback for datasets with no clear single target: just show the single
        # most correlated pair, as before.
        def _fallback_scatter_chart():
            c = _zero_diagonal(corr_df.abs())
            if c.values.max() <= 0:
                return None
            c1, c2 = c.stack().idxmax()
            fig = _trendline_figure(sampled, c1, c2)
            return _fig_to_dict(
                fig, f"{c1} vs {c2}",
                f"Scatter plot of the two most correlated numeric fields, showing how '{c1}' "
                f"relates to '{c2}' across all records.",
                "scatter",
            )
        _try_add(charts, "fallback_scatter", _fallback_scatter_chart)

    # 9. Feature importance style chart — |correlation| with the target column,
    # ranked like a simple driver-analysis chart.
    if target_col and other_numeric:
        def _feature_importance_chart():
            importance = corr_df.loc[other_numeric, target_col].abs().sort_values(ascending=True)
            fig = px.bar(x=importance.values, y=importance.index, orientation="h",
                         labels={"x": f"|correlation| with {target_col}", "y": ""})
            top = importance.index[-1]
            return _fig_to_dict(
                fig, f"Feature Importance (Correlation with {target_col})",
                f"'{top}' has the strongest relationship with '{target_col}' among the "
                "available numeric fields, based on absolute correlation.",
                "bar_horizontal",
            )
        _try_add(charts, "feature_importance", _feature_importance_chart)

    # 10. Comparative averages bar chart — e.g. average spend across advertising channels.
    if len(other_numeric) >= 2:
        def _comparative_bar_chart():
            means = df[other_numeric].mean().sort_values(ascending=False)
            fig = px.bar(x=means.index, y=means.values, labels={"x": "Column", "y": "Average value"})
            return _fig_to_dict(
                fig, "Comparative Averages",
                f"'{means.index[0]}' has the highest average value ({means.iloc[0]:.2f}) "
                f"among {', '.join(other_numeric[:4])}.",
                "bar",
            )
        _try_add(charts, "comparative_averages", _comparative_bar_chart)

    # 11. Top-N chart — top categories ranked by the target's average, when both exist.
    if cat_cols and target_col:
        def _top_n_chart():
            col = cat_cols[0]
            grouped = df.groupby(col)[target_col].mean().sort_values(ascending=False).head(10)
            if grouped.empty:
                return None
            fig = px.bar(x=grouped.index.astype(str), y=grouped.values,
                         labels={"x": col, "y": f"Avg {target_col}"})
            return _fig_to_dict(
                fig, f"Top {col} by Avg {target_col}",
                f"'{grouped.index[0]}' leads with an average '{target_col}' of {grouped.iloc[0]:.2f}.",
                "bar",
            )
        _try_add(charts, "top_n", _top_n_chart)

    return charts[:max_charts]


def build_chart_from_request(df: pd.DataFrame, chart_type: str, x_column: str = None,
                              y_column: str = None, title: str = "Chart",
                              columns: "list[str] | None" = None) -> dict:
    """Used by the chat agent's generate_chart tool call — builds a chart on demand
    from columns the model chose, with safety checks against the real dataframe."""
    numeric_cols_all = df.select_dtypes(include="number").columns.tolist()

    # Multi-column chart types operate over a set of numeric columns (either the
    # caller-supplied `columns` list or every numeric column in the dataset) —
    # they don't use x_column/y_column at all.
    if chart_type == "heatmap":
        cols = [c for c in (columns or numeric_cols_all) if c in numeric_cols_all]
        if len(cols) < 2:
            raise ValueError("Need at least two numeric columns to build a correlation heatmap.")
        corr_df = df[cols].corr(numeric_only=True)
        fig = px.imshow(corr_df, text_auto=".2f", color_continuous_scale=DIVERGING_COLORSCALE,
                         zmin=-1, zmax=1)
        entry = _fig_to_dict(fig, title, "", "heatmap")
        try:
            entry["fallback"] = {"items": _correlation_fallback_items(corr_df)}
        except Exception:  # noqa: BLE001 - fallback summary is best-effort
            entry["fallback"] = {"items": []}
        return entry

    if chart_type in ("pairplot", "scatter_matrix"):
        cols = [c for c in (columns or numeric_cols_all) if c in numeric_cols_all][:6]
        if len(cols) < 2:
            raise ValueError("Need at least two numeric columns to build a pairwise relationship chart.")
        sampled = _sample_df(df)
        fig = px.scatter_matrix(sampled, dimensions=cols)
        fig.update_traces(diagonal_visible=False, marker=dict(size=4, opacity=0.6, color=PALETTE[0]))
        return _fig_to_dict(fig, title, "", "scatter_matrix")

    if chart_type == "box":
        # Box plots are the one chart type that can be driven by either
        # axis: a single numeric column (pass it as y_column, x_column
        # null) for one overall box, or numeric y_column + categorical
        # x_column for a grouped box plot. Previously this fell through to
        # the generic "x_column not in df.columns" check below, which
        # raised whenever x_column was null/None — that was the actual bug
        # behind "box plots fail when x_column is null".
        value_col = y_column if y_column else x_column
        if not value_col or value_col not in df.columns:
            raise ValueError("Box plot needs a numeric column — pass it as y_column "
                              "(optionally with a categorical x_column to group by).")
        group_col = x_column if x_column and x_column != value_col and x_column in df.columns else None
        fig = px.box(df, x=group_col, y=value_col) if group_col else px.box(df, y=value_col)
        return _fig_to_dict(fig, title, "", chart_type)

    if not x_column or x_column not in df.columns:
        raise ValueError(f"Column '{x_column}' not found in dataset.")

    if chart_type == "histogram":
        fig = px.histogram(df, x=x_column, nbins=30)
    elif chart_type == "pie":
        vc = df[x_column].value_counts().head(10)
        fig = px.pie(names=vc.index.astype(str), values=vc.values)
    elif chart_type == "bar":
        if y_column and y_column in df.columns:
            grouped = df.groupby(x_column)[y_column].mean().sort_values(ascending=False).head(15)
            fig = px.bar(x=grouped.index.astype(str), y=grouped.values, labels={"x": x_column, "y": y_column})
        else:
            vc = df[x_column].value_counts().head(15)
            fig = px.bar(x=vc.index.astype(str), y=vc.values, labels={"x": x_column, "y": "Count"})
    elif chart_type == "line":
        fig = px.line(df.sort_values(x_column), x=x_column, y=y_column)
    elif chart_type == "scatter":
        fig = px.scatter(df, x=x_column, y=y_column)
    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")

    return _fig_to_dict(fig, title, "", chart_type)


def compute_kpis(df: pd.DataFrame, profile: dict) -> list[dict]:
    """Top-line KPI cards for the dashboard header."""
    kpis = [
        {"label": "Total Rows", "value": f"{profile['n_rows']:,}"},
        {"label": "Total Columns", "value": f"{profile['n_cols']}"},
        {"label": "Missing Cells", "value": f"{profile['total_missing_cells']:,}",
         "sub": f"{profile['total_missing_cells']/(profile['n_rows']*profile['n_cols'])*100:.1f}% of data" if profile['n_rows'] and profile['n_cols'] else ""},
        {"label": "Duplicate Rows", "value": f"{profile['duplicate_rows']:,}"},
    ]
    if profile["numeric_columns"]:
        col = profile["numeric_columns"][0]
        kpis.append({"label": f"Avg {col}", "value": f"{df[col].mean():,.2f}"})
    return kpis
