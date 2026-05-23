"""
Multiple scanning strategies for the VN stock scanner.

Each strategy is a self-contained module with an `evaluate()` function that
returns a Result dataclass (or None if the stock doesn't qualify).

Available strategies:
  - golden_cross: MA crossover signal (long/short presets)
  - ichimoku: Ichimoku Kinko Hyo trend system
"""

from . import golden_cross
from . import ichimoku

__all__ = ['golden_cross', 'ichimoku']
