import os
import pickle
import numpy as np
import jax
import jax.numpy as jnp
from jax import lax

# ==========================================
# GLOBAL STATE
# ==========================================
_ML_PACKAGE = None
_SEIR_FORWARD_JIT = None
_GET_TERMINAL_JIT = None


# ==========================================
# MODEL LOADING
# ==========================================
def load_ml_package():
    """Loads the pickled model parameters into memory on startup."""
    global _ML_PACKAGE, _SEIR_FORWARD_JIT, _GET_TERMINAL_JIT

    if _ML_PACKAGE is not None:
        return  # Already loaded

    current_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(current_dir, "aegis_api_package.pkl")

    try:
        with open(model_path, "rb") as f:
            _ML_PACKAGE = pickle.load(f)
        print("ML Service: Successfully loaded model parameters.")

        # Pre-compile both simulation functions via JIT
        _SEIR_FORWARD_JIT = jax.jit(_seir_forward_simulate)
        _GET_TERMINAL_JIT = jax.jit(_get_terminal_state)

        # Convert observed-period matrices to JAX once at load time
        _ML_PACKAGE["_mask_matrix_jax"] = jnp.array(_ML_PACKAGE["mask_matrix"])
        _ML_PACKAGE["_lock_matrix_jax"] = jnp.array(_ML_PACKAGE["lockdown_matrix"])
        _ML_PACKAGE["_S0_jax"] = jnp.array(_ML_PACKAGE["S0"])
        _ML_PACKAGE["_E0_jax"] = jnp.array(_ML_PACKAGE["E0"])
        _ML_PACKAGE["_I0_jax"] = jnp.array(_ML_PACKAGE["I0"])
        _ML_PACKAGE["_R0_jax"] = jnp.array(_ML_PACKAGE["R0"])
        _ML_PACKAGE["_N_jax"] = jnp.array(_ML_PACKAGE["N_vector"])
        _ML_PACKAGE["_M_jax"] = jnp.array(_ML_PACKAGE["M_matrix"])

        print("ML Service: JIT compilation queued. First call will compile.")

    except FileNotFoundError:
        print(f"ML Service: WARNING - Model file not found at {model_path}.")
        _ML_PACKAGE = None
    except Exception as e:
        print(f"ML Service: Error loading model: {e}")
        _ML_PACKAGE = None


def is_model_loaded() -> bool:
    return _ML_PACKAGE is not None


# ==========================================
# CORE SIMULATION ENGINE (JAX)
# ==========================================
def _seir_step(carry, intervention_t, beta_base, eta_mask, eta_lock, sigma, gamma, N, M):
    """Single SEIR timestep — shared by both forward simulate and terminal state."""
    S, E, I, R = carry
    mask_t, lock_t = intervention_t[0], intervention_t[1]

    beta_t = beta_base * (1.0 - eta_mask * mask_t) * (1.0 - eta_lock * lock_t)

    imported = jnp.dot(M.T, I / N)
    effective_I = I + imported

    new_exposed = (beta_t * S * effective_I) / N
    new_infected = sigma * E
    new_recovered = gamma * I

    S_next = S - new_exposed
    E_next = E + new_exposed - new_infected
    I_next = I + new_infected - new_recovered
    R_next = R + new_recovered

    return (S_next, E_next, I_next, R_next), new_infected


def _seir_forward_simulate(
    beta_base, eta_mask, eta_lock, sigma, gamma,
    mask_schedule, lock_schedule,
    S0, E0, I0, R0, N, M,
):
    """
    Run SEIR forward simulation.
    Returns new_infected with shape (num_days, num_states).
    """
    interventions = jnp.stack([mask_schedule, lock_schedule], axis=1)

    def step(carry, intervention_t):
        return _seir_step(carry, intervention_t, beta_base, eta_mask, eta_lock, sigma, gamma, N, M)

    _, new_infected_all = lax.scan(step, (S0, E0, I0, R0), interventions)
    return new_infected_all


def _get_terminal_state(
    beta_base, eta_mask, eta_lock, sigma, gamma,
    mask_schedule, lock_schedule,
    S0, E0, I0, R0, N, M,
):
    """
    Run SEIR through the observed period and return the final (S, E, I, R) compartments.
    This is the critical step that was missing — it advances the model to 'today'
    before any forecast projection begins.
    """
    interventions = jnp.stack([mask_schedule, lock_schedule], axis=1)

    def step(carry, intervention_t):
        return _seir_step(carry, intervention_t, beta_base, eta_mask, eta_lock, sigma, gamma, N, M)

    final_carry, _ = lax.scan(step, (S0, E0, I0, R0), interventions)
    return final_carry  # (S_end, E_end, I_end, R_end)


