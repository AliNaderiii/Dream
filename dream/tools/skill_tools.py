"""Skill management tools for learning, retrieving, editing, and applying skills."""

from __future__ import annotations

from typing import Any

from dream.tools.base import tool


@tool(risk="guarded")
def save_skill(name: str, description: str, steps: list) -> dict[str, Any]:
    """Save a reusable skill: a named procedure to follow in later requests.

    The skill becomes a plain text file inside ``skills/`` in the workspace
    that the owner can read and correct by hand. The description must say
    when the skill applies; it is what future requests are matched against.

    :param name: Skill name; also the file name, so path characters are refused.
    :param description: When this skill applies, in the owner's words.
    :param steps: Ordered steps the assistant should follow.
    """
    from dream import skills  # deferred: dream.skills imports this module

    cleaned = skills.validate_name(name)
    was_present = (skills._skills_dir() / f"{cleaned}{skills.SKILL_SUFFIX}").exists()
    filename = skills.save_skill(cleaned, description, steps)
    return {"filename": filename, "status": "updated" if was_present else "created"}


@tool(risk="safe")
def use_skill(query: str) -> dict[str, Any]:
    """Find the stored skill that applies to a request and return its steps.

    Reading a skill never runs anything: the steps are text the assistant
    follows using its ordinary tools and their ordinary approvals.

    :param query: The request to match, in any wording.
    """
    from dream import skills  # deferred: dream.skills imports this module

    skill = skills.find_skill(query)
    if skill is None:
        return {"match": None}
    try:
        from dream.skills.store import get_ledger

        with get_ledger() as ledger:
            ledger.log_use(skill.name, "success", duration_ms=0.0, source="use_skill")
    except Exception:
        pass
    return {
        "match": {
            "name": skill.name,
            "description": skill.description,
            "steps": list(skill.steps),
            "filename": skill.filename,
        }
    }


@tool(risk="safe")
def list_skills() -> dict[str, Any]:
    """List every stored skill, plus any file that failed to load."""
    from dream import skills  # deferred: dream.skills imports this module

    loaded, problems = skills.load_skills()
    return {
        "skills": [
            {
                "name": skill.name,
                "description": skill.description,
                "steps": list(skill.steps),
                "filename": skill.filename,
            }
            for skill in loaded
        ],
        "problems": [
            {"filename": problem.filename, "detail": problem.detail} for problem in problems
        ],
    }


@tool(risk="safe")
def skill_view(name: str) -> dict[str, Any]:
    """Load one installed skill's body. Catalog entries never include the body.

    :param name: Skill name or slash name (for example ``ocr-and-documents``).
    """
    from dream import skills  # deferred: dream.skills imports this module

    return skills.view_skill(name)


@tool(risk="guarded")
def edit_skill(name: str, description: str, body: str) -> dict[str, Any]:
    """Create or version a SKILL.md skill. Never silently overwrites history.

    :param name: Hyphen-case skill name (folder name).
    :param description: When this skill applies; at most 60 characters.
    :param body: Markdown instructions. Do not invent commands.
    """
    from dream import skills  # deferred: dream.skills imports this module

    return skills.edit_skill(name, description, body)


@tool(risk="guarded")
def delete_skill(name: str) -> dict[str, Any]:
    """Delete the current file for an installed skill. Version history is kept.

    :param name: Skill name or slash name.
    """
    from dream import skills  # deferred: dream.skills imports this module

    return skills.delete_skill(name)


@tool(risk="guarded")
def save_skill_bundle(
    name: str,
    description: str,
    body: str,
    references: dict | None = None,
) -> dict[str, Any]:
    """Save a knowledge-base skill (SKILL.md plus references/). Merges on re-learn.

    :param name: Hyphen-case skill name.
    :param description: When this skill applies; at most 60 characters.
    :param body: Lean markdown instructions.
    :param references: Optional map of topic name to distilled markdown.
    """
    from dream.skills.learn import install_skill_bundle

    return install_skill_bundle(name, description, body, references)


@tool(risk="guarded")
def apply_skill_proposal(proposal_id: str) -> dict[str, Any]:
    """Apply an approved post-task skill proposal. Denial must not call this.

    :param proposal_id: Identifier from the proposal notice.
    """
    from dream.skills.propose import apply_proposal

    return apply_proposal(proposal_id)


@tool(risk="safe")
def discard_skill_proposal(proposal_id: str) -> dict[str, Any]:
    """Discard a pending skill proposal. Nothing is written.

    :param proposal_id: Identifier from the proposal notice.
    """
    from dream.skills.propose import discard_proposal

    discarded = discard_proposal(proposal_id)
    return {"discarded": discarded, "proposal_id": proposal_id}
