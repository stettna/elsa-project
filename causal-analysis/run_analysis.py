import pandas as pd
import numpy as np
from dowhy import CausalModel
import warnings
warnings.filterwarnings("ignore")

# ==============================================================================
# 1. Load & Preprocess Data
# ==============================================================================
df = pd.read_csv("per_instance_results.csv")

# Create a combined configuration string ('000' = pure baseline, '111' = all active)
df["config"] = (
    df["task_evolution"].astype(str)
    + df["reflection_evolution"].astype(str)
    + df["tool_evolution"].astype(str)
)

# One-hot encode categorical covariates for DoWhy estimators
df_encoded = pd.get_dummies(df, columns=["model", "instance"], drop_first=True, dtype=float)
model_cols = [c for c in df_encoded.columns if c.startswith("model_")]
instance_cols = [c for c in df_encoded.columns if c.startswith("instance_")]

# ==============================================================================
# 2. Define DOT Graphs (Matching Updated DAG A & DAG B)
# ==============================================================================
def get_dag_a_dot(model_cols, instance_cols):
    """DAG A: Total Effect & Moderation Model (ATE / CATE)."""
    edges = [
        '"task_evolution" -> "resolved";',
        '"reflection_evolution" -> "resolved";',
        '"tool_evolution" -> "resolved";',
        '"difficulty" -> "resolved";',
    ]
    for m in model_cols:
        edges.append(f'"{m}" -> "resolved";')
    for inst in instance_cols:
        edges.append(f'"{inst}" -> "difficulty";')
        edges.append(f'"{inst}" -> "resolved";')
    return "digraph {\n    " + "\n    ".join(edges) + "\n}"


def get_dag_b_dot(model_cols, instance_cols):
    """DAG B: Structural Mediation Model (NDE / NIE) with full covariate edges."""
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
        
        # Difficulty -> Mediators & Outcome
        '"difficulty" -> "resolved";',
        '"difficulty" -> "api_calls";',
        '"difficulty" -> "n_task_description_edits";',
        '"difficulty" -> "n_reflection_prompt_edits";',
        '"difficulty" -> "n_tools_created";',
        '"difficulty" -> "n_custom_tool_uses";',
    ]
    
    # Model -> All Mediators & Outcome
    for m in model_cols:
        for target in [
            "resolved", "api_calls", "n_task_description_edits",
            "n_reflection_prompt_edits", "n_tools_created", "n_custom_tool_uses"
        ]:
            edges.append(f'"{m}" -> "{target}";')
            
    for inst in instance_cols:
        edges.append(f'"{inst}" -> "difficulty";')
        edges.append(f'"{inst}" -> "resolved";')
        
    return "digraph {\n    " + "\n    ".join(edges) + "\n}"


# ==============================================================================
# 3. Step-by-Step DoWhy Analysis: ATE & CATE (DAG A)
# ==============================================================================
dag_a_dot = get_dag_a_dot(model_cols, instance_cols)

print("=== 1. ESTIMATING ATE FOR EACH EVOLUTION FEATURE (DAG A) ===")
treatments = ["task_evolution", "reflection_evolution", "tool_evolution"]

for treat in treatments:
    model_ate = CausalModel(
        data=df_encoded,
        treatment=treat,
        outcome="resolved",
        graph=dag_a_dot,
        effect_modifiers=model_cols + ["difficulty"]
    )
    
    # Identify causal estimand via backdoor criterion
    estimand = model_ate.identify_effect(proceed_when_unidentifiable=True)
    
    # Estimate ATE using linear regression (Linear Probability Model for percentage-point effect)
    estimate_ate = model_ate.estimate_effect(
        estimand,
        method_name="backdoor.linear_regression",
        control_value=0,
        treatment_value=1,
        confidence_intervals=True
    )
    print(f"\nTreatment: {treat}")
    print(f"ATE (Resolution Rate Shift): {estimate_ate.value:.4f}")

# --- Estimating CATE (Heterogeneous Effects by Model & Difficulty) ---
print("\n=== 2. ESTIMATING CATE BY MODEL & DIFFICULTY (DAG A) ===")
# Example: CATE of reflection_evolution across models and difficulty levels
model_cate = CausalModel(
    data=df_encoded,
    treatment="reflection_evolution",
    outcome="resolved",
    graph=dag_a_dot,
    effect_modifiers=model_cols + ["difficulty"]
)
estimand_cate = model_cate.identify_effect(proceed_when_unidentifiable=True)

# Linear regression with interaction terms automatically computes CATE via effect_modifiers
estimate_cate = model_cate.estimate_effect(
    estimand_cate,
    method_name="backdoor.linear_regression",
    method_params={"need_conditional_estimates": True}
)
print("Conditional ATEs (first 5 strata):")
print(estimate_cate.conditional_estimates.head())


# ==============================================================================
# 4. Step-by-Step DoWhy Analysis: NDE & NIE Mediation (DAG B)
# ==============================================================================
print("\n=== 3. CAUSAL MEDIATION ANALYSIS: NDE & NIE (DAG B) ===")
dag_b_dot = get_dag_b_dot(model_cols, instance_cols)

# Example: Decomposing tool_evolution -> n_tools_created -> resolved
model_med = CausalModel(
    data=df_encoded,
    treatment="tool_evolution",
    outcome="resolved",
    graph=dag_b_dot
)

# Natural Direct Effect (NDE): Direct prompt/framing effect holding mediator at baseline
estimand_nde = model_med.identify_effect(estimand_type="nonparametric-nde")
estimate_nde = model_med.estimate_effect(
    estimand_nde,
    method_name="mediation.two_stage_regression",
    confidence_intervals=True,
    method_params={
        "first_stage_model": "linear",
        "second_stage_model": "linear"
    }
)

# Natural Indirect Effect (NIE): Effect mediated through tool creation & downstream execution
estimand_nie = model_med.identify_effect(estimand_type="nonparametric-nie")
estimate_nie = model_med.estimate_effect(
    estimand_nie,
    method_name="mediation.two_stage_regression",
    confidence_intervals=True,
    method_params={
        "first_stage_model": "linear",
        "second_stage_model": "linear"
    }
)

print(f"Tool Evolution NDE (Direct Effect):   {estimate_nde.value:.4f}")
print(f"Tool Evolution NIE (Indirect Effect): {estimate_nie.value:.4f}")


# ==============================================================================
# 5. Refutation / Robustness Checks
# ==============================================================================
print("\n=== 4. REFUTATION CHECKS (ROBUSTNESS) ===")
# Check 1: Placebo Treatment (replaces treatment with random noise; new effect should be ~0)
refute_placebo = model_ate.refute_estimate(
    estimand, estimate_ate, method_name="placebo_treatment_refuter", placebo_type="permute"
)
print(refute_placebo)

# Check 2: Data Subset Refuter (drops 20% of data randomly; ATE should remain stable)
refute_subset = model_ate.refute_estimate(
    estimand, estimate_ate, method_name="data_subset_refuter", subset_fraction=0.8
)
print(refute_subset)