# ==========================================
# HELPER: EXTRACT SAMPLE PARAMS
# ==========================================
def _extract_sample_params(idx: int) -> dict:
    """Extract a single posterior sample's parameters as JAX/float values."""
    pkg = _ML_PACKAGE
    sigma_data = pkg["sigma"]
    gamma_data = pkg["gamma"]

    return {
        "beta_base": jnp.array(pkg["beta_base"][idx]),
        "eta_mask": float(pkg["eta_mask"][idx]),
        "eta_lock": float(pkg["eta_lock"][idx]),
        "sigma": float(sigma_data[idx] if isinstance(sigma_data, np.ndarray) else sigma_data),
        "gamma": float(gamma_data[idx] if isinstance(gamma_data, np.ndarray) else gamma_data),
    }


def _run_single_sample_through_observed(idx: int):
    """
    Run one posterior sample through the full observed period
    to obtain the terminal SEIR state (i.e. 'where we are today').
    """
    params = _extract_sample_params(idx)
    pkg = _ML_PACKAGE

    S_end, E_end, I_end, R_end = _GET_TERMINAL_JIT(
        beta_base=params["beta_base"],
        eta_mask=params["eta_mask"],
        eta_lock=params["eta_lock"],
        sigma=params["sigma"],
        gamma=params["gamma"],
        mask_schedule=pkg["_mask_matrix_jax"],
        lock_schedule=pkg["_lock_matrix_jax"],
        S0=pkg["_S0_jax"],
        E0=pkg["_E0_jax"],
        I0=pkg["_I0_jax"],
        R0=pkg["_R0_jax"],
        N=pkg["_N_jax"],
        M=pkg["_M_jax"],
    )
    return S_end, E_end, I_end, R_end


def _run_single_forecast(idx: int, mask_j, lock_j, S_end, E_end, I_end, R_end):
    """
    Run one posterior sample's 30-day (or N-day) forecast
    starting from the terminal SEIR state.
    Returns new_infected array of shape (forecast_days, num_states).
    """
    params = _extract_sample_params(idx)
    pkg = _ML_PACKAGE

    fc = _SEIR_FORWARD_JIT(
        beta_base=params["beta_base"],
        eta_mask=params["eta_mask"],
        eta_lock=params["eta_lock"],
        sigma=params["sigma"],
        gamma=params["gamma"],
        mask_schedule=mask_j,
        lock_schedule=lock_j,
        S0=S_end,
        E0=E_end,
        I0=I_end,
        R0=R_end,
        N=pkg["_N_jax"],
        M=pkg["_M_jax"],
    )
    return np.array(fc)  # (forecast_days, num_states)


# ==========================================
# PUBLIC API: NATIONAL FORECAST
# ==========================================
def generate_forecast(
    mask_matrix: np.ndarray,
    lockdown_matrix: np.ndarray,
    forecast_days: int = 30,
    n_sims: int = 200,
) -> dict:
    """
    Generate national forecast trajectory using posterior samples.

    Pipeline (matching the notebook):
      1. For each posterior sample, run through the observed period → terminal state
      2. From terminal state, simulate forward under the given intervention schedule
      3. Aggregate across states, compute median and CI bands

    Args:
        mask_matrix:     (forecast_days, num_states) binary intervention schedule
        lockdown_matrix: (forecast_days, num_states) binary intervention schedule
        forecast_days:   projection horizon (default 30)
        n_sims:          number of posterior samples to use (default 200)

    Returns:
        Dictionary with daily national case projections (median, 5th, 95th percentiles).
    """
    if not is_model_loaded():
        raise RuntimeError("ML Model not loaded. Call load_ml_package() first.")

    pkg = _ML_PACKAGE
    n_states = len(pkg["state_names"])

    # --- Input validation ---
    if mask_matrix.shape != (forecast_days, n_states):
        raise ValueError(
            f"Expected mask_matrix shape ({forecast_days}, {n_states}), got {mask_matrix.shape}"
        )
    if lockdown_matrix.shape != (forecast_days, n_states):
        raise ValueError(
            f"Expected lockdown_matrix shape ({forecast_days}, {n_states}), got {lockdown_matrix.shape}"
        )

    # Convert forecast schedules to JAX once
    mask_j = jnp.array(mask_matrix)
    lock_j = jnp.array(lockdown_matrix)

    # Select evenly spaced posterior sample indices
    n_sims = min(n_sims, pkg["n_samples"])
    indices = np.linspace(0, pkg["n_samples"] - 1, n_sims, dtype=int)

    # --- Main simulation loop ---
    national_results = []  # (n_sims, forecast_days)

    for idx in indices:
        # Step 1: Advance through observed period to get terminal state
        S_end, E_end, I_end, R_end = _run_single_sample_through_observed(idx)

        # Step 2: Forecast forward from terminal state
        fc = _run_single_forecast(idx, mask_j, lock_j, S_end, E_end, I_end, R_end)
        # fc shape: (forecast_days, num_states)

        # Step 3: Sum across states for national daily totals
        national_results.append(fc.sum(axis=1))

    results_stack = np.stack(national_results)  # (n_sims, forecast_days)

    # --- Compute confidence intervals ---
    median_cases = np.median(results_stack, axis=0)
    lower_cases = np.percentile(results_stack, 5, axis=0)
    upper_cases = np.percentile(results_stack, 95, axis=0)

    return {
        "days": list(range(1, forecast_days + 1)),
        "median": [round(float(x)) for x in median_cases],
        "lower_90": [round(float(x)) for x in lower_cases],
        "upper_90": [round(float(x)) for x in upper_cases],
        "cumulative_median": round(float(median_cases.sum())),
        "state_names": pkg["state_names"],
    }


