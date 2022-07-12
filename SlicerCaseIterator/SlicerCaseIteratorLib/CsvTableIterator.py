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

  def __init__(self, parent):
    super().__init__(parent)

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


class CaseTableIteratorLogic(IteratorBase.TableIteratorLogicBase):

  def __init__(self, reader, tableNode, columnMap):
    super(CaseTableIteratorLogic, self).__init__(reader,
                                                 SegmentationBackend.SegmentEditorBackend(),
                                                 tableNode,
                                                 None)
    required_columns = []
    self.mainImage = columnMap['image']
    required_columns.append(self.mainImage)

    self.mainMask = columnMap.get('mask', None)
    required_columns.append(self.mainMask)

    self.additionalImages = columnMap.get('additionalImages', [])
    required_columns += self.additionalImages

    self.additionalMasks = columnMap.get('additionalMasks', [])
    required_columns += self.additionalMasks

    self.root = columnMap.get('root', None)
    required_columns.append(self.root)

    if self.batchTable.GetColumnByName('patient') is not None:
      self.patient = 'patient'
    elif self.batchTable.GetColumnByName('ID') is not None:
      self.patient = 'ID'
    else:
      self.patient = None

    self.checkColumns(required_columns)

    self.caseCount = self.batchTable.GetNumberOfRows()  # Counter equalling the total number of cases
    self.currentCaseFolder = None  # Represents the currently loaded case

    self.resetGridShortCut = qt.QShortcut(slicer.util.mainWindow())
    self.resetGridShortCut.setKey(qt.QKeySequence('Alt+R'))
    self.resetGridShortCut.connect('activated()', self.onResetGrid)

  # ------------------------------------------------------------------------------
  def loadCase(self, case_idx):
    assert 0 <= case_idx < self.caseCount, 'case_idx %d is out of range (n cases: %d)' % (case_idx, self.caseCount)

    patient = self.getColumnValue(self.patient, case_idx)
    if patient is not None:
      self.logger.info('\nLoading patient (%d/%d): %s...', case_idx + 1, self.caseCount, patient)
    else:
      self.logger.info('\nLoading patient (%d/%d)...', case_idx + 1, self.caseCount)

    root = self.getColumnValue(self.root, case_idx)

    # Load images
    im = self.getColumnValue(self.mainImage, case_idx)
    im_node = self._loadImageNode(root, im)
    assert im_node is not None, 'Failed to load main image'
    self.currentCaseFolder = os.path.dirname(im_node.GetStorageNode().GetFileName())

    additionalImageNodes = []
    for additional_image in self.additionalImages:
      im = self.getColumnValue(additional_image, case_idx)
      add_im_node = self._loadImageNode(root, im)
      if add_im_node is not None:
        additionalImageNodes.append(add_im_node)

    # Load masks
    ma = self.getColumnValue(self.mainMask, case_idx)
    ma_path = self.buildPath(ma, root)
    ma_node = self.backend.loadMask(ma_path, im_node)

    additionalMaskNodes = []
    for additional_mask in self.additionalMasks:
      ma = self.getColumnValue(additional_mask, case_idx)
      ma_path = self.buildPath(ma, root)
      add_ma_node = self.backend.loadMask(ma_path)
      if add_ma_node is not None:
        additionalMaskNodes.append(add_ma_node)

    return im_node, ma_node, additionalImageNodes, additionalMaskNodes

  #   # ------------------------------------------------------------------------------
  def _loadImageNode(self, root, fname):
    im_path = self.buildPath(fname, root)
    if im_path is None:
      return None

    if not os.path.isfile(im_path):
      self.logger.warning('Volume file %s does not exist, skipping...', fname)
      return None

    im_node = slicer.util.loadVolume(im_path)

    # Use the file basename as the name for the loaded volume
    im_node.SetName(os.path.splitext(os.path.basename(im_path))[0])

    return im_node

  # ------------------------------------------------------------------------------
  def saveMask(self, node, overwrite_existing=False):
    self._save_node(node, self.currentCaseFolder, overwrite_existing)

  # ------------------------------------------------------------------------------
  def onResetGrid(self):
    self.logger.info('Snapping to IJK grid...')
    # Snap to IJK to try and avoid rounding errors
    sliceLogics = slicer.app.layoutManager().mrmlSliceLogics()
    numLogics = sliceLogics.GetNumberOfItems()
    for n in range(numLogics):
      l = sliceLogics.GetItemAsObject(n)
      l.SnapSliceOffsetToIJK()
      
  # ------------------------------------------------------------------------------
  def cleanupIterator(self):
    super(CaseTableIteratorLogic, self).cleanupIterator()

    self.mainImage = None
    self.mainMask = None
    self.additionalImages = None
    self.additionalMasks = None
    self.root = None
    self.patient = None

    if hasattr(self, 'resetGridShortCut') and self.resetGridShortCut is not None:
      self.resetGridShortCut.disconnect('activated()')
      self.resetGridShortCut.setParent(None)
      self.resetGridShortCut = None
