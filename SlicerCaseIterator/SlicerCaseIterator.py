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

import logging

import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *

from SlicerCaseIteratorLib import IteratorBase, CsvTableIterator, DicomTableIterator


# ------------------------------------------------------------------------------
# SlicerCaseIterator
# ------------------------------------------------------------------------------
class SlicerCaseIterator(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = 'Case Iterator'
    self.parent.categories = ['Utilities']
    self.parent.dependencies = []
    self.parent.contributors = ["Joost van Griethuysen (AVL-NKI)"]
    self.parent.helpText = """
    This is a scripted loadable module to iterate over a batch of images (with/without prior segmentations) for segmentation or review.
    """
    self.parent.acknowledgementText = "This work is covered by the 3-clause BSD License. No funding was received for this work."


# ------------------------------------------------------------------------------
# SlicerCaseIteratorWidget
# ------------------------------------------------------------------------------
class SlicerCaseIteratorWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __del__(self):
    self.logger.debug('Destroying Slicer Case Iterator Widget')
    self.logic = None
    self.inputWidgets = None
    self.currentInput = None
    self._disconnectHandlers()

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Setup a logger for the extension log messages
    self.logger = logging.getLogger('SlicerCaseIterator')

    self.logic = None

    # These variables hold connections to other parts of Slicer, such as registered keyboard shortcuts and
    # Event observers
    self.shortcuts = []
    self.observers = []

    # Instantiate and connect widgets ...

    #
    # Select and Load input data section
    #

    self.inputDataCollapsibleButton = ctk.ctkCollapsibleButton()
    self.inputDataCollapsibleButton.text = 'Select and Load case data'
    self.layout.addWidget(self.inputDataCollapsibleButton)

    inputDataFormLayout = qt.QFormLayout(self.inputDataCollapsibleButton)

    self.inputSelector = qt.QComboBox()
    self.inputSelector.addItems(['Local File Table', 'DICOM Table'])
    self.inputSelector.toolTip = 'Select method for defining the batch'
    inputDataFormLayout.addRow('Iterator Type', self.inputSelector)

    self.inputWidgets = [
      CsvTableIterator.CaseTableIteratorWidget(),
      DicomTableIterator.DicomTableIteratorWidget()
    ]

    for idx, inputwidget in enumerate(self.inputWidgets):
      widget_layout = inputwidget.setup()
      inputwidget.validationHandler = self.onValidateInput
      if idx > 0:  # Only show the first widget (currently selected)
        widget_layout.visible = False
      inputDataFormLayout.addRow(widget_layout)
    self.currentInput = self.inputWidgets[0]

    #
    # Parameters Area
    #
    self.parametersCollapsibleButton = ctk.ctkCollapsibleButton()
    self.parametersCollapsibleButton.text = 'Parameters'
    self.layout.addWidget(self.parametersCollapsibleButton)

    # Layout within the dummy collapsible button
    parametersFormLayout = qt.QFormLayout(self.parametersCollapsibleButton)

    #
    # Start position
    #
    self.npStart = qt.QSpinBox()
    self.npStart.minimum = 1
    self.npStart.maximum = 999999
    self.npStart.value = 1
    self.npStart.toolTip = 'Start position in the CSV file (1 = first patient)'
    parametersFormLayout.addRow('Start position', self.npStart)

    #
    # Reader Name
    #
    self.txtReaderName = qt.QLineEdit()
    self.txtReaderName.text = ''
    self.txtReaderName.toolTip = 'Name of the current reader; if not empty, this name will be added to the filename ' \
                                 'of saved masks'
    parametersFormLayout.addRow('Reader name', self.txtReaderName)

    #
    # Auto-redirect to SegmentEditor
    #

    self.chkAutoRedirect = qt.QCheckBox()
    self.chkAutoRedirect.checked = 1
    self.chkAutoRedirect.toolTip = 'Automatically switch module to "SegmentEditor" when each case is loaded'
    parametersFormLayout.addRow('Go to Segment Editor', self.chkAutoRedirect)

    #
    # Save masks
    #
    self.chkSaveMasks = qt.QCheckBox()
    self.chkSaveMasks.checked = 0
    self.chkSaveMasks.toolTip = 'save all initially loaded masks when proceeding to next case'
    parametersFormLayout.addRow('Save loaded masks', self.chkSaveMasks)

    #
    # Save masks
    #
    self.chkSaveNewMasks = qt.QCheckBox()
    self.chkSaveNewMasks.checked = 1
    self.chkSaveNewMasks.toolTip = 'save all newly generated masks when proceeding to next case'
    parametersFormLayout.addRow('Save new masks', self.chkSaveNewMasks)

    #
    # Previous Case
    #

    self.previousButton = qt.QPushButton('Previous Case')
    self.previousButton.enabled = False
    self.previousButton.toolTip = '(Ctrl+P) Press this button to go to the previous case, previous new masks are not reloaded'
    self.layout.addWidget(self.previousButton)

    #
    # Load CSV / Next Case
    #
    self.nextButton = qt.QPushButton('Next Case')
    self.nextButton.enabled = False
    self.nextButton.toolTip = '(Ctrl+N) Press this button to go to the next case'
    self.layout.addWidget(self.nextButton)

    #
    # Reset
    #
    self.resetButton = qt.QPushButton('Start Batch')
    self.resetButton.enabled = False
    self.layout.addWidget(self.resetButton)

    self.layout.addStretch(1)

    #
    # Connect buttons to functions
    #

    self.inputSelector.connect('currentIndexChanged(int)', self.onChangeInput)
    self.previousButton.connect('clicked(bool)', self.onPrevious)
    self.nextButton.connect('clicked(bool)', self.onNext)
    self.resetButton.connect('clicked(bool)', self.onReset)

    self._setGUIstate(csv_loaded=False)

  # ------------------------------------------------------------------------------
  def enter(self):
    if hasattr(self, 'currentInput'):
      self.currentInput.enter()

  def onChangeInput(self):
    self.currentInput.layout.visible = False
    self.currentInput = self.inputWidgets[self.inputSelector.currentIndex]
    self.currentInput.layout.visible = True

  # ------------------------------------------------------------------------------
  def onValidateInput(self, is_valid):
    self.resetButton.enabled = is_valid

  # ------------------------------------------------------------------------------
  def onReset(self):
    if self.logic is None:
      # Start the batch!
      # Lock GUI during loading
      self._unlockGUI(False)

      try:
        reader = self.txtReaderName.text
        if reader == '':
          reader = None
        iterator = self.currentInput.startBatch()
        self.logic = SlicerCaseIteratorLogic(iterator,
                                             self.npStart.value,
                                             self.chkAutoRedirect.checked == 1,
                                             reader,
                                             saveNew=(self.chkSaveNewMasks.checked == 1),
                                             saveLoaded=(self.chkSaveMasks.checked == 1))
        self._setGUIstate()
      except Exception as e:
        self.logger.error('Error loading batch! %s', e.message)
        self.logger.debug('', exc_info=True)
        self._setGUIstate(csv_loaded=False)

    else:
      # End the batch and clean up
      self.currentInput.cleanupBatch()
      self.logic = None
      self._setGUIstate(csv_loaded=False)

  #------------------------------------------------------------------------------
  def onPrevious(self):
    # Lock GUI during loading
    self._unlockGUI(False)

    self.logic.previousCase()

    # Unlock GUI
    self._unlockGUI(True)

  #------------------------------------------------------------------------------
  def onNext(self):
    # Lock GUI during loading
    self._unlockGUI(False)

    if self.logic.nextCase():
      # Last case processed, reset GUI
      self.onReset()

    # Unlock GUI
    self._unlockGUI(True)

  #------------------------------------------------------------------------------
  def onEndClose(self, caller, event):
    # Pass event on to the input widget (enables restoring batch related nodes to
    # the new scene)
    if hasattr(self, 'currentInput'):
      self.currentInput.onEndClose()

    if self.logic is not None and self.logic.currentCase is not None:
      self.logic.currentCase = None
      self.logger.info('case closed')

  # ------------------------------------------------------------------------------
  def _unlockGUI(self, unlocked):
    self.previousButton.enabled = unlocked
    self.nextButton.enabled = unlocked
    self.resetButton.enabled = unlocked
    if unlocked:
      self.nextButton.text = 'Next Case'
    else:
      self.nextButton.text = 'Loading...'

  # ------------------------------------------------------------------------------
  def _setGUIstate(self, csv_loaded=True):
    if csv_loaded:
      self.resetButton.enabled = True
      self.resetButton.text = 'Reset'

      self._connectHandlers()
    else:
      # reset Button is locked when loading cases, ensure it is unlocked to load new batch
      self.resetButton.enabled = self.currentInput.is_valid()
      self.resetButton.text = 'Start Batch'

      self._disconnectHandlers()

    self.previousButton.enabled = csv_loaded
    self.nextButton.enabled = csv_loaded

    self.inputSelector.enabled = not csv_loaded
    self.currentInput.layout.enabled = not csv_loaded

  # ------------------------------------------------------------------------------
  def _connectHandlers(self):
    # Connect the CTRL + N and CTRL + P Shortcut
    if len(self.shortcuts) == 0:
      shortcutNext = qt.QShortcut(slicer.util.mainWindow())
      shortcutNext.setKey(qt.QKeySequence('Ctrl+N'))

      shortcutNext.connect('activated()', self.onNext)
      self.shortcuts.append(shortcutNext)

      shortcutPrevious = qt.QShortcut(slicer.util.mainWindow())
      shortcutPrevious.setKey(qt.QKeySequence('Ctrl+P'))

      shortcutPrevious.connect('activated()', self.onPrevious)
      self.shortcuts.append(shortcutPrevious)
    else:
      self.logger.warning('Shortcuts already initialized!')

    # Add an observer for the "MRML Scene End Close Event"
    if len(self.observers) == 0:
      self.observers.append(slicer.mrmlScene.AddObserver(slicer.mrmlScene.EndCloseEvent, self.onEndClose))
    else:
      self.logger.warning('Event observer already initialized!')

  # ------------------------------------------------------------------------------
  def _disconnectHandlers(self):
    # Remove the keyboard shortcut
    for sc in self.shortcuts:
      sc.disconnect('activated()')
      sc.setParent(None)
    self.shortcuts = []

    # Remove the event observer
    for obs in self.observers:
      slicer.mrmlScene.RemoveObserver(obs)
    self.observers = []


# ------------------------------------------------------------------------------
# SlicerCaseIteratorLogic
# ------------------------------------------------------------------------------
class SlicerCaseIteratorLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, iterator, start, redirect, reader=None, saveNew=False, saveLoaded=False):

    self.logger = logging.getLogger('SlicerCaseIterator.logic')

    # Iterator class defining the iterable to iterate over cases
    assert isinstance(iterator, IteratorBase.IteratorLogicBase)
    self.iterator = iterator
    assert self.iterator.caseCount >= start, 'No cases to process (%d cases, start %d)' % (self.caseCount, start)
    self.currentIdx = start - 1  # Current case index (starts at 0 for fist case, -1 means nothing loaded)

    # Some variables that control the output (formatting and control of discarding/saving
    self.reader = reader
    self.saveNew = saveNew
    self.saveLoaded = saveLoaded

    # Variables to hold references to loaded image and mask nodes
    self.currentCase = None

    self.redirect = redirect
    self._loadCase()

  def __del__(self):
    # Free up the references to the nodes to allow GC and prevent memory leaks
    self.logger.debug('Destroying Case Iterator Logic instance')
    self.currentCase = None
    self.iterator = None

  # ------------------------------------------------------------------------------
  def nextCase(self):
    self.currentIdx += 1
    return self._loadCase()

  def previousCase(self):
    self.currentIdx -= 1
    return self._loadCase()

  def _loadCase(self):
    """
    This function proceeds to the next case. If a current case is open, it is saved if necessary and then closed.
    Next, a new case is obtained from the iterator, which is then loaded as the new ``currentCase``.
    If the last case was loaded, the iterator exits and resets the GUI to allow for loading a new batch of cases.
    :return: Boolean indicating whether the end of the batch is reached
    """
    if self.currentIdx < 0:
      self.currentIdx = 0
      # Cannot select a negative index, so give a warning and exit the function
      self.logger.warning('First case selected, cannot select previous case!')
      return False

    if self.currentCase is not None:
      self._closeCase()

    if self.currentIdx >= self.iterator.caseCount:
      self.logger.info('########## All Done! ##########')
      return True

    try:
      self.currentCase = self.iterator.loadCase(self.currentIdx)
      im, ma, add_im, add_ma = self.currentCase

      # Set the slice viewers to the correct volumes
      red_logic = slicer.app.layoutManager().sliceWidget('Red').sliceLogic().GetSliceCompositeNode()
      green_logic = slicer.app.layoutManager().sliceWidget('Green').sliceLogic().GetSliceCompositeNode()
      yellow_logic = slicer.app.layoutManager().sliceWidget('Yellow').sliceLogic().GetSliceCompositeNode()

      red_logic.SetBackgroundVolumeID(im.GetID())
      green_logic.SetBackgroundVolumeID(im.GetID())
      yellow_logic.SetBackgroundVolumeID(im.GetID())

      if len(add_im) > 0:
        red_logic.SetForegroundVolumeID(add_im[0].GetID())
        green_logic.SetForegroundVolumeID(add_im[0].GetID())
        yellow_logic.SetForegroundVolumeID(add_im[0].GetID())

      # Snap the viewers to the slice plane of the main image
      self._rotateToVolumePlanes(im)

      if self.redirect:
        if slicer.util.selectedModule() != 'SegmentEditor':
          slicer.util.selectModule('SegmentEditor')
        else:
          slicer.modules.SegmentEditorWidget.enter()

        # Explictly set the segmentation and master volume nodes
        segmentEditorWidget = slicer.modules.segmenteditor.widgetRepresentation().self().editor
        if ma is not None:
          segmentEditorWidget.setSegmentationNode(ma)
        segmentEditorWidget.setMasterVolumeNode(im)

    except Exception as e:
      self.logger.warning("Error loading new case: %s", e.message)
      self.logger.debug('', exc_info=True)
    return False

  def _closeCase(self):
    _, mask, _, additionalMasks = self.currentCase
    if self.saveLoaded:
      if mask is not None:
        self.iterator.saveMask(mask, self.reader)
      for ma in additionalMasks:
        self.iterator.saveMask(ma, self.reader)
    if self.saveNew:
      nodes = [n for n in slicer.util.getNodesByClass('vtkMRMLSegmentationNode')
               if n not in additionalMasks and n != mask]
      for n in nodes:
        self.iterator.saveMask(n, self.reader)

    # Remove reference to current case, signalling it is closed
    self.currentCase = None

    # Close the scene and start a fresh one
    slicer.mrmlScene.Clear(0)

    if slicer.util.selectedModule() == 'SegmentEditor':
      slicer.modules.SegmentEditorWidget.exit()

    node = slicer.vtkMRMLViewNode()
    slicer.mrmlScene.AddNode(node)

  # ------------------------------------------------------------------------------
  def _rotateToVolumePlanes(self, referenceVolume):
    sliceNodes = slicer.util.getNodes('vtkMRMLSliceNode*')
    for name, node in sliceNodes.items():
      node.RotateToVolumePlane(referenceVolume)
    # Snap to IJK to try and avoid rounding errors
    sliceLogics = slicer.app.layoutManager().mrmlSliceLogics()
    numLogics = sliceLogics.GetNumberOfItems()
    for n in range(numLogics):
      l = sliceLogics.GetItemAsObject(n)
      l.SnapSliceOffsetToIJK()
