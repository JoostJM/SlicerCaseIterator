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
# SlicerCaseIterator CSV iterator
# ------------------------------------------------------------------------------

class IteratorWidgetBase(object):

  def __init__(self):
    self.logger = logging.getLogger('SlicerCaseIterator.IteratorWidget')
    self.validationHandler = None

  @abstractmethod
  def setup(self):
    """
    This function should return a qt.QGroupbox containing all the GUI elements needed to configure the iterator
    :return: qt.QGroupbox
    """

  def enter(self):
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

  @abstractmethod
  def cleanupBatch(self):
    """
    Function to cleanup after finishing or resetting a batch. Main objective is to remove non-needed references to
    tracked nodes in the widgeet, thereby allowing their associated resources to be released and GC'ed.
    :return: None
    """



# ------------------------------------------------------------------------------
# SlicerCaseIterator CSV iterator
# ------------------------------------------------------------------------------

class IteratorBase(object):

  def __init__(self):
    self.logger = logging.getLogger('SlicerCaseIterator.Iterator')
    self.caseCount = None

  @abstractmethod
  def loadCase(self, case_idx):
    """
    Function called by the logic to load the next desired case, as specified by the case_idx.
    :param case_idx: index of the next case to load, 0 <= case_idx < self.caseCount
    :return:
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
