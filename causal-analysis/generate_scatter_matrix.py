"""
Calculate a Pearson correlation matrix for a task-level SWE-agent dataset.

Categorical handling:
- difficulty: ordinal encoding (easy=1, medium=2, hard=3)
- configuration and model: one-hot encoding (nominal categories)
- instance: excluded because it is an identifier, not a meaningful measurement
- task_evolution, reflection_evolution, tool_evolution: excluded as requested

Outputs:
- pearson_correlation_matrix.csv
- pearson_correlation_heatmap.png
"""

from pathlib import Path
import argparse
import sys

import pandas as pd
import matplotlib.pyplot as plt
from pandas.plotting import scatter_matrix



EXCLUDED_COLUMNS = {
    "tool_evolution",
    "task_evolution",
    "reflection_evolution",
}

# An identifier should not be treated as a measured variable. One-hot encoding
# instance would create many arbitrary, difficult-to-interpret columns.
IDENTIFIER_COLUMNS = {"instance"}

# This order reflects the natural ordering of the difficulty levels.
ORDINAL_MAPPINGS = {
    "difficulty": {
        "easy": 1,
        "medium": 2,
        "hard": 3,
    }
}


def build_analysis_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Encode categorical variables and return numeric columns for correlation."""
    excluded = EXCLUDED_COLUMNS | IDENTIFIER_COLUMNS
    missing_exclusions = EXCLUDED_COLUMNS.intersection(df.columns)
    if missing_exclusions != EXCLUDED_COLUMNS:
        absent = sorted(EXCLUDED_COLUMNS - set(df.columns))
        print(
            "Warning: requested exclusion column(s) not found: "
            + ", ".join(absent),
            file=sys.stderr,
        )

    work = df.drop(columns=[c for c in excluded if c in df.columns]).copy()

    # Encode known ordinal variables with an explicitly defined order.
    for column, mapping in ORDINAL_MAPPINGS.items():
        if column in work.columns:
            values = work[column].astype("string").str.strip().str.lower()
            unknown = sorted(set(values.dropna().unique()) - set(mapping))
            if unknown:
                raise ValueError(
                    f"Unexpected value(s) in ordinal column '{column}': {unknown}. "
                    f"Update ORDINAL_MAPPINGS before continuing."
                )
            work[column] = values.map(mapping)

    # One-hot encode remaining categorical (nominal) columns.
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

    # Convert any remaining boolean columns to 0/1.
    boolean_columns = work.select_dtypes(include=["bool"]).columns
    if len(boolean_columns):
        work[boolean_columns] = work[boolean_columns].astype("int64")

    # Ensure every column is numeric; fail clearly rather than silently omit data.
    non_numeric = work.select_dtypes(exclude=["number"]).columns.tolist()
    if non_numeric:
        raise TypeError(
            "These columns could not be converted to numeric values: "
            + ", ".join(non_numeric)
        )

    # Correlation is undefined for constant columns.
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


def main():
    parser = argparse.ArgumentParser(
        description="Create a Pearson correlation matrix from a CSV dataset."
    )
    parser.add_argument(
        "input_csv",
        nargs="?",
        default="per_instance_results(1).csv",
        help="Input CSV path (default: per_instance_results(1).csv)",
    )
    parser.add_argument(
        "--output-dir",
        default="correlation_output",
        help="Directory for output files (default: correlation_output)",
    )
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.is_file():
        parser.error(f"Input CSV not found: {input_path}")

    df = pd.read_csv(input_path)
    analysis_df = build_analysis_dataframe(df)

    if analysis_df.shape[1] < 2:
        raise ValueError("At least two usable variables are required.")

    # pandas computes each pair using rows with non-missing values for that pair.
    correlation = analysis_df.corr(method="pearson", min_periods=2)

    csv_path = output_dir / "pearson_correlation_matrix.csv"
    correlation.to_csv(csv_path, float_format="%.6f")

    # Plot the matrix. Labels are rotated to remain readable when there are
    # several one-hot encoded categorical columns.
    width = max(10, min(24, 0.55 * len(correlation.columns)))
    height = max(8, min(22, 0.50 * len(correlation.columns)))
    fig, ax = plt.subplots(figsize=(width, height))
    image = ax.imshow(
        correlation.to_numpy(),
        cmap="coolwarm",
        vmin=-1,
        vmax=1,
        aspect="auto",
    )
    ax.set_xticks(range(len(correlation.columns)))
    ax.set_yticks(range(len(correlation.index)))
    ax.set_xticklabels(correlation.columns, rotation=90, fontsize=8)
    ax.set_yticklabels(correlation.index, fontsize=8)
    ax.set_title("Pearson Correlation Matrix")
    fig.colorbar(image, ax=ax, label="Pearson r", shrink=0.8)
    fig.tight_layout()

    heatmap_path = output_dir / "pearson_correlation_heatmap.png"
    fig.savefig(heatmap_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    print(f"Rows in input dataset: {len(df)}")
    print(f"Variables used after encoding: {analysis_df.shape[1]}")
    print(f"Encoded variables: {', '.join(analysis_df.columns)}")
    print(f"\nCorrelation matrix saved to: {csv_path}")
    print(f"Heatmap saved to: {heatmap_path}")
    print("\nCorrelation matrix:")
    print(correlation.round(3).to_string())


if __name__ == "__main__":
    main()
