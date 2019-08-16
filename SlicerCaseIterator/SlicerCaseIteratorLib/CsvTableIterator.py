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

import os

import vtk, qt, ctk, slicer

from . import IteratorBase, SegmentationBackend

# ------------------------------------------------------------------------------
# SlicerCaseIterator CSV iterator Widget
# ------------------------------------------------------------------------------


class CaseTableIteratorWidget(IteratorBase.IteratorWidgetBase):

  def __init__(self):
    super(CaseTableIteratorWidget, self).__init__()

    self.tableNode = None
    self.tableStorageNode = None

  @classmethod
  def get_header(cls):
    return 'Local File Table'

  # ------------------------------------------------------------------------------
  def setup(self):
    self.layout = qt.QGroupBox('CSV input for local files')

    InputLayout = qt.QFormLayout(self.layout)

    #
    # Input CSV Path
    #
    self.batchTableSelector = slicer.qMRMLNodeComboBox()
    self.batchTableSelector.nodeTypes = ['vtkMRMLTableNode']
    self.batchTableSelector.addEnabled = True
    self.batchTableSelector.selectNodeUponCreation = True
    self.batchTableSelector.renameEnabled = True
    self.batchTableSelector.removeEnabled = True
    self.batchTableSelector.noneEnabled = False
    self.batchTableSelector.setMRMLScene(slicer.mrmlScene)
    self.batchTableSelector.toolTip = 'Select the table representing the cases to process.'
    InputLayout.addRow(self.batchTableSelector)

    self.batchTableView = slicer.qMRMLTableView()
    InputLayout.addRow(self.batchTableView)
    self.batchTableView.show()

    #
    # Parameters Area
    #
    self.parametersCollapsibleButton = ctk.ctkCollapsibleButton()
    self.parametersCollapsibleButton.text = 'Parameters'
    InputLayout.addWidget(self.parametersCollapsibleButton)

    # Layout within the dummy collapsible button
    parametersFormLayout = qt.QFormLayout(self.parametersCollapsibleButton)

    #
    # Input parameters GroupBox
    #

    self.inputParametersGroupBox = qt.QGroupBox('Input parameters')
    parametersFormLayout.addRow(self.inputParametersGroupBox)

    inputParametersFormLayout = qt.QFormLayout(self.inputParametersGroupBox)

    #
    # Root Path
    #
    self.rootSelector = qt.QLineEdit()
    self.rootSelector.text = 'path'
    self.rootSelector.toolTip = 'Location of the root directory to load from, or the column name specifying said ' \
                                'directory in the input CSV'
    inputParametersFormLayout.addRow('Root Column', self.rootSelector)

    #
    # Image Path
    #
    self.imageSelector = qt.QLineEdit()
    self.imageSelector.text = 'image'
    self.imageSelector.toolTip = 'Name of the column specifying main image files in input CSV'
    inputParametersFormLayout.addRow('Image Column', self.imageSelector)

    #
    # Mask Path
    #
    self.maskSelector = qt.QLineEdit()
    self.maskSelector.text = 'mask'
    self.maskSelector.toolTip = 'Name of the column specifying main mask files in input CSV'
    inputParametersFormLayout.addRow('Mask Column', self.maskSelector)

    #
    # Additional images
    #
    self.addImsSelector = qt.QLineEdit()
    self.addImsSelector.text = ''
    self.addImsSelector.toolTip = 'Comma separated names of the columns specifying additional image files in input CSV'
    inputParametersFormLayout.addRow('Additional images Column', self.addImsSelector)

    #
    # Additional masks
    #
    self.addMasksSelector = qt.QLineEdit()
    self.addMasksSelector.text = ''
    self.addMasksSelector.toolTip = 'Comma separated names of the columns specifying additional mask files in input CSV'
    inputParametersFormLayout.addRow('Additional masks Column', self.addMasksSelector)

    #
    # Connect Event Handlers
    #

    self.batchTableSelector.connect('nodeActivated(vtkMRMLNode*)', self.onChangeTable)
    self.imageSelector.connect('textEdited(QString)', self.onChangeImageColumn)

    return self.layout

  # ------------------------------------------------------------------------------
  def enter(self):
    self.onChangeTable()

  # ------------------------------------------------------------------------------
  def onEndClose(self):
    if self.tableNode is not None:
      slicer.mrmlScene.AddNode(self.tableNode)
      self.batchTableSelector.setCurrentNode(self.tableNode)
      self.batchTableView.setMRMLTableNode(self.tableNode)
      if self.tableStorageNode is not None:
        slicer.mrmlScene.AddNode(self.tableStorageNode)
        self.tableNode.SetAndObserveStorageNodeID(self.tableStorageNode.GetID())

  # ------------------------------------------------------------------------------
  def is_valid(self):
    """
    This function checks the current config to decide whether a batch can be started. This is used to enable/disable
    the "start batch" button.
    :return: boolean specifying if the current setting is valid and a batch may be started
    """
    return self.batchTableSelector.currentNodeID != '' and self.imageSelector.text != ''

  # ------------------------------------------------------------------------------
  def startBatch(self, reader):
    """
    Function to start the batch. In the derived class, this should store relevant nodes to keep track of important data
    :return: instance of an Iterator class defining the dataset to iterate over, and function for loading/storing a case
    """
    self.tableNode = self.batchTableSelector.currentNode()
    self.tableStorageNode = self.tableNode.GetStorageNode()

    columnMap = self._parseConfig()

    return CaseTableIteratorLogic(reader, self.tableNode, columnMap)

  # ------------------------------------------------------------------------------
  def cleanupBatch(self):
    self.tableNode = None
    self.tableStorageNode = None

  # ------------------------------------------------------------------------------
  def onChangeTable(self):
    self.batchTableView.setMRMLTableNode(self.batchTableSelector.currentNode())
    self.validate()

  # ------------------------------------------------------------------------------
  def onChangeImageColumn(self):
    self.validate()

  # ------------------------------------------------------------------------------
  def _parseConfig(self):
    """
    This parses the user input in the selectors of different column types.
    :return: Dictionary mapping requested columns to the correct keys
    """
    columnMap = {}

    if self.rootSelector.text != '':
      columnMap['root'] = str(self.rootSelector.text).strip()

    assert self.imageSelector.text != ''  # Image column is a required column
    columnMap['image'] = str(self.imageSelector.text).strip()

    if self.maskSelector.text != '':
      columnMap['mask'] = str(self.maskSelector.text).strip()

    if self.addImsSelector.text != '':
      columnMap['additionalImages'] = [str(c).strip() for c in self.addImsSelector.text.split(',')]

    if self.addMasksSelector.text != '':
      columnMap['additionalMasks'] = [str(c).strip() for c in self.addMasksSelector.text.split(',')]

    return columnMap


