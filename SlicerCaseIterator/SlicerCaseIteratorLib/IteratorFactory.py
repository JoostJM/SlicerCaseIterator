from . import CsvTableIterator
from functools import wraps
import logging

def onExceptionReturnNone(func):

  @wraps(func)
  def wrapper(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except (IndexError, AttributeError, KeyError) as exc:
      logging.error(exc)
      return None
  return wrapper


class IteratorFactory(object):

  IMPLEMENTATIONS = {
    "simple_csv_iteration": CsvTableIterator.CaseTableIteratorWidget,
  }

  @staticmethod
  def getImplementationNames():
    return IteratorFactory.IMPLEMENTATIONS.keys()

  @staticmethod
  @onExceptionReturnNone
  def getIteratorWidget(mode):
    return IteratorFactory.IMPLEMENTATIONS[mode]
