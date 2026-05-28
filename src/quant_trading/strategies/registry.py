from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from quant_trading.strategies.base import Strategy
from quant_trading.strategies.sma_crossover import SMACrossoverStrategy
from quant_trading.strategies.volume_surge import VolumeSurgeStrategy

ParamType = Literal["int", "float"]


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: ParamType
    default: int | float
    min: int | float | None = None
    max: int | float | None = None
    label: str = ""

    def to_api(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "default": self.default,
            "min": self.min,
            "max": self.max,
            "label": self.label or self.name,
        }


@dataclass(frozen=True)
class StrategyEntry:
    id: str
    name: str
    description: str
    factory: Callable[..., Strategy]
    params: tuple[ParamSpec, ...]

    def instantiate(self, raw: dict[str, Any]) -> Strategy:
        kwargs: dict[str, Any] = {}
        for spec in self.params:
            val = raw.get(spec.name, spec.default)
            if spec.type == "int":
                val = int(val)
            else:
                val = float(val)
            if spec.min is not None and val < spec.min:
                raise ValueError(f"{spec.name} must be >= {spec.min}")
            if spec.max is not None and val > spec.max:
                raise ValueError(f"{spec.name} must be <= {spec.max}")
            kwargs[spec.name] = val
        return self.factory(**kwargs)

    def to_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "params": [p.to_api() for p in self.params],
        }


_REGISTRY: tuple[StrategyEntry, ...] = (
    StrategyEntry(
        id="sma_crossover",
        name="双均线交叉",
        description="快线在慢线上方做多，否则空仓",
        factory=SMACrossoverStrategy,
        params=(
            ParamSpec("fast", "int", default=10, min=2, max=120, label="快线"),
            ParamSpec("slow", "int", default=40, min=5, max=250, label="慢线"),
        ),
    ),
    StrategyEntry(
        id="volume_surge",
        name="量能突破",
        description="成交量高于均量×倍数且当日收涨做多；trend_ma=0 关闭趋势过滤",
        factory=VolumeSurgeStrategy,
        params=(
            ParamSpec("vol_ma", "int", default=20, min=5, max=120, label="均量窗口"),
            ParamSpec(
                "vol_ratio",
                "float",
                default=1.2,
                min=1.0,
                max=5.0,
                label="放量倍数",
            ),
            ParamSpec(
                "trend_ma",
                "int",
                default=60,
                min=0,
                max=250,
                label="趋势均线(0=关)",
            ),
        ),
    ),
)


def list_strategies_for_api() -> list[dict[str, Any]]:
    return [e.to_api() for e in _REGISTRY]


def get_strategy_entry(strategy_id: str) -> StrategyEntry | None:
    for entry in _REGISTRY:
        if entry.id == strategy_id:
            return entry
    return None
