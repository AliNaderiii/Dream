"""Shared constants and public DTO builders for provider hubs."""

from __future__ import annotations

from typing import Any, Final

RUNTIME_IDS: Final[tuple[str, ...]] = (
    "ollama",
    "vllm",
    "sglang",
    "llamacpp",
    "lmstudio",
    "generic",
)

PARSER_FAMILIES: Final[tuple[str, ...]] = (
    "function_tools",
    "qwen",
    "llama3",
    "mistral",
    "hermes",
    "deepseek",
    "glm",
    "generic_fallback",
)

GATEWAY_TOOLS: Final[tuple[str, ...]] = ("web_search", "image", "tts", "browser")

ROUTE_PRIORITY: Final[tuple[str, ...]] = ("hosted", "aval", "ollama", "byok", "echo")

PROBE_TIMEOUT_SECONDS: Final[float] = 1.5
CHAT_TIMEOUT_SECONDS: Final[float] = 8.0
MAX_RETRIES: Final[int] = 2
BACKOFF_BASE_SECONDS: Final[float] = 0.05

LOCAL_PRIVACY_EN = "Data stays on this machine."
LOCAL_PRIVACY_FA = "داده روی همین دستگاه می‌ماند."
CLOUD_PRIVACY_EN = "Requests leave this machine when this route is used."
CLOUD_PRIVACY_FA = "در صورت استفاده از این مسیر، درخواست‌ها این دستگاه را ترک می‌کنند."

FIX_HINTS: Final[dict[str, dict[str, str]]] = {
    "ollama": {
        "reason": "Ollama tool calling is on by default.",
        "reason_fa": "فراخوانی ابزار در Ollama به‌صورت پیش‌فرض روشن است.",
        "fix": "Ollama tool calling is on by default.",
        "fix_fa": "فراخوانی ابزار در Ollama به‌صورت پیش‌فرض روشن است.",
    },
    "vllm": {
        "reason": "This server does not have tool calling enabled.",
        "reason_fa": "این سرور فراخوانی ابزار را فعال نکرده است.",
        "fix": (
            "Start vLLM with --enable-auto-tool-choice --tool-call-parser qwen "
            "(or the parser that matches your model family)."
        ),
        "fix_fa": (
            "vLLM را با --enable-auto-tool-choice --tool-call-parser qwen "
            "(یا تجزیه‌گر هم‌خوان با خانواده مدل) راه‌اندازی کنید."
        ),
    },
    "sglang": {
        "reason": "This server does not have tool calling enabled.",
        "reason_fa": "این سرور فراخوانی ابزار را فعال نکرده است.",
        "fix": (
            "Start SGLang with --tool-call-parser mistral "
            "(or the parser that matches your model family)."
        ),
        "fix_fa": (
            "SGLang را با --tool-call-parser mistral "
            "(یا تجزیه‌گر هم‌خوان با خانواده مدل) راه‌اندازی کنید."
        ),
    },
    "llamacpp": {
        "reason": "llama-server is not emitting structured tool calls.",
        "reason_fa": "llama-server فراخوانی ابزار ساخت‌یافته تولید نمی‌کند.",
        "fix": "Start llama-server with --jinja so templates emit structured tool calls.",
        "fix_fa": "llama-server را با --jinja راه‌اندازی کنید تا قالب‌ها فراخوانی ساخت‌یافته بسازند.",
    },
    "lmstudio": {
        "reason": "LM Studio tools are off in the local server settings.",
        "reason_fa": "ابزارهای LM Studio در تنظیمات سرور محلی خاموش هستند.",
        "fix": "Enable structured output / tools in the LM Studio server settings.",
        "fix_fa": "خروجی ساخت‌یافته / ابزارها را در تنظیمات سرور LM Studio روشن کنید.",
    },
    "generic": {
        "reason": "Native tools are unavailable. The generic fallback parser is active.",
        "reason_fa": "ابزار بومی در دسترس نیست. تجزیه‌گر پشتیبان عمومی فعال است.",
        "fix": (
            "This endpoint has no native tools. Dream will parse structured text "
            "with the generic fallback — reliability is lower."
        ),
        "fix_fa": (
            "این نقطه پایانی ابزار بومی ندارد. Dream متن ساخت‌یافته را با "
            "تجزیه‌گر پشتیبان عمومی می‌خواند — قابلیت اطمینان کمتر است."
        ),
    },
}

