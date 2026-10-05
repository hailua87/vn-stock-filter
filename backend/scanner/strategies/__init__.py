"""
Multiple scanning strategies for the VN stock scanner.

Each strategy is a self-contained module with an `evaluate()` function that
returns a Result dataclass (or None if the stock doesn't qualify).

Available strategies:
  - golden_cross: MA crossover signal (long/short presets)
  - ichimoku: Ichimoku Kinko Hyo trend system
  - ma7_25: MA7 x MA25 — 5 tin hieu mua/ban (MUA_1, MUA_2, CHOT_LOI, GIAM, THOAT)
"""

from . import golden_cross
from . import ichimoku
from . import ma7_25

__all__ = ['golden_cross', 'ichimoku', 'ma7_25']