# ==========================================
# PUBLIC API: STATE-LEVEL FORECAST
# ==========================================
def generate_state_forecast(
    mask_matrix: np.ndarray,
    lockdown_matrix: np.ndarray,
    forecast_days: int = 30,
    n_sims: int = 200,
) -> dict:
    """
    Generate per-state forecast trajectories.

    Same pipeline as generate_forecast but returns state-level breakdowns
    for the state coordinator dashboards.

    Returns:
        Dictionary with per-state and national projections.
    """
    if not is_model_loaded():
        raise RuntimeError("ML Model not loaded. Call load_ml_package() first.")

    pkg = _ML_PACKAGE
    n_states = len(pkg["state_names"])

    if mask_matrix.shape != (forecast_days, n_states):
        raise ValueError(
            f"Expected mask_matrix shape ({forecast_days}, {n_states}), got {mask_matrix.shape}"
        )
    if lockdown_matrix.shape != (forecast_days, n_states):
        raise ValueError(
            f"Expected lockdown_matrix shape ({forecast_days}, {n_states}), got {lockdown_matrix.shape}"
        )

    mask_j = jnp.array(mask_matrix)
    lock_j = jnp.array(lockdown_matrix)

    n_sims = min(n_sims, pkg["n_samples"])
    indices = np.linspace(0, pkg["n_samples"] - 1, n_sims, dtype=int)

    # Collect full state-level results: (n_sims, forecast_days, num_states)
    all_results = []

    for idx in indices:
        S_end, E_end, I_end, R_end = _run_single_sample_through_observed(idx)
        fc = _run_single_forecast(idx, mask_j, lock_j, S_end, E_end, I_end, R_end)
        all_results.append(fc)

    results_stack = np.stack(all_results)  # (n_sims, forecast_days, num_states)

    # --- Per-state statistics ---
    state_median = np.median(results_stack, axis=0)   # (forecast_days, num_states)
    state_lower = np.percentile(results_stack, 5, axis=0)
    state_upper = np.percentile(results_stack, 95, axis=0)

    # --- National aggregate ---
    national_stack = results_stack.sum(axis=2)  # (n_sims, forecast_days)
    national_median = np.median(national_stack, axis=0)
    national_lower = np.percentile(national_stack, 5, axis=0)
    national_upper = np.percentile(national_stack, 95, axis=0)

    # Build per-state response
    state_forecasts = {}
    for j, state_name in enumerate(pkg["state_names"]):
        state_forecasts[state_name] = {
            "median": [round(float(x)) for x in state_median[:, j]],
            "lower_90": [round(float(x)) for x in state_lower[:, j]],
            "upper_90": [round(float(x)) for x in state_upper[:, j]],
            "cumulative_median": round(float(state_median[:, j].sum())),
        }

    return {
        "days": list(range(1, forecast_days + 1)),
        "national": {
            "median": [round(float(x)) for x in national_median],
            "lower_90": [round(float(x)) for x in national_lower],
            "upper_90": [round(float(x)) for x in national_upper],
            "cumulative_median": round(float(national_median.sum())),
        },
        "states": state_forecasts,
        "state_names": pkg["state_names"],
    }


