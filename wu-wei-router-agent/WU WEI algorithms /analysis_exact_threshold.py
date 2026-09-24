"""
Exact fixed point of the composed (endogenous + intervention) map, and the
closed-form wu-wei threshold r*.  Validates the deterministic theory against
the stochastic simulation's empirical cliff.

Derivation (log space).  Each force is an e-geodesic tilt:
    endogenous:    log p -> (1-a_e) log p + a_e log p_env  - log Z
    intervention:  log p -> (1-a_i) log p + a_i log p_star - log Z
Composing and solving log p* = (compose)(log p*) gives the EXACT fixed point
    p*_i  ∝  p_env,i^{w_env} · p_star,i^{w_star},
    w_star = a_i / (a_i + a_e - a_i a_e),   w_env = 1 - w_star,
a NORMALISED WEIGHTED GEOMETRIC MEAN of the two attractors.

A non-target species (p_star,i = floor f) sits at p*_i ∝ p_env,i^{w_env} f^{w_star}.
It is driven below one individual (extinct) when p*_i < 1/N.  At the symmetric
rate a_e = a_i (=> r_int = r_eco) the weights are 1/2 and
    p*_i = sqrt(p_env,i · f),
so the rarest species crosses 1/N exactly when  sqrt(p_env,min · f) = 1/N, i.e.
    f = 1 / (N^2 · p_env,min).
=> The cliff sits at r_int = r_eco precisely when the manager's suppression
   floor, community size, and rarest viable abundance satisfy N^2 f p_env,min = 1.
"""
import numpy as np
import wu_wei_dominance as w

EPS = 1e-300


def _norm(v):
    return v / v.sum()


def selection(p, target, rate_bits):
    return w.selection_step(p, target, rate_bits)


def deterministic_cycle_fixed_point(p_env, p_star, r_eco, r_int, iters=4000):
    """Iterate endogenous∘intervention with NO noise / NO extinction threshold.
    Return the post-intervention abundance (the per-cycle minimum phase)."""
    p = _norm(np.ones_like(p_env))
    for _ in range(iters):
        p = selection(p, p_env, r_eco)
        p = selection(p, p_star, r_int)
    return p


def fit_weights(p_star_post, p_env, p_star):
    """Recover (w_env, w_star) by least squares on log p* = w_env log p_env +
    w_star log p_star + c, over the target species (p_star > floor)."""
    mask = p_star > 1e-3
    A = np.column_stack([np.log(p_env[mask]), np.log(p_star[mask]),
                         np.ones(mask.sum())])
    b = np.log(p_star_post[mask] + EPS)
    coef, *_ = np.linalg.lstsq(A, b, rcond=None)
    return coef[0], coef[1]


if __name__ == "__main__":
    p_env, p_star, p0, N = w.build_world()
    r_eco = 0.15
    floor = 1e-4
    p_env_min = p_env.min()
    nontarget = p_star <= 1e-3

    print(f"N={N}  r_eco={r_eco}  p_env_min={p_env_min:.4f}  floor={floor}")
    print(f"1/N = {1/N:.5f}")
    print(f"symmetric-rate prediction sqrt(p_env_min*floor) = "
          f"{np.sqrt(p_env_min*floor):.5f}  "
          f"({'>' if np.sqrt(p_env_min*floor)>1/N else '<'} 1/N "
          f"=> cliff {'above' if np.sqrt(p_env_min*floor)>1/N else 'below'} r_eco)\n")

    print(f"{'r_int/r_eco':>11} | {'min nontarget p* (theory)':>25} | "
          f"{'survive? (>1/N)':>15} | {'empirical P(loss)':>17}")
    print("-" * 80)

    ratios = [0.25, 0.5, 0.7, 0.85, 0.95, 1.0, 1.25, 1.5, 2.0]
    det_thresh = None
    for k in ratios:
        p_post = deterministic_cycle_fixed_point(p_env, p_star, r_eco, k * r_eco)
        min_nt = p_post[nontarget].min()
        survive = min_nt > 1.0 / N
        if det_thresh is None and not survive:
            det_thresh = k
        # empirical loss prob from the stochastic sim
        loss = []
        for s in range(80):
            rng = np.random.default_rng(3000 + s)
            out = w.run_episode(p0, p_env, p_star, r_eco, k * r_eco, N, 200, rng,
                                noise=True)
            loss.append(out["viable_lost"] > 0)
        print(f"{k:>11.2f} | {min_nt:>25.6f} | {str(survive):>15} | "
              f"{np.mean(loss):>17.3f}")

    print(f"\nDeterministic threshold r* (min p* crosses 1/N): "
          f"~{det_thresh:.2f} x r_eco")

    # validate the weighted-geometric-mean fixed-point form at r_int = r_eco
    p_post = deterministic_cycle_fixed_point(p_env, p_star, r_eco, r_eco)
    w_env, w_star = fit_weights(p_post, p_env, p_star)
    print(f"\nFixed-point form check at r_int=r_eco:")
    print(f"  recovered weights  w_env={w_env:.3f}  w_star={w_star:.3f}  "
          f"(sum={w_env+w_star:.3f}, theory: equal => 0.5/0.5)")
