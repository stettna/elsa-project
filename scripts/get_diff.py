import pandas as pd

def get_difficulty_from_instance_dict() -> Optional[Dict[str, int]]:

    splits = {'test': 'data/test-00000-of-00001.parquet', 'dev': 'data/dev-00000-of-00001.parquet'}
    df = pd.read_parquet("hf://datasets/SWE-bench/SWE-bench/" + splits["test"])

    #read instance_id into list from csv file
    instance_ids = pd.read_csv("../subsets/swe-bench-verified-50.csv")["instance_id"].tolist()

    #select only rows with instance_id in the list and save difficulty field and instance_id to a new dataframe
    df_filtered = df[df['instance_id'].isin(instance_ids)][['instance_id', 'difficulty']]

    #encode difficulty as 0 for easy, 1 for medium, 2 for hard
    df_filtered['difficulty'] = df_filtered['difficulty'].map({'<15 min fix': 1, '15 min - 1 hour': 2, '1-4 hours': 3, '>4 hours': 3})

    #use dictionary comprehension to create a dictionary from the filtered dataframe
    difficulty_dict = {row['instance_id']: row['difficulty'] for _, row in df_filtered.iterrows()} 

    return difficulty_dict

print(get_difficulty_from_instance_dict())