# ==========================================
# PUBLIC API: SCENARIO COMPARISON
# ==========================================
def run_scenario_comparison(
    scenarios: dict[str, dict],
    forecast_days: int = 30,
    n_sims: int = 200,
) -> dict:
    """
    Run multiple what-if scenarios and return comparative results.

    Args:
        scenarios: Dictionary of scenario_name -> {"mask": np.ndarray, "lockdown": np.ndarray}
                   Each matrix has shape (forecast_days, num_states).
        forecast_days: projection horizon
        n_sims: number of posterior samples

    Returns:
        Dictionary with per-scenario national projections and cumulative impact comparison.
    """
    if not is_model_loaded():
        raise RuntimeError("ML Model not loaded. Call load_ml_package() first.")

    pkg = _ML_PACKAGE
    n_sims = min(n_sims, pkg["n_samples"])
    indices = np.linspace(0, pkg["n_samples"] - 1, n_sims, dtype=int)

    # Pre-compute terminal states once (shared across all scenarios)
    terminal_states = {}
    for idx in indices:
        terminal_states[idx] = _run_single_sample_through_observed(idx)

    results = {}

    for scenario_name, schedule in scenarios.items():
        mask_j = jnp.array(schedule["mask"])
        lock_j = jnp.array(schedule["lockdown"])

        national_trajectories = []

        for idx in indices:
            S_end, E_end, I_end, R_end = terminal_states[idx]
            fc = _run_single_forecast(idx, mask_j, lock_j, S_end, E_end, I_end, R_end)
            national_trajectories.append(fc.sum(axis=1))

        stack = np.stack(national_trajectories)
        median = np.median(stack, axis=0)
        cumulative = stack.sum(axis=1)

        results[scenario_name] = {
            "days": list(range(1, forecast_days + 1)),
            "median": [round(float(x)) for x in median],
            "lower_90": [round(float(x)) for x in np.percentile(stack, 5, axis=0)],
            "upper_90": [round(float(x)) for x in np.percentile(stack, 95, axis=0)],
            "cumulative_median": round(float(np.median(cumulative))),
            "cumulative_lower_90": round(float(np.percentile(cumulative, 5))),
            "cumulative_upper_90": round(float(np.percentile(cumulative, 95))),
        }

    # Add relative impact vs first scenario (assumed status quo)
    scenario_names = list(results.keys())
    if len(scenario_names) > 1:
        baseline_cumul = results[scenario_names[0]]["cumulative_median"]
        for name in scenario_names:
            cumul = results[name]["cumulative_median"]
            if baseline_cumul > 0:
                results[name]["vs_baseline_pct"] = round(
                    ((cumul - baseline_cumul) / baseline_cumul) * 100, 1
                )
            else:
                results[name]["vs_baseline_pct"] = 0.0

    return {
        "forecast_days": forecast_days,
        "n_posterior_samples": n_sims,
        "scenarios": results,
    }


# ==========================================
# CONVENIENCE: STATUS QUO SCHEDULE
# ==========================================
def get_status_quo_schedule(forecast_days: int = 30) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns the status quo intervention schedule: last observed day's
    interventions tiled forward for the forecast horizon.
    """
    if not is_model_loaded():
        raise RuntimeError("ML Model not loaded.")

    pkg = _ML_PACKAGE
    n_states = len(pkg["state_names"])
    last_mask = pkg["last_mask"]  # (num_states,)
    last_lock = pkg["last_lock"]  # (num_states,)

    mask_schedule = np.tile(last_mask, (forecast_days, 1))  # (forecast_days, num_states)
    lock_schedule = np.tile(last_lock, (forecast_days, 1))

    return mask_schedule, lock_schedule


def get_no_intervention_schedule(forecast_days: int = 30) -> tuple[np.ndarray, np.ndarray]:
    """All interventions removed."""
    if not is_model_loaded():
        raise RuntimeError("ML Model not loaded.")
    n_states = len(_ML_PACKAGE["state_names"])
    return np.zeros((forecast_days, n_states)), np.zeros((forecast_days, n_states))


def get_full_lockdown_schedule(forecast_days: int = 30) -> tuple[np.ndarray, np.ndarray]:
    """Full national lockdown + masks everywhere."""
    if not is_model_loaded():
        raise RuntimeError("ML Model not loaded.")
    n_states = len(_ML_PACKAGE["state_names"])
    return np.ones((forecast_days, n_states)), np.ones((forecast_days, n_states))
