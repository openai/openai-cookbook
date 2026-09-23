from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

try:  # optional dependency
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore

try:  # optional dependency
    import plotly.express as px
    import plotly.graph_objects as go
except Exception:  # pragma: no cover
    px = None  # type: ignore
    go = None  # type: ignore

try:  # optional dependency
    import networkx as nx
except Exception:  # pragma: no cover
    nx = None  # type: ignore

try:  # optional dependency
    from sklearn.cluster import AgglomerativeClustering, DBSCAN
    from sklearn.decomposition import PCA, TruncatedSVD
    from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.preprocessing import normalize
except Exception:  # pragma: no cover
    AgglomerativeClustering = DBSCAN = PCA = TruncatedSVD = CountVectorizer = TfidfVectorizer = cosine_similarity = normalize = None  # type: ignore

try:  # optional dependency
    import hdbscan
except Exception:  # pragma: no cover
    hdbscan = None  # type: ignore

try:  # optional dependency
    import umap
except Exception:  # pragma: no cover
    umap = None  # type: ignore

try:  # optional dependency
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover
    SentenceTransformer = None  # type: ignore

from data_prep import (
    DEFAULT_DOC_COLUMNS,
    build_trace_documents,
    load_trace_tables,
    resolve_dataset_root,
    stack_document_views,
)

DEFAULT_RANDOM_STATE = 13
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_TOPIC_LABEL = "mixed operational pattern"
DEFAULT_CACHE_DIR = Path(".cache/macro_eval")
STATUS_ORDER = {
    "successful_completion": 0,
    "review_escalation": 1,
    "hard_failure": 2,
}
ROLE_HINTS = {
    "pricing": "pricing and offer",
    "compliance": "compliance",
    "buildability": "validation",
    "validation": "validation",
    "factory": "fulfillment",
    "routing": "fulfillment",
    "supplier": "supply",
    "supply": "supply",
    "escalation": "escalation",
    "clarification": "clarification",
    "human": "escalation",
    "review": "review",
}
FAILURE_LABEL_HINTS = [
    ("WHEEL_TRIM_CONFLICT", "wheel and trim mismatch"),
    ("BASE_MSRP_DRIFT", "pricing drift"),
    ("ESTIMATED_TOTAL_MISMATCH", "estimated total mismatch"),
    ("FULFILLMENT_REROUTE", "fulfillment reroute"),
    ("CUSTOMER_INTENT_AMBIGUOUS", "ambiguous customer intent"),
    ("SCHEDULE_DEFERRED", "schedule deferral"),
]
SEVERITY_BAND_COLORS = {
    "low": "#80b1d3",
    "medium": "#fdb462",
    "high": "#fb8072",
}
TOPIC_COLOR_SEQUENCE = [
    "#8dd3c7",
    "#fb8072",
    "#80b1d3",
    "#fdb462",
    "#b3de69",
    "#bc80bd",
    "#fccde5",
    "#bebada",
    "#66c2a5",
    "#fc8d62",
    "#8da0cb",
    "#e78ac3",
]
NODE_KIND_COLORS = {
    "status": "#80b1d3",
    "handoff": "#fdb462",
    "function": "#bebada",
    "response": "#8dd3c7",
    "tool": "#fb8072",
    "agent": "#bc80bd",
    "finding": "#b3de69",
    "default": "#bdbdbd",
}
STAGE_SHADES = {
    "early": "rgba(128, 177, 211, 0.12)",
    "middle": "rgba(253, 180, 98, 0.12)",
    "late": "rgba(251, 128, 114, 0.12)",
}
HIGHLIGHT_ACCENT = "#6a3d9a"
ANCHOR_ACCENT = "#d7301f"
OUTLINE_ACCENT = "#374151"


@dataclass
class EmbeddingBundle:
    embeddings: Any
    method: str
    vectorizer: Any = None
    reducer: Any = None


@dataclass
class TopicBundle:
    trace_topics: pd.DataFrame
    topic_keywords: pd.DataFrame
    topic_summary: pd.DataFrame
    documents_df: pd.DataFrame
    vectors: EmbeddingBundle
    reduced_embeddings: Any
    topic_assignments: pd.DataFrame


@dataclass
class MacroDiscoveryArtifacts:
    traces_df: pd.DataFrame
    events_df: pd.DataFrame
    documents_df: pd.DataFrame
    stacked_documents_df: pd.DataFrame
    topic_bundle: TopicBundle

    @property
    def trace_topics(self) -> pd.DataFrame:
        return self.topic_bundle.trace_topics

    @property
    def topic_keywords(self) -> pd.DataFrame:
        return self.topic_bundle.topic_keywords

    @property
    def topic_summary(self) -> pd.DataFrame:
        return self.topic_bundle.topic_summary

    @property
    def topic_assignments(self) -> pd.DataFrame:
        return self.topic_bundle.topic_assignments

    @property
    def trace_topic_df(self) -> pd.DataFrame:
        return self.trace_topics

    @property
    def topic_info_df(self) -> pd.DataFrame:
        return self.topic_summary


@dataclass
class TopicDrilldownArtifacts:
    topic_id: Any
    focus_topic: pd.Series
    topic_traces: pd.DataFrame
    representative_traces: pd.DataFrame
    topic_suspects: pd.DataFrame
    root_cause_cards: list[dict[str, Any]]
    graph_bundle: dict[str, Any] | None
    summary: str
    representative_trace_id: str | None = None
    anchor_node_id: str | None = None
    suspect_summary_df: pd.DataFrame | None = None
    trace_window_df: pd.DataFrame | None = None
    selected_path_nodes: list[dict[str, Any]] | None = None

    @property
    def cluster_suspects(self) -> pd.DataFrame:
        return self.topic_suspects

    @property
    def suspect_summary(self) -> pd.DataFrame:
        return (
            self.suspect_summary_df
            if isinstance(self.suspect_summary_df, pd.DataFrame)
            else pd.DataFrame()
        )

    @property
    def representative_graph(self) -> dict[str, Any] | None:
        return self.graph_bundle

    @property
    def representative_trace_window(self) -> pd.DataFrame:
        return (
            self.trace_window_df
            if isinstance(self.trace_window_df, pd.DataFrame)
            else pd.DataFrame()
        )

    @property
    def story_path_nodes(self) -> list[dict[str, Any]]:
        return self.selected_path_nodes or []

    @property
    def highlight_node_ids(self) -> list[str]:
        if self.selected_path_nodes:
            return [
                str(node["node_id"])
                for node in self.selected_path_nodes
                if node.get("node_id") is not None
            ]
        if self.topic_suspects.empty or "node_id" not in self.topic_suspects.columns:
            return []
        return self.topic_suspects["node_id"].dropna().astype(str).head(5).tolist()

    @property
    def cluster_card_markdown(self) -> str:
        return _build_cluster_card_markdown(
            self.focus_topic, self.topic_suspects, self.representative_traces
        )

    @property
    def root_cause_markdown(self) -> str:
        return _build_root_cause_markdown(
            self.focus_topic,
            (
                self.suspect_summary
                if not self.suspect_summary.empty
                else self.topic_suspects
            ),
            self.summary,
        )

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


def load_macro_eval_tables(
    dataset_root: str | Path | None = None,
    data_dir: str | Path = "data",
    limit: int | None = None,
    use_cache: bool = True,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    refresh_cache: bool = False,
    max_workers: int | None = None,
) -> dict[str, pd.DataFrame]:
    dataset_root = (
        Path(dataset_root) if dataset_root else resolve_dataset_root(data_dir)
    )
    cache_paths = _macro_eval_cache_paths(
        dataset_root, limit=limit, cache_dir=cache_dir
    )

    if use_cache and not refresh_cache and _macro_eval_cache_ready(cache_paths):
        return {name: pd.read_pickle(path) for name, path in cache_paths.items()}

    traces_df, events_df = load_trace_tables(
        dataset_root=dataset_root,
        data_dir=data_dir,
        limit=limit,
        max_workers=max_workers,
    )
    documents_df = build_trace_documents(traces_df, events_df)
    stacked_documents_df = stack_document_views(documents_df)
    tables = {
        "traces_df": traces_df,
        "events_df": events_df,
        "documents_df": documents_df,
        "stacked_documents_df": stacked_documents_df,
    }
    if use_cache:
        cache_paths["traces_df"].parent.mkdir(parents=True, exist_ok=True)
        for name, frame in tables.items():
            frame.to_pickle(cache_paths[name])
    return tables


def choose_document_view(
    documents_df: pd.DataFrame,
    doc_type: str = "doc_structured_summary",
    fallback_order: Sequence[str] = DEFAULT_DOC_COLUMNS,
) -> pd.DataFrame:
    if documents_df.empty:
        return documents_df.copy()
    preferred = doc_type if doc_type in documents_df.columns else None
    if preferred:
        cols = ["trace_id", preferred]
        for col in fallback_order:
            if col in documents_df.columns and col not in cols:
                cols.append(col)
        return documents_df.loc[:, cols].copy()
    for candidate in fallback_order:
        if candidate in documents_df.columns:
            return documents_df.loc[:, ["trace_id", candidate]].copy()
    raise KeyError("No recognized document column found in documents_df.")


def get_trace_corpus(
    documents_df: pd.DataFrame,
    doc_type: str = "doc_structured_summary",
    min_chars: int = 20,
) -> pd.DataFrame:
    doc_col = (
        doc_type
        if doc_type in documents_df.columns
        else _first_available_doc_column(documents_df)
    )
    keep_cols = ["trace_id", doc_col]
    for extra_col in ("anchor_event_id", "anchor_stage_label", "doc_type"):
        if extra_col in documents_df.columns:
            keep_cols.append(extra_col)
    corpus = documents_df.loc[
        :, [col for col in keep_cols if col in documents_df.columns]
    ].copy()
    corpus = corpus.rename(columns={doc_col: "document_text"})
    corpus["document_text"] = corpus["document_text"].fillna("").astype(str)
    corpus = corpus[corpus["document_text"].str.len() >= min_chars].reset_index(
        drop=True
    )
    corpus["document_length_chars"] = corpus["document_text"].str.len()
    corpus["document_length_tokens_est"] = (
        corpus["document_length_chars"].div(4).round().astype(int)
    )
    return corpus


def compute_dense_embeddings(
    texts: Sequence[str],
    method: str = "auto",
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    random_state: int = DEFAULT_RANDOM_STATE,
    max_features: int = 6000,
    n_components: int = 256,
) -> EmbeddingBundle:
    cleaned = [_clean_text(text) for text in texts]
    if method in {"auto", "sentence_transformer"} and SentenceTransformer is not None:
        try:
            model = SentenceTransformer(model_name)
            embeddings = model.encode(
                cleaned, normalize_embeddings=True, show_progress_bar=False
            )
            return EmbeddingBundle(
                embeddings=embeddings,
                method=f"sentence_transformer:{model_name}",
                vectorizer=model,
            )
        except Exception:
            if method == "sentence_transformer":
                raise

    if TfidfVectorizer is None or TruncatedSVD is None or normalize is None:
        raise RuntimeError(
            "scikit-learn is required for the fallback embedding pipeline."
        )

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        min_df=2,
        max_features=max_features,
    )
    tfidf = vectorizer.fit_transform(cleaned)
    if tfidf.shape[1] > 1:
        n_components = max(
            2, min(n_components, tfidf.shape[1] - 1, max(2, tfidf.shape[0] - 1))
        )
        svd = TruncatedSVD(n_components=n_components, random_state=random_state)
        embeddings = svd.fit_transform(tfidf)
        embeddings = normalize(embeddings)
        reducer = {"vectorizer": vectorizer, "svd": svd}
        return EmbeddingBundle(
            embeddings=embeddings, method="tfidf_svd", vectorizer=reducer
        )

    embeddings = tfidf.toarray()
    return EmbeddingBundle(
        embeddings=embeddings, method="tfidf_sparse", vectorizer=vectorizer
    )


