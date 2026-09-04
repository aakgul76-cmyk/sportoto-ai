"""Select the weekly Spor Toto workflow mode in Europe/Istanbul time."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

ISTANBUL = ZoneInfo("Europe/Istanbul")
PREDICTION_DAYS = {1, 2, 3, 4}  # Tuesday-Friday
EVALUATION_DAYS = {0, 5, 6}  # Monday, Saturday, Sunday
MORNING_CUTOFF_HOUR = 12


@dataclass(frozen=True)
class CycleDecision:
    mode: str
    close_previous_week: bool
    local_date: str
    reason: str


def decide_cycle(now: datetime, event_name: str) -> CycleDecision:
    local = now.astimezone(ISTANBUL)
    weekday = local.weekday()

    if event_name == "push":
        return CycleDecision(
            mode="publish_only",
            close_previous_week=False,
            local_date=local.isoformat(),
            reason="Push mevcut veriyi yayımlar; planlı tahmin döngüsünü değiştirmez.",
        )

    if (
        event_name == "schedule"
        and weekday in PREDICTION_DAYS
        and local.hour < MORNING_CUTOFF_HOUR
    ):
        return CycleDecision(
            mode="prediction",
            close_previous_week=weekday == 1,
            local_date=local.isoformat(),
            reason="Salı-cuma sabah planlı tahmin dönemi.",
        )

    if event_name == "workflow_dispatch" and weekday in {1, 2, 3}:
        return CycleDecision(
            mode="prediction",
            close_previous_week=False,
            local_date=local.isoformat(),
            reason="Salı-perşembe manuel tahmin yenilemesi.",
        )

    if weekday in EVALUATION_DAYS:
        return CycleDecision(
            mode="evaluation",
            close_previous_week=False,
            local_date=local.isoformat(),
            reason="Cumartesi-pazartesi yalnız sonuç değerlendirme dönemi.",
        )

    return CycleDecision(
        mode="frozen",
        close_previous_week=False,
        local_date=local.isoformat(),
        reason="Planlı sabah tahmin penceresi kapalı; mevcut kupon dondurulmuştur.",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", default=os.getenv("GITHUB_EVENT_NAME", "workflow_dispatch"))
    parser.add_argument("--github-output", default=os.getenv("GITHUB_OUTPUT", ""))
    args = parser.parse_args()
    decision = decide_cycle(datetime.now(ISTANBUL), args.event)
    lines = [
        f"mode={decision.mode}",
        f"close_previous_week={'true' if decision.close_previous_week else 'false'}",
        f"cycle_local_date={decision.local_date}",
        f"cycle_reason={decision.reason}",
    ]
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as output:
            output.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
