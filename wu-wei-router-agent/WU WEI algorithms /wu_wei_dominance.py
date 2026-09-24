"""
wu_wei_dominance.py
===============================================================================
"Wu wei = the data-limited regime": ecosystem-as-inferrer + a dominance
theorem for rate-matched (minimal) intervention.

Mapping (exact, from the intelligence-bound engine):
  belief p        <-> relative abundance on the simplex
  likelihood      <-> intervention selection vector
  update rate     <-> intervention rate r_int (bits/step)
  KL(p'||p)       <-> community displacement (information injected)
  support loss    <-> EXTINCTION (absorbing simplex boundary)
  entropy of p    <-> biodiversity = recovery optionality

Two forces per step:
  ENDOGENOUS   : ecosystem pulls toward true environmental optimum p_env
                 (rich, all species viable) at intrinsic rate r_eco.
  INTERVENTION : manager pulls toward impoverished target p_star
                 (suppresses non-target species to a low floor) at rate r_int.

A species i viable under p_env reaches quasi-equilibrium abundance
  log p_i* ~ (r_eco*log p_env_i + r_int*log floor)/(r_eco+r_int),
and goes EXTINCT (absorbing) once p_i* < 1/N. So it survives iff
  r_int/r_eco  <  log(N*p_env_i)/log(p_env_i/floor)   (rate threshold).
Rarer species have lower thresholds => they die first as r_int rises.
Extinction is irreversible => long-run diversity is strictly lower above
threshold => r_int <= r_eco (wu wei) dominates.
===============================================================================
"""
import numpy as np

EPS = 1e-15


def _normalize(w):
    s = w.sum()
    return w / s if s > EPS else w


def kl_bits(p, q):
    m = p > 0
    return float(np.sum(p[m] * np.log2(p[m] / q[m]))) if np.all(q[m] > 0) else np.inf


def shannon_bits(p):
    m = p > 0
    return float(-np.sum(p[m] * np.log2(p[m])))


def resilience(p):
    """Fisher-Rao distance to extinction of the rarest extant species.
    Distance to face {q_i=0} = 2*arcsin(sqrt(p_i)); resilience = min over extant."""
    extant = p[p > 0]
    return float(2.0 * np.arcsin(np.sqrt(extant.min()))) if extant.size else 0.0


def selection_step(p, target, rate_bits):
    """Budgeted e-geodesic toward `target`: p' ∝ p^(1-a)*target^a, with a tuned
    so KL(p'||p) == rate_bits (capped at a=1). KL is monotone increasing in a."""
    pos = p > 0
    def tilt(a):
        w = np.zeros_like(p)
        w[pos] = p[pos] ** (1 - a) * target[pos] ** a
        return _normalize(w)
    if kl_bits(tilt(1.0), p) <= rate_bits + 1e-12:
        return tilt(1.0)
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if kl_bits(tilt(mid), p) - rate_bits > 0:
            hi = mid
        else:
            lo = mid
    return tilt(0.5 * (lo + hi))


def run_episode(p0, p_env, p_star, r_eco, r_int, N, steps, rng, noise=False):
    p = p0.copy()
    env_support = set(np.where(p_env > 1.0 / N)[0])   # species viable under p_env
    thr = 1.0 / N
    for _ in range(steps):
        p = selection_step(p, p_env, r_eco)      # nature's pace (fixed)
        p = selection_step(p, p_star, r_int)     # manager's pace (control)
        if noise:
            p = _normalize(rng.multinomial(N, _normalize(np.clip(p, 0, None))) / N)
        p = np.where(p < thr, 0.0, p)            # absorbing extinction
        p = _normalize(p)
    final_support = set(np.where(p > 0)[0])
    viable_lost = len(env_support - final_support)
    return dict(p=p, viable_lost=viable_lost, shannon=shannon_bits(p),
                resilience=resilience(p), support=len(final_support))


def build_world(n=10, m_target=4, N=300, seed=0):
    rng = np.random.default_rng(seed)
    p_env = _normalize(0.04 + 0.16 * rng.random(n))          # all viable, graded
    floor = 1e-4
    star = np.full(n, floor)
    idx = rng.choice(n, m_target, replace=False)
    star[idx] = 0.4 + rng.random(m_target)
    p_star = _normalize(star)
    p0 = p_env.copy()                                        # start at the rich state
    return p_env, p_star, p0, N


def sweep(seeds=60, steps=200):
    p_env, p_star, p0, N = build_world()
    r_eco = 0.15
    ratios = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0]
    rows = []
    for k in ratios:
        lost, shan, resil = [], [], []
        for s in range(seeds):
            rng = np.random.default_rng(1000 + s)
            out = run_episode(p0, p_env, p_star, r_eco, k * r_eco, N, steps, rng,
                              noise=True)
            lost.append(out["viable_lost"]); shan.append(out["shannon"])
            resil.append(out["resilience"])
        rows.append((k, np.mean([x > 0 for x in lost]), np.mean(lost),
                     np.mean(shan), np.mean(resil)))
    return p_env, p_star, r_eco, N, rows


if __name__ == "__main__":
    p_env, p_star, r_eco, N, rows = sweep()
    print(f"r_eco = {r_eco} bits/step | community N = {N} | "
          f"p_env viable = {int((p_env>1/N).sum())} species | "
          f"p_star target = {int((p_star>1e-3).sum())} species\n")
    print(f"{'r_int/r_eco':>11} | {'P(species loss)':>15} | {'mean lost':>9} | "
          f"{'Shannon bits':>12} | {'resilience':>10}")
    print("-" * 72)
    for k, pviol, mlost, shan, resil in rows:
        flag = "  <- wu wei" if k == 1.0 else ""
        print(f"{k:>11.2f} | {pviol:>15.3f} | {mlost:>9.2f} | {shan:>12.3f} | "
              f"{resil:>10.4f}{flag}")

    ks = [r[0] for r in rows]; pv = [r[1] for r in rows]; sh = [r[3] for r in rows]
    mono = all(pv[i] <= pv[i + 1] + 1e-6 for i in range(len(pv) - 1))
    below = max(p for k, p in zip(ks, pv) if k <= 1.0)
    dominance = sh[ks.index(1.0)] > sh[-1] + 1e-9
    print("\nInvariants:")
    print(f"  INV-1  extinction risk monotone increasing in r_int : {mono}")
    print(f"  INV-2  P(loss) at r_int<=r_eco                       : {below:.3f}")
    print(f"  INV-3  dominance: Shannon(wu wei) > Shannon(8x rate) : {dominance} "
          f"({sh[ks.index(1.0)]:.3f} vs {sh[-1]:.3f})")
