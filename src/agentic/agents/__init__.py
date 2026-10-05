"""6 tác tử của hệ thống.

Mỗi tác tử là một module riêng, đều kế thừa Agent (base.py) trừ reporter
— reporter là code thuần, không gọi model.
"""

from agentic.agents import architect, designer, developer, devops, qa, reporter

__all__ = [
    "architect",
    "designer",
    "developer",
    "devops",
    "qa",
    "reporter",
]
