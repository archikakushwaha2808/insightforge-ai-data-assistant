"""
Automated machine learning layer.
- If the user picks a target column -> auto-detect classification vs regression,
  train several models, pick the best by cross-validated score, return metrics +
  feature importance + a plain-English summary.
- If no target -> unsupervised mode: KMeans clustering (auto-k via silhouette) + PCA
  for 2D visualization.
"""
import pandas as pd
import numpy as np
import plotly.express as px
import json

from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor, GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import accuracy_score, f1_score, r2_score, mean_absolute_error, silhouette_score


def _prepare_features(df: pd.DataFrame, feature_cols: list[str]):
    X = df[feature_cols].copy()
    encoders = {}
    for col in X.columns:
        if X[col].dtype == object or str(X[col].dtype).startswith("category"):
            X[col] = X[col].astype(str)
            le = LabelEncoder()
            X[col] = le.fit_transform(X[col])
            encoders[col] = le
        elif pd.api.types.is_datetime64_any_dtype(X[col]):
            X[col] = X[col].astype("int64") // 10**9  # to unix timestamp
    imputer = SimpleImputer(strategy="median")
    X_imputed = pd.DataFrame(imputer.fit_transform(X), columns=X.columns, index=X.index)
    return X_imputed, encoders

def get_valid_target_columns(df: pd.DataFrame) -> list[str]:
    """
    Automatically find columns that are suitable ML prediction targets.
    Excludes date/time columns, obvious ID columns, empty columns,
    constant columns, and extremely high-cardinality text columns.
    """

    valid_targets = []

    for col in df.columns:
        series = df[col]

        # Ignore completely empty columns
        if series.dropna().empty:
            continue

        # Ignore columns with only one unique value
        if series.dropna().nunique() <= 1:
            continue

        # Ignore actual datetime columns
        if pd.api.types.is_datetime64_any_dtype(series):
            continue

        # Detect date columns stored as strings
        if series.dtype == object:
            sample = series.dropna().astype(str).head(100)

            if len(sample) > 0:
                parsed_dates = pd.to_datetime(sample, errors="coerce")

                if parsed_dates.notna().mean() >= 0.8:
                    continue

        # Ignore obvious ID columns
        col_lower = str(col).strip().lower()

        if (
            col_lower == "id"
            or col_lower.endswith("_id")
            or col_lower.endswith(" id")
            or col_lower in {
                "order id",
                "customer id",
                "product id",
                "transaction id",
                "transaction_id",
                "customer_id",
                "product_id",
                "order_id"
            }
        ):
            continue

        # Numeric columns can be prediction targets
        if pd.api.types.is_numeric_dtype(series):
            valid_targets.append(col)
            continue

        # Boolean columns can be classification targets
        if pd.api.types.is_bool_dtype(series):
            valid_targets.append(col)
            continue

        # Categorical/text columns can be classification targets
        if (
            series.dtype == object
            or str(series.dtype).startswith("category")
        ):
            unique_count = series.dropna().nunique()

            if unique_count <= min(50, max(2, int(len(series) * 0.2))):
                valid_targets.append(col)

    return valid_targets


