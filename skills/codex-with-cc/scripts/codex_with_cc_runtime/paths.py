from __future__ import annotations

import os
from pathlib import Path



def runtime_python_root() -> Path:
    return Path(__file__).resolve().parents[1]



def workflow_root() -> Path:
    return runtime_python_root().parent



def repo_root() -> Path:
    return Path.cwd().resolve()



def workflow_relative_path() -> str:
    root = workflow_root().resolve()
    repo = repo_root().resolve()
    try:
        return root.relative_to(repo).as_posix()
    except ValueError:
        return root.as_posix()



def script_family() -> str:
    return "windows_scripts" if os.name == "nt" else "macos_scripts"



def script_ext() -> str:
    return ".ps1" if os.name == "nt" else ".sh"