def reduce_embeddings(
    embeddings: Any,
    method: str = "umap",
    n_components: int = 2,
    random_state: int = DEFAULT_RANDOM_STATE,
    n_neighbors: int = 15,
    min_dist: float = 0.05,
) -> tuple[Any, Any]:
    sample_count = len(embeddings) if hasattr(embeddings, "__len__") else 0

    if (
        umap is not None
        and method == "umap"
        and sample_count > max(n_components + 1, 3)
    ):
        effective_neighbors = min(max(2, n_neighbors), max(2, sample_count - 1))
        reducer = umap.UMAP(
            n_neighbors=effective_neighbors,
            min_dist=min_dist,
            n_components=n_components,
            metric="cosine",
            random_state=random_state,
        )
        reduced = reducer.fit_transform(embeddings)
        return reduced, reducer

    if PCA is None:
        raise RuntimeError("No dimensionality reduction backend is available.")
    reducer = PCA(n_components=n_components, random_state=random_state)
    reduced = reducer.fit_transform(embeddings)
    return reduced, reducer


def cluster_embeddings(
    embeddings: Any,
    min_cluster_size: int = 20,
    min_samples: int | None = None,
    clusterer: str = "hdbscan",
    eps: float | None = None,
) -> tuple[Any, dict[str, Any]]:
    if clusterer == "hdbscan" and hdbscan is not None:
        model = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric="euclidean",
            prediction_data=True,
        )
        labels = model.fit_predict(embeddings)
        return labels, {"clusterer": model, "kind": "hdbscan"}

    if DBSCAN is not None:
        if eps is None:
            eps = _estimate_dbscan_eps(embeddings)
        model = DBSCAN(eps=eps, min_samples=min_cluster_size)
        labels = model.fit_predict(embeddings)
        return labels, {"clusterer": model, "kind": "dbscan", "eps": eps}

    if AgglomerativeClustering is None:
        raise RuntimeError("No clustering backend is available.")
    model = AgglomerativeClustering(
        n_clusters=max(2, min(12, len(embeddings) // max(min_cluster_size, 1)))
    )
    labels = model.fit_predict(embeddings)
    return labels, {"clusterer": model, "kind": "agglomerative"}


def compute_topic_keywords(
    documents_df: pd.DataFrame,
    topic_column: str = "topic_id",
    document_column: str = "document_text",
    top_n: int = 10,
    min_df: int = 2,
    ngram_range: tuple[int, int] = (1, 2),
) -> pd.DataFrame:
    if documents_df.empty:
        return pd.DataFrame(
            columns=[topic_column, "keywords", "weights", "document_count"]
        )

    working = documents_df[[topic_column, document_column]].copy()
    working[document_column] = working[document_column].fillna("").astype(str)
    if CountVectorizer is None:
        raise RuntimeError("scikit-learn is required for keyword extraction.")
    vectorizer = CountVectorizer(
        stop_words="english", min_df=min_df, ngram_range=ngram_range
    )
    dtm = vectorizer.fit_transform(working[document_column])
    terms = vectorizer.get_feature_names_out()
    rows = []
    for topic_id, topic_docs in working.groupby(topic_column, sort=False):
        idx = topic_docs.index.to_list()
        if not idx:
            continue
        topic_matrix = dtm[idx]
        term_counts = topic_matrix.sum(axis=0).A1
        if term_counts.sum() == 0:
            continue
        topic_counts = topic_matrix.shape[0]
        tf = term_counts / term_counts.sum()
        doc_presence = (topic_matrix > 0).sum(axis=0).A1
        idf = (
            np.log((1 + working.shape[0]) / (1 + doc_presence)) + 1
            if np is not None
            else [1.0] * len(term_counts)
        )
        scores = tf * idf
        order = scores.argsort()[::-1][:top_n]
        rows.append(
            {
                topic_column: topic_id,
                "keywords": [terms[i] for i in order if scores[i] > 0],
                "weights": [float(scores[i]) for i in order if scores[i] > 0],
                "document_count": int(topic_counts),
            }
        )
    return pd.DataFrame(rows)


def build_topic_labels(
    topic_keywords: pd.DataFrame,
    representative_examples: pd.DataFrame | None = None,
    topic_column: str = "topic_id",
    keyword_column: str = "keywords",
    example_column: str = "representative_text",
) -> pd.DataFrame:
    rows = []
    example_map = {}
    if (
        representative_examples is not None
        and not representative_examples.empty
        and topic_column in representative_examples.columns
    ):
        example_map = (
            representative_examples.groupby(topic_column)[example_column]
            .apply(lambda series: [text for text in series if text])
            .to_dict()
        )
    for _, row in topic_keywords.iterrows():
        topic_id = row[topic_column]
        keywords = [str(x) for x in row.get(keyword_column, [])]
        label_short, label_long, owner = _label_from_keywords(
            keywords, example_map.get(topic_id, [])
        )
        rows.append(
            {
                topic_column: topic_id,
                "label_short": label_short,
                "label_long": label_long,
                "likely_owner": owner,
                "keywords": keywords,
            }
        )
    return pd.DataFrame(rows)


def assign_topics(
    traces_df: pd.DataFrame,
    documents_df: pd.DataFrame,
    doc_type: str = "doc_structured_summary",
    embedding_method: str = "auto",
    reducer: str = "umap",
    clusterer: str = "hdbscan",
    min_cluster_size: int = 20,
    random_state: int = DEFAULT_RANDOM_STATE,
    n_neighbors: int = 15,
    top_n_terms: int = 10,
) -> TopicBundle:
    corpus = get_trace_corpus(documents_df, doc_type=doc_type)
    embeddings = compute_dense_embeddings(
        corpus["document_text"].tolist(),
        method=embedding_method,
        random_state=random_state,
    )
    reduced, reducer_obj = reduce_embeddings(
        embeddings.embeddings,
        method=reducer,
        random_state=random_state,
        n_neighbors=n_neighbors,
    )
    topic_ids, cluster_meta = cluster_embeddings(
        reduced, min_cluster_size=min_cluster_size, clusterer=clusterer
    )
    topic_assignments = corpus.copy()
    topic_assignments["topic_id"] = topic_ids
    topic_assignments["is_noise"] = topic_assignments["topic_id"].eq(-1)
    topic_assignments["reduced_x"] = _safe_column(reduced, 0)
    topic_assignments["reduced_y"] = _safe_column(reduced, 1)
    topic_assignments = topic_assignments.merge(
        traces_df, on="trace_id", how="left", suffixes=("", "_trace")
    )
    topic_keywords = compute_topic_keywords(
        topic_assignments,
        topic_column="topic_id",
        document_column="document_text",
        top_n=top_n_terms,
    )
    representative_examples = select_representative_examples(topic_assignments)
    labels = build_topic_labels(
        topic_keywords, representative_examples=representative_examples
    )
    topic_summary = summarize_topics(topic_assignments, labels=labels)
    trace_topics = topic_assignments.merge(labels, on="topic_id", how="left")
    trace_topics["topic_label"] = trace_topics["label_short"].fillna(
        trace_topics["topic_id"].map(_noise_label)
    )
    return TopicBundle(
        trace_topics=trace_topics,
        topic_keywords=topic_keywords,
        topic_summary=topic_summary,
        documents_df=documents_df,
        vectors=embeddings,
        reduced_embeddings=reduced,
        topic_assignments=topic_assignments,
    )


def select_representative_examples(
    topic_assignments: pd.DataFrame,
    topic_column: str = "topic_id",
    doc_column: str = "document_text",
    top_k: int = 3,
) -> pd.DataFrame:
    rows = []
    for topic_id, group in topic_assignments.groupby(topic_column, sort=False):
        if group.empty:
            continue
        if group.shape[0] == 1:
            selected = group
        else:
            if {"reduced_x", "reduced_y"}.issubset(group.columns) and np is not None:
                center = group[["reduced_x", "reduced_y"]].mean(axis=0).to_numpy()
                coords = group[["reduced_x", "reduced_y"]].to_numpy()
                distances = np.linalg.norm(coords - center, axis=1)
                selected = group.iloc[np.argsort(distances)[:top_k]]
            else:
                selected = group.head(top_k)
        for _, row in selected.iterrows():
            rows.append(
                {
                    topic_column: topic_id,
                    "trace_id": row["trace_id"],
                    "representative_text": row[doc_column],
                    "topic_score": float(
                        row.get("topic_prob", 1.0)
                        if pd.notna(row.get("topic_prob", 1.0))
                        else 1.0
                    ),
                }
            )
    return pd.DataFrame(rows)


def summarize_topics(
    topic_assignments: pd.DataFrame,
    labels: pd.DataFrame | None = None,
    topic_column: str = "topic_id",
) -> pd.DataFrame:
    if topic_assignments.empty:
        return pd.DataFrame(columns=[topic_column])

    summary = (
        topic_assignments.groupby(topic_column)
        .agg(
            document_count=("trace_id", "count"),
            trace_count=("trace_id", "nunique"),
            severity_weighted_prevalence=("severity_weight", "mean"),
            avg_loop_count=("loop_count", "mean"),
            avg_retry_count=("retry_count", "mean"),
            avg_arbitration_count=("arbitration_count", "mean"),
            noise_share=("is_noise", "mean"),
            dominant_scenario_family=(
                "scenario_family",
                lambda s: s.mode().iloc[0] if not s.mode().empty else None,
            ),
            dominant_topology_id=(
                "topology_id",
                lambda s: s.mode().iloc[0] if not s.mode().empty else None,
            ),
            dominant_customer_region=(
                "customer_region",
                lambda s: s.mode().iloc[0] if not s.mode().empty else None,
            ),
        )
        .reset_index()
    )
    summary["prevalence_share"] = (
        summary["document_count"] / summary["document_count"].sum()
    )
    summary["prevalence"] = summary["prevalence_share"]
    summary["impact_score"] = summary["prevalence_share"] * summary[
        "severity_weighted_prevalence"
    ].fillna(1.0)
    if labels is not None and not labels.empty:
        summary = summary.merge(
            labels[
                [topic_column, "label_short", "label_long", "likely_owner", "keywords"]
            ],
            on=topic_column,
            how="left",
        )
    else:
        summary["label_short"] = summary[topic_column].map(_noise_label)
        summary["label_long"] = summary["label_short"]
        summary["likely_owner"] = "orchestration owner"
        summary["keywords"] = [[] for _ in range(len(summary))]
    summary["topic_label"] = summary["label_short"].fillna(
        summary[topic_column].map(_noise_label)
    )
    summary["dominant_owner"] = summary["likely_owner"].fillna("orchestration owner")
    summary["keywords_text"] = summary["keywords"].apply(
        lambda values: ", ".join(values) if isinstance(values, list) else ""
    )
    return summary.sort_values(
        ["impact_score", "document_count"], ascending=False
    ).reset_index(drop=True)


def slice_topics_by_metadata(
    topic_assignments: pd.DataFrame,
    group_columns: str | Sequence[str],
    topic_column: str = "topic_id",
    normalize: bool = True,
    top_n_slices: int | None = None,
) -> pd.DataFrame:
    if topic_assignments.empty:
        return pd.DataFrame()
    working = topic_assignments.copy()
    if isinstance(group_columns, str):
        group_columns = [group_columns]
    cols = [c for c in group_columns if c in working.columns]
    if not cols:
        raise KeyError(
            "None of the requested group columns exist in topic_assignments."
        )
    grouped = working.groupby(cols + [topic_column]).size().reset_index(name="count")
    grouped = _attach_topic_label(grouped, working, topic_column)
    if top_n_slices is not None and len(cols) == 1:
        top_values = (
            working[cols[0]]
            .fillna("missing")
            .astype(str)
            .value_counts()
            .head(top_n_slices)
            .index.tolist()
        )
        grouped = grouped[grouped[cols[0]].astype(str).isin(top_values)].copy()
    if not normalize:
        return grouped
    totals = working.groupby(cols).size().reset_index(name="group_total")
    grouped = grouped.merge(totals, on=cols, how="left")
    grouped["trace_count"] = grouped["count"]
    grouped["share"] = grouped["count"] / grouped["group_total"]
    grouped["slice_share"] = grouped["share"]
    grouped["topic_share_within_slice"] = grouped["share"]
    if len(cols) == 1:
        grouped["slice_value"] = grouped[cols[0]]
        baseline = (
            working.groupby(topic_column)
            .size()
            .div(len(working))
            .rename("global_prevalence")
            .reset_index()
        )
        grouped = grouped.merge(baseline, on=topic_column, how="left")
        grouped["lift"] = grouped["share"] / grouped["global_prevalence"].replace(
            0, pd.NA
        )
    return grouped.sort_values("share", ascending=False).reset_index(drop=True)


def topics_over_time(
    topic_assignments: pd.DataFrame,
    time_column: str = "simulation_date",
    topic_column: str = "topic_id",
    freq: str = "W",
    use_stage_index: bool = False,
) -> pd.DataFrame:
    if topic_assignments.empty:
        return pd.DataFrame()
    working = topic_assignments.copy()
    if use_stage_index and "stage_label" in working.columns:
        time_column = "stage_label"
    if time_column not in working.columns:
        raise KeyError(f"Missing time column {time_column!r}.")

    if use_stage_index:
        grouped = (
            working.groupby([time_column, topic_column])
            .size()
            .reset_index(name="count")
        )
        grouped = _attach_topic_label(grouped, working, topic_column)
        totals = working.groupby(time_column).size().reset_index(name="total")
        result = grouped.merge(totals, on=time_column, how="left")
        result["trace_count"] = result["count"]
        result["share"] = result["count"] / result["total"]
        result["slice_share"] = result["share"]
        return result.sort_values(
            [time_column, "share"], ascending=[True, False]
        ).reset_index(drop=True)

    working[time_column] = pd.to_datetime(working[time_column], errors="coerce")
    working = working[working[time_column].notna()].copy()
    working["time_bin"] = working[time_column].dt.to_period(freq).dt.start_time
    grouped = (
        working.groupby(["time_bin", topic_column]).size().reset_index(name="count")
    )
    grouped = _attach_topic_label(grouped, working, topic_column)
    totals = working.groupby("time_bin").size().reset_index(name="total")
    result = grouped.merge(totals, on="time_bin", how="left")
    result["trace_count"] = result["count"]
    result["share"] = result["count"] / result["total"]
    result["slice_share"] = result["share"]
    return result.sort_values(
        ["time_bin", "share"], ascending=[True, False]
    ).reset_index(drop=True)


def topics_by_stage(
    topic_assignments: pd.DataFrame,
    stage_column: str = "anchor_stage_label",
    topic_column: str = "topic_id",
    normalize: bool = True,
) -> pd.DataFrame:
    if topic_assignments.empty:
        return pd.DataFrame()
    working = topic_assignments.copy()
    if stage_column not in working.columns:
        stage_column = (
            "stage_label" if "stage_label" in working.columns else stage_column
        )
    if stage_column not in working.columns:
        raise KeyError(f"Missing stage column {stage_column!r}.")
    grouped = (
        working.groupby([stage_column, topic_column]).size().reset_index(name="count")
    )
    grouped = _attach_topic_label(grouped, working, topic_column)
    if not normalize:
        return grouped.sort_values(["count"], ascending=False).reset_index(drop=True)
    totals = working.groupby(stage_column).size().reset_index(name="total")
    result = grouped.merge(totals, on=stage_column, how="left")
    result["trace_count"] = result["count"]
    result["share"] = result["count"] / result["total"]
    result["slice_share"] = result["share"]
    result["stage_bucket"] = result[stage_column]
    return result.sort_values(
        [stage_column, "share"], ascending=[True, False]
    ).reset_index(drop=True)


def build_execution_graph(
    trace_events: pd.DataFrame,
    trace_row: pd.Series | None = None,
) -> dict[str, Any]:
    nodes = _execution_nodes(trace_events, trace_row=trace_row)
    edges = _execution_edges(nodes)
    graph = None
    if nx is not None:
        graph = nx.DiGraph()
        for node in nodes:
            graph.add_node(node["node_id"], **node)
        for edge in edges:
            graph.add_edge(edge["source"], edge["target"], **edge)
    return {"nodes": nodes, "edges": edges, "graph": graph}


def rank_upstream_suspects(
    trace_events: pd.DataFrame,
    failure_anchor_id: str | None = None,
    trace_row: pd.Series | None = None,
    max_hops: int = 3,
) -> pd.DataFrame:
    if trace_events.empty:
        return pd.DataFrame(columns=["candidate", "score"])

    graph_bundle = build_execution_graph(trace_events, trace_row=trace_row)
    nodes = pd.DataFrame(graph_bundle["nodes"])
    edges = pd.DataFrame(graph_bundle["edges"])
    if nodes.empty:
        return pd.DataFrame(columns=["candidate", "score"])

    failure_node = None
    if failure_anchor_id is not None and "node_id" in nodes.columns:
        subset = nodes[nodes["node_id"].eq(failure_anchor_id)]
        if not subset.empty:
            failure_node = subset.iloc[0]
    if failure_node is None:
        failure_candidates = nodes[nodes["is_failure_marker"].fillna(False)]
        if not failure_candidates.empty:
            failure_node = failure_candidates.sort_values(
                ["sequence_index", "depth"], ascending=[False, False]
            ).iloc[0]
    if failure_node is None:
        failure_node = nodes.sort_values(
            ["sequence_index", "depth"], ascending=[False, False]
        ).iloc[0]

    candidates = []
    predecessor_map = _predecessor_map(edges)
    frontier = {failure_node["node_id"]}
    seen = {failure_node["node_id"]}
    for hop in range(1, max_hops + 1):
        next_frontier = set()
        for node_id in frontier:
            for parent in predecessor_map.get(node_id, []):
                if parent in seen:
                    continue
                seen.add(parent)
                next_frontier.add(parent)
                node = nodes[nodes["node_id"].eq(parent)].iloc[0]
                candidates.append(
                    {
                        "candidate": node["label"],
                        "short_label": node.get("short_label") or node["label"],
                        "node_id": parent,
                        "node_kind": node["node_kind"],
                        "agent_name": node["agent_name"],
                        "tool_name": node.get("tool_name"),
                        "lane_label": node.get("lane_label"),
                        "hop_distance": hop,
                        "sequence_index": node["sequence_index"],
                        "stage_label": node["stage_label"],
                        "score_proximity": 1.0 / hop,
                        "score_frequency": _candidate_frequency_weight(node, nodes),
                        "score_bridge": _candidate_bridge_weight(node, edges),
                        "score_role": _candidate_role_weight(node),
                        "is_failure_marker": bool(node.get("is_failure_marker")),
                    }
                )
        frontier = next_frontier
        if not frontier:
            break

    suspects = pd.DataFrame(candidates)
    if suspects.empty:
        return suspects
    suspects["score"] = (
        suspects["score_proximity"] * 0.4
        + suspects["score_frequency"] * 0.3
        + suspects["score_bridge"] * 0.2
        + suspects["score_role"] * 0.1
    )
    suspects = suspects.sort_values(
        ["score", "hop_distance", "sequence_index"], ascending=[False, True, True]
    ).reset_index(drop=True)
    return suspects


def root_cause_drilldown(
    trace_row: pd.Series,
    trace_events: pd.DataFrame,
    max_hops: int = 3,
) -> dict[str, Any]:
    graph_bundle = build_execution_graph(trace_events, trace_row=trace_row)
    suspects = rank_upstream_suspects(
        trace_events, trace_row=trace_row, max_hops=max_hops
    )
    top_suspects = suspects.head(5)
    anchor = _failure_anchor_node(pd.DataFrame(graph_bundle["nodes"]))
    summary = _build_root_cause_summary(trace_row, anchor, top_suspects)
    return {
        "trace_id": trace_row["trace_id"],
        "summary": summary,
        "failure_anchor": anchor,
        "anchor_node_id": None if anchor is None else anchor.get("node_id"),
        "suspects": suspects,
        "graph": graph_bundle,
    }


def _node_frame_from_bundle(graph_bundle: dict[str, Any] | None) -> pd.DataFrame:
    if graph_bundle is None:
        return pd.DataFrame()
    nodes = pd.DataFrame(graph_bundle.get("nodes", []))
    if nodes.empty:
        return nodes
    sort_cols = [col for col in ("sequence_index", "depth") if col in nodes.columns]
    if sort_cols:
        nodes = nodes.sort_values(sort_cols).reset_index(drop=True)
    return nodes


def _edge_frame_from_bundle(graph_bundle: dict[str, Any] | None) -> pd.DataFrame:
    if graph_bundle is None:
        return pd.DataFrame()
    return pd.DataFrame(graph_bundle.get("edges", []))


def _ordered_trace_ids(
    topic_traces: pd.DataFrame, representative_traces: pd.DataFrame, max_traces: int
) -> list[str]:
    representative_ids = (
        representative_traces["trace_id"].dropna().astype(str).tolist()
        if not representative_traces.empty
        and "trace_id" in representative_traces.columns
        else []
    )
    all_ids = topic_traces["trace_id"].dropna().astype(str).tolist()
    ordered: list[str] = []
    for trace_id in representative_ids + all_ids:
        if trace_id not in ordered:
            ordered.append(trace_id)
        if len(ordered) >= max_traces:
            break
    return ordered


def _summarize_cluster_suspects(
    topic_suspects: pd.DataFrame, trace_count: int
) -> pd.DataFrame:
    if topic_suspects.empty:
        return pd.DataFrame(
            columns=[
                "suspect_label",
                "node_kind",
                "agent_name",
                "tool_name",
                "lane_label",
                "mean_score",
                "traces_covered",
                "trace_coverage_share",
                "mean_hop_distance",
                "trace_mentions",
            ]
        )
    working = topic_suspects.copy()
    if "short_label" not in working.columns:
        working["short_label"] = working["candidate"]
    if "lane_label" not in working.columns:
        working["lane_label"] = working.apply(_lane_label, axis=1)
    group_cols = [
        "short_label",
        "node_kind",
        "agent_name",
        "tool_name",
        "lane_label",
    ]
    summary = (
        working.groupby(group_cols, dropna=False)
        .agg(
            mean_score=("score", "mean"),
            traces_covered=("trace_id", "nunique"),
            trace_mentions=("trace_id", "size"),
            mean_hop_distance=("hop_distance", "mean"),
            mean_sequence_index=("sequence_index", "mean"),
        )
        .reset_index()
        .rename(columns={"short_label": "suspect_label"})
    )
    denom = max(trace_count, 1)
    summary["trace_coverage_share"] = summary["traces_covered"] / denom
    summary["display_label"] = summary["suspect_label"].apply(
        lambda value: _truncate_text(value, width=42)
    )
    summary["owner_label"] = summary.apply(
        lambda row: _clean_text(row["agent_name"])
        or _clean_text(row["tool_name"])
        or _clean_text(row["lane_label"])
        or _clean_text(row["node_kind"])
        or "event",
        axis=1,
    )
    return summary.sort_values(
        ["mean_score", "traces_covered", "mean_hop_distance"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def _extract_path_nodes(
    graph_bundle: dict[str, Any] | None,
    suspect_node_id: str | None,
    anchor_node_id: str | None,
) -> list[dict[str, Any]]:
    nodes = _node_frame_from_bundle(graph_bundle)
    if nodes.empty or not suspect_node_id or not anchor_node_id:
        return []
    node_lookup = {
        str(row["node_id"]): row.to_dict()
        for _, row in nodes.iterrows()
        if pd.notna(row.get("node_id"))
    }
    if suspect_node_id not in node_lookup or anchor_node_id not in node_lookup:
        return []

    path: list[str] = []
    graph = None if graph_bundle is None else graph_bundle.get("graph")
    if nx is not None and graph is not None:
        try:
            path = [
                str(node_id)
                for node_id in nx.shortest_path(graph, suspect_node_id, anchor_node_id)
            ]
        except Exception:
            path = []
    if not path:
        edges = _edge_frame_from_bundle(graph_bundle)
        successors: dict[str, list[str]] = {}
        for _, edge in edges.iterrows():
            successors.setdefault(str(edge["source"]), []).append(str(edge["target"]))
        current = str(suspect_node_id)
        path = [current]
        seen = {current}
        while current != str(anchor_node_id):
            next_nodes = successors.get(current, [])
            if not next_nodes:
                break
            current = next_nodes[0]
            if current in seen:
                break
            seen.add(current)
            path.append(current)
    ordered_nodes = [node_lookup[node_id] for node_id in path if node_id in node_lookup]
    return sorted(ordered_nodes, key=lambda row: row.get("sequence_index", 0))


def _anchor_centered_window(
    graph_bundle: dict[str, Any] | None,
    anchor_node_id: str | None,
    window_before: int = 6,
    window_after: int = 6,
) -> pd.DataFrame:
    nodes = _node_frame_from_bundle(graph_bundle)
    if nodes.empty:
        return nodes
    if anchor_node_id is not None and "node_id" in nodes.columns:
        anchor_rows = nodes[nodes["node_id"].astype(str).eq(str(anchor_node_id))]
    else:
        anchor_rows = pd.DataFrame()
    if anchor_rows.empty:
        anchor = _failure_anchor_node(nodes)
        anchor_node_id = None if anchor is None else str(anchor.get("node_id"))
        anchor_rows = (
            nodes[nodes["node_id"].astype(str).eq(str(anchor_node_id))]
            if anchor_node_id is not None
            else pd.DataFrame()
        )
    if anchor_rows.empty:
        window = nodes.copy()
        anchor_sequence = int(window["sequence_index"].max())
    else:
        anchor_sequence = int(anchor_rows.iloc[0]["sequence_index"])
        lower = anchor_sequence - window_before
        upper = anchor_sequence + window_after
        window = nodes[nodes["sequence_index"].between(lower, upper)].copy()
        if window.empty:
            window = nodes.copy()
    window["is_anchor"] = (
        window["node_id"].astype(str).eq(str(anchor_node_id))
        if anchor_node_id is not None
        else False
    )
    window["relative_sequence"] = window["sequence_index"] - anchor_sequence
    return window.reset_index(drop=True)


def run_macro_discovery(
    source: pd.DataFrame | str | Path | None = None,
    dataset_root: str | Path | None = None,
    data_dir: str | Path = "data",
    limit: int | None = None,
    document_column: str | None = None,
    doc_type: str = "doc_structured_summary",
    embedding_method: str = "auto",
    reducer: str = "umap",
    clusterer: str = "hdbscan",
    min_cluster_size: int = 20,
    random_state: int = DEFAULT_RANDOM_STATE,
    n_neighbors: int = 15,
    top_n_terms: int = 10,
    failure_only: bool = False,
) -> MacroDiscoveryArtifacts:
    if isinstance(source, pd.DataFrame):
        traces_df = source.copy()
        if failure_only and "has_failure" in traces_df.columns:
            traces_df = traces_df[traces_df["has_failure"]].copy()
        doc_type = document_column or doc_type or _first_available_doc_column(traces_df)
        doc_columns = [col for col in DEFAULT_DOC_COLUMNS if col in traces_df.columns]
        if doc_type not in traces_df.columns:
            raise KeyError(
                f"Document column {doc_type!r} not found in source dataframe."
            )
        documents_df = traces_df.loc[
            :, ["trace_id", doc_type, *(col for col in doc_columns if col != doc_type)]
        ].copy()
        for extra_col in ("anchor_event_id", "anchor_stage_label"):
            if extra_col in traces_df.columns and extra_col not in documents_df.columns:
                documents_df[extra_col] = traces_df[extra_col]
        topic_bundle = assign_topics(
            traces_df,
            documents_df,
            doc_type=doc_type,
            embedding_method=embedding_method,
            reducer=reducer,
            clusterer=clusterer,
            min_cluster_size=min_cluster_size,
            random_state=random_state,
            n_neighbors=n_neighbors,
            top_n_terms=top_n_terms,
        )
        return MacroDiscoveryArtifacts(
            traces_df=traces_df,
            events_df=pd.DataFrame(),
            documents_df=documents_df,
            stacked_documents_df=pd.DataFrame(),
            topic_bundle=topic_bundle,
        )

    if source is not None and dataset_root is None:
        dataset_root = source

    tables = load_macro_eval_tables(
        dataset_root=dataset_root, data_dir=data_dir, limit=limit
    )
    if failure_only:
        failure_trace_ids = tables["traces_df"].loc[
            tables["traces_df"]["has_failure"], "trace_id"
        ]
        tables["traces_df"] = tables["traces_df"][
            tables["traces_df"]["trace_id"].isin(failure_trace_ids)
        ].copy()
        tables["documents_df"] = tables["documents_df"][
            tables["documents_df"]["trace_id"].isin(failure_trace_ids)
        ].copy()
        tables["events_df"] = tables["events_df"][
            tables["events_df"]["trace_id"].isin(failure_trace_ids)
        ].copy()

    doc_type = document_column or doc_type
    topic_bundle = assign_topics(
        tables["traces_df"],
        tables["documents_df"],
        doc_type=doc_type,
        embedding_method=embedding_method,
        reducer=reducer,
        clusterer=clusterer,
        min_cluster_size=min_cluster_size,
        random_state=random_state,
        n_neighbors=n_neighbors,
        top_n_terms=top_n_terms,
    )
    return MacroDiscoveryArtifacts(
        traces_df=tables["traces_df"],
        events_df=tables["events_df"],
        documents_df=tables["documents_df"],
        stacked_documents_df=tables["stacked_documents_df"],
        topic_bundle=topic_bundle,
    )


def pick_focus_topic(
    topic_summary: pd.DataFrame,
    by: str = "impact_score",
    exclude_noise: bool = True,
    topic_id: Any | None = None,
) -> pd.Series:
    if topic_summary.empty:
        raise ValueError("topic_summary is empty.")
    full_summary = topic_summary.copy()
    working = full_summary
    if exclude_noise and "topic_id" in working.columns:
        working = working[working["topic_id"].ne(-1)]
    if topic_id is not None:
        selection = full_summary[full_summary["topic_id"].eq(topic_id)]
        if selection.empty:
            raise KeyError(f"Topic {topic_id!r} not found.")
        return selection.iloc[0]
    if working.empty:
        working = full_summary
    if by not in working.columns:
        raise KeyError(f"Column {by!r} not found in topic_summary.")
    return working.sort_values(by, ascending=False).iloc[0]


def drill_down_topic_root_causes(
    discovery: MacroDiscoveryArtifacts | TopicBundle | dict[str, Any] | pd.DataFrame,
    events_df: pd.DataFrame | None = None,
    topic_id: Any | None = None,
    max_traces: int = 8,
    max_hops: int = 3,
    top_n_traces: int | None = None,
    max_depth: int | None = None,
) -> TopicDrilldownArtifacts:
    if top_n_traces is not None:
        max_traces = top_n_traces
    if max_depth is not None:
        max_hops = max_depth

    if isinstance(discovery, pd.DataFrame):
        topic_assignments = discovery.copy()
        if events_df is None:
            raise TypeError(
                "events_df is required when passing a topic-assignment dataframe directly."
            )
        labels = None
        if "label_short" in topic_assignments.columns:
            labels = (
                topic_assignments.groupby("topic_id")[
                    ["label_short", "label_long", "likely_owner"]
                ]
                .first()
                .reset_index()
            )
            if "keywords" in topic_assignments.columns:
                labels["keywords"] = (
                    topic_assignments.groupby("topic_id")["keywords"]
                    .first()
                    .reindex(labels["topic_id"])
                    .tolist()
                )
            else:
                labels["keywords"] = [[] for _ in range(len(labels))]
        topic_summary = summarize_topics(topic_assignments, labels=labels)
        traces_df = topic_assignments
    else:
        topic_summary, topic_assignments, traces_df, derived_events = (
            _coerce_discovery_inputs(discovery)
        )
        if events_df is None:
            events_df = derived_events

    if events_df is None:
        raise TypeError("events_df is required for topic drilldown.")

    focus_topic = pick_focus_topic(topic_summary, topic_id=topic_id)
    selected_topic_id = focus_topic["topic_id"]
    topic_traces = topic_assignments[
        topic_assignments["topic_id"].eq(selected_topic_id)
    ].copy()
    sort_columns = [
        column
        for column in ("impact_score", "severity_weight", "document_length_chars")
        if column in topic_traces.columns
    ]
    if sort_columns:
        topic_traces = topic_traces.sort_values(
            sort_columns, ascending=[False] * len(sort_columns)
        )
    representative_traces = select_representative_examples(
        topic_traces, top_k=max_traces
    )

    root_cause_cards: list[dict[str, Any]] = []
    trace_suspect_tables = []
    trace_drilldowns: dict[str, dict[str, Any]] = {}
    ordered_trace_ids = _ordered_trace_ids(
        topic_traces, representative_traces, max_traces=max_traces
    )
    topic_trace_lookup = {
        str(row["trace_id"]): row for _, row in topic_traces.iterrows()
    }
    for trace_id in ordered_trace_ids:
        row = topic_trace_lookup.get(str(trace_id))
        if row is None:
            continue
        trace_events = events_df[events_df["trace_id"].eq(trace_id)].copy()
        if trace_events.empty:
            continue
        drilldown = root_cause_drilldown(row, trace_events, max_hops=max_hops)
        trace_drilldowns[str(trace_id)] = drilldown
        trace_suspect_tables.append(
            drilldown["suspects"]
            .head(10)
            .assign(trace_id=trace_id, topic_id=selected_topic_id)
        )
        root_cause_cards.append(
            {
                "trace_id": trace_id,
                "summary": drilldown["summary"],
                "top_suspect": (
                    None
                    if drilldown["suspects"].empty
                    else drilldown["suspects"].iloc[0].to_dict()
                ),
            }
        )

    topic_suspects = (
        pd.concat(trace_suspect_tables, ignore_index=True)
        if trace_suspect_tables
        else pd.DataFrame()
    )
    suspect_summary_df = _summarize_cluster_suspects(
        topic_suspects, trace_count=max(len(trace_drilldowns), 1)
    )
    representative_trace_id = next(iter(trace_drilldowns.keys()), None)
    for candidate_trace_id in (
        representative_traces["trace_id"].dropna().astype(str).tolist()
        if not representative_traces.empty
        and "trace_id" in representative_traces.columns
        else []
    ):
        if candidate_trace_id in trace_drilldowns:
            representative_trace_id = candidate_trace_id
            break
    representative_drilldown = (
        trace_drilldowns.get(representative_trace_id)
        if representative_trace_id is not None
        else None
    )
    graph_bundle = (
        representative_drilldown.get("graph") if representative_drilldown else None
    )
    anchor_node_id = (
        representative_drilldown.get("anchor_node_id")
        if representative_drilldown
        else None
    )
    selected_path_nodes: list[dict[str, Any]] = []
    if representative_drilldown and not representative_drilldown["suspects"].empty:
        representative_suspects = representative_drilldown["suspects"].copy()
        family_top_label = (
            suspect_summary_df.iloc[0]["suspect_label"]
            if not suspect_summary_df.empty
            else None
        )
        if (
            family_top_label is not None
            and "short_label" in representative_suspects.columns
        ):
            matching = representative_suspects[
                representative_suspects["short_label"]
                .astype(str)
                .eq(str(family_top_label))
            ]
        else:
            matching = pd.DataFrame()
        selected_suspect = (
            matching.iloc[0] if not matching.empty else representative_suspects.iloc[0]
        )
        selected_path_nodes = _extract_path_nodes(
            graph_bundle,
            suspect_node_id=str(selected_suspect["node_id"]),
            anchor_node_id=None if anchor_node_id is None else str(anchor_node_id),
        )
    trace_window_df = _anchor_centered_window(graph_bundle, anchor_node_id)
    summary = _compose_topic_root_cause_summary(
        focus_topic, topic_suspects, representative_traces
    )
    return TopicDrilldownArtifacts(
        topic_id=selected_topic_id,
        focus_topic=focus_topic,
        topic_traces=topic_traces,
        representative_traces=representative_traces,
        topic_suspects=topic_suspects,
        root_cause_cards=root_cause_cards,
        graph_bundle=graph_bundle,
        summary=summary,
        representative_trace_id=representative_trace_id,
        anchor_node_id=None if anchor_node_id is None else str(anchor_node_id),
        suspect_summary_df=suspect_summary_df,
        trace_window_df=trace_window_df,
        selected_path_nodes=selected_path_nodes,
    )


def plot_topic_leaderboard(
    topic_summary: pd.DataFrame,
    topic_label_col: str = "topic_label",
    impact_col: str = "impact_score",
    count_col: str = "trace_count",
    top_n: int | None = None,
):
    _require_plotly()
    if topic_summary.empty:
        return go.Figure()
    if (
        topic_label_col not in topic_summary.columns
        and "label_short" in topic_summary.columns
    ):
        topic_label_col = "label_short"
    if (
        count_col not in topic_summary.columns
        and "document_count" in topic_summary.columns
    ):
        count_col = "document_count"
    df = topic_summary.copy()
    if impact_col not in df.columns:
        raise KeyError(f"Missing impact column {impact_col!r}.")
    severity_values = (
        pd.to_numeric(df["severity_weighted_prevalence"], errors="coerce")
        if "severity_weighted_prevalence" in df.columns
        else pd.to_numeric(df[impact_col], errors="coerce")
    )
    severity_rank = severity_values.rank(method="average", pct=True)
    df["severity_band"] = "medium"
    df.loc[severity_rank <= 0.34, "severity_band"] = "low"
    df.loc[severity_rank >= 0.67, "severity_band"] = "high"
    df["display_label"] = df[topic_label_col].fillna(df.get("label_short")).astype(str)
    owner_source = (
        df["dominant_owner"]
        if "dominant_owner" in df.columns
        else pd.Series("orchestration owner", index=df.index)
    )
    df["owner_label"] = owner_source.fillna("orchestration owner")
    if count_col not in df.columns:
        df[count_col] = 0
    if top_n is not None:
        df = df.sort_values(impact_col, ascending=False).head(top_n)
    else:
        df = df.sort_values(impact_col, ascending=False)
    prevalence_source = (
        df["prevalence"]
        if "prevalence" in df.columns
        else pd.Series(index=df.index, dtype=float)
    )
    df["prevalence_text"] = prevalence_source.apply(
        lambda value: f"{float(value):.1%}" if pd.notna(value) else "n/a"
    )
    df["count_text"] = (
        pd.to_numeric(df[count_col], errors="coerce").fillna(0).astype(int).astype(str)
        + " traces"
    )
    df["bar_text"] = (
        df["prevalence_text"] + " | " + df["count_text"] + " | " + df["owner_label"]
    )
    df = df.sort_values(impact_col, ascending=True)
    fig = px.bar(
        df,
        x=impact_col,
        y="display_label",
        color="severity_band",
        orientation="h",
        title="Failure families by weighted impact",
        category_orders={"severity_band": ["low", "medium", "high"]},
        color_discrete_map=SEVERITY_BAND_COLORS,
    )
    fig.update_traces(
        text=df["bar_text"],
        textposition="outside",
        marker_line=dict(width=0.9, color=OUTLINE_ACCENT),
        customdata=df[
            ["prevalence_text", count_col, "owner_label", "severity_band"]
        ].to_numpy(),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Weighted impact: %{x:.3f}<br>"
            "Prevalence: %{customdata[0]}<br>"
            "Trace count: %{customdata[1]}<br>"
            "Likely owner: %{customdata[2]}<br>"
            "Severity band: %{customdata[3]}<extra></extra>"
        ),
        cliponaxis=False,
    )
    fig.update_layout(
        height=max(420, 34 * len(df)),
        margin=dict(l=20, r=220, t=60, b=30),
        legend_title_text="Severity-weighted prevalence",
    )
    fig.update_xaxes(title="Weighted impact")
    fig.update_yaxes(title="")
    return fig


def plot_topic_heatmap(
    slice_df: pd.DataFrame,
    row_col: str = "topic_label",
    col_col: str = "topology_id",
    value_col: str = "lift",
    title: str = "Topic prevalence by cohort",
    slice_column: str | None = None,
    top_n_rows: int | None = 8,
    top_n_cols: int | None = 8,
):
    _require_plotly()
    if slice_df.empty:
        return go.Figure()
    if slice_column is not None:
        col_col = slice_column
    if value_col not in slice_df.columns:
        if "lift" in slice_df.columns:
            value_col = "lift"
        elif "slice_share" in slice_df.columns:
            value_col = "slice_share"
    working = slice_df.copy()
    if top_n_rows is not None and row_col in working.columns:
        row_scores = (
            working.groupby(row_col)[value_col]
            .apply(
                lambda series: (
                    series.abs().max() if value_col == "lift" else series.mean()
                )
            )
            .sort_values(ascending=False)
            .head(top_n_rows)
            .index
        )
        working = working[working[row_col].isin(row_scores)].copy()
    if top_n_cols is not None and col_col in working.columns:
        col_scores = (
            working.groupby(col_col)["trace_count"]
            .sum()
            .sort_values(ascending=False)
            .head(top_n_cols)
            .index
            if "trace_count" in working.columns
            else working[col_col].astype(str).value_counts().head(top_n_cols).index
        )
        working = working[working[col_col].isin(col_scores)].copy()
    pivot = working.pivot_table(
        index=row_col, columns=col_col, values=value_col, aggfunc="mean", fill_value=0
    )
    if pivot.empty:
        return go.Figure()
    text_auto = ".2f" if pivot.shape[0] * pivot.shape[1] <= 64 else False
    midpoint = 1.0 if value_col == "lift" else 0.0
    heatmap_title = (
        "Failure family concentration by cohort" if value_col == "lift" else title
    )
    fig = px.imshow(
        pivot,
        aspect="auto",
        color_continuous_scale="BrBG",
        color_continuous_midpoint=midpoint,
        text_auto=text_auto,
        title=heatmap_title,
    )
    fig.update_layout(
        height=max(420, 34 * len(pivot.index)),
        margin=dict(l=20, r=20, t=60, b=100),
        coloraxis_colorbar=dict(
            title="Lift vs overall" if value_col == "lift" else "Share"
        ),
    )
    fig.update_xaxes(title="", tickangle=-35)
    fig.update_yaxes(title="")
    return fig


def plot_topic_trend(
    trend_df: pd.DataFrame,
    topic_label_col: str = "topic_label",
    time_col: str = "time_bin",
    share_col: str = "share",
    top_n: int = 5,
    x_column: str | None = None,
    value_column: str | None = None,
):
    _require_plotly()
    if trend_df.empty:
        return go.Figure()
    if x_column is not None:
        time_col = x_column
    if value_column is not None:
        share_col = value_column
    if share_col not in trend_df.columns and "slice_share" in trend_df.columns:
        share_col = "slice_share"
    top_topics = (
        trend_df.groupby(topic_label_col)[share_col]
        .mean()
        .sort_values(ascending=False)
        .head(top_n)
        .index.tolist()
    )
    df = trend_df[trend_df[topic_label_col].isin(top_topics)].copy()
    if df.empty:
        return go.Figure()
    df[share_col] = pd.to_numeric(df[share_col], errors="coerce").fillna(0.0)
    topic_colors = {
        label: TOPIC_COLOR_SEQUENCE[idx % len(TOPIC_COLOR_SEQUENCE)]
        for idx, label in enumerate(top_topics)
    }
    title_text = (
        "Failure family share by stage"
        if time_col == "stage_bucket"
        else "Failure family share over time"
    )
    fig = px.line(
        df,
        x=time_col,
        y=share_col,
        color=topic_label_col,
        markers=True,
        color_discrete_map=topic_colors,
        category_orders={topic_label_col: top_topics},
        title=title_text,
    )
    fig.update_traces(
        line=dict(width=3),
        marker=dict(
            size=9,
            line=dict(width=1, color="rgba(55, 65, 81, 0.55)"),
        ),
    )
    endpoint_rows = (
        df.sort_values(time_col)
        .groupby(topic_label_col, as_index=False, sort=False)
        .tail(1)
    )
    for _, row in endpoint_rows.iterrows():
        label = str(row[topic_label_col])
        fig.add_annotation(
            x=row[time_col],
            y=row[share_col],
            text=_truncate_text(label, width=24),
            showarrow=False,
            xanchor="left",
            xshift=10,
            font=dict(color=OUTLINE_ACCENT, size=11),
            bgcolor="rgba(255,255,255,0.78)",
            bordercolor=topic_colors.get(label, OUTLINE_ACCENT),
            borderwidth=1,
        )
    fig.update_layout(
        height=420,
        margin=dict(l=20, r=170, t=60, b=30),
        showlegend=False,
    )
    fig.update_yaxes(title="Share of traces in bin", tickformat=".0%")
    fig.update_xaxes(title="")
    if time_col == "stage_bucket":
        fig.update_xaxes(
            categoryorder="array", categoryarray=["early", "middle", "late"]
        )
    return fig


def plot_topic_scatter(
    topic_assignments: pd.DataFrame,
    x_col: str = "reduced_x",
    y_col: str = "reduced_y",
    color_col: str = "topic_label",
    hover_cols: Sequence[str] = ("trace_id", "scenario_family", "severity_label"),
    title: str = "Trace population map",
):
    _require_plotly()
    df = topic_assignments.copy()
    if df.empty:
        return go.Figure()
    if x_col not in df.columns or y_col not in df.columns:
        raise KeyError("Reduced coordinates are missing from topic_assignments.")
    if color_col not in df.columns and "label_short" in df.columns:
        color_col = "label_short"
    if color_col not in df.columns:
        df[color_col] = "trace"
    topic_order = (
        df[color_col].fillna("unlabeled").astype(str).value_counts().index.tolist()
    )
    noise_labels = {
        label
        for label in topic_order
        if label == "noise / outliers" or label.lower().startswith("noise")
    }
    color_map = {
        label: TOPIC_COLOR_SEQUENCE[idx % len(TOPIC_COLOR_SEQUENCE)]
        for idx, label in enumerate(
            [label for label in topic_order if label not in noise_labels]
        )
    }
    for label in noise_labels:
        color_map[label] = "#c5ced6"
    fig = px.scatter(
        df,
        x=x_col,
        y=y_col,
        color=color_col if color_col in df.columns else None,
        color_discrete_map=color_map,
        category_orders={color_col: topic_order},
        hover_data=[c for c in hover_cols if c in df.columns],
        opacity=0.72,
        title=f"{title} (diagnostic view)",
    )
    fig.update_traces(
        marker=dict(
            size=8,
            line=dict(width=0.6, color="rgba(55, 65, 81, 0.45)"),
        )
    )
    fig.update_layout(
        legend_title_text="Failure family",
        showlegend=len(topic_order) <= 10,
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig


def plot_suspect_leaderboard(
    cluster_suspects: pd.DataFrame | TopicDrilldownArtifacts | dict[str, Any],
    top_n: int = 8,
    title: str = "Repeated upstream suspects across sampled traces",
):
    _require_plotly()
    if isinstance(cluster_suspects, TopicDrilldownArtifacts):
        df = cluster_suspects.suspect_summary.copy()
    elif (
        isinstance(cluster_suspects, dict) and "suspect_summary_df" in cluster_suspects
    ):
        df = cluster_suspects["suspect_summary_df"].copy()
    else:
        df = cluster_suspects.copy()
        if not df.empty and "mean_score" not in df.columns:
            trace_count = (
                int(df["trace_id"].nunique())
                if "trace_id" in df.columns and df["trace_id"].notna().any()
                else 1
            )
            df = _summarize_cluster_suspects(df, trace_count=trace_count)
    if df.empty:
        return go.Figure()
    df = df.sort_values(
        ["mean_score", "traces_covered", "mean_hop_distance"],
        ascending=[False, False, True],
    ).head(top_n)
    df = df.sort_values("mean_score", ascending=True)
    df["bar_text"] = df.apply(
        lambda row: f"{int(row['traces_covered'])} traces | hop {row['mean_hop_distance']:.1f}",
        axis=1,
    )
    fig = px.bar(
        df,
        x="mean_score",
        y="display_label",
        color="trace_coverage_share",
        orientation="h",
        title=title,
        color_continuous_scale=["#edf8b1", "#7fcdbb", "#2c7fb8"],
    )
    fig.update_traces(
        text=df["bar_text"],
        textposition="outside",
        marker_line=dict(width=0.9, color=OUTLINE_ACCENT),
        customdata=df[
            [
                "owner_label",
                "traces_covered",
                "trace_coverage_share",
                "mean_hop_distance",
            ]
        ].to_numpy(),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Mean suspect score: %{x:.3f}<br>"
            "Likely surface: %{customdata[0]}<br>"
            "Traces covered: %{customdata[1]} (%{customdata[2]:.0%})<br>"
            "Mean hop distance: %{customdata[3]:.1f}<extra></extra>"
        ),
        cliponaxis=False,
    )
    fig.update_layout(
        height=max(360, 34 * len(df)),
        margin=dict(l=20, r=180, t=60, b=30),
        coloraxis_colorbar=dict(title="Trace coverage"),
    )
    fig.update_xaxes(title="Mean suspect score")
    fig.update_yaxes(title="")
    return fig


def plot_trace_swimlane(
    trace_window: pd.DataFrame | TopicDrilldownArtifacts | dict[str, Any],
    anchor_node_id: str | None = None,
    highlight_nodes: Sequence[str] | None = None,
    title: str = "Representative trace drilldown",
):
    _require_plotly()
    if isinstance(trace_window, TopicDrilldownArtifacts):
        df = trace_window.representative_trace_window.copy()
        anchor_node_id = anchor_node_id or trace_window.anchor_node_id
        highlight_nodes = highlight_nodes or trace_window.highlight_node_ids
    elif isinstance(trace_window, dict) and "trace_window_df" in trace_window:
        df = trace_window["trace_window_df"].copy()
        anchor_node_id = anchor_node_id or trace_window.get("anchor_node_id")
        highlight_nodes = highlight_nodes or trace_window.get("highlight_node_ids")
    else:
        df = trace_window.copy()
    if df.empty:
        return go.Figure()
    if "lane_label" not in df.columns:
        df["lane_label"] = df.apply(_lane_label, axis=1)
    if "short_label" not in df.columns:
        df["short_label"] = df.apply(_short_event_label, axis=1)
    highlight_set = {str(node_id) for node_id in (highlight_nodes or [])}
    df["node_id"] = df["node_id"].astype(str)
    df["is_highlight"] = df["node_id"].isin(highlight_set)
    df["is_anchor"] = (
        df["node_id"].eq(str(anchor_node_id))
        if anchor_node_id is not None
        else df.get("is_anchor", False)
    )
    df = df.sort_values("sequence_index").reset_index(drop=True)
    lanes = df["lane_label"].astype(str).drop_duplicates().tolist()
    lane_positions = {lane: len(lanes) - idx for idx, lane in enumerate(lanes)}
    df["lane_y"] = df["lane_label"].astype(str).map(lane_positions)

    fig = go.Figure()
    for stage_label, stage_group in df.groupby("stage_label", dropna=True, sort=False):
        if not stage_label:
            continue
        fig.add_vrect(
            x0=stage_group["sequence_index"].min() - 0.45,
            x1=stage_group["sequence_index"].max() + 0.45,
            fillcolor=STAGE_SHADES.get(stage_label, "rgba(53, 80, 112, 0.04)"),
            line_width=0,
            layer="below",
            annotation_text=str(stage_label),
            annotation_position="top left",
            annotation_font=dict(size=11, color="#56616b"),
        )
    fig.add_trace(
        go.Scatter(
            x=df["sequence_index"],
            y=df["lane_y"],
            mode="lines",
            line=dict(color="rgba(128, 138, 148, 0.45)", width=1.5),
            hoverinfo="skip",
            showlegend=False,
        )
    )
    marker_symbols = {
        "status": "circle",
        "handoff": "triangle-right",
        "function": "square",
        "response": "diamond",
    }
    customdata = (
        df[["label", "lane_label", "stage_label", "sequence_index", "text"]]
        .fillna("")
        .to_numpy()
    )
    for node_kind, group in df.groupby("node_kind", dropna=False, sort=False):
        kind_label = str(node_kind) if pd.notna(node_kind) else "event"
        fig.add_trace(
            go.Scatter(
                x=group["sequence_index"],
                y=group["lane_y"],
                mode="markers",
                name=kind_label,
                marker=dict(
                    size=11,
                    color=NODE_KIND_COLORS.get(kind_label, NODE_KIND_COLORS["default"]),
                    symbol=marker_symbols.get(kind_label, "circle"),
                    line=dict(width=1.1, color=OUTLINE_ACCENT),
                ),
                customdata=customdata[group.index],
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Lane: %{customdata[1]}<br>"
                    "Stage: %{customdata[2]}<br>"
                    "Sequence: %{customdata[3]}<br>"
                    "%{customdata[4]}<extra></extra>"
                ),
            )
        )
    highlight_df = df[df["is_highlight"] & ~df["is_anchor"]].copy()
    if not highlight_df.empty:
        fig.add_trace(
            go.Scatter(
                x=highlight_df["sequence_index"],
                y=highlight_df["lane_y"],
                mode="markers",
                name="Highlighted suspect",
                marker=dict(
                    size=17,
                    color="rgba(0,0,0,0)",
                    symbol="circle-open",
                    line=dict(width=3, color=HIGHLIGHT_ACCENT),
                ),
                hoverinfo="skip",
            )
        )
    anchor_df = df[df["is_anchor"]].copy()
    if not anchor_df.empty:
        fig.add_trace(
            go.Scatter(
                x=anchor_df["sequence_index"],
                y=anchor_df["lane_y"],
                mode="markers",
                name="Failure anchor",
                marker=dict(
                    size=18,
                    color=ANCHOR_ACCENT,
                    symbol="diamond",
                    line=dict(width=1.5, color=OUTLINE_ACCENT),
                ),
                hoverinfo="skip",
            )
        )
    label_ids = []
    if not anchor_df.empty:
        label_ids.extend(anchor_df["node_id"].astype(str).tolist())
    label_ids.extend(
        highlight_df["node_id"].astype(str).drop_duplicates().head(3).tolist()
    )
    label_df = df[df["node_id"].isin(label_ids)].drop_duplicates("node_id")
    if not label_df.empty:
        fig.add_trace(
            go.Scatter(
                x=label_df["sequence_index"],
                y=label_df["lane_y"],
                mode="text",
                text=label_df["short_label"].apply(
                    lambda value: _truncate_text(value, 32)
                ),
                textposition="top center",
                textfont=dict(size=11, color="#2d3640"),
                showlegend=False,
                hoverinfo="skip",
            )
        )
    trace_id = (
        df["trace_id"].dropna().astype(str).iloc[0]
        if "trace_id" in df.columns and df["trace_id"].notna().any()
        else None
    )
    fig.update_layout(
        title=f"{title}{'' if trace_id is None else f' ({trace_id})'}",
        height=max(420, 80 + 80 * len(lanes)),
        margin=dict(l=20, r=20, t=60, b=40),
        legend_title_text="Event type",
    )
    fig.update_xaxes(title="Sequence index", dtick=1, zeroline=False)
    fig.update_yaxes(
        title="Execution lane",
        tickmode="array",
        tickvals=list(lane_positions.values()),
        ticktext=list(lane_positions.keys()),
        range=[0.5, len(lanes) + 0.5],
    )
    return fig


def plot_root_cause_story(
    path_nodes: Sequence[dict[str, Any]] | TopicDrilldownArtifacts | dict[str, Any],
    title: str = "Root-cause story strip",
):
    _require_plotly()
    if isinstance(path_nodes, TopicDrilldownArtifacts):
        nodes = path_nodes.story_path_nodes
    elif isinstance(path_nodes, dict) and "selected_path_nodes" in path_nodes:
        nodes = path_nodes.get("selected_path_nodes") or []
    else:
        nodes = list(path_nodes)
    if not nodes:
        return go.Figure()
    story_nodes = [dict(node) for node in nodes]
    if len(story_nodes) > 5:
        interior = story_nodes[1:-1]
        keep = [story_nodes[0]]
        if interior:
            step = max(1, math.ceil(len(interior) / 3))
            keep.extend(interior[::step][:3])
        keep.append(story_nodes[-1])
        story_nodes = keep[:5]
    fig = go.Figure()
    for idx, node in enumerate(story_nodes):
        x0 = idx * 1.6
        x1 = x0 + 1.15
        fill = (
            "#fdb462"
            if idx == 0
            else "#fb8072" if idx == len(story_nodes) - 1 else "#80b1d3"
        )
        fig.add_shape(
            type="rect",
            x0=x0,
            x1=x1,
            y0=0,
            y1=1,
            line=dict(color=OUTLINE_ACCENT, width=1.2),
            fillcolor=fill,
            layer="below",
        )
        if idx < len(story_nodes) - 1:
            fig.add_annotation(
                x=x1 + 0.18,
                y=0.5,
                text="→",
                showarrow=False,
                font=dict(size=18, color=OUTLINE_ACCENT),
            )
        label = _truncate_text(node.get("short_label") or node.get("label"), 28)
        lane = _truncate_text(node.get("lane_label") or node.get("node_kind"), 22)
        fig.add_annotation(
            x=(x0 + x1) / 2,
            y=0.56,
            text=f"{label}<br><span style='font-size:10px'>{lane}</span>",
            showarrow=False,
            align="center",
        )
    fig.update_layout(
        title=title,
        xaxis=dict(visible=False, range=[-0.1, max(1.6 * len(story_nodes), 2.4)]),
        yaxis=dict(visible=False, range=[-0.1, 1.1]),
        height=230,
        margin=dict(l=20, r=20, t=60, b=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=False,
    )
    return fig


def plot_causal_graph(
    drilldown: dict[str, Any] | TopicDrilldownArtifacts,
    max_nodes: int = 20,
    highlight_nodes: Sequence[str] | None = None,
    anchor_node_id: str | None = None,
):
    _require_plotly()
    if isinstance(drilldown, TopicDrilldownArtifacts):
        graph_bundle = drilldown.graph_bundle
        anchor_node_id = anchor_node_id or drilldown.anchor_node_id
        highlight_nodes = highlight_nodes or drilldown.highlight_node_ids
    elif isinstance(drilldown, dict) and "nodes" in drilldown and "edges" in drilldown:
        graph_bundle = drilldown
    else:
        graph_bundle = drilldown["graph"]
    if graph_bundle is None:
        return go.Figure()
    nodes = _node_frame_from_bundle(graph_bundle)
    edges = _edge_frame_from_bundle(graph_bundle)
    if nodes.empty:
        return go.Figure()
    if "lane_label" not in nodes.columns:
        nodes["lane_label"] = nodes.apply(_lane_label, axis=1)
    if "short_label" not in nodes.columns:
        nodes["short_label"] = nodes.apply(_short_event_label, axis=1)
    nodes["node_id"] = nodes["node_id"].astype(str)
    highlight_set = {str(node_id) for node_id in (highlight_nodes or [])}
    focus_ids = set(highlight_set)
    if anchor_node_id is not None:
        focus_ids.add(str(anchor_node_id))
    if focus_ids:
        neighbor_ids = set()
        for _, edge in edges.iterrows():
            source = str(edge["source"])
            target = str(edge["target"])
            if source in focus_ids or target in focus_ids:
                neighbor_ids.update([source, target])
        filtered_ids = focus_ids | neighbor_ids
        filtered_nodes = nodes[nodes["node_id"].isin(filtered_ids)].copy()
    else:
        filtered_nodes = nodes.copy()
        if anchor_node_id is not None and "sequence_index" in filtered_nodes.columns:
            anchor_rows = filtered_nodes[
                filtered_nodes["node_id"].eq(str(anchor_node_id))
            ]
            if not anchor_rows.empty:
                anchor_sequence = int(anchor_rows.iloc[0]["sequence_index"])
                filtered_nodes = (
                    filtered_nodes.assign(
                        _distance=(
                            filtered_nodes["sequence_index"] - anchor_sequence
                        ).abs()
                    )
                    .sort_values("_distance")
                    .head(max_nodes)
                )
        filtered_nodes = filtered_nodes.sort_values("sequence_index").head(max_nodes)
    filtered_nodes = filtered_nodes.sort_values("sequence_index").reset_index(drop=True)
    filtered_ids = set(filtered_nodes["node_id"].tolist())
    filtered_edges = edges[
        edges["source"].astype(str).isin(filtered_ids)
        & edges["target"].astype(str).isin(filtered_ids)
    ].copy()
    lanes = filtered_nodes["lane_label"].astype(str).drop_duplicates().tolist()
    lane_positions = {lane: len(lanes) - idx for idx, lane in enumerate(lanes)}
    filtered_nodes["lane_y"] = (
        filtered_nodes["lane_label"].astype(str).map(lane_positions)
    )
    node_lookup = {
        row["node_id"]: (row["sequence_index"], row["lane_y"])
        for _, row in filtered_nodes.iterrows()
    }
    fig = go.Figure()
    for _, edge in filtered_edges.iterrows():
        src = node_lookup.get(str(edge["source"]))
        dst = node_lookup.get(str(edge["target"]))
        if src is None or dst is None:
            continue
        fig.add_trace(
            go.Scatter(
                x=[src[0], dst[0]],
                y=[src[1], dst[1]],
                mode="lines",
                line=dict(width=1.1, color="rgba(128, 138, 148, 0.45)"),
                hoverinfo="skip",
                showlegend=False,
            )
        )
    customdata = (
        filtered_nodes[["label", "lane_label", "stage_label", "sequence_index", "text"]]
        .fillna("")
        .to_numpy()
    )
    fig.add_trace(
        go.Scatter(
            x=filtered_nodes["sequence_index"],
            y=filtered_nodes["lane_y"],
            mode="markers",
            marker=dict(
                size=12,
                color=filtered_nodes["node_kind"]
                .fillna("default")
                .map(
                    lambda value: NODE_KIND_COLORS.get(
                        value, NODE_KIND_COLORS["default"]
                    )
                ),
                line=dict(width=1.1, color=OUTLINE_ACCENT),
            ),
            customdata=customdata,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Lane: %{customdata[1]}<br>"
                "Stage: %{customdata[2]}<br>"
                "Sequence: %{customdata[3]}<br>"
                "%{customdata[4]}<extra></extra>"
            ),
            showlegend=False,
        )
    )
    overlay_df = filtered_nodes[
        filtered_nodes["node_id"].isin(focus_ids)
        | filtered_nodes["is_failure_marker"].fillna(False)
    ].copy()
    if not overlay_df.empty:
        overlay_df["marker_color"] = overlay_df["node_id"].map(
            lambda value: (
                ANCHOR_ACCENT if str(value) == str(anchor_node_id) else HIGHLIGHT_ACCENT
            )
        )
        overlay_df["marker_symbol"] = overlay_df["node_id"].map(
            lambda value: (
                "diamond" if str(value) == str(anchor_node_id) else "circle-open"
            )
        )
        fig.add_trace(
            go.Scatter(
                x=overlay_df["sequence_index"],
                y=overlay_df["lane_y"],
                mode="markers+text",
                text=overlay_df["short_label"].apply(
                    lambda value: _truncate_text(value, 30)
                ),
                textposition="top center",
                marker=dict(
                    size=18,
                    color=overlay_df["marker_color"],
                    symbol=overlay_df["marker_symbol"],
                    line=dict(width=2, color=OUTLINE_ACCENT),
                ),
                hoverinfo="skip",
                showlegend=False,
            )
        )
    fig.update_layout(
        title="Technical dependency and path view",
        height=max(420, 80 + 80 * len(lanes)),
        margin=dict(l=20, r=20, t=60, b=40),
        xaxis=dict(title="Sequence index", dtick=1),
        yaxis=dict(
            title="Execution lane",
            tickmode="array",
            tickvals=list(lane_positions.values()),
            ticktext=list(lane_positions.keys()),
            range=[0.5, len(lanes) + 0.5],
        ),
    )
    return fig


def build_macro_eval_package(
    dataset_root: str | Path | None = None,
    data_dir: str | Path = "data",
    limit: int | None = None,
    doc_type: str = "doc_structured_summary",
    embedding_method: str = "auto",
    reducer: str = "umap",
    clusterer: str = "hdbscan",
    min_cluster_size: int = 20,
) -> dict[str, Any]:
    discovery = run_macro_discovery(
        dataset_root=dataset_root,
        data_dir=data_dir,
        limit=limit,
        doc_type=doc_type,
        embedding_method=embedding_method,
        reducer=reducer,
        clusterer=clusterer,
        min_cluster_size=min_cluster_size,
    )
    return {
        "traces_df": discovery.traces_df,
        "events_df": discovery.events_df,
        "documents_df": discovery.documents_df,
        "stacked_documents_df": discovery.stacked_documents_df,
        "topic_bundle": discovery.topic_bundle,
        "trace_topics": discovery.trace_topics,
        "topic_keywords": discovery.topic_keywords,
        "topic_summary": discovery.topic_summary,
        "topic_assignments": discovery.topic_assignments,
    }


def _require_plotly():
    if px is None or go is None:
        raise RuntimeError("plotly is required for visualization helpers.")


def _macro_eval_cache_paths(
    dataset_root: Path,
    limit: int | None = None,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
) -> dict[str, Path]:
    cache_root = (
        Path(cache_dir) / _dataset_cache_key(dataset_root) / _cache_limit_tag(limit)
    )
    return {
        "traces_df": cache_root / "traces.pkl",
        "events_df": cache_root / "events.pkl",
        "documents_df": cache_root / "documents.pkl",
        "stacked_documents_df": cache_root / "stacked_documents.pkl",
    }


def _dataset_cache_key(dataset_root: Path) -> str:
    fingerprint = hashlib.sha1()
    fingerprint.update(str(dataset_root.resolve()).encode("utf-8"))
    for name in ("summary.json", "results.jsonl"):
        path = dataset_root / name
        if not path.exists():
            continue
        stat = path.stat()
        fingerprint.update(f"{name}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8"))
    return f"{dataset_root.name}-{fingerprint.hexdigest()[:10]}"


def _cache_limit_tag(limit: int | None) -> str:
    return "limit-full" if limit is None else f"limit-{int(limit):05d}"


def _macro_eval_cache_ready(cache_paths: dict[str, Path]) -> bool:
    return all(path.exists() for path in cache_paths.values())


def _noise_label(topic_id: Any) -> str:
    return "noise / outliers" if int(topic_id) == -1 else f"topic {int(topic_id)}"


def _label_from_keywords(
    keywords: Sequence[str], examples: Sequence[str]
) -> tuple[str, str, str]:
    keywords_text = " ".join(keywords).lower()
    example_text = " ".join(examples).lower()
    combined = f"{keywords_text} {example_text}"
    for needle, label in FAILURE_LABEL_HINTS:
        if needle.lower() in combined:
            return (
                label,
                f"Recurring pattern centered on {label}.",
                _owner_from_text(combined),
            )
    if "price" in combined or "msrp" in combined or "total" in combined:
        return (
            "pricing drift",
            "Repeated pricing or offer mismatch across the trace population.",
            "pricing and offer owner",
        )
    if "compliance" in combined or "region" in combined or "state" in combined:
        return (
            "compliance gate",
            "Repeated validation pressure around policy or regional constraints.",
            "compliance validation owner",
        )
    if "retry" in combined or "timeout" in combined or "handoff" in combined:
        return (
            "retry loop",
            "Trace population shows a repeated retry or handoff loop.",
            _owner_from_text(combined),
        )
    if "clarification" in combined or "ambiguous" in combined:
        return (
            "clarification gap",
            "The traces repeatedly stall on missing or ambiguous user intent.",
            "customer conversation owner",
        )
    if "supplier" in combined or "inventory" in combined or "availability" in combined:
        return (
            "supply mismatch",
            "The recurring pattern is a supply or availability mismatch.",
            "supply and routing owner",
        )
    return (
        DEFAULT_TOPIC_LABEL,
        "A recurring operational pattern detected across traces.",
        _owner_from_text(combined),
    )


def _owner_from_text(text: str) -> str:
    for needle, owner in ROLE_HINTS.items():
        if needle in text:
            return f"{owner} owner"
    return "orchestration owner"


def _safe_column(arr: Any, idx: int) -> Any:
    if np is None:
        return [None] * len(arr)
    arr = np.asarray(arr)
    if arr.ndim == 1:
        return arr
    if arr.shape[1] <= idx:
        return np.zeros(arr.shape[0])
    return arr[:, idx]


def _estimate_dbscan_eps(embeddings: Any, quantile: float = 0.8) -> float:
    if np is None or cosine_similarity is None:
        return 0.5
    embeddings = np.asarray(embeddings)
    if len(embeddings) < 3:
        return 0.5
    sample = embeddings[: min(len(embeddings), 300)]
    sim = cosine_similarity(sample)
    distances = 1 - sim
    upper = distances[np.triu_indices_from(distances, k=1)]
    if len(upper) == 0:
        return 0.5
    return float(np.clip(np.quantile(upper, quantile), 0.1, 1.5))


def _humanize_token(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = text.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def _truncate_text(value: Any, width: int = 42) -> str:
    text = _clean_text(value)
    if len(text) <= width:
        return text
    return f"{text[: max(0, width - 1)].rstrip()}…"


def _lane_label(row: pd.Series | dict[str, Any]) -> str:
    getter = row.get
    for candidate in ("agent_name", "tool_name", "node_kind"):
        value = getter(candidate)
        if value and pd.notna(value):
            return str(value)
    return "event"


def _short_event_label(row: pd.Series | dict[str, Any]) -> str:
    getter = row.get
    node_kind = _clean_text(getter("node_kind"))
    actor = _clean_text(getter("agent_name") or getter("tool_name"))
    marker = _humanize_token(getter("failure_marker_type"))
    terminal_state = _clean_text(getter("terminal_state"))
    if getter("is_failure_marker"):
        if marker:
            return _truncate_text(f"failure: {marker}", width=44)
        return "failure marker"
    if node_kind == "status" and actor:
        suffix = f" [{terminal_state}]" if terminal_state else ""
        return _truncate_text(f"status: {actor}{suffix}", width=44)
    if node_kind and actor:
        return _truncate_text(f"{node_kind}: {actor}", width=44)
    if actor:
        return _truncate_text(actor, width=44)
    if node_kind:
        return _truncate_text(node_kind, width=44)
    return str(getter("event_id"))


def _execution_nodes(
    trace_events: pd.DataFrame, trace_row: pd.Series | None = None
) -> list[dict[str, Any]]:
    if trace_events.empty:
        return []
    nodes = []
    for _, row in trace_events.sort_values(["sequence_index", "ts"]).iterrows():
        node_id = str(row["event_id"])
        nodes.append(
            {
                "node_id": node_id,
                "label": _node_label(row),
                "short_label": _short_event_label(row),
                "node_kind": row.get("node_kind"),
                "agent_name": row.get("agent_name"),
                "tool_name": row.get("tool_name"),
                "lane_label": _lane_label(row),
                "sequence_index": int(row.get("sequence_index", 0)),
                "stage_label": row.get("stage_label"),
                "is_failure_marker": bool(row.get("is_failure_marker")),
                "failure_marker_type": row.get("failure_marker_type"),
                "text": row.get("text"),
                "duration_ms": row.get("duration_ms"),
                "terminal_state": row.get("terminal_state"),
                "trace_id": row.get("trace_id"),
                "trace_family": (
                    trace_row.get("trace_family") if trace_row is not None else None
                ),
                "outcome_group": (
                    trace_row.get("outcome_group") if trace_row is not None else None
                ),
                "severity_label": (
                    trace_row.get("severity_label") if trace_row is not None else None
                ),
                "depth": _depth_from_stage(row),
            }
        )
    return nodes


def _execution_edges(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not nodes:
        return []
    edges = []
    for prev, nxt in zip(nodes[:-1], nodes[1:]):
        edges.append(
            {
                "source": prev["node_id"],
                "target": nxt["node_id"],
                "relation": "temporal",
                "weight": 1.0,
            }
        )
    return edges


def _predecessor_map(edges: pd.DataFrame) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    if edges.empty:
        return mapping
    for _, edge in edges.iterrows():
        mapping.setdefault(edge["target"], []).append(edge["source"])
    return mapping


def _candidate_frequency_weight(node: pd.Series, all_nodes: pd.DataFrame) -> float:
    if all_nodes.empty:
        return 0.0
    key = node["label"]
    return float((all_nodes["label"] == key).mean())


def _candidate_bridge_weight(node: pd.Series, edges: pd.DataFrame) -> float:
    if edges.empty:
        return 0.0
    node_id = node["node_id"]
    degree = ((edges["source"] == node_id) | (edges["target"] == node_id)).sum()
    return float(math.log1p(degree))


def _candidate_role_weight(node: pd.Series) -> float:
    label = f"{node.get('agent_name') or ''} {node.get('tool_name') or ''} {node.get('label') or ''}".lower()
    if any(key in label for key in ("orchestrator", "monitor", "review")):
        return 0.9
    if any(
        key in label
        for key in ("validation", "pricing", "supplier", "factory", "routing")
    ):
        return 0.8
    return 0.5


def _node_label(row: pd.Series) -> str:
    bits = [row.get("node_kind"), row.get("agent_name"), row.get("tool_name")]
    bits = [str(bit) for bit in bits if bit and pd.notna(bit)]
    if row.get("is_failure_marker"):
        bits.append(f"[{row.get('failure_marker_type')}]")
    return " ".join(bits) if bits else str(row.get("event_id"))


def _depth_from_stage(row: pd.Series) -> int:
    stage = row.get("stage_label")
    if stage == "early":
        return 0
    if stage == "middle":
        return 1
    if stage == "late":
        return 2
    return 1


def _failure_anchor_node(nodes: pd.DataFrame) -> dict[str, Any] | None:
    if nodes.empty:
        return None
    failing = nodes[nodes["is_failure_marker"].fillna(False)]
    if not failing.empty:
        return (
            failing.sort_values(["sequence_index", "depth"], ascending=[False, False])
            .iloc[0]
            .to_dict()
        )
    return (
        nodes.sort_values(["sequence_index", "depth"], ascending=[False, False])
        .iloc[0]
        .to_dict()
    )


def _build_root_cause_summary(
    trace_row: pd.Series,
    anchor: dict[str, Any] | None,
    suspects: pd.DataFrame,
) -> str:
    if anchor is None:
        return "No failure anchor could be recovered from the trace."
    if suspects.empty:
        return f"Anchor at {anchor['label']} with no upstream suspects recovered."
    top = suspects.iloc[0]
    label = top["candidate"]
    family = (
        trace_row.get("topic_label")
        or trace_row.get("scenario_family")
        or "the selected family"
    )
    return (
        f"Within {family}, the most likely upstream driver is {label}. "
        f"The failure anchor is {anchor['label']}, and the highest-scoring predecessor is {label} "
        f"at hop {int(top['hop_distance'])} with repeated pattern support across the trace population."
    )


def _clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def _first_available_doc_column(documents_df: pd.DataFrame) -> str:
    for candidate in DEFAULT_DOC_COLUMNS:
        if candidate in documents_df.columns:
            return candidate
    raise KeyError("No document column found.")


def _safe_array(values: Any) -> list[Any]:
    if values is None:
        return []
    if isinstance(values, list):
        return values
    if np is not None and hasattr(values, "tolist"):
        return values.tolist()
    return list(values)


def _attach_topic_label(
    frame: pd.DataFrame, source: pd.DataFrame, topic_column: str
) -> pd.DataFrame:
    if frame.empty or topic_column not in frame.columns:
        return frame
    label_col = None
    for candidate in ("topic_label", "label_short", "label_long"):
        if candidate in source.columns:
            label_col = candidate
            break
    if label_col is None:
        frame["topic_label"] = frame[topic_column].map(_noise_label)
        return frame
    lookup = (
        source[[topic_column, label_col]]
        .dropna()
        .drop_duplicates(subset=[topic_column])
        .rename(columns={label_col: "topic_label"})
    )
    return frame.merge(lookup, on=topic_column, how="left")


def _coerce_discovery_inputs(
    discovery: MacroDiscoveryArtifacts | TopicBundle | dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if isinstance(discovery, MacroDiscoveryArtifacts):
        return (
            discovery.topic_summary,
            discovery.topic_assignments,
            discovery.traces_df,
            discovery.events_df,
        )
    if isinstance(discovery, TopicBundle):
        return (
            discovery.topic_summary,
            discovery.topic_assignments,
            discovery.trace_topics,
            pd.DataFrame(),
        )
    if isinstance(discovery, dict):
        topic_summary = discovery.get("topic_summary")
        topic_assignments = discovery.get("topic_assignments")
        traces_df = discovery.get("traces_df")
        events_df = discovery.get("events_df")
        if not isinstance(topic_summary, pd.DataFrame) or not isinstance(
            topic_assignments, pd.DataFrame
        ):
            raise TypeError(
                "Discovery dict must contain topic_summary and topic_assignments dataframes."
            )
        return (
            topic_summary,
            topic_assignments,
            traces_df if isinstance(traces_df, pd.DataFrame) else pd.DataFrame(),
            events_df if isinstance(events_df, pd.DataFrame) else pd.DataFrame(),
        )
    raise TypeError(f"Unsupported discovery object: {type(discovery)!r}")


def _compose_topic_root_cause_summary(
    focus_topic: pd.Series,
    topic_suspects: pd.DataFrame,
    representative_traces: pd.DataFrame,
) -> str:
    label = focus_topic.get("label_short") or _noise_label(focus_topic.get("topic_id"))
    owner = focus_topic.get("likely_owner") or "an orchestration owner"
    if topic_suspects.empty:
        return f"{label} appears to be owned by {owner}, but no consistent upstream suspect surfaced across the sampled traces."
    top = (
        topic_suspects.groupby(["candidate", "node_kind", "agent_name"], dropna=False)[
            "score"
        ]
        .mean()
        .sort_values(ascending=False)
        .head(3)
    )
    suspect_bits = ", ".join([str(idx[0]) for idx in top.index.tolist()])
    trace_ids = (
        representative_traces["trace_id"].dropna().astype(str).head(3).tolist()
        if not representative_traces.empty
        else []
    )
    exemplar = f" Representative traces: {', '.join(trace_ids)}." if trace_ids else ""
    return (
        f"{label} is the dominant failure family in this slice, and the leading upstream suspects are {suspect_bits}. "
        f"The likely ownership surface is {owner}.{exemplar}"
    )


def _build_cluster_card_markdown(
    focus_topic: pd.Series,
    topic_suspects: pd.DataFrame,
    representative_traces: pd.DataFrame,
) -> str:
    label = (
        focus_topic.get("topic_label")
        or focus_topic.get("label_short")
        or DEFAULT_TOPIC_LABEL
    )
    owner = (
        focus_topic.get("dominant_owner")
        or focus_topic.get("likely_owner")
        or "orchestration owner"
    )
    keywords_text = focus_topic.get("keywords_text") or ""
    scenario = focus_topic.get("dominant_scenario_family") or "mixed scenarios"
    trace_share = focus_topic.get("prevalence")
    trace_share_text = f"{float(trace_share):.1%}" if pd.notna(trace_share) else "n/a"
    suspects = []
    if not topic_suspects.empty and "candidate" in topic_suspects.columns:
        suspects = (
            topic_suspects.groupby("candidate")["score"]
            .mean()
            .sort_values(ascending=False)
            .head(3)
            .index.astype(str)
            .tolist()
        )
    trace_ids = (
        representative_traces["trace_id"].dropna().astype(str).head(3).tolist()
        if not representative_traces.empty
        else []
    )
    suspect_text = (
        ", ".join(suspects)
        if suspects
        else "No repeated suspect surfaced from the sampled traces."
    )
    example_text = (
        ", ".join(trace_ids) if trace_ids else "No representative traces selected."
    )
    return (
        f"### Failure Family: {label}\n\n"
        f"- Share of modeled traces: {trace_share_text}\n"
        f"- Dominant scenario family: {scenario}\n"
        f"- Keywords: {keywords_text or 'n/a'}\n"
        f"- Likely owner: {owner}\n"
        f"- Leading upstream suspects: {suspect_text}\n"
        f"- Representative traces: {example_text}\n"
    )


def _build_root_cause_markdown(
    focus_topic: pd.Series,
    topic_suspects: pd.DataFrame,
    summary: str,
) -> str:
    label = (
        focus_topic.get("topic_label")
        or focus_topic.get("label_short")
        or DEFAULT_TOPIC_LABEL
    )
    lines = [f"### Root-cause localization for {label}", "", summary]
    if not topic_suspects.empty:
        if {"candidate", "node_kind", "agent_name", "hop_distance", "score"}.issubset(
            topic_suspects.columns
        ):
            preview = topic_suspects[
                ["candidate", "node_kind", "agent_name", "hop_distance", "score"]
            ].head(5)
            lines.append("")
            lines.append("Top ranked suspects:")
            for _, row in preview.iterrows():
                agent = (
                    f" via {row['agent_name']}"
                    if pd.notna(row.get("agent_name"))
                    else ""
                )
                lines.append(
                    f"- {row['candidate']} ({row['node_kind']}{agent}, hop={int(row['hop_distance'])}, score={row['score']:.3f})"
                )
        elif {
            "suspect_label",
            "node_kind",
            "owner_label",
            "mean_hop_distance",
            "mean_score",
        }.issubset(topic_suspects.columns):
            preview = topic_suspects[
                [
                    "suspect_label",
                    "node_kind",
                    "owner_label",
                    "mean_hop_distance",
                    "mean_score",
                ]
            ].head(5)
            lines.append("")
            lines.append("Top ranked suspects:")
            for _, row in preview.iterrows():
                owner = (
                    f" via {row['owner_label']}"
                    if pd.notna(row.get("owner_label")) and row.get("owner_label")
                    else ""
                )
                lines.append(
                    f"- {row['suspect_label']} ({row['node_kind']}{owner}, hop={row['mean_hop_distance']:.1f}, score={row['mean_score']:.3f})"
                )
    return "\n".join(lines)


plot_umap_scatter = plot_topic_scatter
plot_root_cause_network = plot_causal_graph


__all__ = [
    "EmbeddingBundle",
    "MacroDiscoveryArtifacts",
    "TopicBundle",
    "TopicDrilldownArtifacts",
    "assign_topics",
    "build_execution_graph",
    "build_macro_eval_package",
    "build_topic_labels",
    "choose_document_view",
    "cluster_embeddings",
    "compute_dense_embeddings",
    "compute_topic_keywords",
    "drill_down_topic_root_causes",
    "get_trace_corpus",
    "load_macro_eval_tables",
    "pick_focus_topic",
    "plot_causal_graph",
    "plot_root_cause_story",
    "plot_suspect_leaderboard",
    "plot_trace_swimlane",
    "plot_topic_heatmap",
    "plot_topic_leaderboard",
    "plot_topic_trend",
    "plot_topic_scatter",
    "plot_umap_scatter",
    "rank_upstream_suspects",
    "reduce_embeddings",
    "root_cause_drilldown",
    "run_macro_discovery",
    "select_representative_examples",
    "slice_topics_by_metadata",
    "summarize_topics",
    "topics_by_stage",
    "topics_over_time",
]
