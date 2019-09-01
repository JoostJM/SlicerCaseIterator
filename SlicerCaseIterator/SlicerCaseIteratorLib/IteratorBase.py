# =========================================================================
#  Copyright Joost van Griethuysen
#
#  Licensed under the 3-Clause BSD-License (the "License");
#  you may not use this file except in compliance with the License.
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# ========================================================================

from abc import abstractmethod
import logging

# ------------------------------------------------------------------------------
# IteratorWidgetBase
# ------------------------------------------------------------------------------

class IteratorWidgetBase(object):
  """
  Base class for the GUI subsection controlling the input. It defines the GUI elements (via the `setup` function), and
  controls the starting of the batch (`startBatch`, returns an instance derived from IteratorLogicBase). Moreover, this
  class contains functionality to signal or provide information on validity of the current config (used to determine
  whether the user is allowed to start the batch) and some functionality to cleanup after a batch is done. Finally,
  this class can respond to the user activating the CaseIterator module and when a scene is closed by the user during
  the iterator over a batch (should treated as "cancel the review/updates of this case", but not stop the iteration).
  """

  def __init__(self):
    self.logger = logging.getLogger('SlicerCaseIterator.IteratorWidget')
    self.validationHandler = None
    self.layout = None

  def __del__(self):
    self.logger.debug('Destroying Iterator Widget')
    self.cleanupBatch()

  @abstractmethod
  def setup(self):
    """
    This function should return a qt.QGroupbox containing all the GUI elements needed to configure the iterator.
    Moreover, this groupbox should also be assigned to `self.layout`, which is used to control visibility in the GUI.
    :return: qt.QGroupbox
    """

  def enter(self):
    """
    This function is called from the main widget when the user activates the CaseIterator module GUI, and can be used
    to refresh controls
    :return: None
    """
    pass

  def onEndClose(self):
    pass

  def validate(self):
    if self.validationHandler is not None:
      self.validationHandler(self.is_valid())

  def is_valid(self):
    """
    This function checks the current config to decide whether a batch can be started. This is used to enable/disable
    the "start batch" button.
    :return: boolean specifying if the current setting is valid and a batch may be started
    """
    return True

  @abstractmethod
  def startBatch(self):
    """
    Function to start the batch. In the derived class, this should store relevant nodes to keep track of important data
    :return: Instance of class, derived from IteratorBase
    """

  def cleanupBatch(self):
    """
    Function to cleanup after finishing or resetting a batch. Main objective is to remove non-needed references to
    tracked nodes in the widgeet, thereby allowing their associated resources to be released and GC'ed.
    :return: None
    """
    pass

# ------------------------------------------------------------------------------
# IteratorLogicBase
# ------------------------------------------------------------------------------

class IteratorLogicBase(object):
  """
  Base class for the iterator object. An instance of a class derived from this class is returned by the corresponding
  widget's startBatch function. 3 attributes are accessed from the CaseIteratorLogic:

  - caseCount: Integer specifying how many cases are present in the batch defined by this iterator
  - loadCase: Function to load a certain case, specified by the passed `case_idx`
  - saveMask: Function to store a loaded or new mask.
  """

  def __init__(self):
    self.logger = logging.getLogger('SlicerCaseIterator.Iterator')
    self.caseCount = None

  @abstractmethod
  def loadCase(self, case_idx):
    """
    Function called by the logic to load the next desired case, as specified by the case_idx.
    :param case_idx: index of the next case to load, 0 <= case_idx < self.caseCount
    :return: Tuple containing loaded nodes: (main_image, main_mask, list of additional images, list of additional masks)
    """

  @abstractmethod
  def saveMask(self, node, reader, overwrite_existing=False):
    """
    Function to save the passed mask
    :param node: vtkMRMLSegmentationNode containing the segmentation to store
    :param reader: String defining the reader who created/updated the segmentation, can be None
    :param overwrite_existing: If set to True, existing files are overwritten, otherwise, unique filenames are generated
    :return: None
    """