def run_supervised(df: pd.DataFrame, target_col: str) -> dict:
    df = df.dropna(subset=[target_col])
    feature_cols = [c for c in df.columns if c != target_col]
    X, _ = _prepare_features(df, feature_cols)
    y_raw = df[target_col]

    if pd.api.types.is_datetime64_any_dtype(y_raw):
        return {
            "error": (
                f"'{target_col}' is a date/time column. "
                "Please choose a numeric column for regression "
                "or a categorical column for classification."
            )
        }

    is_classification = (
        y_raw.dtype == object
        or str(y_raw.dtype).startswith("category")
        or (
            # Only integer-typed columns with a small, low-cardinality set of
            # values are treated as classification. Float columns (like
            # revenue, price, temperature) are always regression, even if a
            # small sample happens to have few unique values.
            pd.api.types.is_integer_dtype(y_raw)
            and y_raw.nunique() <= min(20, max(2, int(len(y_raw) * 0.05)))
        )
        or pd.api.types.is_bool_dtype(y_raw)
    )

    if is_classification:
        y = LabelEncoder().fit_transform(y_raw.astype(str))
    else:
        y = y_raw.values

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    if is_classification:
        candidates = {
            "Logistic Regression": LogisticRegression(max_iter=1000),
            "Random Forest": RandomForestClassifier(n_estimators=200, random_state=42),
            "Gradient Boosting": GradientBoostingClassifier(random_state=42),
        }
    else:
        candidates = {
            "Linear Regression": LinearRegression(),
            "Random Forest": RandomForestRegressor(n_estimators=200, random_state=42),
            "Gradient Boosting": GradientBoostingRegressor(random_state=42),
        }

    results = {}
    best_name, best_model, best_score = None, None, -np.inf
    for name, model in candidates.items():
        model.fit(X_train_s, y_train)
        preds = model.predict(X_test_s)
        if is_classification:
            score = f1_score(y_test, preds, average="weighted")
            results[name] = {"accuracy": round(float(accuracy_score(y_test, preds)), 4),
                              "f1_score": round(float(score), 4)}
        else:
            score = r2_score(y_test, preds)
            results[name] = {"r2_score": round(float(score), 4),
                              "mae": round(float(mean_absolute_error(y_test, preds)), 4)}
        if score > best_score:
            best_name, best_model, best_score = name, model, score

    feature_importance = None
    if hasattr(best_model, "feature_importances_"):
        fi = pd.Series(best_model.feature_importances_, index=feature_cols).sort_values(ascending=False)
        feature_importance = {k: round(float(v), 4) for k, v in fi.head(10).items()}
    elif hasattr(best_model, "coef_"):
        coef = best_model.coef_
        # Multi-class linear models have coef_ shaped (n_classes, n_features);
        # collapse to one importance score per feature by averaging magnitude
        # across classes so this never breaks regardless of class count.
        importance_vals = np.abs(coef).mean(axis=0) if coef.ndim > 1 else np.abs(coef)
        fi = pd.Series(importance_vals, index=feature_cols).sort_values(ascending=False)
        feature_importance = {k: round(float(v), 4) for k, v in fi.head(10).items()}

    fig = None
    if feature_importance:
        fig = px.bar(x=list(feature_importance.values()), y=list(feature_importance.keys()), orientation="h",
                     labels={"x": "Importance", "y": "Feature"})
        fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           yaxis=dict(autorange="reversed"))

    return {
        "task_type": "classification" if is_classification else "regression",
        "target": target_col,
        "models_compared": results,
        "best_model": best_name,
        "best_score": round(float(best_score), 4),
        "feature_importance": feature_importance,
        "feature_importance_chart": json.loads(fig.to_json()) if fig else None,
        "summary": (
            f"Best model: {best_name} ({'F1' if is_classification else 'R²'} = {best_score:.3f}). "
            f"Top predictor of '{target_col}' is "
            f"'{list(feature_importance.keys())[0]}'." if feature_importance else
            f"Best model: {best_name}."
        ),
    }


def run_unsupervised(df: pd.DataFrame, numeric_cols: list[str]) -> dict:
    if len(numeric_cols) < 2:
        return {"error": "Need at least 2 numeric columns for clustering/PCA."}

    X = df[numeric_cols].dropna()
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # auto-pick k between 2 and 6 via silhouette score
    best_k, best_sil, best_labels = 2, -1, None
    for k in range(2, min(7, len(X))):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X_scaled)
        if len(set(labels)) < 2:
            continue
        sil = silhouette_score(X_scaled, labels)
        if sil > best_sil:
            best_k, best_sil, best_labels = k, sil, labels

    pca = PCA(n_components=2)
    coords = pca.fit_transform(X_scaled)
    plot_df = pd.DataFrame({"PC1": coords[:, 0], "PC2": coords[:, 1], "Cluster": best_labels.astype(str)})
    fig = px.scatter(plot_df, x="PC1", y="PC2", color="Cluster")
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")

    cluster_sizes = pd.Series(best_labels).value_counts().sort_index()

    return {
        "task_type": "clustering",
        "n_clusters": int(best_k),
        "silhouette_score": round(float(best_sil), 4),
        "cluster_sizes": {str(k): int(v) for k, v in cluster_sizes.items()},
        "pca_explained_variance": [round(float(v), 4) for v in pca.explained_variance_ratio_],
        "cluster_chart": json.loads(fig.to_json()),
        "summary": (
            f"Data naturally groups into {best_k} clusters (silhouette score {best_sil:.2f}). "
            f"The first 2 principal components explain "
            f"{sum(pca.explained_variance_ratio_)*100:.1f}% of total variance."
        ),
    }
