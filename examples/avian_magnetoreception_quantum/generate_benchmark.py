"""Regenerate data/frontier_benchmark.json.

Question this answers: for the singlet yield of a radical pair with N coupled
nuclei, how far can exact simulation go on a laptop, and does a correlated
sampling (typicality) estimator agree with it where both can run?

Model. Two electron spins plus N spin-1/2 nuclei, all hyperfine-coupled to
electron 1, in a magnetic field along z:

    H = sum_i a_i (S1 . I_i) + omega (S1z + S2z)

The pair is born singlet with the nuclei unpolarized, and recombines at rate k.
The singlet yield is

    Phi_S = k * integral_0^inf exp(-k t) <P_S>(t) dt

Exact evaluation averages over all 2^N nuclear basis states. The typicality
estimator replaces that average with R random nuclear states. That is the whole
comparison: 2^N propagations against R.

The reported observable is the magnetic field effect, MFE = Phi_S(B) - Phi_S(0).

Run:  python generate_benchmark.py --max-n 16 --exact-max-n 10
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp

K_REC = 1.0  # recombination rate, sets the time unit
OMEGA = 1.4  # Zeeman splitting at "present-day" field, same units
T_MAX = 12.0  # integrate exp(-k t) out to where it is negligible
N_TIME = 120  # Simpson steps over [0, T_MAX]; see --self-test control 4

SX = sp.csr_matrix(np.array([[0, 1], [1, 0]], dtype=complex) / 2)
SY = sp.csr_matrix(np.array([[0, -1j], [1j, 0]], dtype=complex) / 2)
SZ = sp.csr_matrix(np.array([[1, 0], [0, -1]], dtype=complex) / 2)
ID2 = sp.identity(2, dtype=complex, format="csr")


def _op_on(site: int, op: sp.spmatrix, n_sites: int) -> sp.spmatrix:
    """Embed a single-site operator into the full n_sites tensor product."""
    out = sp.identity(1, dtype=complex, format="csr")
    for s in range(n_sites):
        out = sp.kron(out, op if s == site else ID2, format="csr")
    return out


def couplings(n_nuclei: int, seed: int = 20260907) -> np.ndarray:
    """Fixed, reproducible hyperfine couplings spanning a realistic range."""
    rng = np.random.default_rng(seed)
    return np.sort(rng.uniform(0.2, 2.0, size=n_nuclei))[::-1]


def hamiltonian(n_nuclei: int, omega: float) -> sp.spmatrix:
    """Sites are ordered [electron1, electron2, nucleus_0 .. nucleus_{N-1}]."""
    n_sites = 2 + n_nuclei
    a = couplings(n_nuclei)
    h = sp.csr_matrix((2**n_sites, 2**n_sites), dtype=complex)
    for i in range(n_nuclei):
        for op in (SX, SY, SZ):
            h = h + a[i] * (_op_on(0, op, n_sites) @ _op_on(2 + i, op, n_sites))
    if omega:
        h = h + omega * (_op_on(0, SZ, n_sites) + _op_on(1, SZ, n_sites))
    return h.tocsr()


def singlet_projector(n_nuclei: int) -> sp.spmatrix:
    """P_S on the two electrons, identity on the nuclei."""
    s = np.zeros(4, dtype=complex)
    s[1] = 1 / np.sqrt(2)  # |01>
    s[2] = -1 / np.sqrt(2)  # |10>
    p_elec = sp.csr_matrix(np.outer(s, s.conj()))
    return sp.kron(p_elec, sp.identity(2**n_nuclei, format="csr"), format="csr")


def _singlet_born(nuclear: np.ndarray) -> np.ndarray:
    """|S> tensor (nuclear block of column vectors)."""
    n_nuc_dim, n_cols = nuclear.shape
    out = np.zeros((4 * n_nuc_dim, n_cols), dtype=complex)
    out[1 * n_nuc_dim : 2 * n_nuc_dim] = nuclear / np.sqrt(2)
    out[2 * n_nuc_dim : 3 * n_nuc_dim] = -nuclear / np.sqrt(2)
    return out


def singlet_yields(n_nuclei: int, omega: float, nuclear: np.ndarray) -> np.ndarray:
    """Phi_S for each supplied nuclear state, propagating all columns together.

    Returns one yield per column, so the caller can take both the mean and the
    sample spread without re-propagating.
    """
    from scipy.sparse.linalg import expm_multiply

    h = hamiltonian(n_nuclei, omega)
    p_s = singlet_projector(n_nuclei)
    psi = _singlet_born(nuclear)

    dt = T_MAX / N_TIME
    weights = np.array(
        [1 if i in (0, N_TIME) else (4 if i % 2 else 2) for i in range(N_TIME + 1)],
        dtype=float,
    )
    total = np.zeros(psi.shape[1])
    step_prop = -1j * h * dt
    for step in range(N_TIME + 1):
        overlap = np.einsum("ij,ij->j", psi.conj(), p_s @ psi).real
        total += weights[step] * np.exp(-K_REC * step * dt) * overlap
        if step < N_TIME:
            psi = expm_multiply(step_prop, psi)
    return K_REC * total * dt / 3.0


def singlet_yield(n_nuclei: int, omega: float, nuclear: np.ndarray) -> float:
    """Phi_S averaged over the supplied nuclear states."""
    return float(singlet_yields(n_nuclei, omega, nuclear).mean())


def mfe_exact(n_nuclei: int) -> float:
    """Average over the complete 2^N nuclear basis."""
    nuclear = np.eye(2**n_nuclei, dtype=complex)
    return singlet_yield(n_nuclei, OMEGA, nuclear) - singlet_yield(
        n_nuclei, 0.0, nuclear
    )


def mfe_typicality(n_nuclei: int, n_samples: int, seed: int) -> tuple[float, float]:
    """Correlated sampling: the SAME random states are used at both field values.

    Returns (mean MFE, standard error of that mean).
    """
    rng = np.random.default_rng(seed)
    dim = 2**n_nuclei
    v = rng.normal(size=(dim, n_samples)) + 1j * rng.normal(size=(dim, n_samples))
    v /= np.linalg.norm(v, axis=0, keepdims=True)
    per_sample = singlet_yields(n_nuclei, OMEGA, v) - singlet_yields(n_nuclei, 0.0, v)
    return float(per_sample.mean()), float(per_sample.std(ddof=1) / np.sqrt(n_samples))


def self_test() -> bool:
    """Controls that must pass before any number here is worth quoting.

    1. The estimator converges to the exact answer as R grows, and its reported
       error bar is calibrated (deviation stays of order one sigma).
    2. The exact average does not depend on how the nuclear basis is ordered.
    3. A zero-field-against-zero-field comparison returns exactly zero.
    4. The time grid is converged, so the quoted digits are not integrator error.
    """
    ok = True

    print("1. convergence and error-bar calibration (N=6)")
    exact6 = mfe_exact(6)
    print(f"   exact = {exact6:.5f}")
    for r in (8, 32, 128, 512):
        typ, err = mfe_typicality(6, r, seed=7)
        ratio = abs(typ - exact6) / err
        flag = "ok" if ratio < 3.0 else "FAIL"
        ok &= ratio < 3.0
        print(
            f"   R={r:4d}: {typ:.5f} +/- {err:.5f}  deviation {ratio:.2f} sigma  {flag}"
        )

    print("2. nuclear basis ordering must not matter (N=3)")
    eye = np.eye(2**3, dtype=complex)
    perm = np.random.default_rng(0).permutation(2**3)
    a = singlet_yield(3, OMEGA, eye) - singlet_yield(3, 0.0, eye)
    b = singlet_yield(3, OMEGA, eye[:, perm]) - singlet_yield(3, 0.0, eye[:, perm])
    same = bool(np.isclose(a, b))
    ok &= same
    print(f"   ordered {a:.6f} vs permuted {b:.6f}  {'ok' if same else 'FAIL'}")

    print("3. zero-field null must return exactly zero (N=3)")
    null = singlet_yield(3, 0.0, eye) - singlet_yield(3, 0.0, eye)
    ok &= null == 0.0
    print(f"   MFE(0 vs 0) = {null:.1e}  {'ok' if null == 0.0 else 'FAIL'}")

    print("4. time grid must be converged (N=4)")
    global T_MAX, N_TIME
    coarse_t, coarse_n = T_MAX, N_TIME
    eye4 = np.eye(2**4, dtype=complex)
    ref = singlet_yield(4, OMEGA, eye4) - singlet_yield(4, 0.0, eye4)
    T_MAX, N_TIME = 24.0, 720
    fine = singlet_yield(4, OMEGA, eye4) - singlet_yield(4, 0.0, eye4)
    T_MAX, N_TIME = coarse_t, coarse_n
    drift = abs(fine - ref)
    ok &= drift < 1e-4
    print(
        f"   shipped grid {ref:.6f} vs fine grid {fine:.6f}  drift {drift:.1e}  "
        f"{'ok' if drift < 1e-4 else 'FAIL'}"
    )

    print("\nself-test:", "PASS" if ok else "FAIL")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-n", type=int, default=16)
    ap.add_argument("--exact-max-n", type=int, default=10)
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument(
        "--self-test", action="store_true", help="run the controls and exit"
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent / "data" / "frontier_benchmark.json",
    )
    args = ap.parse_args()

    if args.self_test:
        raise SystemExit(0 if self_test() else 1)

    rows = []
    for n in range(1, args.max_n + 1):
        row = {"N": n, "dim": 4 * 2**n, "R": args.samples}

        if n <= args.exact_max_n:
            t0 = time.perf_counter()
            row["exact"] = mfe_exact(n)
            row["exact_t"] = time.perf_counter() - t0
        else:
            row["exact"] = None
            row["exact_t"] = None

        t0 = time.perf_counter()
        typ, err = mfe_typicality(n, args.samples, args.seed)
        row["typ"] = typ
        row["typ_err"] = err
        row["typ_t"] = time.perf_counter() - t0
        row["typ_vs_exact"] = None if row["exact"] is None else abs(typ - row["exact"])

        rows.append(row)
        exact_txt = "    -    " if row["exact"] is None else f"{row['exact']:.5f}"
        exact_t_txt = "  -  " if row["exact_t"] is None else f"{row['exact_t']:.2f}s"
        print(
            f"N={n:2d} dim={row['dim']:7d} exact={exact_txt} ({exact_t_txt}) "
            f"typ={typ:.5f} +/- {err:.5f} ({row['typ_t']:.2f}s)",
            flush=True,
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=1) + "\n")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
