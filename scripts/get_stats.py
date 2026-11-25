# File generated with the help of ChatGPT
#
# Usage: python3 get_model_stats.py PATH_TO_DIRECTORY_CONTAINING_RUN_INFORMATION
#
# The script will recursively find all of the log files for the agent and aggregate
# cost and API call information for the benchmark run. It will save the results as a
# CSV file in the directory given as input and print averages to the command line.
#
# If a trajectory has a corresponding tool-summary JSON file, this script will also
# aggregate:
#   - n_tools_created
#   - n_unique_tools_created
#   - n_custom_tool_uses
#
# Tool-summary JSON lookup:
#   1. <trajectory-name>.tools.json
#      Example:
#        django__django-11163.traj.json
#        django__django-11163.tools.json
#   2. tools.json in the same directory, as a fallback.
#
# If no tool-summary JSON file is present, the tool-related statistics default to 0.

import argparse
import csv
import json
import pandas as pd
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

#Assign each model a unique integer value for easier processing
MODELS = {
    "gpt-5": 1,
    "llama4-scout": 2,
    "qwen3-coder-30b": 3,
}

#Gives binary representation the active evo tasks in the configuration.
#Encoded as (task, reflection, tool)
EVOL_TASKS = {
    "task_and_reflection_and_tool": (1,1,1), #tool + task + reflection
    "task_tool": (1,0,1),                    #tool + task
    "reflection_tool": (0,1,1),              #tool + reflection
    "reflection_task": (1,1,0),              #reflection + task
    "task_only": (1,0,0),                    #task
    "reflection_only": (0,1,0),              #reflection
    "tool_only": (0,0,1),                    #tool
    "no_evo" : (0,0,0),                      #none
}

PATH_TO_AG_CSV = "../results/aggregated_results.csv"   #Assumes script is run from within the scripts directory
PATH_TO_IN_CSV = "../results/per_instance_results.csv" #Assumes script is run from within the scripts directory

AG_MODE = 'w'  # Start with write mode for the aggregated CSV
IN_MODE = 'w'  # Start with write mode for the per-instance CSV

def get_difficulty_from_instance_dict() -> Optional[Dict[str, int]]:

    splits = {'test': 'data/test-00000-of-00001.parquet', 'dev': 'data/dev-00000-of-00001.parquet'}
    df = pd.read_parquet("hf://datasets/SWE-bench/SWE-bench/" + splits["test"])

    #read instance_id into list from csv file
    instance_ids = pd.read_csv("../subsets/swe-bench-verified-50.csv")["instance_id"].tolist()

    #select only rows with instance_id in the list and save difficulty field and instance_id to a new dataframe
    df_filtered = df[df['instance_id'].isin(instance_ids)][['instance_id', 'difficulty']]

    #encode difficulty as 0 for easy, 1 for medium, 2 for hard
    df_filtered['difficulty'] = df_filtered['difficulty'].map({'<15 min fix': "easy", '15 min - 1 hour': "medium", '1-4 hours': "hard", '>4 hours': "hard"})

    #use dictionary comprehension to create a dictionary from the filtered dataframe
    difficulty_dict = {row['instance_id']: row['difficulty'] for _, row in df_filtered.iterrows()} 

    return difficulty_dict

def find_traj_files(root: Path):
    """Recursively find all files matching *.traj.json under root."""
    return root.rglob("*.traj.json")

def get_resolved_ids(eval_path):
    #Parse eval_path to get the number of tasks that were resolved
    eval_path = Path(eval_path)
    if not eval_path.is_file():
        print(f"Error: '{eval_path}' is not a valid file.")
        return 0    

    resolved_ids = []

    #Parse json file to get the number of tasks that were resolved
    with eval_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
        if "resolved_instances" in data:
            resolved_ids =  data["resolved_ids"]
        else:
            print(f"Error: 'resolved_ids' not found in '{eval_path}'.")
            return 0

    return resolved_ids


