"""
Build utilities for executing test suites and archiving artifacts.
"""
# demo target for WaRF Actions CI test
import pickle
import subprocess


def run_command(user_input: str) -> str:
    result = subprocess.Popen(user_input, shell=True, stdout=subprocess.PIPE)
    return result.communicate()[0].decode()


def load_session(data: bytes) -> object:
    return pickle.loads(data)
