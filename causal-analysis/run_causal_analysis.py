import sys
import warnings
import numpy as np
import pandas as pd
from dowhy import CausalModel
from dowhy.causal_estimators.linear_regression_estimator import LinearRegressionEstimator
import statsmodels.formula.api as smf


# Compatibility shim for DoWhy on Pandas >= 3.0 (restores positional fallback on Series[int])
_orig_series_getitem = pd.Series.__getitem__

def _compat_series_getitem(self, key):
    try:
        return _orig_series_getitem(self, key)
    except KeyError:
        if isinstance(key, (int, np.integer)) and not isinstance(self.index, pd.RangeIndex):
            return self.iloc[key]
        raise

pd.Series.__getitem__ = _compat_series_getitem

import networkx as nx

# Compatibility shim for DoWhy on NetworkX >= 3.3
if not hasattr(nx.algorithms, "d_separated"):
    from networkx.algorithms.d_separation import is_d_separator
    nx.algorithms.d_separated = is_d_separator
warnings.filterwarnings("ignore")

# ==============================================================================
# 1. Load & Preprocess Data
# ==============================================================================
IDENTIFIER_COLUMNS = {"instance"}

ORDINAL_MAPPINGS = {
    "difficulty": {
        "easy": 1,
        "medium": 2,
        "hard": 3,
    }
}

CONFIG_DUMMY_COLS = [
    "configuration_task_only",
    "configuration_reflection_only",
    "configuration_tool_only",
    "configuration_reflection_task",
    "configuration_task_tool",
    "configuration_reflection_tool",
    "configuration_task_and_reflection_and_tool",
]


