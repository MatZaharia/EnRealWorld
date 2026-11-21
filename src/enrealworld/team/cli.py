import argparse
import json
from pathlib import Path

from .runner import run


def main():
    parser = argparse.ArgumentParser(description="Run the EnRealWorld team.")
    parser.add_argument("config", type=Path, help="Path to the JSON run configuration")
    args = parser.parse_args()

    try:
        with args.config.open(encoding="utf-8") as config_file:
            config = json.load(config_file)
    except (OSError, ValueError) as error:
        parser.error(f"Could not read configuration {args.config}: {error}")
    if not isinstance(config, dict):
        parser.error("The run configuration must be a JSON object.")

    result = run(config)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1
