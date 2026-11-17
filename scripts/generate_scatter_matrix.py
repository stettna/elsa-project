
import pandas as pd
import matplotlib.pyplot as plt
from pandas.plotting import scatter_matrix

# --------------------------------------------------
# 1. Load dataset
# --------------------------------------------------

df = pd.read_csv("../results/per_instance_results.csv")

# --------------------------------------------------
# 2. Select numerical variables
# --------------------------------------------------

numerical_columns = [
    "n_evo_tasks",
    "api_calls",
    "total_tokens",
    "n_task_description_edits",
    "n_reflection_prompt_edits",
    "n_tools_created",
    "n_custom_tool_uses",
    "resolved"
]

# Keep only the selected numerical variables
numeric_df = df[numerical_columns].copy()

# Remove observations with missing values
numeric_df = numeric_df.dropna()

print(f"Number of observations: {len(numeric_df)}")

# --------------------------------------------------
# 3. Generate scatter matrix
# --------------------------------------------------

plt.figure(figsize=(16, 16))

scatter_matrix(
    numeric_df,
    figsize=(16, 16),
    diagonal="hist",
    alpha=0.4,
    s=15,
    color="steelblue",
    hist_kwds={"bins": 20, "edgecolor": "black"}
)

plt.suptitle(
    "Scatter Matrix - Self-Evolving Agent Performance",
    fontsize=18,
    y=1.02
)

plt.tight_layout()

# Save figure
plt.savefig(
    "scatter_matrix.png",
    dpi=300,
    bbox_inches="tight"
)

plt.show()

# --------------------------------------------------
# 4. Generate Pearson correlation matrix
# --------------------------------------------------

correlation_matrix = numeric_df.corr(method="pearson")

print("\nPearson Correlation Matrix:")
print(correlation_matrix.round(3))

# Save correlation matrix
correlation_matrix.to_csv("correlation_matrix.csv")
