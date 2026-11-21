"""Isolated native three-role collaboration. Runtime performs no semantic review."""
import sys

from enrealworld.coordination import requirements, scene_graph

# Keep existing module imports working after moving the coordination modules.
for _module in (requirements, scene_graph):
    sys.modules[f"{__name__}.{_module.__name__.rsplit('.', 1)[-1]}"] = _module

from .runner import run
