import os
from collections import OrderedDict

import vtk, qt, ctk, slicer

from . import IteratorBase

# ------------------------------------------------------------------------------
# SlicerCaseIterator CSV iterator Widget
# ------------------------------------------------------------------------------


class CsvInferenceIteratorWidget(IteratorBase.IteratorWidgetBase):

  def __init__(self):
    super(CsvInferenceIteratorWidget, self).__init__()

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

    #
    # Parameters Area
    #
    self.parametersCollapsibleButton = ctk.ctkCollapsibleButton()
    self.parametersCollapsibleButton.text = 'Table view and attribute properties'
    CsvInputLayout.addWidget(self.parametersCollapsibleButton)

    # Layout within the dummy collapsible button
    parametersFormLayout = qt.QFormLayout(self.parametersCollapsibleButton)

    self.batchTableView = slicer.qMRMLTableView()
    parametersFormLayout.addRow(self.batchTableView)
    self.batchTableView.show()

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
    # GroundTruth masks
    #
    self.inputGTMaskColumnNames = qt.QLineEdit()
    self.inputGTMaskColumnNames.text = 'gt_0,gt_1,gt_2'
    self.inputGTMaskColumnNames.toolTip = 'Comma separated names of the columns specifying groundtruth mask files in input CSV'
    inputParametersFormLayout.addRow('Groundtruth masks Column(s)', self.inputGTMaskColumnNames)

    #
    # Predicted masks
    #
    self.inputPredMaskColumnNames = qt.QLineEdit()
    self.inputPredMaskColumnNames.text = 'pred_0,pred_1,pred_2'
    self.inputPredMaskColumnNames.toolTip = 'Comma separated names of the columns specifying predicted mask files in input CSV'
    inputParametersFormLayout.addRow('Predicted masks Column(s)', self.inputPredMaskColumnNames)

    self.iterationParametersGroupBox = qt.QGroupBox('Iteration parameters')
    parametersFormLayout.addRow(self.iterationParametersGroupBox)

    iterationParametersFormLayout = qt.QFormLayout(self.iterationParametersGroupBox)

    #
    # Cache Cases
    #
    self.cacheCases = qt.QCheckBox()
    self.cacheCases.checked = True
    self.cacheCases.toolTip = 'Cache cases for faster reload'
    iterationParametersFormLayout.addRow('Cache cases', self.cacheCases)

    #
    # Preload Cases
    #
    self.preloadCases = qt.QCheckBox()
    self.preloadCases.checked = True
    self.preloadCases.toolTip = 'Preloading all cases'
    iterationParametersFormLayout.addRow('Preload cases', self.preloadCases)

    #
    # Progressbar
    #
    self.progressBar = qt.QProgressBar()
    self.progressBar.setFormat("%v/%m")
    self.progressBar.visible = False
    iterationParametersFormLayout.addWidget(self.progressBar)

    #
    # Connect Event Handlers
    #
    self.batchTableSelector.connect('nodeActivated(vtkMRMLNode*)', self.onChangeTable)
    self.imageSelector.connect('textEdited(QString)', self.onChangeImageColumn)
    self.preloadCases.stateChanged.connect(self.onPreloadCasesChanged)

    return self.CsvInputGroupBox

  # ------------------------------------------------------------------------------
  def enter(self):
    self.onChangeTable()

  def onPreloadCasesChanged(self):
    if self.preloadCases.checked:
      self.cacheCases.checked = True

  # ------------------------------------------------------------------------------
  def is_valid(self):
    """
    This function checks the current config to decide whether a batch can be started. This is used to enable/disable
    the "start batch" button.
    :return: boolean specifying if the current setting is valid and a batch may be started
    """
    return self.batchTableSelector.currentNodeID != '' and self.imageSelector.text != ''

  # ------------------------------------------------------------------------------
  def startBatch(self, reader=None):
    """
    Function to start the batch. In the derived class, this should store relevant nodes to keep track of important data
    :return: instance of an Iterator class defining the dataset to iterate over, and function for loading/storing a case
    """
    self.tableNode = self.batchTableSelector.currentNode()
    self.tableStorageNode = self.tableNode.GetStorageNode()

    columnMap = self._parseConfig()

    self._iterator = CsvInferenceIteratorLogic(self.tableNode, columnMap, cacheCases=self.cacheCases.checked)
    self._iterator.registerEventListener(
      CsvTableEventHandler(reader=reader)
    )
    if self.preloadCases.checked:
      self._preload()
    return self._iterator

  def _preload(self):
    if not self._iterator.caseCount or not self._iterator.cacheCases:
      return

    self.progressBar.maximum = self._iterator.caseCount
    self.progressBar.visible = True
    slicer.app.processEvents()
    for caseIdx in range(self._iterator.caseCount):
      self._iterator.loadCase(caseIdx)
      self.progressBar.value = self._iterator.currentIdx + 1
    self._iterator.closeCase()
    self.progressBar.visible = False

  # ------------------------------------------------------------------------------
  def cleanupBatch(self):
    if self._iterator:
      self._iterator.reset()
    self.tableNode = None
    self.tableStorageNode = None
    self._iterator = None

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

    if self.inputGTMaskColumnNames.text != '':
      columnMap['gtMasks'] = [str(c).strip() for c in self.inputGTMaskColumnNames.text.split(',')]

    if self.inputPredMaskColumnNames.text != '':
      columnMap['predMasks'] = [str(c).strip() for c in self.inputPredMaskColumnNames.text.split(',')]

    return columnMap


