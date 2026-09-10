"""Dream Tool Subsystem: definitions, execution, validation, and toolsets."""

from __future__ import annotations

import logging
import socket
from datetime import datetime
from urllib.request import build_opener
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dream.memory import normalize_fa
from dream.security.blocklist import scan as _floor_scan
from dream.security.engine import SHELL_COMMAND_TOOLS as _FLOOR_COMMAND_TOOLS
from dream.tools.base import (
    MAX_LIST_ITEMS,
    MAX_MAPPING_KEYS,
    MAX_NESTING_DEPTH,
    MAX_SERIALIZED_INPUT_SIZE,
    MAX_TOOL_INPUT_CHARS,
    NUMERIC_RANGES,
    REGISTRY,
    RISKS,
    WORKSPACE_ROOT,
    Tool,
    _allows_none,
    _check_cycles,
    _json_type,
    _param_descriptions,
    _union_json_type,
    _validate_tool_arguments,
    _validate_value,
    get_parameter_category,
    tool,
)
from dream.tools.datetime_tools import get_datetime
from dream.tools.execution import _failure_payload, execute
from dream.tools.math_tools import (
    _ALLOWED_BINARY_OPERATORS,
    _ALLOWED_UNARY_OPERATORS,
    _calculate_node,
    calculate,
)
from dream.tools.reminder_tools import (
    cancel_reminder,
    create_reminder,
)
from dream.tools.schemas import (
    anthropic_schemas,
    gemini_schemas,
    openai_schemas,
)
from dream.tools.skill_tools import (
    apply_skill_proposal,
    delete_skill,
    discard_skill_proposal,
    edit_skill,
    list_skills,
    save_skill,
    save_skill_bundle,
    skill_view,
    use_skill,
)
from dream.tools.system_tools import (
    run_shell,
    send_email,
)
from dream.tools.toolsets import (
    BUILTIN_TOOLSETS,
    Toolset,
    filter_tools,
    get_toolset,
    list_toolsets,
    register_toolset,
    unregister_toolset,
)
from dream.tools.web_tools import (
    _NETWORK_ENABLED_VALUES,
    _WIKI_HOSTS,
    NETWORK_DISABLED_MESSAGE,
    NETWORK_EMPTY_MESSAGE,
    NETWORK_REFUSAL_MESSAGE,
    NETWORK_TIMEOUT_SECONDS,
    PAGE_RESPONSE_CAP,
    PAGE_TEXT_CAP,
    SEARCH_RESPONSE_CAP,
    _AddressRefused,
    _default_open_network_request,
    _fetch,
    _network_enabled,
    _open_network_request,
    _ReadableText,
    _related_topics,
    _RestrictedRedirectHandler,
    _strip_markup,
    _validate_network_url,
    _wikipedia_topics,
    read_page,
    search_web,
)
from dream.tools.workspace_tools import (
    _RESERVED_DEVICE_NAMES,
    _check_reserved_path,
    _is_reserved_name,
    _reserved_stem,
    _safe_path,
    list_notes,
    read_note,
    write_note,
)

logger = logging.getLogger(__name__)

# Explicit re-exports for backward compatibility & test monkeypatch seams
_ALLOWED_BINARY_OPERATORS = _ALLOWED_BINARY_OPERATORS
_ALLOWED_UNARY_OPERATORS = _ALLOWED_UNARY_OPERATORS
_calculate_node = _calculate_node
_allows_none = _allows_none
_check_cycles = _check_cycles
_json_type = _json_type
_param_descriptions = _param_descriptions
_union_json_type = _union_json_type
_validate_tool_arguments = _validate_tool_arguments
_validate_value = _validate_value
_failure_payload = _failure_payload
_floor_scan = _floor_scan
_FLOOR_COMMAND_TOOLS = _FLOOR_COMMAND_TOOLS
_AddressRefused = _AddressRefused
_NETWORK_ENABLED_VALUES = _NETWORK_ENABLED_VALUES
_WIKI_HOSTS = _WIKI_HOSTS
_ReadableText = _ReadableText
_RestrictedRedirectHandler = _RestrictedRedirectHandler
_default_open_network_request = _default_open_network_request
_fetch = _fetch
_network_enabled = _network_enabled
_open_network_request = _open_network_request
_related_topics = _related_topics
_strip_markup = _strip_markup
_validate_network_url = _validate_network_url
_wikipedia_topics = _wikipedia_topics
_RESERVED_DEVICE_NAMES = _RESERVED_DEVICE_NAMES
_check_reserved_path = _check_reserved_path
_is_reserved_name = _is_reserved_name
_reserved_stem = _reserved_stem
_safe_path = _safe_path
normalize_fa = normalize_fa
socket = socket
datetime = datetime
ZoneInfo = ZoneInfo
ZoneInfoNotFoundError = ZoneInfoNotFoundError
build_opener = build_opener

__all__ = [
    "BUILTIN_TOOLSETS",
    "MAX_LIST_ITEMS",
    "MAX_MAPPING_KEYS",
    "MAX_NESTING_DEPTH",
    "MAX_SERIALIZED_INPUT_SIZE",
    "MAX_TOOL_INPUT_CHARS",
    "NETWORK_DISABLED_MESSAGE",
    "NETWORK_EMPTY_MESSAGE",
    "NETWORK_REFUSAL_MESSAGE",
    "NETWORK_TIMEOUT_SECONDS",
    "NUMERIC_RANGES",
    "PAGE_RESPONSE_CAP",
    "PAGE_TEXT_CAP",
    "REGISTRY",
    "RISKS",
    "SEARCH_RESPONSE_CAP",
    "Tool",
    "Toolset",
    "WORKSPACE_ROOT",
    "ZoneInfo",
    "ZoneInfoNotFoundError",
    "anthropic_schemas",
    "apply_skill_proposal",
    "build_opener",
    "calculate",
    "cancel_reminder",
    "create_reminder",
    "datetime",
    "delete_skill",
    "discard_skill_proposal",
    "edit_skill",
    "execute",
    "filter_tools",
    "gemini_schemas",
    "get_datetime",
    "get_parameter_category",
    "get_toolset",
    "list_notes",
    "list_skills",
    "list_toolsets",
    "logger",
    "normalize_fa",
    "openai_schemas",
    "read_note",
    "read_page",
    "register_toolset",
    "run_shell",
    "save_skill",
    "save_skill_bundle",
    "search_web",
    "send_email",
    "skill_view",
    "socket",
    "tool",
    "unregister_toolset",
    "use_skill",
    "write_note",
]
