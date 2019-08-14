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

import os
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *

from SlicerCaseIteratorLib import IteratorBase, CsvTableIterator


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
    self.inputWidget = None
    self._disconnectHandlers()

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Setup a logger for the extension log messages
    self.logger = logging.getLogger('SlicerCaseIterator')

    # Setup the widget for CSV table input
    self.inputWidget = CsvTableIterator.CaseTableIteratorWidget()
    self.inputWidget.validationHandler = self.onValidateInput

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

    self.inputParametersGroupBox = self.inputWidget.setup()
    inputDataFormLayout.addRow(self.inputParametersGroupBox)

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
    self.chkAutoRedirect.checked = False
    self.chkAutoRedirect.toolTip = 'Automatically switch module to "SegmentEditor" when each case is loaded'
    parametersFormLayout.addRow('Go to Segment Editor', self.chkAutoRedirect)

    #
    # Save masks
    #
    self.chkSaveMasks = qt.QCheckBox()
    self.chkSaveMasks.checked = False
    self.chkSaveMasks.toolTip = 'save all initially loaded masks when proceeding to next case'
    parametersFormLayout.addRow('Save loaded masks', self.chkSaveMasks)

    #
    # Save masks
    #
    self.chkSaveNewMasks = qt.QCheckBox()
    self.chkSaveNewMasks.checked = True
    self.chkSaveNewMasks.toolTip = 'save all newly generated masks when proceeding to next case'
    parametersFormLayout.addRow('Save new masks', self.chkSaveNewMasks)

    self.maskPropertiesCollapsibleButton = ctk.ctkCollapsibleButton()
    self.maskPropertiesCollapsibleButton.text = 'Mask properties'
    self.layout.addWidget(self.maskPropertiesCollapsibleButton)

    maskPropertiesFormLayout = qt.QFormLayout(self.maskPropertiesCollapsibleButton)

    self.sliceFill2DSlider = slicer.qMRMLSliderWidget()
    self.sliceFill2DSlider.minimum = 0.0
    self.sliceFill2DSlider.maximum = 1.0
    self.sliceFill2DSlider.singleStep = 0.1

    maskPropertiesFormLayout.addRow("Slice 2D fill:", self.sliceFill2DSlider)

    self.sliceOutline2DSlider = slicer.qMRMLSliderWidget()
    self.sliceOutline2DSlider.minimum = 0.0
    self.sliceOutline2DSlider.maximum = 1.0
    self.sliceOutline2DSlider.singleStep = 0.1
    self.sliceOutline2DSlider.value = 1.0

    maskPropertiesFormLayout.addRow("Slice 2D outline:", self.sliceOutline2DSlider)

    #
    # Progressbar
    #
    self.progressBar = qt.QProgressBar()
    self.progressBar.setFormat("%v/%m")
    self.progressBar.visible = False
    self.layout.addWidget(self.progressBar)

    #
    # Case Button Row
    #
    self.caseButtonWidget = qt.QWidget()
    self.caseButtonWidget.setLayout(qt.QHBoxLayout())
    self.layout.addWidget(self.caseButtonWidget)

    #
    # Reset
    #
    self.resetButton = qt.QPushButton('Start Batch')
    self.resetButton.enabled = False
    self.caseButtonWidget.layout().addWidget(self.resetButton)

    #
    # Previous Case
    #
    self.previousButton = qt.QPushButton('Previous Case')
    self.previousButton.enabled = False
    self.previousButton.toolTip = '(Ctrl+P) Press this button to go to the previous case, previous new masks are not reloaded'
    self.caseButtonWidget.layout().addWidget(self.previousButton)

    #
    # Load CSV / Next Case
    #
    self.nextButton = qt.QPushButton('Next Case')
    self.nextButton.enabled = False
    self.nextButton.toolTip = '(Ctrl+N) Press this button to go to the next case'
    self.caseButtonWidget.layout().addWidget(self.nextButton)

    self.layout.addStretch(1)

    #
    # Connect buttons to functions
    #

    self.previousButton.connect('clicked(bool)', self.onPrevious)
    self.nextButton.connect('clicked(bool)', self.onNext)
    self.resetButton.connect('clicked(bool)', self.onReset)
    self.sliceFill2DSlider.valueChanged.connect(lambda value: self.updateSegmentationProperties())
    self.sliceOutline2DSlider.valueChanged.connect(lambda value: self.updateSegmentationProperties())

    self._setGUIstate(csv_loaded=False)

  # ------------------------------------------------------------------------------
  def enter(self):
    if hasattr(self, 'inputWidget'):
      self.inputWidget.enter()

  # ------------------------------------------------------------------------------
  def onValidateInput(self, is_valid):
    self.resetButton.enabled = is_valid

  # ------------------------------------------------------------------------------
  def updateSegmentationProperties(self):
    def update(segNode):
      try:
        segNode.GetDisplayNode().SetOpacity2DFill(self.sliceFill2DSlider.value)
        segNode.GetDisplayNode().SetOpacity2DOutline(self.sliceOutline2DSlider.value)
      except AttributeError:
        pass

    map(update, slicer.util.getNodesByClass("vtkMRMLSegmentationNode"))

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
        iterator = self.inputWidget.startBatch()
        self.logic = SlicerCaseIteratorLogic(iterator,
                                             self.npStart.value,
                                             self.chkAutoRedirect.checked,
                                             reader,
                                             saveNew=self.chkSaveNewMasks.checked,
                                             saveLoaded=self.chkSaveMasks.checked)
        self.updateSegmentationProperties()
        self._setGUIstate()
        self._unlockGUI(True)
      except Exception as e:
        self.logger.error('Error loading batch! %s', e.message)
        self.logger.debug('', exc_info=True)
        self._setGUIstate(csv_loaded=False)

    else:
      # End the batch and clean up
      self.inputWidget.cleanupBatch()
      self.logic = None
      self._setGUIstate(csv_loaded=False)

  #------------------------------------------------------------------------------
  def onPrevious(self):
    # Lock GUI during loading
    self._unlockGUI(False)

    self.logic.previousCase()
    self.progressBar.value = self.logic.currentIdx+1
    self.updateSegmentationProperties()

    # Unlock GUI
    self._unlockGUI(True)

  #------------------------------------------------------------------------------
  def onNext(self):
    # Lock GUI during loading
    self._unlockGUI(False)

    if self.logic.nextCase():
      # Last case processed, reset GUI
      self.onReset()
    else:
      self.progressBar.value = self.logic.currentIdx+1
      self.updateSegmentationProperties()

    # Unlock GUI
    self._unlockGUI(True)

  #------------------------------------------------------------------------------
  def onEndClose(self, caller, event):
    # Pass event on to the input widget (enables restoring batch related nodes to
    # the new scene)
    self.inputWidget.onEndClose()

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

      self.progressBar.value = 1
      self.progressBar.maximum = self.logic.iterator.caseCount
      self._connectHandlers()
    else:
      # reset Button is locked when loading cases, ensure it is unlocked to load new batch
      self.resetButton.enabled = self.inputWidget.is_valid()
      self.resetButton.text = 'Start Batch'

      self._disconnectHandlers()

    self.progressBar.visible = csv_loaded
    self.previousButton.enabled = csv_loaded
    self.nextButton.enabled = csv_loaded

    self.inputParametersGroupBox.enabled = not csv_loaded

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
    ScriptedLoadableModuleLogic.__init__(self)

    self.logger = logging.getLogger('SlicerCaseIterator.logic')

    # Iterator class defining the iterable to iterate over cases
    assert isinstance(iterator, IteratorBase.IteratorLogicBase)
    self.iterator = iterator
    assert self.iterator.caseCount >= start, 'No cases to process (%d cases, start %d)' % (self.iterator.caseCount,
                                                                                           start)
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
    if self.currentCase is not None:
      self._closeCase()
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
      for sliceWidgetName in ['Red', 'Green', 'Yellow']:
        logic = slicer.app.layoutManager().sliceWidget(sliceWidgetName).sliceLogic().GetSliceCompositeNode()
        logic.SetBackgroundVolumeID(im.GetID())
        if len(add_im) > 0:
          logic.SetForegroundVolumeID(add_im[0].GetID())

      # Snap the viewers to the slice plane of the main image
      self._rotateToVolumePlanes(im)

      if self.redirect:
        if slicer.util.selectedModule() != 'SegmentEditor':
          slicer.util.selectModule('SegmentEditor')
        else:
          slicer.modules.SegmentEditorWidget.enter()

        # Explicitly set the segmentation and master volume nodes
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
