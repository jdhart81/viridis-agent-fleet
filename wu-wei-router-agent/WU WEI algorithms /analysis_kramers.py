"""Kramers / mean-first-passage diagnostic (trimmed for speed)."""
import numpy as np

EPS = 1e-15
def _norm(v): return v / v.sum()
def kl_bits(p, q):
    m = p > 0
    return float(np.sum(p[m]*np.log2(p[m]/q[m]))) if np.all(q[m] > 0) else np.inf

def fast_step(p, target, rate):
    """KL-budgeted e-geodesic toward target; 24-iter bisection."""
    pos = p > 0
    def tilt(a):
        w = np.zeros_like(p); w[pos] = p[pos]**(1-a) * target[pos]**a
        return _norm(w)
    if kl_bits(tilt(1.0), p) <= rate + 1e-9: return tilt(1.0)
    lo, hi = 0.0, 1.0
    for _ in range(24):
        mid = 0.5*(lo+hi)
        if kl_bits(tilt(mid), p) - rate > 0: hi = mid
        else: lo = mid
    return tilt(0.5*(lo+hi))

def build():
    rng = np.random.default_rng(0)
    p_env = _norm(0.04 + 0.16*rng.random(10))
    star = np.full(10, 1e-4); idx = rng.choice(10, 4, replace=False)
    star[idx] = 0.4 + rng.random(4)
    return p_env, _norm(star), p_env.copy(), 300

def first_passage(p0, p_env, p_star, r_eco, r_int, N, maxst, rng, nt):
    p = p0.copy(); thr = 1.0/N; env_nt = set(np.where(nt)[0])
    for t in range(1, maxst+1):
        p = fast_step(p, p_env, r_eco)
        p = fast_step(p, p_star, r_int)
        p = _norm(np.where(p < thr, 0.0, p))
        p = _norm(rng.multinomial(N, p)/N)
        if env_nt - set(np.where(p > 0)[0]): return t
    return maxst

p_env, p_star, p0, N = build()
r_eco = 0.15; nt = p_star <= 1e-3; MAX = 400
print(f"N={N} r_eco={r_eco} obs_window={MAX} (mgmt horizon ~200)\n")
print(f"{'r_int/r_eco':>11} | {'MFPT (cens@400)':>15} | {'log10':>6} | {'P(loss<=200)':>12}")
print("-"*54)
ratios = [0.4, 0.55, 0.7, 0.8, 0.9, 1.0]
mf = []
for k in ratios:
    fps = np.array([first_passage(p0, p_env, p_star, r_eco, k*r_eco, N, MAX,
                    np.random.default_rng(5000+s), nt) for s in range(40)])
    mf.append(fps.mean())
    print(f"{k:>11.2f} | {fps.mean():>15.1f} | {np.log10(fps.mean()):>6.2f} | {np.mean(fps<=200):>12.3f}")
ks = np.array(ratios); lm = np.log10(np.array(mf)); safe = ks <= 0.8
A = np.polyfit(ks[safe], lm[safe], 1)
print(f"\nArrhenius slope (log10 MFPT vs rate, safe branch) = {A[0]:.2f}/unit  "
      f"=> ~{10**(-A[0]):.0f}x MFPT drop per 1.0 r_eco of added rate")
