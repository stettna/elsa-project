# Casual Analysis of Self-evolving LLM Agents 
This repository contains all artifacts generated as a result of my Thesis work entitled "". Its contents are broken down as follows:

- custom_configs - Contains the custom configuration files created to enable prompt evolution for the enhancement and run all evaluations.

- mini-swe-agent-v1 - Contains the source code for the original mini-swe-agent v1 implementation which we have modified in a few places to enable prompt evolution.

- results - Contains all results and related data for all experiments conducted during this study.

- scripts - Contains some helpful python and shell script we created to automate some of the process for running the experiments and collecting data. 

- subsets - Contains csv files that list the instance names for the particular random subset of problems from SWE-bench Verified and SWE-bench Multilingual we used in our experiments.

## Installation

To use our modified version of mini-swe-agent in order to support task and reflection prompt evolution, clone our repository and then run `pip install -e .` from the mini-swe-agent directory in our repository. 

Follow the remaining installation steps regardless of which mini-swe-agent you installed.

If you want to be able to run evaluations using SWE-bench, be sure to also install datasets using `pip install datasets`

SWE-bench can be installed using the installation instructions in the [SWE-bench repository](https://github.com/SWE-bench/SWE-bench).

## Running the agent on SWE-bench
In order to benchmark the performance of the agent, we have provided a script to simplify the process of running the subsets of SWE-Bench problems that we use in our research.

The script can be executed in the command line with the following syntax:

`run_subset.sh   PATH_TO_CONFIGURATION_FILE   PATH_TO_CSV_FILE_OF_SWE_BENCH_INSTANCES  SUBSET_NAME <PATH_TO_OUTPUT_DIRECTORY>   <REDO_EXISTING_INSTANCES>`

Arguments encased in <> are optional. If no run directory is specified, a runs directory will be created in the current working directory. If the redo_existing_instances flag is left unspecified, it will default to false. 

## Evaluating the SWE-bench Predictions
Once the agent has finished processing all of the SWE-Bench issues, its performance can be evaluated using the following input on the command line:

` python -m swebench.harness.run_evaluation     --dataset_name SWE-bench/SWE-bench_Verified     --predictions_path PATH_TO_PREDS.JSON_FILE     --run_id UNIQUE_RUN_ID `

If you want more statistics such as how much each instance cost and how many API calls were used, you can use the get_model_stats.py script as follows:

`python get_stats.py PATH_TO_DIRECTORY_CONTAINING_RUN_OUTPUTS`

This will generate a CSV file containing the stats broken down for each instance. The file is stored in the directory provided in the input.

## Additional Documentation
This project spans multiple different existing repo including mini-swe-agent, live-swe-agent, and swe-bench. Below is a summary of all documentation links we found useful in replicating this work.

- [Live-SWE-agent Repo](https://github.com/OpenAutoCoder/live-swe-agent) - This link is for the live-swe-agent repo which contains documentation on how to run live-swe-agent.

- [Mini-SWE-agent Documentation](https://mini-swe-agent.com/v1/usage/swebench/) - This link contains detailed info on working with mini-swe-agent v1 and v2.

- [Mini-SWE-agent Repo](https://github.com/SWE-agent/mini-swe-agent) - This link is for the mini-swe-agent repo which contains documentation on how to run mini-swe-agent.

- [SWE-bench Documentation](https://www.swebench.com/SWE-bench/) - This link is for the SWE-bench site which contains documentation for SWE-bench as well as leaderboard stats.

- [SWE-bench](https://github.com/SWE-bench/SWE-bench) - This is the link to the SWE-bench repo which contains the testing harness to evaluate the predictions made by the agent. 