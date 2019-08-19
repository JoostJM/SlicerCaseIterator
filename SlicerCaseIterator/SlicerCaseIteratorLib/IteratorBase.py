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
import csv
import logging
import os

import slicer

from . import SegmentationBackend


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

  @classmethod
  def get_header(cls):
    return str(cls.__name__).replace('Widget', '')

  def setUserPreferences(self, user_preferences):
    pass

  def getUserPreferences(self):
    return None

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
  def startBatch(self, reader):
    """
    Function to start the batch. In the derived class, this should store relevant nodes to keep track of important data
    :param reader: String defining the reader who created/updated the segmentation, can be None
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

  :param reader: name of the reader performing the segmentation
  :param backend: instance derived from SegmentationBackend.SegmentationBackendBase, that can handle loading a mask
  """

  def __init__(self, reader, backend):
    self.logger = logging.getLogger('SlicerCaseIterator.Iterator')
    self.caseCount = None
    self.reader = reader
    assert isinstance(backend, SegmentationBackend.SegmentationBackendBase)
    self.backend = backend

  # ------------------------------------------------------------------------------
  def __del__(self):
    self.logger.debug('Destroying Iterator Logic')
    self.cleanupIterator()

  @abstractmethod
  def loadCase(self, case_idx):
    """
    Function called by the logic to load the next desired case, as specified by the case_idx.
    :param case_idx: index of the next case to load, 0 <= case_idx < self.caseCount
    :return: Tuple containing loaded nodes: (main_image, main_mask, list of additional images, list of additional masks)
    """

  def should_close(self, case_idx):
    """
    Function to check if the next case to load represents a new patient, or just different masks. In any case, all
    segmentation nodes are closed.
    :param case_idx: index of the new case to load
    :return: boolean indicating whether the current mrml scene should be closed prior to loading the next case
    """
    return True

  @abstractmethod
  def saveMask(self, node, overwrite_existing=False):
    """
    Function to save the passed mask
    :param node: vtkMRMLSegmentationNode containing the segmentation to store
    :param overwrite_existing: If set to True, existing files are overwritten, otherwise, unique filenames are generated
    :return: None
    """

  def _save_node(self, node, root, overwrite_existing=False):
    ext = self.backend.getMaskExtension()

    storage_node = node.GetStorageNode()
    if storage_node is not None and storage_node.GetFileName() is not None:
      # mask was loaded, save the updated mask in the same directory
      target_dir = os.path.dirname(storage_node.GetFileName())
    else:
      target_dir = root

    nodename = node.GetName()
    # Add the reader name if set
    if self.reader is not None:
      nodename += '_' + self.reader
    filename = os.path.join(target_dir, nodename)

    if not os.path.isdir(target_dir):
      self.logger.debug('Creating output directory at %s', target_dir)
      os.makedirs(target_dir)

    # Prevent overwriting existing files
    if os.path.exists(filename + ext) and not overwrite_existing:
      self.logger.debug('Filename exists! Generating unique name...')
      idx = 1
      filename += '(%d)' + ext
      while os.path.exists(filename % idx):
        idx += 1
      filename = filename % idx
    else:
      filename += ext

    # Save the node
    assert slicer.util.saveNode(node, filename), "Error saving node @ %s. See Slicer's log for details" % filename
    self.logger.info('Saved node %s in %s', nodename, filename)

    return filename

  def cleanupIterator(self):
    """
    Function to cleanup after finishing or resetting a batch. Main objective is to remove non-needed references to
    tracked nodes, thereby allowing their associated resources to be released and GC'ed.
    :return: None
    """
    pass


# ------------------------------------------------------------------------------
# TableIteratorLogicBase
# ------------------------------------------------------------------------------

class TableIteratorLogicBase(IteratorLogicBase):

  def __init__(self, reader, backend, tableNode, tableModifiedTime):
    super(TableIteratorLogicBase, self).__init__(reader, backend)

    assert tableNode is not None, 'No table selected! Cannot instantiate batch'

    # If the table was loaded from a file, get the directory containing the file as reference for relative paths
    self.tableStorageNode = tableNode.GetStorageNode()
    if self.tableStorageNode is not None and self.tableStorageNode.GetFileName() is not None:
      self.csv_dir = os.path.dirname(self.tableStorageNode.GetFileName())
    else:  # Table did not originate from a file
      self.csv_dir = None
    self.tableModifiedTime = tableModifiedTime

    # Get the actual table contained in the MRML node
    self.tableNode = tableNode
    self.batchTable = tableNode.GetTable()

  # ------------------------------------------------------------------------------
  def buildPath(self, fname, caseRoot=None):
    if fname is None or fname == '':
      return None

    if os.path.isabs(fname):
      return fname

    # Add the caseRoot if specified
    if caseRoot is not None:
      fname = os.path.join(caseRoot, fname)

      # Check if the caseRoot is an absolute path
      if os.path.isabs(fname):
        return fname

    # Add the csv_dir to the path if it is not None (loaded table)
    if self.csv_dir is not None:
      fname = os.path.join(self.csv_dir, fname)

    return os.path.abspath(fname)

  # ------------------------------------------------------------------------------
  def checkColumns(self, required_columns):
    for col in required_columns:
      if col is None:
        continue

      assert self.batchTable.GetColumnByName(col) is not None, \
          'Unable to find column "%s"' % col

  # ------------------------------------------------------------------------------
  def getColumnValue(self, colName, idx):
    col = self.batchTable.GetColumnByName(colName)
    if col is None:
      return None

    return col.GetValue(idx)

  # ------------------------------------------------------------------------------
  def saveTable(self):
    # Store the results!
    if self.tableStorageNode is not None:
      fname = self.tableStorageNode.GetFileName()
      if fname is not None:
        try:
          mod_time = os.path.getmtime(fname)
          if self.tableModifiedTime is None or self.tableModifiedTime < mod_time:
            self._update_table(fname)
        except OSError:
          pass

        assert slicer.util.saveNode(self.tableNode, fname), \
            "Error saving node @ %s. See Slicer's log for details" % fname
        self.logger.info('Table stored at %s', fname)

        self.tableModifiedTime = os.path.getmtime(fname)
      else:
        self.logger.warning("Filename for table is not set in storage node")
    else:
      self.logger.warning("Storage node is None!")

  # ------------------------------------------------------------------------------
  def _update_table(self, fname):
    if self.tableModifiedTime is not None:
      self.logger.info('Table was changed since loading, updating current table!')
    with open(fname, mode='r') as table_fs:
      reader = csv.DictReader(table_fs)
      for k in reader.fieldnames:
        if self.batchTable.GetColumnByName(k) is None:
          out_clm = self.tableNode.AddColumn()
          out_clm.SetName(k)
      for row_idx, row in enumerate(reader):
        for k in row:
          clm = self.batchTable.GetColumnByName(k)
          cur_val = clm.GetValue(row_idx)
          new_val = row[k]
          if cur_val == '' and new_val != '':
            clm.SetValue(row_idx, new_val)
          elif cur_val != '' and new_val != '' and cur_val != new_val:
            raise AssertionError('Column "%s" (row %i): Different non-null values found! Cannot store table! '
                                 'Manually store table to prevent loss of data.' %
                                 (k, row_idx + 1))

  def cleanupIterator(self):
    self.tableStorageNode = None
    self.tableNode = None

    self.batchTable = None
