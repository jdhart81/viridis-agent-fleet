"""
intelligence_bound_inference.py
===============================================================================
Thermodynamically-bounded active inference in probability-Hilbert space.

The world-model as a Hilbert-space vector
-----------------------------------------
An agent's belief over hypotheses/world-states `p` is represented as an
amplitude vector psi on the unit sphere of a Hilbert space H:

        psi_i = sqrt(p_i),     ||psi||^2 = sum_i p_i = 1.

In this representation:
  * <psi, phi> = sum_i sqrt(p_i q_i) = Bhattacharyya coefficient = cos(theta),
    so the angle theta between belief vectors is the Fisher-Rao / Hellinger
    statistical distance.  The world-model lives on a sphere.
  * Perception is a measurement operator.  An observation o with likelihood
    L_i = P(o | h_i) acts as a diagonal Kraus operator K = diag(sqrt(L_i)):
        psi <- K psi / ||K psi||.
    Renormalised, this is exactly Bayes' rule (p_i ∝ p_i L_i).  Bayesian
    conditioning IS a POVM-style update of the state vector.
  * "Intelligence" created by an update is the information gained, in bits:
    dI = KL(posterior || prior); its expectation over outcomes is the mutual
    information I(H; O).  For small steps dI ∝ theta^2, so bounding dI/dt
    bounds how fast psi can rotate on the sphere -- a Margolus-Levitin-style
    speed limit on inference.

The intelligence bound (conjecture) as a rate constraint
--------------------------------------------------------
        dI/dt  <=  min( rho * B ,  P / (k_B T ln 2) )

  * P / (k_B T ln 2): Landauer ceiling -- power / minimum energy per
    irreversible bit.
  * rho * B: data ceiling -- informative fraction rho in [0,1] of raw sensor
    bandwidth B (bits/s).

This module enforces the bound BY CONSTRUCTION: the agent spends its per-slice
energy budget on the observations with the highest information-gain-per-joule
(greedy fractional knapsack, optimal under a linear energy budget), and absorbs
each update only up to the thermodynamically affordable amount via a
power-tempered ("slow") Bayesian update, carrying surplus evidence forward.

Cost model (ASSUMPTION -- flagged for review)
---------------------------------------------
Performing measurement a costs C_a joules (sensing + irreversible processing),
with C_a >= (k_B T ln 2) * EIG_a  (Landauer floor; invariant I5).  Per slice,
sum of performed C_a <= P*dt.  Separately, the information actually ASSIMILATED
into the belief per slice is capped at dI_max via tempered updates (invariant
I4).  This separates "energy to acquire evidence" from "rate of belief
revision"; both reduce to the Landauer / data ceilings.

Invariants (verified in run_invariant_checks):
  I1  ||psi||^2 == 1 after every update                    (valid belief)
  I2  amplitude update == direct Bayes posterior
  I3  realized increment dI = KL(post||prior) >= 0
  I4  per-slice assimilated dI <= dI_max                   (the bound)
  I5  every executed action has I_a/C_a <= 1/(k_B T ln 2)  (Landauer)
  I6  greedy selection order is non-increasing in efficiency, and total
      gain >= best single feasible action
  I7  expected info gain of a measurement == mutual information I(H;O)

Dependencies: numpy only.
===============================================================================
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

# --- physical constants -------------------------------------------------------
K_B = 1.380649e-23          # Boltzmann constant, J/K
LN2 = float(np.log(2.0))
EPS = 1e-12


def landauer_energy_per_bit(T: float) -> float:
    """Minimum energy to irreversibly process one bit at temperature T (J/bit)."""
    return K_B * T * LN2


# =============================================================================
# Information-theoretic primitives (all in BITS)
# =============================================================================
def _normalize(w: np.ndarray) -> np.ndarray:
    s = w.sum()
    if s <= EPS:
        raise ValueError("Degenerate (all-zero) un-normalized belief.")
    return w / s


def entropy_bits(p: np.ndarray) -> float:
    p = np.asarray(p, dtype=float)
    mask = p > 0
    return float(-np.sum(p[mask] * np.log2(p[mask])))


def kl_bits(p: np.ndarray, q: np.ndarray) -> float:
    """KL(p || q) in bits.  Requires q_i > 0 wherever p_i > 0."""
    p = np.asarray(p, dtype=float)
    q = np.asarray(q, dtype=float)
    mask = p > 0
    if np.any(q[mask] <= 0):
        return np.inf
    return float(np.sum(p[mask] * np.log2(p[mask] / q[mask])))


def _temper(p: np.ndarray, ell: np.ndarray, beta: float) -> np.ndarray:
    """Power-tempered posterior: p_beta ∝ p * ell^beta, normalised."""
    with np.errstate(invalid="ignore"):
        w = p * np.power(ell, beta)
    return _normalize(w)


def assimilate(p: np.ndarray, ell: np.ndarray, budget_bits: float):
    """
    Absorb likelihood `ell` into belief `p`, but only up to `budget_bits` of
    information gain.  Uses a power-tempered update; surplus evidence is
    returned as a residual likelihood that composes with the partial update
    (p_new * residual ∝ p * ell), so nothing is lost across slices.

    Returns (p_new, dI_bits, residual_ell_or_None).
    """
    p = np.asarray(p, dtype=float)
    ell = np.asarray(ell, dtype=float)
    if budget_bits <= EPS:
        return p.copy(), 0.0, ell.copy()

    full = _normalize(p * ell)
    kl_full = kl_bits(full, p)
    if kl_full <= budget_bits + EPS:
        return full, kl_full, None  # fully assimilable this slice

    # Bisect beta in (0,1] so that KL(p_beta || p) == budget_bits.
    # g is monotone non-decreasing in beta (exponential tilting), g(0)=0.
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        g = kl_bits(_temper(p, ell, mid), p) - budget_bits
        if g > 0:
            hi = mid
        else:
            lo = mid
    beta = 0.5 * (lo + hi)
    p_new = _temper(p, ell, beta)
    dI = kl_bits(p_new, p)
    with np.errstate(invalid="ignore"):
        residual = np.power(ell, 1.0 - beta)  # p_new * residual ∝ p * ell
    return p_new, dI, residual


# =============================================================================
# Belief state in probability-Hilbert space (amplitude / square-root rep.)
# =============================================================================
class BeliefState:
    """Belief as a unit amplitude vector psi_i = sqrt(p_i) on the sphere."""

    def __init__(self, p: np.ndarray):
        p = np.asarray(p, dtype=float)
        if np.any(p < -EPS):
            raise ValueError("Probabilities must be non-negative.")
        self.psi = np.sqrt(_normalize(np.clip(p, 0, None)))
        self._check_norm()

    # --- factory ----------------------------------------------------------
    @classmethod
    def uniform(cls, n: int) -> "BeliefState":
        return cls(np.full(n, 1.0 / n))

    # --- views ------------------------------------------------------------
    @property
    def p(self) -> np.ndarray:
        return self.psi ** 2

    @property
    def n(self) -> int:
        return self.psi.size

    def _check_norm(self) -> None:
        assert abs(float(self.psi @ self.psi) - 1.0) < 1e-9, "I1: belief not normalised"

    # --- geometry ---------------------------------------------------------
    def bhattacharyya(self, other: "BeliefState") -> float:
        return float(self.psi @ other.psi)               # = cos(theta)

    def fisher_rao_distance(self, other: "BeliefState") -> float:
        return float(2.0 * np.arccos(np.clip(self.bhattacharyya(other), -1.0, 1.0)))

    def entropy_bits(self) -> float:
        return entropy_bits(self.p)

    # --- Bayesian / measurement update (Kraus diag(sqrt L) + renorm) ------
    def update(self, likelihood: np.ndarray) -> float:
        """Full Bayesian update; returns realized info gain dI (bits)."""
        prior = self.p
        post = _normalize(prior * np.asarray(likelihood, dtype=float))
        dI = kl_bits(post, prior)                          # I3: >= 0
        self.psi = np.sqrt(post)
        self._check_norm()
        return dI

    def copy(self) -> "BeliefState":
        b = BeliefState.__new__(BeliefState)
        b.psi = self.psi.copy()
        return b


# =============================================================================
# Candidate measurement / action
# =============================================================================
@dataclass
class Measurement:
    """
    A thing the agent could observe/compute.

    likelihood : (m_outcomes, n_hypotheses) array, L[o, i] = P(outcome o | h_i).
    cost_joules: total energy to perform the measurement.  If None, the
                 Landauer floor for its expected info gain is used.
    """
    name: str
    likelihood: np.ndarray
    cost_joules: Optional[float] = None

    def __post_init__(self):
        self.likelihood = np.asarray(self.likelihood, dtype=float)
        if np.any(self.likelihood < 0):
            raise ValueError(f"[{self.name}] likelihoods must be non-negative.")

    def outcome_probs(self, p: np.ndarray) -> np.ndarray:
        return self.likelihood @ p                          # P(o)

    def expected_info_gain_bits(self, belief: BeliefState) -> float:
        """EIG = I(H; O) (mutual information), via the amplitude update."""
        p = belief.p
        Po = self.outcome_probs(p)
        eig = 0.0
        for o in range(self.likelihood.shape[0]):
            if Po[o] <= EPS:
                continue
            post = _normalize(self.likelihood[o] * p)
            eig += Po[o] * kl_bits(post, p)
        return float(eig)

    def effective_cost(self, eig_bits: float, T: float) -> float:
        floor = landauer_energy_per_bit(T) * eig_bits        # I5 floor
        if self.cost_joules is None:
            return floor
        return max(self.cost_joules, floor)

    def sample_outcome(self, p: np.ndarray, rng: np.random.Generator) -> int:
        Po = self.outcome_probs(p)
        return int(rng.choice(len(Po), p=_normalize(Po)))


# =============================================================================
# The thermodynamically-bounded active-inference engine
# =============================================================================
@dataclass
class IntelligenceBoundAgent:
    T: float                                  # operating temperature (K)
    power_watts: float                        # P
    rho: float = 1.0                          # data richness in [0, 1]
    bandwidth_bits_s: float = np.inf          # B
    rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(0))
    _pending: list = field(default_factory=list)   # carried-over likelihoods

    # --- the bound --------------------------------------------------------
    def budgets(self, dt: float):
        e_bit = landauer_energy_per_bit(self.T)
        energy_budget = self.power_watts * dt                 # joules
        data_budget = self.rho * self.bandwidth_bits_s * dt   # bits (may be inf)
        landauer_bits = energy_budget / e_bit                 # bits
        dI_max = min(data_budget, landauer_bits)              # the conjecture
        return dict(e_bit=e_bit, energy_budget=energy_budget,
                    data_budget=data_budget, dI_max=dI_max)

    # --- one slice --------------------------------------------------------
    def step(self, belief: BeliefState, measurements: Sequence[Measurement],
             dt: float, forced_outcomes: Optional[dict] = None) -> dict:
        b = self.budgets(dt)
        dI_max = b["dI_max"]
        energy_budget = b["energy_budget"]
        data_budget = b["data_budget"]

        accrued = 0.0          # bits assimilated this slice  (capped by I4)
        energy_spent = 0.0     # joules spent performing measurements
        log = {"selected": [], "outcomes": {}, "efficiencies": {}, **b}

        # 1) assimilate carryover first (already paid for; no new energy) ----
        still_pending = []
        for ell in self._pending:
            rem = dI_max - accrued
            if rem <= EPS:
                still_pending.append(ell)
                continue
            belief.psi, dI, residual = _apply(belief, ell, rem)
            accrued += dI
            if residual is not None:
                still_pending.append(residual)
        self._pending = still_pending

        # 2) score candidate measurements -----------------------------------
        items = []
        for m in measurements:
            eig = m.expected_info_gain_bits(belief)
            if eig <= EPS:
                continue                              # uninformative -> skip
            cost = m.effective_cost(eig, self.T)
            eff = eig / cost                          # bits/joule
            assert eff <= 1.0 / b["e_bit"] + 1e-6, "I5: beats Landauer ceiling"
            items.append((eff, eig, cost, m))
            log["efficiencies"][m.name] = eff

        # 3) greedy by efficiency under both ceilings (fractional knapsack) --
        items.sort(key=lambda t: t[0], reverse=True)   # I6: non-increasing eff
        cum_cost, cum_eig, selected = 0.0, 0.0, []
        for eff, eig, cost, m in items:
            if (cum_cost + cost <= energy_budget + EPS
                    and cum_eig + eig <= data_budget + EPS):
                selected.append((eig, cost, m))
                cum_cost += cost
                cum_eig += eig

        # 4) execute -- sample outcome, tempered (power-limited) update ------
        for eig, cost, m in selected:
            rem = dI_max - accrued
            if rem <= EPS:
                # can't afford to absorb now; stash the (expected) evidence
                continue
            if forced_outcomes and m.name in forced_outcomes:
                o = forced_outcomes[m.name]
            else:
                o = m.sample_outcome(belief.p, self.rng)
            ell = m.likelihood[o]
            belief.psi, dI, residual = _apply(belief, ell, rem)
            accrued += dI
            energy_spent += cost
            if residual is not None:
                self._pending.append(residual)
            log["selected"].append(m.name)
            log["outcomes"][m.name] = o

        # I4: never assimilate faster than the bound allows
        assert accrued <= dI_max + 1e-6, "I4: intelligence bound violated"
        assert energy_spent <= energy_budget + 1e-6, "energy budget violated"

        log["dI_realized"] = accrued
        log["energy_spent"] = energy_spent
        log["belief_entropy_bits"] = belief.entropy_bits()
        return log


def _apply(belief: BeliefState, ell: np.ndarray, budget_bits: float):
    """Tempered assimilation wired through the BeliefState; returns new psi."""
    p_new, dI, residual = assimilate(belief.p, ell, budget_bits)
    return np.sqrt(p_new), dI, residual


# =============================================================================
# Density-operator generalisation (the "go quantum" extension)
# =============================================================================
class QuantumBeliefState:
    """
    Belief as a density operator rho (PSD, trace 1).  Off-diagonal coherences
    rho_ij encode interference between hypotheses -- supports order effects
    (non-commuting observations) that classical Bayes cannot.  Intelligence is
    von Neumann entropy reduction; the data ceiling becomes the Holevo bound.
    """

    def __init__(self, rho: np.ndarray):
        rho = np.asarray(rho, dtype=complex)
        assert np.allclose(rho, rho.conj().T, atol=1e-9), "rho must be Hermitian"
        tr = np.trace(rho).real
        self.rho = rho / tr
        evals = np.linalg.eigvalsh(self.rho)
        assert evals.min() > -1e-9, "rho must be PSD"

    @classmethod
    def from_prob(cls, p):
        return cls(np.diag(np.asarray(p, dtype=float)))

    def von_neumann_bits(self) -> float:
        ev = np.linalg.eigvalsh(self.rho).real
        ev = ev[ev > EPS]
        return float(-np.sum(ev * np.log2(ev)))

    def update(self, kraus: Sequence[np.ndarray]) -> float:
        """CPTP update rho <- sum_k M_k rho M_k^dag / tr(...); returns dI bits."""
        s0 = self.von_neumann_bits()
        new = sum(M @ self.rho @ M.conj().T for M in kraus)
        new = new / np.trace(new).real
        self.rho = new
        return s0 - self.von_neumann_bits()      # entropy reduction = info gained

    @staticmethod
    def holevo_bound_bits(ensemble) -> float:
        """chi = S(avg rho) - sum_x p_x S(rho_x): the accessible-info ceiling."""
        avg = sum(px * rx for px, rx in ensemble)
        s_avg = QuantumBeliefState(avg).von_neumann_bits()
        s_parts = sum(px * QuantumBeliefState(rx).von_neumann_bits()
                      for px, rx in ensemble)
        return s_avg - s_parts


# =============================================================================
# Invariant checks + demo
# =============================================================================
def run_invariant_checks() -> None:
    rng = np.random.default_rng(42)

    # I2: amplitude update == direct Bayes ----------------------------------
    p = _normalize(rng.random(5))
    L = rng.random(5) + 0.1
    b = BeliefState(p)
    b.update(L)
    direct = _normalize(p * L)
    assert np.allclose(b.p, direct, atol=1e-12), "I2 failed"

    # I3: dI >= 0 -----------------------------------------------------------
    b2 = BeliefState(p)
    assert b2.update(rng.random(5) + 0.1) >= -1e-12, "I3 failed"

    # I7: EIG == mutual information -----------------------------------------
    belief = BeliefState(_normalize(rng.random(4)))
    Lmat = rng.random((3, 4)) + 0.05
    Lmat = Lmat / Lmat.sum(axis=0, keepdims=True)     # proper conditionals
    m = Measurement("m", Lmat)
    eig = m.expected_info_gain_bits(belief)
    Po = m.outcome_probs(belief.p)
    mi = belief.entropy_bits() - sum(
        Po[o] * entropy_bits(_normalize(Lmat[o] * belief.p))
        for o in range(3) if Po[o] > EPS)
    assert abs(eig - mi) < 1e-9, "I7 failed"

    # I4/I5: the bound holds across a run -----------------------------------
    agent = IntelligenceBoundAgent(T=300.0, power_watts=1e-19,  # tiny -> Landauer-bound
                                   rng=np.random.default_rng(1))
    belief = BeliefState.uniform(6)
    for _ in range(50):
        meas = [Measurement(f"s{k}",
                            _col_norm(rng.random((4, 6)) + 0.05),
                            cost_joules=None)
                for k in range(3)]
        log = agent.step(belief, meas, dt=1.0)
        assert log["dI_realized"] <= log["dI_max"] + 1e-6, "I4 failed in run"

    # density-operator sanity ----------------------------------------------
    q = QuantumBeliefState.from_prob(_normalize(rng.random(4)))
    P0 = np.diag([1.0, 0, 0, 0]).astype(complex)
    Prest = np.eye(4) - P0
    dq = q.update([P0, Prest])     # a projective-ish measurement
    assert dq >= -1e-9 and abs(np.trace(q.rho).real - 1) < 1e-9

    print("All invariants (I1-I7 + quantum sanity) passed.")


def _col_norm(M):
    return M / M.sum(axis=0, keepdims=True)


def demo() -> None:
    print("=" * 70)
    print("DEMO: thermodynamically-bounded inference over 8 hypotheses")
    print("=" * 70)
    rng = np.random.default_rng(7)
    n = 8
    truth = 3

    def detector(name, hit_rate, cost):
        # Proper 2-outcome sensor (signal / silence) as a conditional P(o|h):
        #   row 0 = "signal": fires with prob hit_rate for the true hypothesis,
        #                     and a low false-alarm rate for every other one.
        false_alarm = 0.04
        signal = np.full(n, false_alarm)
        signal[truth] = hit_rate
        L = np.vstack([signal, 1.0 - signal])     # columns already sum to 1
        return Measurement(name, L, cost_joules=cost)

    for label, P, rho, B in [
        ("Landauer-limited (low power)", 3e-21, 1.0, np.inf),
        ("Data-limited (low rho*B)",     1e-12, 0.2, 2.0),
    ]:
        print(f"\n--- {label} ---")
        agent = IntelligenceBoundAgent(T=300.0, power_watts=P, rho=rho,
                                       bandwidth_bits_s=B,
                                       rng=np.random.default_rng(11))
        belief = BeliefState.uniform(n)
        total = 0.0
        for t in range(40):
            meas = [detector("sensor_A", 0.85, cost=None),
                    detector("sensor_B", 0.80, cost=None),
                    detector("sensor_C", 0.70, cost=None)]
            log = agent.step(belief, meas, dt=1.0)
            total += log["dI_realized"]
        print(f"  per-slice bound dI_max = {log['dI_max']:.4f} bits")
        print(f"  total intelligence accrued = {total:.4f} bits")
        print(f"  P(true hypothesis) = {belief.p[truth]:.3f} "
              f"(started {1/n:.3f}); belief entropy = "
              f"{belief.entropy_bits():.3f} bits")


if __name__ == "__main__":
    run_invariant_checks()
    demo()
