"""What-If decision simulator — pure financial projection logic (no DB).

Given a waste item's recoverable amount and implementation parameters, project
the monthly cash-flow impact and net-profit impact over a horizon.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WhatIfInputs:
    base_amount_iqd: float          # the waste item's amount (max recoverable)
    recovery_pct: float             # 0..100
    implementation_months: int      # 1..12
    implementation_cost_iqd: float  # total cost to implement (manual input)
    horizon_months: int = 6


@dataclass
class WhatIfResult:
    recovered_amount: float
    total_implementation_cost: float
    monthly_implementation_cost: float
    monthly_cash_flow_impact: float
    net_profit_impact: float
    projection: list[dict]  # [{month, cumulative_cash_flow}]

    def as_dict(self) -> dict:
        return {
            "recovered_amount": round(self.recovered_amount, 2),
            "total_implementation_cost": round(self.total_implementation_cost, 2),
            "monthly_implementation_cost": round(self.monthly_implementation_cost, 2),
            "monthly_cash_flow_impact": round(self.monthly_cash_flow_impact, 2),
            "net_profit_impact": round(self.net_profit_impact, 2),
            "projection": [
                {"month": p["month"], "cumulative_cash_flow": round(p["cumulative_cash_flow"], 2)}
                for p in self.projection
            ],
        }


def simulate(inp: WhatIfInputs) -> WhatIfResult:
    """Run the simulation.

    - recovered_amount = base_amount * recovery_pct/100
    - monthly recovery is spread over implementation_months
    - monthly cash-flow impact (during implementation) =
        (recovered_amount / implementation_months) - monthly_implementation_cost
    - net profit impact = recovered_amount - total_implementation_cost
    - projection: cumulative cash flow per month over the horizon. During the
      implementation window each month adds (monthly recovery - monthly cost);
      after implementation completes, only the recovery inflow continues at the
      per-month recovery rate is finished, so post-implementation months add 0
      (the one-off recovery is fully realized by month = implementation_months).
    """
    months = max(1, int(inp.implementation_months))
    horizon = max(1, int(inp.horizon_months))
    recovery_pct = max(0.0, min(100.0, inp.recovery_pct))

    recovered = inp.base_amount_iqd * (recovery_pct / 100.0)
    total_cost = float(inp.implementation_cost_iqd)
    monthly_cost = total_cost / months
    monthly_recovery = recovered / months
    monthly_cash_flow = monthly_recovery - monthly_cost
    net_profit = recovered - total_cost

    projection: list[dict] = []
    cumulative = 0.0
    for m in range(1, horizon + 1):
        if m <= months:
            cumulative += monthly_recovery - monthly_cost
        # after implementation: recovery already counted, no further monthly delta
        projection.append({"month": m, "cumulative_cash_flow": cumulative})

    return WhatIfResult(
        recovered_amount=recovered,
        total_implementation_cost=total_cost,
        monthly_implementation_cost=monthly_cost,
        monthly_cash_flow_impact=monthly_cash_flow,
        net_profit_impact=net_profit,
        projection=projection,
    )