# ------------------------------------------------------------------------------
# SlicerCaseIterator CSV iterator
# ------------------------------------------------------------------------------


class CsvInferenceIteratorLogic(IteratorBase.IteratorLogicBase):

  def _createTable(self):
    table = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTableNode')
    table.SetUseColumnNameAsColumnHeader(True)
    table.SetName("Case_{}".format(self.currentIdx))
    return table

  @property
  def table(self):
    if self.cacheCases:
      self.getCachedTable(self.currentIdx)

    if not hasattr(self, '_table') or self._table is None:
      self._table = self._createTable()
    return self._table

  def getCachedTable(self, caseIdx):
    try:
      return self._tablesCache[caseIdx]
    except KeyError:
      self._tablesCache[self.currentIdx] = self._createTable()
      return self._tablesCache[self.currentIdx]

  @staticmethod
  def getAllSegmentIDs(segmentationNode):
    segmentIDs = vtk.vtkStringArray()
    segmentation = segmentationNode.GetSegmentation()
    segmentation.GetSegmentIDs(segmentIDs)
    return [segmentIDs.GetValue(idx) for idx in range(segmentIDs.GetNumberOfValues())]

  def __init__(self, tableNode, columnMap, cacheCases):
    super(CsvInferenceIteratorLogic, self).__init__()
    assert tableNode is not None, 'No table selected! Cannot instantiate batch'

    # If the table was loaded from a file, get the directory containing the file as reference for relative paths
    tableStorageNode = tableNode.GetStorageNode()
    if tableStorageNode is not None and tableStorageNode.GetFileName() is not None:
      self.csv_dir = os.path.dirname(tableStorageNode.GetFileName())
    else:  # Table did not originate from a file
      self.csv_dir = None

    # Get the actual table contained in the MRML node
    self.batchTable = tableNode.GetTable()

    self.caseColumns = self._getColumns(columnMap)

    self.caseCount = self.batchTable.GetNumberOfRows()  # Counter equalling the total number of cases

    self.cacheCases = cacheCases
    if self.cacheCases:
      self._tablesCache = dict()

  # ------------------------------------------------------------------------------
  def __del__(self):
    super(CsvInferenceIteratorLogic, self).__del__()
    self.logger.debug('Destroying CSV inference Iterator')
    self.batchTable = None
    self.caseColumns = None

  def reset(self):
    if self.cacheCases:
      for caseIdx in range(self.caseCount):
        self.cacheCases = False
        self.currentIdx = caseIdx
        self.closeCase()
        # caseData = self.getCaseData(caseIdx)
        # if caseData:
        #   im, gt_ma, pred_ma = caseData
        #   slicer.mrmlScene.RemoveNode(im)
        #   map(slicer.mrmlScene.RemoveNode, gt_ma)
        #   map(slicer.mrmlScene.RemoveNode, pred_ma)
        #   self.parameterNode.UnsetParameter("CaseData_{}".format(caseIdx))
        #   if caseIdx in list(self._tablesCache.keys()):
        #     slicer.mrmlScene.RemoveNode(self._tablesCache[caseIdx])
        #     del self._tablesCache[caseIdx]
        # else:
        #   import logging
        #   logging.info("Cannot find case data for {}".format(caseIdx))
    else:
      self.closeCase()

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
    getListColumn('gtMasks')
    getListColumn('predMasks')

    return caseColumns

  # ------------------------------------------------------------------------------
  def loadCase(self, case_idx):
    assert 0 <= case_idx < self.caseCount, 'case_idx %d is out of range (n cases: %d)' % (case_idx, self.caseCount)

    if self.currentIdx is not None:
      self.closeCase()

    if not self.getCaseData(case_idx):
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

      # TODO: load all gt masks into same segmentation node
      gtMaskNodes = []
      for ma in self._getColumnValue('gtMasks', case_idx, True):
        gt_ma_node = self._loadMaskNode(root, ma, ref_im=im_node)
        if gt_ma_node is not None:
          gtMaskNodes.append(gt_ma_node)

      # TODO: load all pred masks into same segmentation node
      predMaskNodes = []
      for ma in self._getColumnValue('predMasks', case_idx, True):
        pred_ma_node = self._loadMaskNode(root, ma, ref_im=im_node, color=(1., 0.07, 0.03))
        if pred_ma_node is not None:
          predMaskNodes.append(pred_ma_node)

      self.parameterNode.SetParameter("CaseData_{}".format(case_idx), {
        "InputImage_ID": im_node.GetID(),
        "GT_Mask_IDs": [node.GetID() for node in gtMaskNodes],
        "PRED_Mask_IDs": [node.GetID() for node in predMaskNodes],
      }.__str__())

    self.currentIdx = case_idx

    self._eventListeners.caseLoaded(self.parameterNode)
    return True

  def closeCase(self):
    self._eventListeners.caseAboutToClose(self.parameterNode)
    caseData = self.getCaseData()
    if caseData:
      im, gt_ma, pred_ma = caseData

    if not self.cacheCases:
      slicer.mrmlScene.RemoveNode(im)
      map(slicer.mrmlScene.RemoveNode, gt_ma)
      map(slicer.mrmlScene.RemoveNode, pred_ma)
      self.parameterNode.UnsetParameter("CaseData_{}".format(self.currentIdx))
      slicer.mrmlScene.RemoveNode(self.table)
      self.currentIdx = None
      self._table = None

  def getCaseData(self, caseIdx=None):
    """
    :return: image node, mask node, additional image nodes, additional mask nodes
    """
    caseIdx = caseIdx if caseIdx else self.currentIdx
    caseData = self.parameterNode.GetParameter("CaseData_{}".format(caseIdx))
    if caseData:
      caseData = eval(caseData)
      im_node = slicer.mrmlScene.GetNodeByID(caseData["InputImage_ID"])
      gt_mask_nodes = list(map(slicer.mrmlScene.GetNodeByID, caseData["GT_Mask_IDs"]))
      pred_mask_nodes = list(map(slicer.mrmlScene.GetNodeByID, caseData["PRED_Mask_IDs"]))
      return im_node, gt_mask_nodes, pred_mask_nodes
    else:
      return None

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
  def _loadMaskNode(self, root, fname, ref_im=None, color=None):
    ma_path = self._buildPath(root, fname)
    if ma_path is None:
      return None

    # Check if the file actually exists
    if not os.path.isfile(ma_path):
      self.logger.warning('Segmentation file %s does not exist, skipping...', fname)
      return None

    # Determine if file is segmentation based on extension
    isSegmentation = os.path.splitext(ma_path)[0].endswith('.seg')
    if isSegmentation:
      self.logger.debug('Loading segmentation')
      load_success, ma_node = slicer.util.loadSegmentation(ma_path, returnNode=True)
    else:
      load_success, ma_node = self.loadLabelIntoSegmentation(ma_path, ref_im, color)

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

  def loadLabelIntoSegmentation(self, ma_path, ref_im, color=None):
    # TODO: allow seg_node parameter to prevent creation of new node for every segment
    self.logger.debug('Loading labelmap and converting to segmentation')

    load_success, ma_node = slicer.util.loadLabelVolume(ma_path, returnNode=True)
    if load_success:
      seg_node = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLSegmentationNode')
      seg_node.SetReferenceImageGeometryParameterFromVolumeNode(ref_im)
      load_success = slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(ma_node, seg_node)
      try:
        segment = seg_node.GetSegmentation().GetSegment(self.getAllSegmentIDs(seg_node)[-1])
        if segment and color:
          segment.SetColor(*color)
      except IndexError:
        pass
      slicer.mrmlScene.RemoveNode(ma_node)
      ma_node = seg_node
    return load_success, ma_node