RUNTIME_SPECS: Final[dict[str, dict[str, Any]]] = {
    "ollama": {
        "name": "Ollama",
        "endpoint": "http://127.0.0.1:11434/v1",
        "parser": "function_tools",
        "parser_guidance": "Ollama tool calling is on by default.",
        "env_keys": ("OLLAMA_HOST", "DREAM_OLLAMA_URL"),
        "backend_names": ("ollama",),
        "tool_calling": "native",
        "cost_tier": "local",
        "recommended": True,
        "notes": "Recommended local default. No VPN. No cloud key.",
    },
    "vllm": {
        "name": "vLLM",
        "endpoint": "http://127.0.0.1:8000/v1",
        "parser": "qwen",
        "parser_guidance": "Match the parser to the model family (qwen, mistral, or hermes).",
        "env_keys": ("DREAM_VLLM_URL",),
        "backend_names": ("vllm",),
        "tool_calling": "disabled",
        "cost_tier": "local",
        "recommended": False,
        "notes": "Local serving stack. Enable the matching tool-call parser.",
    },
    "sglang": {
        "name": "SGLang",
        "endpoint": "http://127.0.0.1:30000/v1",
        "parser": "mistral",
        "parser_guidance": "Use --tool-call-parser mistral (or the family that matches the model).",
        "env_keys": ("DREAM_SGLANG_URL",),
        "backend_names": ("sglang",),
        "tool_calling": "disabled",
        "cost_tier": "local",
        "recommended": False,
        "notes": "Local serving stack. Pass --tool-call-parser for your family.",
    },
    "llamacpp": {
        "name": "llama.cpp",
        "endpoint": "http://127.0.0.1:8080/v1",
        "parser": "llama3",
        "parser_guidance": "llama-server needs --jinja so templates emit structured tool calls.",
        "env_keys": ("DREAM_LLAMACPP_URL",),
        "backend_names": ("llamacpp",),
        "tool_calling": "disabled",
        "cost_tier": "local",
        "recommended": False,
        "notes": "Local llama-server. Use --jinja for structured tools.",
    },
    "lmstudio": {
        "name": "LM Studio",
        "endpoint": "http://127.0.0.1:1234/v1",
        "parser": "function_tools",
        "parser_guidance": "Enable structured output / tools in the LM Studio server settings.",
        "env_keys": ("DREAM_LMSTUDIO_URL",),
        "backend_names": ("lmstudio",),
        "tool_calling": "disabled",
        "cost_tier": "local",
        "recommended": False,
        "notes": "Local desktop server. Enable tools in its settings.",
    },
    "generic": {
        "name": "Generic compatible endpoint",
        "endpoint": "http://127.0.0.1:8000/v1",
        "parser": "generic_fallback",
        "parser_guidance": (
            "No native tools. Dream parses structured text with the generic fallback "
            "— reliability is lower."
        ),
        "env_keys": ("DREAM_GENERIC_URL",),
        "backend_names": ("generic",),
        "tool_calling": "fallback",
        "cost_tier": "local",
        "recommended": False,
        "notes": "Fallback parser. Reduced reliability is shown in the UI.",
    },
}

CATALOG_CLOUD: Final[tuple[dict[str, Any], ...]] = (
    {
        "id": "aval",
        "name": "Aval",
        "local": False,
        "runtimes": [],
        "cost_tier": "byok",
        "data_leaves_machine": True,
        "privacy_en": CLOUD_PRIVACY_EN,
        "privacy_fa": CLOUD_PRIVACY_FA,
        "tool_calling": True,
        "notes": "Bring your own key. Dream does not list a price.",
    },
    {
        "id": "hosted",
        "name": "Hosted",
        "local": False,
        "runtimes": [],
        "cost_tier": "optional",
        "data_leaves_machine": True,
        "privacy_en": CLOUD_PRIVACY_EN,
        "privacy_fa": CLOUD_PRIVACY_FA,
        "tool_calling": True,
        "notes": "Optional hosted route. Price is not invented here.",
    },
)

PARSER_INFO: Final[tuple[dict[str, Any], ...]] = (
    {"id": "function_tools", "runtimes": ["ollama", "lmstudio", "generic"], "native": True},
    {"id": "qwen", "runtimes": ["vllm", "ollama"], "native": True},
    {"id": "llama3", "runtimes": ["llamacpp", "ollama"], "native": True},
    {"id": "mistral", "runtimes": ["sglang", "ollama"], "native": True},
    {"id": "hermes", "runtimes": ["vllm", "sglang"], "native": True},
    {"id": "deepseek", "runtimes": ["vllm"], "native": True},
    {"id": "glm", "runtimes": ["vllm", "sglang"], "native": True},
    {"id": "generic_fallback", "runtimes": ["generic"], "native": False},
)
