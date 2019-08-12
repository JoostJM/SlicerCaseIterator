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

import qt, ctk, slicer

from . import IteratorBase

# ------------------------------------------------------------------------------
# SlicerCaseIterator CSV iterator Widget
# ------------------------------------------------------------------------------


class CaseTableIteratorWidget(IteratorBase.IteratorWidgetBase):

  def __init__(self):
    super(CaseTableIteratorWidget, self).__init__()

    self.tableNode = None
    self.tableStorageNode = None

  # ------------------------------------------------------------------------------
  def setup(self):
    self.CsvInputGroupBox = qt.QGroupBox('CSV input for local files')

    CsvInputLayout = qt.QFormLayout(self.CsvInputGroupBox)

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
    CsvInputLayout.addRow(self.batchTableSelector)

    self.batchTableView = slicer.qMRMLTableView()
    CsvInputLayout.addRow(self.batchTableView)
    self.batchTableView.show()

    #
    # Parameters Area
    #
    self.parametersCollapsibleButton = ctk.ctkCollapsibleButton()
    self.parametersCollapsibleButton.text = 'Parameters'
    CsvInputLayout.addWidget(self.parametersCollapsibleButton)

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

    return self.CsvInputGroupBox

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
  def startBatch(self):
    """
    Function to start the batch. In the derived class, this should store relevant nodes to keep track of important data
    :return: instance of an Iterator class defining the dataset to iterate over, and function for loading/storing a case
    """
    self.tableNode = self.batchTableSelector.currentNode()
    self.tableStorageNode = self.tableNode.GetStorageNode()

    columnMap = self._parseConfig()

    return CaseTableIteratorLogic(self.tableNode, columnMap)

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

  def __init__(self, tableNode, columnMap):
    super(CaseTableIteratorLogic, self).__init__()
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
  def __del__(self):
    self.logger.debug('Destroying CSV Table Iterator')
    self.batchTable = None
    self.caseColumns = None

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
      self.logger.info('Loading patient (%d/%d): %s...', case_idx + 1, self.caseCount, patient)
    else:
      self.logger.info('Loading patient (%d/%d)...', case_idx + 1, self.caseCount)

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
    ma = self._getColumnValue('mask', case_idx)
    if ma is not None:
      ma_node = self._loadMaskNode(root, ma, im_node)
    else:
      ma_node = None

    additionalMaskNodes = []
    for ma in self._getColumnValue('additionalMasks', case_idx, True):
      add_ma_node = self._loadMaskNode(root, ma)
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
  def _loadMaskNode(self, root, fname, ref_im=None):
    ma_path = self._buildPath(root, fname)
    if ma_path is None:
      return None

    # Check if the file actually exists
    if not os.path.isfile(ma_path):
      self.logger.warning('Segmentation file %s does not exist, skipping...', fname)
      return None

    # Determine if file is segmentation based on extension
    isSegmentation = os.path.splitext(ma_path)[0].endswith('.seg')
    # Try to load the mask
    if isSegmentation:
      self.logger.debug('Loading segmentation')
      load_success, ma_node = slicer.util.loadSegmentation(ma_path, returnNode=True)
    else:
      self.logger.debug('Loading labelmap and converting to segmentation')
      # If not segmentation, then load as labelmap then convert to segmentation
      load_success, ma_node = slicer.util.loadLabelVolume(ma_path, returnNode=True)
      if load_success:
        # Only try to make a segmentation node if Slicer was able to load the label map
        seg_node = slicer.vtkMRMLSegmentationNode()
        slicer.mrmlScene.AddNode(seg_node)
        seg_node.SetReferenceImageGeometryParameterFromVolumeNode(ref_im)
        load_success = slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(ma_node, seg_node)
        slicer.mrmlScene.RemoveNode(ma_node)
        ma_node = seg_node

        # Add a storage node for this segmentation node
        file_base, ext = os.path.splitext(ma_path)
        store_node = seg_node.CreateDefaultStorageNode()
        slicer.mrmlScene.AddNode(store_node)
        seg_node.SetAndObserveStorageNodeID(store_node.GetID())

        store_node.SetFileName('%s.seg%s' % (file_base, ext))

        # UnRegister the storage node to prevent a memory leak
        store_node.UnRegister(None)

    if not load_success:
      self.logger.warning('Failed to load ' + ma_path)
      return None

    # Use the file basename as the name for the newly loaded segmentation node
    file_base = os.path.splitext(os.path.basename(ma_path))[0]
    if isSegmentation:
      # split off .seg
      file_base = os.path.splitext(file_base)[0]
    ma_node.SetName(file_base)

    return ma_node

  # ------------------------------------------------------------------------------
  def saveMask(self, node, reader, overwrite_existing=False):
    storage_node = node.GetStorageNode()
    if storage_node is not None and storage_node.GetFileName() is not None:
      # mask was loaded, save the updated mask in the same directory
      target_dir = os.path.dirname(storage_node.GetFileName())
    else:
      target_dir = self.currentCaseFolder

    nodename = node.GetName()
    # Add the readername if set
    if reader is not None:
      nodename += '_' + reader
    filename = os.path.join(target_dir, nodename)

    # Prevent overwriting existing files
    if os.path.exists(filename + '.seg.nrrd') and not overwrite_existing:
      self.logger.debug('Filename exists! Generating unique name...')
      idx = 1
      filename += '(%d).seg.nrrd'
      while os.path.exists(filename % idx):
        idx += 1
      filename = filename % idx
    else:
      filename += '.seg.nrrd'

    # Save the node
    slicer.util.saveNode(node, filename)
    self.logger.info('Saved node %s in %s', nodename, filename)
