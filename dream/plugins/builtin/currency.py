"""Built-in Currency, Crypto, and Gold Exchange Plugin."""

from __future__ import annotations

import json
import logging
from typing import Any

from dream.plugins.base import BasePlugin
from dream.plugins.types import PluginManifest

logger = logging.getLogger(__name__)

# Baseline reference exchange rates (relative to USD = 1.0)
BASE_RATES_USD: dict[str, float] = {
    "usd": 1.0,
    "eur": 0.92,
    "gbp": 0.78,
    "aed": 3.67,
    "try": 34.2,
    "irr": 600_000.0,  # Rial
    "toman": 60_000.0,  # Toman
    "usdt": 1.0,
    "btc": 68_500.0,
    "eth": 3_500.0,
    "gold_ounce_usd": 2_500.0,
}


class CurrencyPlugin(BasePlugin):
    """Provides financial currency exchange rates and crypto asset pricing."""

    def __init__(self) -> None:
        manifest = PluginManifest(
            name="currency_plugin",
            version="1.0.0",
            author="Dream Core Team",
            description_en="Currency conversion and exchange rates (IRR, Toman, USD, EUR, Crypto).",
            description_fa="محاسبه و تبدیل نرخ ارز، طلا و رمزارزها (ریال، تومان، دلار، تتر).",
            permissions=["tools"],
        )
        super().__init__(manifest)

    def register_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "convert_currency",
                "description": (
                    "Convert an amount from one currency to another (USD, EUR, IRR, Toman, USDT).\n"
                    "تبدیل مبلغ بین واحدهای پولی مختلف (دلار، یورو، تومان، ریال، درهم، تتر)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "amount": {"type": "number", "description": "Numeric amount to convert"},
                        "from_currency": {
                            "type": "string",
                            "description": "Source currency (e.g. 'USD', 'EUR', 'Toman', 'IRR')",
                        },
                        "to_currency": {
                            "type": "string",
                            "description": "Target currency (e.g. 'Toman', 'IRR', 'USD', 'EUR')",
                        },
                    },
                    "required": ["amount", "from_currency", "to_currency"],
                },
                "handler": self.convert_currency,
            }
        ]

    def convert_currency(self, amount: float, from_currency: str, to_currency: str) -> str:
        """Convert financial currency amounts."""
        from_c = from_currency.strip().lower()
        to_c = to_currency.strip().lower()

        # Handle Persian labels
        labels_map = {
            "تومان": "toman",
            "ریال": "irr",
            "دلار": "usd",
            "یورو": "eur",
            "درهم": "aed",
            "تتر": "usdt",
            "بیت کوین": "btc",
            "بیت‌کوین": "btc",
            "اتریوم": "eth",
        }
        from_c = labels_map.get(from_c, from_c)
        to_c = labels_map.get(to_c, to_c)

        rate_from = BASE_RATES_USD.get(from_c)
        rate_to = BASE_RATES_USD.get(to_c)

        if rate_from is None or rate_to is None:
            supported = list(BASE_RATES_USD.keys())
            return json.dumps(
                {
                    "error": f"واحد ارزی ناشناخته است. ارزهای پشتیبانی شده: {supported}",
                },
                ensure_ascii=False,
            )

        # Calculate conversion via USD base
        # from_amount in USD = amount / rate_from (if rate is quotes per USD) or amount * rate_from
        # Here: IRR/Toman/AED/TRY are quotes per 1 USD; BTC/ETH/Gold are USD per unit.
        usd_value = amount / rate_from if from_c not in ("btc", "eth") else amount * rate_from
        converted = usd_value * rate_to if to_c not in ("btc", "eth") else usd_value / rate_to

        res_dict = {
            "amount": amount,
            "from_currency": from_currency.upper(),
            "to_currency": to_currency.upper(),
            "converted_amount": round(converted, 4),
            "rate": round(converted / amount if amount != 0 else 0, 6),
            "summary_fa": (
                f"{amount:,.2f} {from_currency} معادل {converted:,.2f} {to_currency} است."
            ),
            "summary_en": f"{amount:,.2f} {from_currency} equals {converted:,.2f} {to_currency}.",
        }
        return json.dumps(res_dict, ensure_ascii=False, indent=2)