def corresponding_tools_json_candidates(traj_path: Path) -> List[Path]:
    """
    Return possible tool-summary JSON paths for a trajectory.

    The preferred filename matches the output convention used by the
    find_agent_tools extractor:
      <trajectory basename>.tools.json

    A same-directory `tools.json` fallback is also supported.
    """
    traj_name = traj_path.name
    if traj_name.endswith(".traj.json"):
        per_traj_name = traj_name[:-len(".traj.json")] + ".tools.json"
    elif traj_name.endswith(".json"):
        per_traj_name = traj_name[:-len(".json")] + ".tools.json"
    else:
        per_traj_name = traj_name + ".tools.json"

    return [
        traj_path.with_name(per_traj_name),
        traj_path.with_name("tools.json"),
    ]


def find_corresponding_tools_json(traj_path: Path) -> Optional[Path]:
    """Return the first matching tool-summary JSON file, or None if absent."""
    for candidate in corresponding_tools_json_candidates(traj_path):
        if candidate.is_file():
            return candidate
    return None


def _coerce_tool_records(data: Any) -> List[Dict[str, Any]]:
    """
    Normalize supported tool-summary JSON shapes into a list of records.

    The current extractor writes a JSON array directly. A small amount of
    defensive support for dict-wrapped records is included for convenience.
    """
    if isinstance(data, list):
        return [record for record in data if isinstance(record, dict)]

    if isinstance(data, dict):
        for key in ("definitions", "tools", "records"):
            records = data.get(key)
            if isinstance(records, list):
                return [record for record in records if isinstance(record, dict)]

    raise TypeError("tools JSON is not a supported record list")


def extract_tool_stats(traj_path: Path) -> Dict[str, int]:
    """
    Extract tool-related statistics from a sibling tools JSON file.

    Returns zeros when no matching tools JSON file exists. If a matching file
    exists but cannot be parsed, the trajectory is still processed and zeros are
    returned for the tool fields.
    """
    tools_json_path = find_corresponding_tools_json(traj_path)
    if tools_json_path is None:
        return {
            "n_tools_created": 0,
            #"n_unique_tools_created": 0,
            "n_custom_tool_uses": 0,
        }

    try:
        with tools_json_path.open("r", encoding="utf-8") as f:
            tools_data = json.load(f)

        tool_records = _coerce_tool_records(tools_data)

        # "Tools created" counts every tool definition/version record.
        n_tools_created = len(tool_records)

        # "Unique tools created" collapses multiple versions/overwrites of the
        # same tool file path into a single tool.
        unique_tool_paths = {
            record.get("path")
            for record in tool_records
            if isinstance(record.get("path"), str) and record.get("path")
        }
        n_unique_tools_created = len(unique_tool_paths)

        n_custom_tool_uses = 0

        for record in tool_records:
            later_step_uses = record.get("used_steps") or []
            same_step_uses = record.get("same_step_use_steps") or []

            if isinstance(later_step_uses, list):
                n_custom_tool_uses += len(later_step_uses)
            else:
                print(
                    f"Warning: ignoring non-list used_steps in "
                    f"{tools_json_path} for {traj_path.name}"
                )

            if isinstance(same_step_uses, list):
                n_custom_tool_uses += len(same_step_uses)
            else:
                print(
                    f"Warning: ignoring non-list same_step_use_steps in "
                    f"{tools_json_path} for {traj_path.name}"
                )

        return {
            "n_tools_created": n_tools_created,
            #"n_unique_tools_created" : n_unique_tools_created,
            "n_custom_tool_uses": n_custom_tool_uses,
        }

    except (json.JSONDecodeError, OSError, TypeError) as e:
        print(
            f"Warning: could not extract tool stats from {tools_json_path} "
            f"for {traj_path.name} ({e}); defaulting tool stats to 0."
        )
        return {
            "n_tools_created": 0,
            "n_unique_tools_created" : 0,
            "n_custom_tool_uses": 0,
        }


