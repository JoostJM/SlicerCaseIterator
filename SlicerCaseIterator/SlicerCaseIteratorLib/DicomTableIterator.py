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

from . import IteratorBase

# ------------------------------------------------------------------------------
# SlicerCaseIterator CSV iterator Widget
# ------------------------------------------------------------------------------


class DicomTableIteratorWidget(IteratorBase.IteratorWidgetBase):

  def __init__(self):
    super(DicomTableIteratorWidget, self).__init__()

    self.tableNode = None
    self.tableStorageNode = None

  # ------------------------------------------------------------------------------
  def setup(self):
    self.layout = qt.QGroupBox('CSV input for DICOM')

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
    # Image Path
    #
    self.imageSelector = qt.QLineEdit()
    self.imageSelector.text = 'image'
    self.imageSelector.toolTip = 'Name of the column specifying main dicom series uid in input CSV'
    inputParametersFormLayout.addRow('Main Series Column', self.imageSelector)

    #
    # Mask Path
    #
    self.maskSelector = qt.QLineEdit()
    self.maskSelector.text = 'mask'
    self.maskSelector.toolTip = 'Name of the column specifying main mask files in input CSV'
    inputParametersFormLayout.addRow('Main Mask Column', self.maskSelector)

    #
    # Additional images
    #
    self.addImsSelector = qt.QLineEdit()
    self.addImsSelector.text = ''
    self.addImsSelector.toolTip = 'Comma separated names of the columns specifying additional series uids in input CSV'
    inputParametersFormLayout.addRow('Additional series Column', self.addImsSelector)

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
  def startBatch(self):
    """
    Function to start the batch. In the derived class, this should store relevant nodes to keep track of important data
    :return: instance of an Iterator class defining the dataset to iterate over, and function for loading/storing a case
    """
    self.tableNode = self.batchTableSelector.currentNode()
    self.tableStorageNode = self.tableNode.GetStorageNode()

    columnMap = self._parseConfig()

    return DicomTableIteratorLogic(self.tableNode, columnMap)

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

    assert self.imageSelector.text != ''  # Image column is a required column
    columnMap['mainSeries'] = str(self.imageSelector.text).strip()

    if self.maskSelector.text != '':
      columnMap['mainMask'] = str(self.maskSelector.text).strip()

    if self.addImsSelector.text != '':
      columnMap['additionalSeries'] = [str(c).strip() for c in self.addImsSelector.text.split(',')]

    if self.addMasksSelector.text != '':
      columnMap['additionalMasks'] = [str(c).strip() for c in self.addMasksSelector.text.split(',')]

    return columnMap


# ------------------------------------------------------------------------------
# SlicerCaseIterator CSV iterator
# ------------------------------------------------------------------------------


