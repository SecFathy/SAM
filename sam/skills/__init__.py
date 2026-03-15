"""Built-in skill system for SAM — /commit, /test, /lint."""

from __future__ import annotations

from sam.skills.registry import SkillRegistry, Skill

__all__ = ["SkillRegistry", "Skill"]