def extract_stats(file_path: Path):
    """
    Extract:
      - name: everything before '.traj.json'
      - total_tokens
      - api_calls
      - optional prompt-evolution edit counts
      - optional tool-summary counts from a sibling tools JSON file

    Returns a dict or None if trajectory parsing fails / required trajectory
    fields are missing.
    """
    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        model_stats = data["info"]["model_stats"]
        prompt_evo_info = data["info"].get("prompt_evo_info", None)

        total_tokens = 0
        for m in data["messages"]:
            total_tokens += m.get("extra", {}).get("response", {}).get("usage", {}).get("total_tokens", 0)

        res = {
            "instance": file_path.name[:-len(".traj.json")],
            "api_calls": model_stats["api_calls"],
            "total_tokens": total_tokens,
            "n_task_description_edits": 0,
            "n_reflection_prompt_edits": 0,
        }

        if prompt_evo_info is not None:
            res.update({
                "n_task_description_edits": prompt_evo_info.get("n_task_description_edits", 0),
                "n_reflection_prompt_edits": prompt_evo_info.get("n_reflection_prompt_edits", 0),
            })

        res.update(extract_tool_stats(file_path))
        return res

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Skipping {file_path}: could not extract stats ({e})")
        return None


def write_to_ag_csv(rows):
    """Write aggregated rows to CSV."""
    with open(PATH_TO_AG_CSV, AG_MODE, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "configuration",
                "model", 
                "total_api_calls",
                "total_total_tokens",
                "total_task_description_edits",
                "total_reflection_prompt_edits",
                "total_tools_created",
                "total_custom_tool_uses", 
                "avg_api_calls",
                "avg_total_tokens", 
                "avg_task_edits",
                "avg_reflection_edits", 
                "avg_tools_created",
                "avg_tools_used",
                "resolve_rate"
            ],
        )
        if AG_MODE == 'w':
            writer.writeheader()
        writer.writerows(rows)

def write_to_in_csv(rows):
    """Write aggregated rows to CSV."""
    with open(PATH_TO_IN_CSV, IN_MODE, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "instance",
                "difficulty",
                "configuration",
                "task_evolution",
                "reflection_evolution",
                "tool_evolution",
                "model", 
                "api_calls",
                "total_tokens",
                "n_task_description_edits",
                "n_reflection_prompt_edits",
                "n_tools_created",
                "n_custom_tool_uses", 
                "resolved"
            ],
        )
        if IN_MODE == 'w':
            writer.writeheader()
        writer.writerows(rows)      