class DicomTableIteratorLogic(IteratorBase.IteratorLogicBase):

  def __init__(self, tableNode, columnMap):
    super(DicomTableIteratorLogic, self).__init__()
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

  # ------------------------------------------------------------------------------
  def __del__(self):
    self.logger.debug('Destroying Dicom Table Iterator')
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

    # Get the other configurable columns
    getColumn('mainSeries')
    getColumn('mainMask')
    getListColumn('additionalSeries')
    getListColumn('additionalMasks')

    return caseColumns

  # ------------------------------------------------------------------------------
  def loadCase(self, case_idx):
    assert 0 <= case_idx < self.caseCount, 'case_idx %d is out of range (n cases: %d)' % (case_idx, self.caseCount)

    self.logger.debug('Starting load of case %i', case_idx)

    # Load images
    series = self._getColumnValue('mainSeries', case_idx)
    study = slicer.dicomDatabase.studyForSeries(series)
    patient = slicer.dicomDatabase.patientForStudy(study)
    pt_name = slicer.dicomDatabase.nameForPatient(patient)

    series_description = slicer.dicomDatabase.descriptionForSeries(series)
    filenames = slicer.dicomDatabase.filesForSeries(series)

    self.logger.info('Loading patient (%d/%d): %s...', case_idx + 1, self.caseCount, pt_name)

    load_success, series_node = self._tryLoadDICOMSeries(series_description, filenames)

    assert load_success, 'Failed to load main image (%s)' % series_description

    additionalSeriesNodes = []
    for series in self._getColumnValue('additionalSeries', case_idx, True):
      series_description = slicer.dicomDatabase.descriptionForSeries(series)
      filenames = slicer.dicomDatabase.filesForSeries(series)

      load_success, add_se_node = self._tryLoadDICOMSeries(series_description, filenames)
      if load_success:
        additionalSeriesNodes.append(add_se_node)

    # Load masks
    ma = self._getColumnValue('mainMask', case_idx)
    if ma is not None:
      ma_node = self._loadMaskNode(ma, series_node)
    else:
      ma_node = None

    additionalMaskNodes = []
    for ma in self._getColumnValue('additionalMasks', case_idx, True):
      add_ma_node = self._loadMaskNode(root, ma)
      if add_ma_node is not None:
        additionalMaskNodes.append(add_ma_node)

    return series_node, ma_node, additionalSeriesNodes, additionalMaskNodes

  # ------------------------------------------------------------------------------
  def _getColumnValue(self, colName, idx, is_list=False):
    if colName not in self.caseColumns or self.caseColumns[colName] is None:
      return None

    if is_list:
      return [col.GetValue(idx) for col in self.caseColumns[colName]]
    else:
      return self.caseColumns[colName].GetValue(idx)

  # ------------------------------------------------------------------------------
  def _buildPath(self, fname):
    if fname is None or fname == '':
      return None

    if os.path.isabs(fname):
      return fname

    # Add the csv_dir to the path if it is not None (loaded table)
    if self.csv_dir is not None:
      fname = os.path.join(self.csv_dir, fname)

    return os.path.abspath(fname)

  # ------------------------------------------------------------------------------
  def _loadMaskNode(self, fname, ref_im=None):
    ma_path = self._buildPath(fname)
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

  def _tryLoadDICOMSeries(self, seriesdescription, filenames):
    """
    Function to examine filenames and attempt to get a valid loadable to get the DICOM series.
    Adapted from https://github.com/SlicerProstate/mpReview/blob/master/mpReviewPreprocessor.py#L173-L184
    :param filenames: filenames corresponding to the series to load
    :return: (Boolean indicating if the load was successful, loaded node)
    """
    if len(filenames) == 0:
      self.logger.warning('No files found for SeriesUID %s' % seriesdescription)
      return False, None

    self.logger.debug('Found %i files for series %s', len(filenames), seriesdescription)

    plugins = ('MultiVolumeImporterPlugin', 'DICOMScalarVolumePlugin')
    for p_name in plugins:
      self.logger.debug('Attempting to load Series using plugin %s', p_name)
      plugin = slicer.modules.dicomPlugins[p_name]()
      loadables = plugin.examineFiles(filenames)
      if len(loadables) == 0:
        continue
      loadables.sort(key=lambda x: x.confidence, reverse=True)
      if loadables[0].confidence > 0.1:
        self.logger.debug('Loading DICOM Series %s using plugin %s', seriesdescription, p_name)
        return True, plugin.load(loadables[0])  # Loads the series into a new node and adds it to the scene
    self.logger.warning('Failed to find a valid loader for series %s', seriesdescription)
    return False, None

  # ------------------------------------------------------------------------------
  def saveMask(self, node, reader, overwrite_existing=False):
    storage_node = node.GetStorageNode()
    if storage_node is not None and storage_node.GetFileName() is not None:
      # mask was loaded, save the updated mask in the same directory
      target_dir = os.path.dirname(storage_node.GetFileName())
    else:
      target_dir = self.csv_dir

    if not os.path.isdir(target_dir):
      self.logger.debug('Creating output directory at %s', target_dir)
      os.makedirs(target_dir)

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