class CsvTableEventHandler(IteratorBase.IteratorEventHandlerBase):

  COMPARISON_NAMES_GETTERS = OrderedDict({"Hausdorff_Maximum_mm": "GetMaximumHausdorffDistanceForVolumeMm",
                                          "Hausdorff_Average_mm": "GetAverageHausdorffDistanceForBoundaryMm",
                                          "Hausdorff_95_mm": "GetPercent95HausdorffDistanceForBoundaryMm",
                                          "Dice_coefficient": "GetDiceCoefficient",
                                          "Dice_Reference_volume_cc": "GetReferenceVolumeCc",
                                          "Dice_Compare_volume_cc": "GetCompareVolumeCc"})

  @staticmethod
  def showSegmentation(segmentationNode):
    segmentationNode.CreateClosedSurfaceRepresentation()
    displayNode = segmentationNode.GetDisplayNode()
    displayNode.SetAllSegmentsVisibility3D(True)
    displayNode.SetAllSegmentsOpacity3D(0.5)
    displayNode.SetAllSegmentsVisibility(True)

  @staticmethod
  def hideAllSegmentations():
    seg_nodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
    for seg_node in seg_nodes:
      displayNode = seg_node.GetDisplayNode()
      displayNode.SetAllSegmentsVisibility(False)

  def __init__(self, reader=None):
    super(CsvTableEventHandler, self).__init__()

    self.reader = reader
    self._onQuantificationRowChanged = None

  def onCaseLoaded(self, caller, *args, **kwargs):
    try:
      im, gt_ma, pred_ma = caller.getCaseData()

      # Set the slice viewers to the correct volumes
      for sliceWidgetName in ['Red', 'Green', 'Yellow']:
        logic = slicer.app.layoutManager().sliceWidget(sliceWidgetName).sliceLogic().GetSliceCompositeNode()
        logic.SetBackgroundVolumeID(im.GetID())

      if caller.table.GetNumberOfRows() == 0:
        self.initializeTableHeader(caller)
        self.createSegmentsComparison(gt_ma, pred_ma, caller.table)

      self.setupFourUpTableViewConnection(caller)
    except Exception as e:
      self.logger.warning("Error loading new case: %s", e.message)
      self.logger.debug('', exc_info=True)

  def initializeTableHeader(self, caller):
    for colName in ["Segments"] + list(self.COMPARISON_NAMES_GETTERS.keys()):
      col = caller.table.AddColumn()
      col.SetName(colName)

  def setupFourUpTableViewConnection(self, caller):
    if not slicer.app.layoutManager().tableWidget(0):
      slicer.app.layoutManager().setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpTableView)

    slicer.app.applicationLogic().GetSelectionNode().SetReferenceActiveTableID(caller.table.GetID())
    slicer.app.applicationLogic().PropagateTableSelection()

    self.fourUpTableView = slicer.app.layoutManager().tableWidget(0).tableView()
    self.fourUpTableView.setSelectionBehavior(qt.QTableView.SelectRows)

    def onQuantificationRowChanged(caller, itemSelection=None):
      selectionModel = self.fourUpTableView.selectionModel()
      selectedRows = [selectionModel.selectedRows()[idx].row() for idx in range(len(selectionModel.selectedRows()))]
      self.hideAllSegmentations()
      if selectedRows:
        _, gt_masks, pred_masks = caller.getCaseData()
        zipped = zip(gt_masks, pred_masks)

        for selectedRow in selectedRows:
          gt_mask, pred_mask = zipped[selectedRow]
          self.showSegmentation(gt_mask)
          self.showSegmentation(pred_mask)

    self._onQuantificationRowChanged = lambda sel: onQuantificationRowChanged(caller, sel)

    self.fourUpTableView.selectionModel().selectionChanged.connect(self._onQuantificationRowChanged)
    self.fourUpTableView.selectAll()

    onQuantificationRowChanged(caller)

    threeDWidget = slicer.app.layoutManager().threeDWidget(0)
    threeDView = threeDWidget.threeDView()
    threeDView.resetFocalPoint()

  def createSegmentsComparison(self, gt_ma, pred_ma, table):
    for rowIdx, (gt_seg, pred_seg) in enumerate(zip(gt_ma, pred_ma)):
      # NB: assuming that every imported mask has only one segment
      segmentComparisonNode = self._compareSegments(gt_seg, pred_seg, gt_seg, pred_seg)

      rowIdx = table.AddEmptyRow()
      table.SetCellText(rowIdx, 0, "{}/{}".format(gt_seg.GetName(), pred_seg.GetName()))

      if segmentComparisonNode:
        for colIdx, getter in enumerate(self.COMPARISON_NAMES_GETTERS.values(), start=1):
          table.SetCellText(rowIdx, colIdx, str(getattr(segmentComparisonNode, getter)()))
      slicer.mrmlScene.RemoveNode(segmentComparisonNode)

  def _compareSegments(self, gt_seg_node, pred_seg_node, gt_seg, pred_seg):
    try:
      gt_seg_id = CsvInferenceIteratorLogic.getAllSegmentIDs(gt_seg)[-1]
      pred_seg_id = CsvInferenceIteratorLogic.getAllSegmentIDs(pred_seg)[-1]
    except IndexError:
      return None
    segmentComparisonNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLSegmentComparisonNode', 'Inference')
    segmentComparisonNode.SetAndObserveReferenceSegmentationNode(gt_seg_node)
    segmentComparisonNode.SetReferenceSegmentID(gt_seg_id)
    segmentComparisonNode.SetAndObserveCompareSegmentationNode(pred_seg_node)
    segmentComparisonNode.SetCompareSegmentID(pred_seg_id)
    segmentComparisonLogic = slicer.modules.segmentcomparison.logic()
    segmentComparisonLogic.ComputeHausdorffDistances(segmentComparisonNode)
    segmentComparisonLogic.ComputeDiceStatistics(segmentComparisonNode)
    return segmentComparisonNode

  def onCaseAboutToClose(self, caller, *args, **kwargs):
    if self._onQuantificationRowChanged is not None:
      self.fourUpTableView.selectionModel().selectionChanged.disconnect(self._onQuantificationRowChanged)
