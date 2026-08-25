"""``workspace.*`` RPC surface, registered through the P0 extension seam.

``dream/bridge/methods.py`` is never edited. Every handler name starts with
``workspace.`` so discovery accepts the module. Existing ``project.*`` RPCs
remain the S06 surface; Projects 2.0 extras live here.
"""

from __future__ import annotations

from typing import Any

from dream.agentmodes.errors import AgentModeError
from dream.agentmodes.service import get_service as agent_service
from dream.agentmodes.service import reset_service as reset_agent_service
from dream.bridge.errors import BridgeError, invalid_params
from dream.workspace.errors import WorkspaceError, WorkspaceSecurityError
from dream.workspace.service import get_service as workspace_service
from dream.workspace.service import reset_service as reset_workspace_service

__all__ = ["HANDLERS", "reset_agent_service", "reset_workspace_service"]


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged


def _wrap(call):  # type: ignore[no-untyped-def]
    try:
        return call()
    except (WorkspaceSecurityError, WorkspaceError, AgentModeError) as exc:
        raise invalid_params(str(exc)) from None
    except BridgeError:
        raise
    except (TypeError, ValueError) as exc:
        raise invalid_params(str(exc)) from None


def _string(data: dict[str, Any], key: str, *, required: bool = True, limit: int = 4_096) -> str:
    value = data.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise invalid_params(f"{key} must be a non-empty string of at most {limit} characters")
    return value.strip()


