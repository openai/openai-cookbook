from pathlib import Path
import logging
import sys
from pprint import pformat
import yaml

# Load config items from config.yaml.
# Use Path.resolve() to get the absolute path of the parent directory
yaml_dir = Path(__file__).resolve().parent
yaml_path = yaml_dir / "config.yaml"  # Use Path / operator to join paths

def load_yaml_config(path):
    """Load a yaml file and return a dictionary of its contents."""
    try:
        with open(path, "r") as stream:
            return yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        logging.error(f"Failed to load {path}: {exc}")
        return None

# Load the config and update the global variables
yaml_config = load_yaml_config(yaml_path)
if yaml_config is not None:
    logging.info(f"Loaded config from {yaml_path}:")
    logging.info(pformat(yaml_config))
    globals().update(yaml_config)
else:
    logging.error(f"Could not load config from {yaml_path}.")
    sys.exit(1)  # Exit the program if the config is invalid

# Set a default value for SERVER_PORT if not specified in the config
SERVER_PORT = yaml_config.get("SERVER_PORT", None)

# Use Path.resolve() to get the absolute path of the current directory
SERVER_DIR = Path(__file__).resolve().parent
