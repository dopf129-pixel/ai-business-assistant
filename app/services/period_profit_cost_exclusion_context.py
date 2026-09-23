from contextvars import ContextVar


_COST_EXCLUDED = ContextVar("period_profit_cost_excluded", default=False)


def cost_excluded():
    return _COST_EXCLUDED.get() is True


def activate_cost_exclusion():
    return _COST_EXCLUDED.set(True)


def reset_cost_exclusion(token):
    _COST_EXCLUDED.reset(token)