def process_config_directory(config_dir: Path, difficulty_dict: Dict[str, int]):
    """Process a single configuration directory."""

    config = str(config_dir).split("/")[-1]

    for model_dir in config_dir.iterdir():

        #Ensure path is dir
        if not model_dir.is_dir():
            print(f"Warning: '{model_dir}' is not a directory; skipping.")
            continue

        model = str(model_dir).split("/")[-1]

        #Initialize cumulative statistics for the model/configuration
        avg_total_tokens = 0.0
        avg_api_calls = 0.0
        avg_task_description_edits = 0.0
        avg_reflection_prompt_edits = 0.0
        avg_tools_created = 0.0
        avg_unique_tools_created = 0.0
        avg_custom_tool_uses = 0.0
        resolve_rate = 0.0

        #Total counters for the model/configuration
        total_total_tokens = 0.0
        total_api_calls = 0
        total_task_description_edits = 0
        total_reflection_prompt_edits = 0
        total_tools_created = 0
        total_unique_tools_created = 0
        total_custom_tool_uses = 0

        NUMBER_OF_RUNS = len(list(model_dir.iterdir()))  # Count the number of runs for this model/configuration

        #Process each model dir in config dir
        model = model_dir.name

        for run_dir in model_dir.iterdir():

            resolved_ids = get_resolved_ids(str(run_dir) + "/eval-results.json")

            run_total_tokens = 0.0
            run_api_calls = 0
            run_task_description_edits = 0
            run_reflection_prompt_edits = 0
            run_tools_created = 0
            run_unique_tools_created = 0
            run_custom_tool_uses = 0
            run_resolved = 0

            count =  0

            for file_path in find_traj_files(run_dir):
                stats = extract_stats(file_path)

                if stats is None:
                    continue

                resolved = int(stats["instance"] in resolved_ids)

                difficulty = difficulty_dict.get(stats["instance"], None)

                config_tuple = EVOL_TASKS.get(config, (0, 0, 0))

                stats.update({
                                "resolved": resolved,
                                "configuration": config,
                                "model" : model,
                                "task_evolution": config_tuple[0],
                                "reflection_evolution": config_tuple[1],
                                "tool_evolution": config_tuple[2],
                                "difficulty": difficulty
                            })

                write_to_in_csv([stats])
                global IN_MODE
                IN_MODE = 'a'  # Switch to append mode after the first write

                run_total_tokens += float(stats["total_tokens"])
                run_api_calls += int(stats["api_calls"])
                run_task_description_edits += int(stats.get("n_task_description_edits", 0))
                run_reflection_prompt_edits += int(stats.get("n_reflection_prompt_edits", 0))
                run_tools_created += int(stats.get("n_tools_created", 0))
                run_unique_tools_created += int(stats.get("n_unique_tools_created", 0))
                run_custom_tool_uses += int(stats.get("n_custom_tool_uses", 0))
                run_resolved += resolved
                count += 1

            avg_total_tokens += round(run_total_tokens / count, 2) if count else 0.0
            avg_api_calls += round(run_api_calls / count, 2) if count else 0.0
            avg_task_description_edits += round(run_task_description_edits / count, 2) if count else 0.0
            avg_reflection_prompt_edits += round(run_reflection_prompt_edits / count, 2) if count else 0.0
            avg_tools_created += round(run_tools_created / count, 2) if count else 0.0
            avg_unique_tools_created += round(run_unique_tools_created / count, 2) if count else 0.0
            avg_custom_tool_uses += round(run_custom_tool_uses / count, 2) if count else 0.0
            resolve_rate += round(run_resolved / count, 2) if count else 0.0

            total_total_tokens += run_total_tokens
            total_api_calls += run_api_calls
            total_task_description_edits += run_task_description_edits
            total_reflection_prompt_edits += run_reflection_prompt_edits
            total_tools_created += run_tools_created
            total_unique_tools_created += run_unique_tools_created     
            total_custom_tool_uses += run_custom_tool_uses

        cummulative_stats = {
            "model" :  model,
            "configuration" : config,
            "total_total_tokens" : round(total_total_tokens/NUMBER_OF_RUNS, 2),
            "total_api_calls" : round(total_api_calls/NUMBER_OF_RUNS, 2),
            "total_task_description_edits" : round(total_task_description_edits/NUMBER_OF_RUNS, 2),
            "total_reflection_prompt_edits" : round(total_reflection_prompt_edits/NUMBER_OF_RUNS, 2),
            "total_tools_created" : round(total_tools_created/NUMBER_OF_RUNS, 2),
            #"total_unique_tools_created" : round(total_unique_tools_created/NUMBER_OF_RUNS, 2),
            "total_custom_tool_uses" : round(total_custom_tool_uses/NUMBER_OF_RUNS, 2),
            "avg_total_tokens" : round(avg_total_tokens/NUMBER_OF_RUNS, 2),
            "avg_api_calls" : round(avg_api_calls/NUMBER_OF_RUNS, 2),
            "avg_task_edits" : round(avg_task_description_edits/NUMBER_OF_RUNS, 2),
            "avg_reflection_edits" : round(avg_reflection_prompt_edits/NUMBER_OF_RUNS, 2),
            "avg_tools_created" : round(avg_tools_created/NUMBER_OF_RUNS, 2),
            #"avg_unique_tools_created" : round(avg_unique_tools_created/NUMBER_OF_RUNS, 2),
            "avg_tools_used" : round(avg_custom_tool_uses/NUMBER_OF_RUNS, 2),
            "resolve_rate" : round(resolve_rate/NUMBER_OF_RUNS, 2)
        }

        write_to_ag_csv([cummulative_stats])

        global AG_MODE
        AG_MODE = 'a'  # Switch to append mode after the first write


def main():

    parser = argparse.ArgumentParser(
        description="Aggregate model_stats from *.traj.json files into a CSV."
    )
    parser.add_argument(
        "directory",
        help="Root directory to search recursively"
    )
    args = parser.parse_args()

    root = Path(args.directory).resolve()

    if not root.is_dir():
        print(f"Error: '{root}' is not a valid directory.")
        return 1

    difficulty_dict = get_difficulty_from_instance_dict()

    config_paths = list(root.iterdir())
    for path in config_paths:
        if not path.is_dir():
            print(f"Warning: '{path}' is not a directory; skipping.")
            continue
        process_config_directory(path, difficulty_dict)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
