import inspect
import os
import pkgutil
import sys

from . import IteratorBase

_iterators = None


def get_iterators():
  global _iterators
  if _iterators is None:
    _iterators = {}
    for _, mod, _ in pkgutil.iter_modules([os.path.dirname(__file__)]):
      if str(mod).startswith('_'):  # skip __init__.py
        continue
      if str(mod) == 'IteratorBase':
        continue
      __import__('SlicerCaseIteratorLib.' + mod)
      module = sys.modules['SlicerCaseIteratorLib.' + mod]
      attributes = inspect.getmembers(module, inspect.isclass)

      widget = None
      logic = None
      for a_name, a in attributes:
        if issubclass(a, IteratorBase.IteratorWidgetBase):
          widget = a
        elif issubclass(a, IteratorBase.IteratorLogicBase):
          logic = a

      if widget is not None and logic is not None:
        iterator_name = widget.get_header()
        _iterators[iterator_name] = (widget, logic)

  return _iterators
