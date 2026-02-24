#!/usr/bin/env python3
"""
RNS Company Name Search — CUIT lookup by company name.

Solves the mobile CUIT friction problem: instead of typing 11 digits,
users search by company name and select from autocomplete results.

Uses the RNS dataset (3M+ records from datos.gob.ar) as the source.
Designed for <100ms response times after initial load.

Usage:
    # Interactive search
    python rns_name_search.py --search "panaderia martinez"

    # With province filter
    python rns_name_search.py --search "constructora" --provincia "Buenos Aires"

    # Autocomplete mode (prefix-optimized)
    python rns_name_search.py --autocomplete "BANCO BB"

    # Benchmark search performance
    python rns_name_search.py --benchmark
"""

import os
import re
import time
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CompanyMatch:
    """A single company match from the RNS dataset."""
    cuit: str
    razon_social: str
    tipo_societario: str
    provincia: str
    actividad: str
    fecha_contrato: str
    score: float  # 0-100, higher = better match


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

def _strip_accents(text: str) -> str:
    """Remove accents/diacritics: á→a, ñ→n, ü→u, etc."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# Common legal suffixes to strip for better matching
_LEGAL_SUFFIXES = re.compile(
    r"\b(S\.?A\.?S?\.?|S\.?R\.?L\.?|S\.?C\.?|S\.?H\.?|S\.?E\.?|"
    r"SOCIEDAD ANONIMA|SOCIEDAD DE RESPONSABILIDAD LIMITADA|"
    r"SOCIEDAD POR ACCIONES SIMPLIFICADA)\s*$",
    re.IGNORECASE,
)


def normalize_name(raw: str) -> str:
    """Normalize a company name for search matching.

    Pipeline: uppercase → strip accents → remove legal suffixes → collapse whitespace.
    """
    if not isinstance(raw, str):
        return ""
    text = raw.upper().strip()
    text = _strip_accents(text)
    text = _LEGAL_SUFFIXES.sub("", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_query(raw: str) -> str:
    """Normalize a user query (same pipeline, no suffix stripping)."""
    if not isinstance(raw, str):
        return ""
    text = raw.upper().strip()
    text = _strip_accents(text)
    text = re.sub(r"\s+", " ", text)
    return text


# ---------------------------------------------------------------------------
# Main search class
# ---------------------------------------------------------------------------

class RNSNameSearch:
    """Fast company name search over the RNS dataset.

    Loads the dataset once into memory, creates a normalized name column,
    and provides multi-token substring search with optional province filter.

    Typical memory usage: ~800MB for the 3M-row dataset.
    Load time: ~8-15s on first call (cached afterward).
    Search time: <100ms per query.
    """

    def __init__(self, dataset_path: Optional[str] = None):
        self._df: Optional[pd.DataFrame] = None
        self._dataset_path = dataset_path or self._find_default_dataset()

    @staticmethod
    def _find_default_dataset() -> str:
        """Locate the most recent RNS CSV in the standard directory."""
        datasets_dir = Path(__file__).resolve().parent / "rns_datasets"
        csvs = sorted(datasets_dir.glob("registro-nacional-sociedades-*.csv"))
        if not csvs:
            raise FileNotFoundError(
                f"No RNS dataset found in {datasets_dir}. "
                "Download from https://datos.jus.gob.ar/dataset/registro-nacional-de-sociedades"
            )
        return str(csvs[-1])  # Most recent by filename sort

    def _load(self) -> pd.DataFrame:
        """Load and prepare the dataset (called once, cached)."""
        if self._df is not None:
            return self._df

        t0 = time.time()
        print(f"Loading RNS dataset from {self._dataset_path}...")

        df = pd.read_csv(
            self._dataset_path,
            encoding="utf-8",
            low_memory=False,
            on_bad_lines="skip",
            usecols=[
                "cuit",
                "razon_social",
                "tipo_societario",
                "dom_fiscal_provincia",
                "actividad_descripcion",
                "fecha_hora_contrato_social",
            ],
            dtype={
                "cuit": str,
                "razon_social": str,
                "tipo_societario": str,
                "dom_fiscal_provincia": str,
                "actividad_descripcion": str,
                "fecha_hora_contrato_social": str,
            },
        )

        # Drop rows without a name (can't search them)
        df = df.dropna(subset=["razon_social"])

        # Deduplicate by CUIT — keep first (same company may appear in
        # multiple semesters with slightly different data)
        df = df.drop_duplicates(subset=["cuit"], keep="first")

        # Create normalized search column
        df["_name_norm"] = df["razon_social"].apply(normalize_name)

        # Normalize province for filtering
        df["_prov_norm"] = df["dom_fiscal_provincia"].fillna("").apply(
            lambda x: _strip_accents(x.upper().strip()) if isinstance(x, str) else ""
        )

        # Fill NAs for display fields
        for col in ["tipo_societario", "dom_fiscal_provincia", "actividad_descripcion", "fecha_hora_contrato_social"]:
            df[col] = df[col].fillna("")

        self._df = df.reset_index(drop=True)

        elapsed = time.time() - t0
        print(f"  Loaded {len(self._df):,} companies in {elapsed:.1f}s")

        return self._df

    # ------------------------------------------------------------------
    # Search methods
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        provincia: Optional[str] = None,
        limit: int = 10,
    ) -> list[CompanyMatch]:
        """Multi-token substring search with scoring.

        All tokens in the query must appear somewhere in the normalized name
        (AND logic). Results are ranked by match quality.

        Args:
            query: User search string (e.g. "panaderia martinez")
            provincia: Optional province filter (e.g. "Buenos Aires")
            limit: Max results to return (default 10)

        Returns:
            List of CompanyMatch sorted by score descending.
        """
        df = self._load()
        q = normalize_query(query)
        tokens = q.split()

        if not tokens:
            return []

        # Build boolean mask: all tokens must appear in _name_norm
        mask = pd.Series(True, index=df.index)
        for token in tokens:
            mask &= df["_name_norm"].str.contains(token, regex=False)

        # Province filter
        if provincia:
            prov_norm = _strip_accents(provincia.upper().strip())
            mask &= df["_prov_norm"].str.contains(prov_norm, regex=False)

        matches = df[mask]

        if matches.empty:
            return []

        # Score and rank
        scored = self._score_matches(matches, tokens, q)

        # Take top N
        top = scored.nlargest(limit, "score")

        return [
            CompanyMatch(
                cuit=row["cuit"],
                razon_social=row["razon_social"],
                tipo_societario=row["tipo_societario"],
                provincia=row["dom_fiscal_provincia"],
                actividad=row["actividad_descripcion"],
                fecha_contrato=row["fecha_hora_contrato_social"][:10] if row["fecha_hora_contrato_social"] else "",
                score=round(row["score"], 1),
            )
            for _, row in top.iterrows()
        ]

    def autocomplete(
        self,
        prefix: str,
        provincia: Optional[str] = None,
        limit: int = 10,
    ) -> list[CompanyMatch]:
        """Prefix-optimized search for autocomplete UX.

        Like search(), but the LAST token is treated as a prefix (user is
        still typing it), while earlier tokens must match as complete words.

        Args:
            prefix: What the user has typed so far (e.g. "BANCO BB")
            provincia: Optional province filter
            limit: Max results

        Returns:
            List of CompanyMatch sorted by score descending.
        """
        df = self._load()
        q = normalize_query(prefix)
        tokens = q.split()

        if not tokens:
            return []

        mask = pd.Series(True, index=df.index)

        # All tokens except the last: full substring match
        for token in tokens[:-1]:
            mask &= df["_name_norm"].str.contains(token, regex=False)

        # Last token: prefix match (starts-with on any word boundary)
        last = tokens[-1]
        # Match if name contains a word starting with the last token
        # Use regex for word-boundary prefix: \bTOKEN
        mask &= df["_name_norm"].str.contains(r"\b" + re.escape(last), regex=True)

        # Province filter
        if provincia:
            prov_norm = _strip_accents(provincia.upper().strip())
            mask &= df["_prov_norm"].str.contains(prov_norm, regex=False)

        matches = df[mask]

        if matches.empty:
            return []

        scored = self._score_matches(matches, tokens, q)
        top = scored.nlargest(limit, "score")

        return [
            CompanyMatch(
                cuit=row["cuit"],
                razon_social=row["razon_social"],
                tipo_societario=row["tipo_societario"],
                provincia=row["dom_fiscal_provincia"],
                actividad=row["actividad_descripcion"],
                fecha_contrato=row["fecha_hora_contrato_social"][:10] if row["fecha_hora_contrato_social"] else "",
                score=round(row["score"], 1),
            )
            for _, row in top.iterrows()
        ]

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score_matches(
        self,
        matches: pd.DataFrame,
        tokens: list[str],
        full_query: str,
    ) -> pd.DataFrame:
        """Score matched rows by relevance.

        Scoring hierarchy (max 100):
          - Exact match with normalized name:      100
          - Name starts with the full query:        80
          - Each token matches a word start:        +10 per token (up to 50)
          - Shorter names (more specific) get a bonus: up to 20
        """
        df = matches.copy()
        scores = pd.Series(0.0, index=df.index)

        names = df["_name_norm"]

        # Exact match bonus
        scores += (names == full_query).astype(float) * 100

        # Starts-with bonus
        scores += names.str.startswith(full_query).astype(float) * 30

        # Per-token word-start bonus
        for token in tokens:
            pattern = r"\b" + re.escape(token)
            scores += names.str.contains(pattern, regex=True).astype(float) * 10

        # Length penalty: shorter (more specific) names rank higher
        # Normalize: names range ~5-100 chars, score bonus 0-20
        name_lens = names.str.len().clip(upper=100)
        scores += (1 - name_lens / 100) * 20

        df["score"] = scores
        return df

    # ------------------------------------------------------------------
    # Stats / diagnostics
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Return dataset statistics."""
        df = self._load()
        return {
            "total_companies": len(df),
            "unique_cuits": df["cuit"].nunique(),
            "provinces": sorted(df["dom_fiscal_provincia"].dropna().unique().tolist()),
            "tipo_societario_counts": df["tipo_societario"].value_counts().head(10).to_dict(),
        }

    def benchmark(self, queries: Optional[list[str]] = None) -> None:
        """Run benchmark searches and print timing."""
        if queries is None:
            queries = [
                "panaderia martinez",
                "BANCO BBVA",
                "constructora",
                "farmacia",
                "SEGU GAL",
                "tecnologia",
                "ABC",
                "YPF",
            ]

        # Ensure dataset is loaded (don't count load time)
        self._load()

        print(f"\nBenchmark: {len(queries)} queries")
        print("-" * 70)

        for q in queries:
            t0 = time.time()
            results = self.search(q, limit=10)
            elapsed_ms = (time.time() - t0) * 1000

            print(f"  '{q}' → {len(results)} results ({elapsed_ms:.0f}ms)")
            if results:
                top = results[0]
                print(f"    #1: {top.razon_social} [{top.cuit}] ({top.provincia})")

        # Province-filtered benchmark
        print("\nWith province filter (Buenos Aires):")
        for q in ["constructora", "farmacia", "panaderia"]:
            t0 = time.time()
            results = self.search(q, provincia="Buenos Aires", limit=10)
            elapsed_ms = (time.time() - t0) * 1000
            print(f"  '{q}' + Buenos Aires → {len(results)} results ({elapsed_ms:.0f}ms)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_results(results: list[CompanyMatch]) -> None:
    """Pretty-print search results."""
    if not results:
        print("  No results found.")
        return

    for i, m in enumerate(results, 1):
        print(f"  {i}. {m.razon_social}")
        print(f"     CUIT: {m.cuit}  |  {m.tipo_societario}  |  {m.provincia}")
        if m.actividad:
            print(f"     Actividad: {m.actividad[:80]}")
        if m.fecha_contrato:
            print(f"     Contrato social: {m.fecha_contrato}")
        print(f"     Score: {m.score}")
        print()


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Search RNS dataset by company name to find CUITs"
    )
    parser.add_argument("--search", help="Search query (multi-token substring)")
    parser.add_argument("--autocomplete", help="Autocomplete prefix (last token is partial)")
    parser.add_argument("--provincia", help="Province filter")
    parser.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--benchmark", action="store_true", help="Run search benchmark")
    parser.add_argument("--stats", action="store_true", help="Show dataset stats")
    parser.add_argument("--dataset", help="Path to RNS CSV file")

    args = parser.parse_args()
    searcher = RNSNameSearch(dataset_path=args.dataset)

    if args.stats:
        s = searcher.stats()
        print(f"Total companies: {s['total_companies']:,}")
        print(f"Unique CUITs: {s['unique_cuits']:,}")
        print(f"Provinces: {len(s['provinces'])}")
        print(f"\nTop tipo_societario:")
        for tipo, count in s["tipo_societario_counts"].items():
            print(f"  {tipo}: {count:,}")
        return

    if args.benchmark:
        searcher.benchmark()
        return

    if args.search:
        results = searcher.search(args.search, provincia=args.provincia, limit=args.limit)
        if args.json:
            print(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))
        else:
            print(f"\nSearch: '{args.search}'" + (f" (provincia: {args.provincia})" if args.provincia else ""))
            print(f"Found: {len(results)} results\n")
            _print_results(results)
        return

    if args.autocomplete:
        results = searcher.autocomplete(args.autocomplete, provincia=args.provincia, limit=args.limit)
        if args.json:
            print(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))
        else:
            print(f"\nAutocomplete: '{args.autocomplete}'" + (f" (provincia: {args.provincia})" if args.provincia else ""))
            print(f"Found: {len(results)} results\n")
            _print_results(results)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
