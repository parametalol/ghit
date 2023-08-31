
from dataclasses import dataclass


@dataclass
class Args:
    stack: str
    repository: str
    offline: bool
    title: str
    debug: bool
    verbose: bool
    draft: bool
    branch: str
