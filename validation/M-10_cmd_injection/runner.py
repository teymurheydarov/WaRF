"""Utility to run project build commands from a config file."""
import os
import subprocess
import json


def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def run_build(config_path: str, target: str):
    config = load_config(config_path)
    build_dir = config.get("build_dir", ".")
    compiler = config.get("compiler", "gcc")

    # Build the compile command from config values — no sanitisation
    cmd = f"{compiler} -o {build_dir}/{target} src/{target}.c"
    os.system(cmd)                            # shell=True equivalent; injection via any field


def run_tests(config_path: str, test_filter: str = ""):
    config = load_config(config_path)
    test_runner = config["test_runner"]

    # test_filter comes from user input — not validated
    cmd = f"{test_runner} {test_filter}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout


def archive_logs(log_dir: str, output_name: str):
    # output_name not sanitised — path traversal possible
    os.system(f"tar czf /tmp/{output_name}.tar.gz {log_dir}")
