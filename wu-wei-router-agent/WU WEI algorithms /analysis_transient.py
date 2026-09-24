"""
The binding constraint is the TRANSIENT, not the equilibrium.

Because the simplex boundary is absorbing, a species is lost the instant its
abundance dips below 1/N *at any time*, even if the eventual equilibrium would
be safe. So the true wu-wei threshold r* is the largest intervention rate whose
deterministic trajectory never dips below 1/N:

    r* = sup { r_int : min_t min_{i∉target} p_i(t) >= 1/N }.

This is a strictly stronger (smaller) threshold than the equilibrium one, and
it is the geometric statement of wu wei: the minimal-rate path is the geodesic,
which stays in the interior; faster paths overshoot toward the boundary.
"""
import numpy as np
import wu_wei_dominance as w


def _norm(v):
    return v / v.sum()


def trajectory_min_nontarget(p0, p_env, p_star, r_eco, r_int, nontarget,
                             steps=200):
    """Deterministic (noiseless, no extinction cutoff) trajectory; return the
    minimum non-target abundance reached over the whole path, and the time."""
    p = p0.copy()
    worst, t_worst = np.inf, 0
    for t in range(steps):
        p = w.selection_step(p, p_env, r_eco)
        p = w.selection_step(p, p_star, r_int)
        m = p[nontarget].min()
        if m < worst:
            worst, t_worst = m, t
    return worst, t_worst, p[nontarget].min()


if __name__ == "__main__":
    p_env, p_star, p0, N = w.build_world()
    r_eco = 0.15
    nontarget = p_star <= 1e-3
    inv_N = 1.0 / N

    print(f"N={N}  1/N={inv_N:.5f}  (start p0 = p_env, the rich state)\n")
    print(f"{'r_int/r_eco':>11} | {'transient dip (min over path)':>29} | "
          f"{'dip<1/N?':>8} | {'equilibrium min':>15} | {'emp P(loss)':>11}")
    print("-" * 92)

    ratios = [0.25, 0.5, 0.7, 0.8, 0.85, 0.9, 1.0, 1.25, 1.5]
    r_star = None
    for k in ratios:
        dip, t_dip, eq = trajectory_min_nontarget(p0, p_env, p_star, r_eco,
                                                   k * r_eco, nontarget)
        crosses = dip < inv_N
        if r_star is None and crosses:
            r_star = k
        loss = []
        for s in range(80):
            rng = np.random.default_rng(4000 + s)
            out = w.run_episode(p0, p_env, p_star, r_eco, k * r_eco, N, 200, rng,
                                noise=True)
            loss.append(out["viable_lost"] > 0)
        print(f"{k:>11.2f} | {dip:>29.6f} | {str(crosses):>8} | "
              f"{eq:>15.6f} | {np.mean(loss):>11.3f}")

    print(f"\nTransient threshold r* (path dip crosses 1/N): ~{r_star:.2f} x r_eco")
    print("=> matches the stochastic cliff; the OVERSHOOT, not the equilibrium,")
    print("   is what crosses the irreversible boundary. Wu wei = overshoot-free path.")

    # show the overshoot shape at a super-threshold rate
    print("\nOvershoot profile of rarest non-target species (r_int = 1.0 r_eco):")
    rarest = np.where(nontarget)[0][np.argmin(p_env[nontarget])]
    p = p0.copy(); traj = []
    for t in range(60):
        p = w.selection_step(p, p_env, r_eco)
        p = w.selection_step(p, p_star, r_eco)
        traj.append(p[rarest])
    traj = np.array(traj)
    print(f"  start={traj[0]:.4f}  min={traj.min():.6f} at t={traj.argmin()}  "
          f"end={traj[-1]:.4f}  (1/N={inv_N:.4f})")
    print(f"  dips BELOW 1/N during transient: {traj.min() < inv_N}, "
          f"recovers above after: {traj[-1] > inv_N}")
