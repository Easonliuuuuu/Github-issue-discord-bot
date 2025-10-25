import json
import os
from config import DATA_FILE_PATH

def load_data():
    """Loads the watch list and notified issues from the JSON file."""
    watched_repos = {}
    notified_issues = set()
    
    if os.path.exists(DATA_FILE_PATH):
        try:
            with open(DATA_FILE_PATH, 'r') as f:
                data = json.load(f)
                
                # Check for old data format and migrate
                raw_watched_repos = data.get('watched_repos', {})
                migrated_watched_repos = {}
                if raw_watched_repos:
                    # Check the format of the first item to guess schema
                    try:
                        first_key = next(iter(raw_watched_repos))
                        first_val = raw_watched_repos[first_key]
                    except StopIteration:
                        first_val = None # Handle empty dict

                    if isinstance(first_val, int): # Old format: "repo": channel_id
                        print("Old data format detected. Migrating...")
                        for repo, channel_id in raw_watched_repos.items():
                            migrated_watched_repos[repo] = {
                                "channel_id": channel_id,
                                "labels": ["good first issue"] # Default old label
                            }
                        watched_repos = migrated_watched_repos
                        print("Migration complete. Saving new format.")
                        # Save immediately after migration
                        save_data(watched_repos, notified_issues) 
                    else: # Assume new format
                        watched_repos = raw_watched_repos
                
                # Load as a set for efficient lookups
                notified_issues = set(data.get('notified_issues', []))
            print(f"Loaded data from {DATA_FILE_PATH}")
        except Exception as e:
            print(f"Error reading or migrating {DATA_FILE_PATH}: {e}. Starting with empty data.")
            watched_repos = {}
            notified_issues = set()
    else:
        print(f"{DATA_FILE_PATH} not found. Starting with empty data.")
        
    return watched_repos, notified_issues

def save_data(watched_repos, notified_issues):
    """Saves the current state to the JSON file."""
    try:
        with open(DATA_FILE_PATH, 'w') as f:
            data = {
                'watched_repos': watched_repos,
                'notified_issues': list(notified_issues)  # Convert set to list for JSON
            }
            json.dump(data, f, indent=4)
        print(f"Saved data to {DATA_FILE_PATH}")
    except IOError as e:
        print(f"Error saving data: {e}")


