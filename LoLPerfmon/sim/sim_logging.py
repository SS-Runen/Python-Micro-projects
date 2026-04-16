"""Structured logging for farm simulation (humans + agents troubleshooting accuracy)."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable

from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.models import ChampionStatic

SIM_LOGGER_NAME = "LoLPerfmon.sim"
DEFAULT_LOG_INTERVAL_SEC = 10.0


def get_sim_logger() -> logging.Logger:
    return logging.getLogger(SIM_LOGGER_NAME)


def configure_sim_logging_stderr(*, level: int = logging.INFO) -> None:
    """Attach a stderr handler to ``LoLPerfmon.sim`` (idempotent for repeated CLI runs)."""
    log = get_sim_logger()
    log.setLevel(level)
    log.handlers.clear()
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    log.addHandler(h)
    log.propagate = False


def format_sim_snapshot(
    t: float,
    mode: FarmMode,
    champ: ChampionStatic,
    *,
    level: int,
    xp: float,
    wallet: float,
    passive_gold: float,
    farm_gold: float,
    gold_spent: float,
    lane_cleared: float,
    jungle_cleared: float,
    lane_dps: float | None,
    jungle_dps: float | None,
    inventory: list[str | None],
    buy_idx: int | None = None,
    buy_order_len: int | None = None,
    lane_unit_id: str | None = None,
    jungle_unit_id: str | None = None,
) -> str:
    inv_s = ",".join(s or "-" for s in inventory)
    buy_s = f"{buy_idx}/{buy_order_len}" if buy_idx is not None and buy_order_len is not None else "—"
    ld = f"{lane_dps:.4g}" if lane_dps is not None else "—"
    jd = f"{jungle_dps:.4g}" if jungle_dps is not None else "—"
    return (
        f"t={t:.1f}s mode={mode.value} champion={champ.champion_id} "
        f"lvl={level} xp={xp:.2f} wallet={wallet:.2f} passive_gold={passive_gold:.2f} farm_gold={farm_gold:.2f} "
        f"gold_spent={gold_spent:.2f} lane_cleared={lane_cleared:.4f} jungle_cleared={jungle_cleared:.4f} "
        f"lane_dps={ld} jungle_dps={jd} lane_unit={lane_unit_id or '—'} jungle_unit={jungle_unit_id or '—'} "
        f"inv=[{inv_s}] buy_progress={buy_s}"
    )


class PeriodicSimLog:
    """Emit at most one log per *interval* seconds of game time (first when t reaches interval)."""

    def __init__(self, interval_sec: float | None) -> None:
        self.interval_sec = interval_sec if interval_sec and interval_sec > 0 else None
        if self.interval_sec:
            self._next_emit_at = float(self.interval_sec)
        else:
            self._next_emit_at = float("inf")

    def after_time_step(self, t_game: float, emit: Callable[[], None]) -> None:
        if self._next_emit_at == float("inf"):
            return
        iv = self.interval_sec
        assert iv is not None
        while t_game + 1e-9 >= self._next_emit_at:
            emit()
            self._next_emit_at += iv
