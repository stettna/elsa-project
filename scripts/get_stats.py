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
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

CONFIG_NUM_OF_EVOL_TASKS = {
    "task_and_reflection_and_tool": 3, #tool + task + reflection
    "task_tool": 2,                    #tool + task
    "reflection_tool": 2,              #tool + reflection
    "task_reflection": 2,              #reflection + task
    "task_only": 1,                    #task
    "reflection_only": 1,              #reflection
    "tool_only": 1,                    #tool
    "no_evo" : 0,                      #none
}

PATH_TO_AG_CSV = "../results/aggregated_results.csv"   #Assumes script is run from within the scripts directory
PATH_TO_IN_CSV = "../results/per_instance_results.csv" #Assumes script is run from within the scripts directory

AG_MODE = 'w'  # Start with write mode for the aggregated CSV
IN_MODE = 'w'  # Start with write mode for the per-instance CSV

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
            "n_unique_tools_created": 0,
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
            "n_unique_tools_created" : n_unique_tools_created,
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
      - instance_cost
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

        res = {
            "instance": file_path.name[:-len(".traj.json")],
            "instance_cost": round(float(model_stats["instance_cost"]), 2),
            "api_calls": model_stats["api_calls"],
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
                "n_evo_tasks",
                "model", 
                "total_cost",
                "total_api_calls",
                "total_task_description_edits",
                "total_reflection_prompt_edits",
                "total_tools_created",
                "total_unique_tools_created",
                "total_custom_tool_uses", 
                "avg_cost", 
                "avg_api_calls", 
                "avg_task_edits",
                "avg_reflection_edits", 
                "avg_tools_created",
                "avg_unique_tools_created", 
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
                "configuration",
                "n_evo_tasks",
                "model", 
                "instance_cost",
                "api_calls",
                "n_task_description_edits",
                "n_reflection_prompt_edits",
                "n_tools_created",
                "n_unique_tools_created",
                "n_custom_tool_uses", 
                "resolved"
            ],
        )
        if IN_MODE == 'w':
            writer.writeheader()
        writer.writerows(rows)      

def process_config_directory(config_dir: Path):
    """Process a single configuration directory."""

    config = str(config_dir).split("/")[-1]
    n_evo_tasks = CONFIG_NUM_OF_EVOL_TASKS[config]

    for model_dir   in config_dir.iterdir():

        #Ensure path is dir
        if not model_dir.is_dir():
            print(f"Warning: '{model_dir}' is not a directory; skipping.")
            continue

        resolved_ids = get_resolved_ids(str(model_dir) + "/eval-results.json")
        model = str(model_dir).split("/")[-1]

        total_cost = 0.0
        total_api_calls = 0
        total_task_description_edits = 0
        total_reflection_prompt_edits = 0
        total_tools_created = 0
        total_unique_tools_created = 0
        total_custom_tool_uses = 0
        total_resolved = 0
        count = 0

        #Process each model dir in config dir
        model = model_dir.name

        for file_path in find_traj_files(model_dir):
            stats = extract_stats(file_path)

            if stats is None:
                continue

            resolved = int(stats["instance"] in resolved_ids)
            stats.update({
                            "resolved": resolved,
                            "model" : model,
                            "configuration": config,
                            "n_evo_tasks" : n_evo_tasks
                        })

            write_to_in_csv([stats])
            global IN_MODE
            IN_MODE = 'a'  # Switch to append mode after the first write

            total_cost += float(stats["instance_cost"])
            total_api_calls += int(stats["api_calls"])
            total_task_description_edits += int(stats.get("n_task_description_edits", 0))
            total_reflection_prompt_edits += int(stats.get("n_reflection_prompt_edits", 0))
            total_tools_created += int(stats.get("n_tools_created", 0))
            total_unique_tools_created += int(stats.get("n_unique_tools_created", 0))
            total_custom_tool_uses += int(stats.get("n_custom_tool_uses", 0))
            total_resolved += resolved
            count += 1

        avg_cost = round(total_cost / count, 2) if count else 0.0
        avg_api_calls = round(total_api_calls / count, 2) if count else 0.0
        avg_task_description_edits = round(total_task_description_edits / count, 2) if count else 0.0
        avg_reflection_prompt_edits = round(total_reflection_prompt_edits / count, 2) if count else 0.0
        avg_tools_created = round(total_tools_created / count, 2) if count else 0.0
        avg_unique_tools_created = total_unique_tools_created / count if count else 0.0
        avg_custom_tool_uses = round(total_custom_tool_uses / count, 2) if count else 0.0
        resolve_rate = round(total_resolved / count, 2) if count else 0.0

        cummulative_stats = {
            "model" :  model,
            "configuration" : config,
            "n_evo_tasks" : n_evo_tasks,
            "total_cost" : round(total_cost, 2),
            "total_api_calls" : total_api_calls,
            "total_task_description_edits" : total_task_description_edits,
            "total_reflection_prompt_edits" : total_reflection_prompt_edits,
            "total_tools_created" : total_tools_created,
            "total_unique_tools_created" : total_unique_tools_created,
            "total_custom_tool_uses" : total_custom_tool_uses,
            "avg_cost" : avg_cost,
            "avg_api_calls" : avg_api_calls,
            "avg_task_edits" : avg_task_description_edits,
            "avg_reflection_edits" : avg_reflection_prompt_edits,
            "avg_tools_created" : avg_tools_created,
            "avg_unique_tools_created" : avg_unique_tools_created,
            "avg_tools_used" : avg_custom_tool_uses,
            "resolve_rate" : resolve_rate
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

    config_paths = list(root.iterdir())
    for path in config_paths:
        if not path.is_dir():
            print(f"Warning: '{path}' is not a directory; skipping.")
            continue
        process_config_directory(path)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