# ------------------------------------------------------------------------------
# SlicerCaseIterator CSV iterator
# ------------------------------------------------------------------------------


class CaseTableIteratorLogic(IteratorBase.IteratorLogicBase):

  def __init__(self, reader, tableNode, columnMap):
    super(CaseTableIteratorLogic, self).__init__(reader, SegmentationBackend.SegmentEditorBackend())
    assert tableNode is not None, 'No table selected! Cannot instantiate batch'

    # If the table was loaded from a file, get the directory containing the file as reference for relative paths
    tableStorageNode = tableNode.GetStorageNode()
    if tableStorageNode is not None and tableStorageNode.GetFileName() is not None:
      self.csv_dir = os.path.dirname(tableStorageNode.GetFileName())
    else:  # Table did not originate from a file
      self.csv_dir = None

    # Get the actual table contained in the MRML node
    self.batchTable = tableNode.GetTable()

    # Dictionary holding the specified (and found) columns from the tableNode
    self.caseColumns = self._getColumns(columnMap)

    self.caseCount = self.batchTable.GetNumberOfRows()  # Counter equalling the total number of cases
    self.currentCaseFolder = None  # Represents the currently loaded case

  # ------------------------------------------------------------------------------
  def _getColumns(self, columnMap):
    caseColumns = {}

    # Declare temporary function to parse out the user config and get the correct columns from the batchTable
    def getColumn(key):
      col = None
      if key in columnMap:
        col = self.batchTable.GetColumnByName(columnMap[key])
        assert col is not None, 'Unable to find column "%s" (key %s)' % (columnMap[key], key)
      caseColumns[key] = col
    def getListColumn(key):
      col_list = []
      if key in columnMap:
        for c_key in columnMap[key]:
          col = self.batchTable.GetColumnByName(c_key)
          assert col is not None, 'Unable to find column "%s" (key %s)' % (c_key, key)
          col_list.append(col)
      caseColumns[key] = col_list

    # Special case: Check if there is a column "patient" or "ID" (used for additional naming of the case during logging)
    patientColumn = self.batchTable.GetColumnByName('patient')
    if patientColumn is None:
      patientColumn = self.batchTable.GetColumnByName('ID')
    if patientColumn is not None:
      caseColumns['patient'] = patientColumn

    # Get the other configurable columns
    getColumn('root')
    getColumn('image')
    getColumn('mask')
    getListColumn('additionalImages')
    getListColumn('additionalMasks')

    return caseColumns

  # ------------------------------------------------------------------------------
  def loadCase(self, case_idx):
    assert 0 <= case_idx < self.caseCount, 'case_idx %d is out of range (n cases: %d)' % (case_idx, self.caseCount)

    if 'patient' in self.caseColumns:
      patient = self.caseColumns['patient'].GetValue(case_idx)
      self.logger.info('\nLoading patient (%d/%d): %s...', case_idx + 1, self.caseCount, patient)
    else:
      self.logger.info('\nLoading patient (%d/%d)...', case_idx + 1, self.caseCount)

    root = self._getColumnValue('root', case_idx)

    # Load images
    im = self._getColumnValue('image', case_idx)
    im_node = self._loadImageNode(root, im)
    assert im_node is not None, 'Failed to load main image'
    self.currentCaseFolder = os.path.dirname(im_node.GetStorageNode().GetFileName())

    additionalImageNodes = []
    for im in self._getColumnValue('additionalImages', case_idx, True):
      add_im_node = self._loadImageNode(root, im)
      if add_im_node is not None:
        additionalImageNodes.append(add_im_node)

    # Load masks
    ma_node = None
    ma = self._getColumnValue('mask', case_idx)
    if ma is not None:
      ma_path = self._buildPath(root, ma)
      if ma_path is not None:
        ma_node = self.backend.loadMask(ma_path, im_node)

    additionalMaskNodes = []
    for ma in self._getColumnValue('additionalMasks', case_idx, True):
      ma_path = self._buildPath(root, ma)
      if ma_path is None:
        continue

      add_ma_node = self.backend.loadMask(ma_path)
      if add_ma_node is not None:
        additionalMaskNodes.append(add_ma_node)

    return im_node, ma_node, additionalImageNodes, additionalMaskNodes

  # ------------------------------------------------------------------------------
  def _getColumnValue(self, colName, idx, is_list=False):
    if colName not in self.caseColumns or self.caseColumns[colName] is None:
      return None

    if is_list:
      return [col.GetValue(idx) for col in self.caseColumns[colName]]
    else:
      return self.caseColumns[colName].GetValue(idx)

  # ------------------------------------------------------------------------------
  def _buildPath(self, caseRoot, fname):
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
  def _loadImageNode(self, root, fname):
    im_path = self._buildPath(root, fname)
    if im_path is None:
      return None

    if not os.path.isfile(im_path):
      self.logger.warning('Volume file %s does not exist, skipping...', fname)
      return None

    load_success, im_node = slicer.util.loadVolume(im_path, returnNode=True)
    if not load_success:
      self.logger.warning('Failed to load ' + im_path)
      return None

    # Use the file basename as the name for the loaded volume
    im_node.SetName(os.path.splitext(os.path.basename(im_path))[0])

    return im_node

  # ------------------------------------------------------------------------------
  def saveMask(self, node, overwrite_existing=False):
    self._save_node(node, self.currentCaseFolder, overwrite_existing)

  # ------------------------------------------------------------------------------
  def cleanupIterator(self):
    self.batchTable = None
    self.caseColumns = None