def build_analysis_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Encode categorical variables and return numeric columns for causal analysis."""
    df = df.copy()
    if "instance" in df.columns:
        df["instance_id"] = df["instance"].astype("category").cat.codes
    work = df.drop(columns=[c for c in IDENTIFIER_COLUMNS if c in df.columns]).copy()

    # Encode known ordinal variables only if they are still strings
    for column, mapping in ORDINAL_MAPPINGS.items():
        if column in work.columns and not pd.api.types.is_numeric_dtype(work[column]):
            values = work[column].astype("string").str.strip().str.lower()
            unknown = sorted(set(values.dropna().unique()) - set(mapping))
            if unknown:
                raise ValueError(
                    f"Unexpected value(s) in ordinal column '{column}': {unknown}. "
                    f"Update ORDINAL_MAPPINGS before continuing."
                )
            work[column] = values.map(mapping)

    # One-hot encode remaining categorical (nominal) columns
    categorical_columns = work.select_dtypes(
        include=["object", "category", "string"]
    ).columns.tolist()

    if categorical_columns:
        work = pd.get_dummies(
            work,
            columns=categorical_columns,
            drop_first=True,
            dtype="int64",
        )

    boolean_columns = work.select_dtypes(include=["bool"]).columns
    if len(boolean_columns):
        work[boolean_columns] = work[boolean_columns].astype("int64")

    non_numeric = work.select_dtypes(exclude=["number"]).columns.tolist()
    if non_numeric:
        raise TypeError(
            "These columns could not be converted to numeric values: "
            + ", ".join(non_numeric)
        )

    constant_columns = [
        column for column in work.columns if work[column].nunique(dropna=True) <= 1
    ]
    if constant_columns:
        print(
            "Dropping constant or all-missing column(s): "
            + ", ".join(constant_columns),
            file=sys.stderr,
        )
        work = work.drop(columns=constant_columns)

    return work


def prepare_dowhy_dataframe(df_encoded: pd.DataFrame):
    """
    Prepares the encoded CSV for DoWhy:
    - Reconstructs an 8-level nominal 'config' column ('baseline' + 7 active arms).
    - One-hot encodes 'instance_id' into fixed-effect indicators so DoWhy does not
      treat integer instance IDs as a continuous linear variable.
    """
    df_model = df_encoded.copy()

    # 1. Reconstruct 8-level 'config' treatment column from configuration_* dummies
    active_config_cols = [c for c in CONFIG_DUMMY_COLS if c in df_model.columns]

    def _extract_config(row):
        for col in active_config_cols:
            if row[col] == 1:
                return col.replace("configuration_", "")
        return "baseline"

    df_model["config"] = df_model.apply(_extract_config, axis=1)

    # 2. One-hot encode instance_id for proper fixed-effects adjustment
    if "instance_id" in df_model.columns:
        df_model = pd.get_dummies(
            df_model, columns=["instance_id"], prefix="instance", drop_first=True, dtype="int64"
        )

    model_cols = [c for c in df_model.columns if c.startswith("model_")]
    instance_cols = [c for c in df_model.columns if c.startswith("instance_")]
    return df_model, model_cols, instance_cols


import statsmodels.formula.api as smf

# ==============================================================================
# 2. Define DOT Graphs (Rank-Full DAG A & Structural Mediation DAG B)
# ==============================================================================
def get_dag_a_8level_dot(model_cols, instance_cols):
    """
    DAG A: Total Effect Model (ATE).
    Note: 'instance_*' fixed effects completely absorb 'difficulty' (since difficulty
    is a deterministic property of instance), avoiding a rank-deficient design matrix.
    """
    edges = ['"treatment_active" -> "resolved";']
    for m in model_cols:
        edges.append(f'"{m}" -> "resolved";')
    for inst in instance_cols:
        edges.append(f'"{inst}" -> "resolved";')
    return "digraph {\n    " + "\n    ".join(edges) + "\n}"


def get_dag_b_dot(model_cols, instance_cols):
    """DAG B: Structural Mediation Model (NDE / NIE)."""
    edges = [
        # Treatments -> Primary Mediators
        '"task_evolution" -> "n_task_description_edits";',
        '"reflection_evolution" -> "n_reflection_prompt_edits";',
        '"reflection_evolution" -> "n_task_description_edits";',
        '"tool_evolution" -> "n_tools_created";',
        # Primary -> Secondary Mediators
        '"n_task_description_edits" -> "api_calls";',
        '"n_reflection_prompt_edits" -> "api_calls";',
        '"n_tools_created" -> "n_custom_tool_uses";',
        '"n_tools_created" -> "api_calls";',
        '"n_custom_tool_uses" -> "api_calls";',
        # Secondary Mediators -> Outcome
        '"api_calls" -> "total_tokens";',
        '"api_calls" -> "resolved";',
        '"total_tokens" -> "resolved";',
        '"n_custom_tool_uses" -> "resolved";',
        '"n_task_description_edits" -> "resolved";',
        '"n_reflection_prompt_edits" -> "resolved";',
        # Direct Paths (Treatment -> Outcome)
        '"task_evolution" -> "resolved";',
        '"reflection_evolution" -> "resolved";',
        '"tool_evolution" -> "resolved";',
    ]

    for m in model_cols:
        for target in [
            "resolved",
            "api_calls",
            "n_task_description_edits",
            "n_reflection_prompt_edits",
            "n_tools_created",
            "n_custom_tool_uses",
        ]:
            edges.append(f'"{m}" -> "{target}";')

    for inst in instance_cols:
        edges.append(f'"{inst}" -> "resolved";')
        edges.append(f'"{inst}" -> "api_calls";')

    return "digraph {\n    " + "\n    ".join(edges) + "\n}"


# ==============================================================================
# 3. Main Execution Pipeline
# ==============================================================================
if __name__ == "__main__":
    df_encoded = build_analysis_dataframe(pd.read_csv("../results/per_instance_results.csv"))
    df_dowhy, model_cols, instance_cols = prepare_dowhy_dataframe(df_encoded)

    # Reconstruct binary evolution flags if needed for DAG B mediation
    if not {"task_evolution", "reflection_evolution", "tool_evolution"}.issubset(df_dowhy.columns):
        df_dowhy["task_evolution"] = df_dowhy[
            [
                "configuration_task_only",
                "configuration_reflection_task",
                "configuration_task_tool",
                "configuration_task_and_reflection_and_tool",
            ]
        ].max(axis=1)
        df_dowhy["reflection_evolution"] = df_dowhy[
            [
                "configuration_reflection_only",
                "configuration_reflection_task",
                "configuration_reflection_tool",
                "configuration_task_and_reflection_and_tool",
            ]
        ].max(axis=1)
        df_dowhy["tool_evolution"] = df_dowhy[
            [
                "configuration_tool_only",
                "configuration_task_tool",
                "configuration_reflection_tool",
                "configuration_task_and_reflection_and_tool",
            ]
        ].max(axis=1)

    # --------------------------------------------------------------------------
    # Step A: 8-Level Configuration ATEs vs. Baseline ('000') via DoWhy
    # --------------------------------------------------------------------------
    dag_a_dot = get_dag_a_8level_dot(model_cols, instance_cols)

    active_configs = [
        "task_only",
        "reflection_only",
        "tool_only",
        "reflection_task",
        "task_tool",
        "reflection_tool",
        "task_and_reflection_and_tool",
    ]

    print("=== 1. 8-LEVEL CONFIG ATEs vs. BASELINE ('000') ===")
    ate_results = []
    last_model = None
    last_estimand = None
    last_estimate = None

    for cfg in active_configs:
        # Subset to pairwise contrast (baseline vs. cfg) with binary 0/1 treatment
        df_pair = df_dowhy[df_dowhy["config"].isin(["baseline", cfg])].copy()
        df_pair["treatment_active"] = (df_pair["config"] == cfg).astype(int)

        # Drop any model/instance dummy columns that have 0 variance in this subset
        valid_models = [c for c in model_cols if df_pair[c].nunique() > 1]
        valid_instances = [c for c in instance_cols if df_pair[c].nunique() > 1]
        pair_dot = get_dag_a_8level_dot(valid_models, valid_instances)

        model_pair = CausalModel(
            data=df_pair,
            treatment="treatment_active",
            outcome="resolved",
            graph=pair_dot,
        )

        estimand_pair = model_pair.identify_effect(proceed_when_unidentifiable=True)
        est = model_pair.estimate_effect(
            estimand_pair,
            method_name="backdoor.linear_regression",
            control_value=0,
            treatment_value=1,
            confidence_intervals=True,
            method_params={"need_conditional_estimates": False},  # Avoids pandas KeyError: 0
        )

        ci = est.get_confidence_intervals()
        if ci is not None and np.size(ci) >= 2:
            ci_flat = np.asarray(ci, dtype=float).ravel()
            ci_low, ci_high = ci_flat[0], ci_flat[1]
        else:
            ci_low, ci_high = np.nan, np.nan

        ate_results.append(
            {
                "config": cfg,
                "n_rows": len(df_pair),
                "ATE_vs_baseline": round(float(est.value), 4),
                "CI_95_low": round(float(ci_low), 4),
                "CI_95_high": round(float(ci_high), 4),
            }
        )
        last_model, last_estimand, last_estimate = model_pair, estimand_pair, est

    ate_df = pd.DataFrame(ate_results)
    print(ate_df.to_string(index=False))

    # --------------------------------------------------------------------------
    # Step B: CATE by Model & Difficulty (Stratified DoWhy + Cluster-Robust OLS)
    # --------------------------------------------------------------------------
    print("\n=== 2. CATE BY MODEL ('task_and_reflection_and_tool' vs 'baseline') ===")
    df_full_arm = df_dowhy[df_dowhy["config"].isin(["baseline", "task_and_reflection_and_tool"])].copy()
    df_full_arm["treatment_active"] = (df_full_arm["config"] == "task_and_reflection_and_tool").astype(int)

    # Reconstruct model label for clean subgroup CATE estimation
    df_full_arm["model_name"] = "gpt-5"
    if "model_llama4-scout" in df_full_arm.columns:
        df_full_arm.loc[df_full_arm["model_llama4-scout"] == 1, "model_name"] = "llama4-scout"
    if "model_qwen3-coder-30b" in df_full_arm.columns:
        df_full_arm.loc[df_full_arm["model_qwen3-coder-30b"] == 1, "model_name"] = "qwen3-coder-30b"

    for m_name, grp in df_full_arm.groupby("model_name"):
        if grp["treatment_active"].nunique() < 2:
            print(f"Model: {m_name:18s} | Skipped (missing baseline or treatment arm in partial data)")
            continue
        valid_inst = [c for c in instance_cols if grp[c].nunique() > 1]
        sub_dot = get_dag_a_8level_dot([], valid_inst)
        m_sub = CausalModel(data=grp, treatment="treatment_active", outcome="resolved", graph=sub_dot)
        est_sub = m_sub.estimate_effect(
            m_sub.identify_effect(proceed_when_unidentifiable=True),
            method_name="backdoor.linear_regression",
            method_params={"need_conditional_estimates": False},
        )
        print(f"Model: {m_name:18s} | CATE ('111' vs '000'): {est_sub.value:+.4f}")

    # --------------------------------------------------------------------------
    # Step C: Structural Mediation Analysis: NDE & NIE (DAG B)
    # --------------------------------------------------------------------------
    print("\n=== 3. CAUSAL MEDIATION ANALYSIS: NDE & NIE (DAG B) ===")
    dag_b_dot = get_dag_b_dot(model_cols, instance_cols)

    for binary_treat in ["task_evolution", "reflection_evolution", "tool_evolution"]:
        model_med = CausalModel(
            data=df_dowhy,
            treatment=binary_treat,
            outcome="resolved",
            graph=dag_b_dot,
        )

        estimand_nde = model_med.identify_effect(estimand_type="nonparametric-nde")
        estimate_nde = model_med.estimate_effect(
            estimand_nde,
            method_name="mediation.two_stage_regression",
            confidence_intervals=True,
            method_params={
                "first_stage_model": LinearRegressionEstimator,
                "second_stage_model": LinearRegressionEstimator,
                "need_conditional_estimates": False,
            },
        )

        estimand_nie = model_med.identify_effect(estimand_type="nonparametric-nie")
        estimate_nie = model_med.estimate_effect(
            estimand_nie,
            method_name="mediation.two_stage_regression",
            confidence_intervals=True,
            method_params={
                "first_stage_model": LinearRegressionEstimator,
                "second_stage_model": LinearRegressionEstimator,
                "need_conditional_estimates": False,
            },
        )

        print(
            f"{binary_treat:22s} | NDE: {estimate_nde.value:+.4f} | NIE: {estimate_nie.value:+.4f}"
        )

    # --------------------------------------------------------------------------
    # Step D: Refutation / Robustness Checks (on 'task_and_reflection_and_tool')
    # --------------------------------------------------------------------------
    print("\n=== 4. REFUTATION CHECKS (ROBUSTNESS) ===")
    refute_placebo = last_model.refute_estimate(
        last_estimand,
        last_estimate,
        method_name="placebo_treatment_refuter",
        placebo_type="permute",
    )
    print(refute_placebo)

    refute_subset = last_model.refute_estimate(
        last_estimand,
        last_estimate,
        method_name="data_subset_refuter",
        subset_fraction=0.8,
    )
    print(refute_subset)