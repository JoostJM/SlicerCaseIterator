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

import vtk, qt, ctk, slicer

from . import IteratorBase, SegmentationBackend

# ------------------------------------------------------------------------------
# SlicerCaseIterator CSV iterator Widget
# ------------------------------------------------------------------------------


class DicomTableIteratorWidget(IteratorBase.IteratorWidgetBase):

  def __init__(self, parent):
    super().__init__(parent)

    self.tableNode = None
    self.tableStorageNode = None

  @classmethod
  def get_header(cls):
    return 'DICOM Table'

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
  def startBatch(self, reader):
    """
    Function to start the batch. In the derived class, this should store relevant nodes to keep track of important data
    :return: instance of an Iterator class defining the dataset to iterate over, and function for loading/storing a case
    """
    self.tableNode = self.batchTableSelector.currentNode()
    self.tableStorageNode = self.tableNode.GetStorageNode()

    columnMap = self._parseConfig()

    return DicomTableIteratorLogic(reader, self.tableNode, columnMap)

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


class DicomTableIteratorLogic(IteratorBase.TableIteratorLogicBase):

  def __init__(self, reader, tableNode, columnMap):
    super(DicomTableIteratorLogic, self).__init__(reader,
                                                  SegmentationBackend.SegmentEditorBackend(),
                                                  tableNode,
                                                  None)

    required_columns = []
    self.mainSeries = columnMap['mainSeries']
    required_columns.append(self.mainSeries)

    self.mainMask = columnMap.get('mainMask', None)
    required_columns.append(self.mainMask)

    self.additionalSeries = columnMap.get('additionalSeries', [])
    required_columns += self.additionalSeries

    self.additionalMasks = columnMap.get('additionalMasks', [])
    required_columns += self.additionalMasks

    self.checkColumns(required_columns)

    self.caseCount = self.batchTable.GetNumberOfRows()  # Counter equalling the total number of cases

  # ------------------------------------------------------------------------------
  def loadCase(self, case_idx):
    assert 0 <= case_idx < self.caseCount, 'case_idx %d is out of range (n cases: %d)' % (case_idx, self.caseCount)

    self.logger.debug('Starting load of case %i', case_idx)

    # Load images
    series = self.getColumnValue(self.mainSeries, case_idx)

    study = slicer.dicomDatabase.studyForSeries(series)
    patient = slicer.dicomDatabase.patientForStudy(study)
    pt_name = slicer.dicomDatabase.nameForPatient(patient)

    series_description = slicer.dicomDatabase.descriptionForSeries(series)
    filenames = slicer.dicomDatabase.filesForSeries(series)

    self.logger.info('Loading patient (%d/%d): %s...', case_idx + 1, self.caseCount, pt_name)

    load_success, series_node = self._tryLoadDICOMSeries(series_description, filenames)

    assert load_success, 'Failed to load main image (%s)' % series_description

    additionalSeriesNodes = []
    for additional_series in self.additionalSeries:
      series = self.getColumnValue(additional_series, case_idx)
      if series is None:
        continue
      series_description = slicer.dicomDatabase.descriptionForSeries(series)
      filenames = slicer.dicomDatabase.filesForSeries(series)

      load_success, add_se_node = self._tryLoadDICOMSeries(series_description, filenames)
      if load_success:
        additionalSeriesNodes.append(add_se_node)

    # Load masks
    ma = self.getColumnValue(self.mainMask, case_idx)
    ma_path = self.buildPath(ma)
    ma_node = self.backend.loadMask(ma_path, series_node)

    additionalMaskNodes = []
    for additional_mask in self.additionalMasks:
      ma = self.getColumnValue(additional_mask, case_idx)
      ma_path = self.buildPath(ma)
      add_ma_node = self.backend.loadMask(ma_path)
      if add_ma_node is not None:
        additionalMaskNodes.append(add_ma_node)

    return series_node, ma_node, additionalSeriesNodes, additionalMaskNodes

  # ------------------------------------------------------------------------------
  def _tryLoadDICOMSeries(self, seriesdescription, filenames):
    """
    Function to examine filenames and attempt to get a valid loadable to get the DICOM series.
    Adapted from https://github.com/SlicerProstate/mpReview/blob/master/mpReviewPreprocessor.py#L173-L184
    :param filenames: filenames corresponding to the series to load
    :return: (Boolean indicating if the load was successful, loaded node)
    """
    if len(filenames) == 0:
      self.logger.warning('No files found for Series %s' % seriesdescription)
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
  def saveMask(self, node, overwrite_existing=False):
    self._save_node(node, self.csv_dir, overwrite_existing)

  # ------------------------------------------------------------------------------
  def cleanupIterator(self):
    super(DicomTableIteratorLogic, self).cleanupIterator()

    self.mainSeries = None
    self.mainMask = None
    self.additionalSeries = None
    self.additionalMasks = None