def workspace_roots_list(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    project_id = data.get("project_id")
    session_id = data.get("session_id")
    if project_id is not None and not isinstance(project_id, str):
        raise invalid_params("project_id must be a string")
    if session_id is not None and not isinstance(session_id, str):
        raise invalid_params("session_id must be a string")
    return _wrap(
        lambda: workspace_service().list_roots(project_id=project_id, session_id=session_id)
    )


def workspace_roots_register(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    folder = _string(data, "folder")
    name = data.get("name")
    if name is not None and not isinstance(name, str):
        raise invalid_params("name must be a string")
    return _wrap(
        lambda: workspace_service().import_folder(
            folder,
            name=name,
            project_id=data.get("project_id") if isinstance(data.get("project_id"), str) else None,
            session_id=data.get("session_id") if isinstance(data.get("session_id"), str) else None,
            adopt_project=bool(data.get("adopt_project", True)),
        )
    )


def workspace_roots_unregister(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    root_id = _string(data, "root_id", limit=80)
    return _wrap(lambda: workspace_service().unregister(root_id))


def workspace_import_folder(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    return workspace_roots_register(params, **kwargs)


def workspace_files_list(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    root_id = _string(data, "root_id", limit=80)
    rel = data.get("path") or data.get("rel") or ""
    if rel is not None and not isinstance(rel, str):
        raise invalid_params("path must be a string")
    cursor = data.get("cursor", 0)
    limit = data.get("limit", 100)
    if not isinstance(cursor, int) or isinstance(cursor, bool):
        raise invalid_params("cursor must be an integer")
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise invalid_params("limit must be an integer")
    return _wrap(
        lambda: workspace_service().files_list(
            root_id,
            rel or None,
            cursor=cursor,
            limit=limit,
            include_hidden=bool(data.get("include_hidden", False)),
        )
    )


def workspace_files_stat(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    root_id = _string(data, "root_id", limit=80)
    rel = _string(data, "path")
    return _wrap(lambda: workspace_service().files_stat(root_id, rel))


def workspace_files_preview(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: workspace_service().files_preview(
            _string(data, "root_id", limit=80), _string(data, "path")
        )
    )


def workspace_files_read(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    root_id = _string(data, "root_id", limit=80)
    rel = _string(data, "path")
    return _wrap(lambda: workspace_service().files_read(root_id, rel))


def workspace_project_adopt(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    folder = _string(data, "folder")
    name = data.get("name") if isinstance(data.get("name"), str) else None
    return _wrap(lambda: workspace_service().project_adopt(folder, name=name))


def workspace_project_settings(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    project_id = _string(data, "project_id", limit=80)
    updates = data.get("settings") or data.get("updates")
    if updates is not None and not isinstance(updates, dict):
        raise invalid_params("settings must be an object")
    return _wrap(lambda: workspace_service().project_settings(project_id, updates))


def workspace_project_move_session(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: workspace_service().project_move_session(
            _string(data, "project_id", limit=80), _string(data, "session_id", limit=80)
        )
    )


def workspace_agentmode_plan(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    prompt = _string(data, "prompt", limit=8_000)
    language = data.get("language", "en")
    if not isinstance(language, str):
        raise invalid_params("language must be a string")
    return _wrap(lambda: agent_service().plan(prompt, language=language))


def workspace_agentmode_continue(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    plan_id = _string(data, "plan_id", limit=80)
    delay = data.get("step_delay", 0.0)
    if not isinstance(delay, (int, float)) or isinstance(delay, bool):
        raise invalid_params("step_delay must be a number")
    return _wrap(lambda: agent_service().continue_plan(plan_id, step_delay=float(delay)))


def workspace_agentmode_goal(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    objective = _string(data, "objective", limit=4_000)
    criteria = data.get("criteria")
    if not isinstance(criteria, list):
        raise invalid_params("criteria must be a list of strings")
    return _wrap(
        lambda: agent_service().goal(
            objective, criteria, allow_network=bool(data.get("allow_network", False))
        )
    )


def workspace_agentmode_report(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: agent_service().report(_string(data, "goal_id", limit=80)))


def workspace_agentmode_stop(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: agent_service().stop(
            plan_id=data.get("plan_id") if isinstance(data.get("plan_id"), str) else None,
            goal_id=data.get("goal_id") if isinstance(data.get("goal_id"), str) else None,
            subagent_id=data.get("subagent_id")
            if isinstance(data.get("subagent_id"), str)
            else None,
        )
    )


def workspace_agentmode_status(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    _params(params, kwargs)
    return _wrap(lambda: agent_service().status())


def workspace_subagents_live(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    _params(params, kwargs)
    return _wrap(lambda: agent_service().live_subagents())


def workspace_refs_parse(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: agent_service().refs_parse(_string(data, "text", limit=20_000)))


def workspace_refs_file(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: agent_service().refs_file(_string(data, "root_id", limit=80), _string(data, "path"))
    )


def workspace_refs_conversation(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: agent_service().refs_conversation(_string(data, "session_id", limit=80)))


def workspace_commands_list(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    query = data.get("query", "")
    if not isinstance(query, str):
        raise invalid_params("query must be a string")
    return _wrap(lambda: agent_service().commands(query))


def workspace_shell_propose(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    return _wrap(
        lambda: agent_service().shell_propose(_string(data, "command", limit=500), cwd=cwd)
    )


def workspace_shell_execute(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: agent_service().shell_execute(
            _string(data, "approval_id", limit=80), approved=bool(data.get("approved", False))
        )
    )


HANDLERS = {
    "workspace.roots_list": workspace_roots_list,
    "workspace.roots_register": workspace_roots_register,
    "workspace.roots_unregister": workspace_roots_unregister,
    "workspace.import_folder": workspace_import_folder,
    "workspace.files_list": workspace_files_list,
    "workspace.files_stat": workspace_files_stat,
    "workspace.files_preview": workspace_files_preview,
    "workspace.files_read": workspace_files_read,
    "workspace.project_adopt": workspace_project_adopt,
    "workspace.project_settings": workspace_project_settings,
    "workspace.project_move_session": workspace_project_move_session,
    "workspace.agentmode_plan": workspace_agentmode_plan,
    "workspace.agentmode_continue": workspace_agentmode_continue,
    "workspace.agentmode_goal": workspace_agentmode_goal,
    "workspace.agentmode_report": workspace_agentmode_report,
    "workspace.agentmode_stop": workspace_agentmode_stop,
    "workspace.agentmode_status": workspace_agentmode_status,
    "workspace.subagents_live": workspace_subagents_live,
    "workspace.refs_parse": workspace_refs_parse,
    "workspace.refs_file": workspace_refs_file,
    "workspace.refs_conversation": workspace_refs_conversation,
    "workspace.commands_list": workspace_commands_list,
    "workspace.shell_propose": workspace_shell_propose,
    "workspace.shell_execute": workspace_shell_execute,
}
