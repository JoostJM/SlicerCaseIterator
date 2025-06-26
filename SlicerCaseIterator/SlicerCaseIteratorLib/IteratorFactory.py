from . import CsvTableIterator
from . import CsvInferenceIterator
from . import IteratorBase
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
    "mask_comparison": CsvInferenceIterator.CsvInferenceIteratorWidget
  }

  @classmethod
  def registerIteratorWidget(cls, name, widget):
    if name in cls.IMPLEMENTATIONS.keys():
      logging.warning(f"Iterator {name} is already registered")
      return
    if not issubclass(widget, IteratorBase.IteratorWidgetBase):
      logging.warning(f"Widget {widget} is no subclass of IteratorBase.IteratorWidgetBase")
      return
    cls.IMPLEMENTATIONS[name] = widget

  @staticmethod
  def reloadSourceFiles():
    packageName='SlicerCaseIteratorLib'
    submoduleNames=['IteratorBase', 'CsvTableIterator', 'CsvInferenceIterator', 'IteratorFactory']
    import imp
    f, filename, description = imp.find_module(packageName)
    package = imp.load_module(packageName, f, filename, description)
    for submoduleName in submoduleNames:
      f, filename, description = imp.find_module(submoduleName, package.__path__)
      try:
          imp.load_module(packageName+'.'+submoduleName, f, filename, description)
      finally:
          f.close()

  @staticmethod
  def getImplementationNames():
    return list(IteratorFactory.IMPLEMENTATIONS.keys())

  @staticmethod
  @onExceptionReturnNone
  def getIteratorWidget(mode):
    return IteratorFactory.IMPLEMENTATIONS[mode]
