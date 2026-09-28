"""
File utility module for reading and writing user-accessible files.
"""

import os


def read_user_file(base_dir: str, filename: str) -> str:
    """Read a file from the base directory using a user-supplied filename.

    Args:
        base_dir: The root directory files are served from.
        filename: The filename requested by the user.

    Returns:
        The file contents as a string.
    """
    path = os.path.join(base_dir, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_user_file(base_dir: str, filename: str, content: str) -> None:
    """Write content to a file in the base directory.

    Args:
        base_dir: The root directory files are written to.
        filename: The filename requested by the user.
        content: The content to write.
    """
    path = os.path.join(base_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
