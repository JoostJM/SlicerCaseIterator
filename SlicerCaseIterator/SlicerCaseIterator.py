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

import qt, ctk, slicer
from collections import deque
from slicer.ScriptedLoadableModule import *

from SlicerDevelopmentToolboxUtils.buttons import *
from SlicerDevelopmentToolboxUtils.mixins import ModuleWidgetMixin

from SlicerCaseIteratorLib import IteratorBase, CsvTableIterator
from SlicerCaseIteratorLib.IteratorFactory import IteratorFactory


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
    self.parent.dependencies = ["SlicerDevelopmentToolbox", "SegmentComparison"]
    self.parent.contributors = ["Joost van Griethuysen (AVL-NKI), Christian Herz (CHOP)"]
    self.parent.helpText = """
    This is a scripted loadable module to iterate over a batch of images (with/without prior segmentations) for 
    segmentation or review.
    """
    self.parent.acknowledgementText = """
    This work is covered by the 3-clause BSD License. No funding was received for this work.
    """


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

  def onReload(self):
    if hasattr(self, 'inputWidget'):
      self.inputWidget = None

    IteratorFactory.reloadSourceFiles()
    ScriptedLoadableModuleWidget.onReload(self)

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    self.setupViewSettingsArea()

    # Setup a logger for the extension log messages
    self.logger = logging.getLogger('SlicerCaseIterator')

    self.logic = None

    # These variables hold connections to other parts of Slicer, such as registered keyboard shortcuts and
    # Event observers
    self.shortcuts = []
    self.observers = []

    # Instantiate and connect widgets ...

    #
    # ComboBox for mode selection
    #
    self.modeGroup = qt.QGroupBox("Mode Selection")
    self.modeGroup.setLayout(qt.QFormLayout())
    self.layout.addWidget(self.modeGroup)

    modes = IteratorFactory.getImplementationNames()
    self.modeComboBox = qt.QComboBox()
    self.modeComboBox.addItems([""] + modes)
    self.modeGroup.layout().addWidget(self.modeComboBox)

    #
    # Select and Load input data section
    #
    self.inputDataCollapsibleButton = ctk.ctkCollapsibleButton()
    self.inputDataCollapsibleButton.text = 'Select and Load case data'
    self.layout.addWidget(self.inputDataCollapsibleButton)

    #
    # Parameters Area
    #
    self.parametersCollapsibleButton = ctk.ctkCollapsibleButton()
    self.parametersCollapsibleButton.text = 'Case iteration parameters'
    self.layout.addWidget(self.parametersCollapsibleButton)

    # Layout within the dummy collapsible button
    parametersFormLayout = qt.QFormLayout(self.parametersCollapsibleButton)

    #
    # Reader Name
    #
    self.txtReaderName = qt.QLineEdit()
    self.txtReaderName.text = ''
    self.txtReaderName.toolTip = 'Name of the current reader; if not empty, this name will be added to the filename ' \
                                 'of saved masks'
    parametersFormLayout.addRow('Reader name', self.txtReaderName)

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
    # Visualization Properties
    #
    self.visualizationPropertiesCollapsibleButton = ctk.ctkCollapsibleButton()
    self.visualizationPropertiesCollapsibleButton.text = 'Visualization properties'
    self.layout.addWidget(self.visualizationPropertiesCollapsibleButton)

    visualizationPropertiesFormLayout = qt.QVBoxLayout(self.visualizationPropertiesCollapsibleButton)

    #
    # Mask Groupbox
    #
    self.maskGroup = qt.QGroupBox("Mask")
    self.maskGroup.setLayout(qt.QFormLayout())
    visualizationPropertiesFormLayout.addWidget(self.maskGroup)

    self.sliceFill2DSlider = slicer.qMRMLSliderWidget()
    self.sliceFill2DSlider.minimum = 0.0
    self.sliceFill2DSlider.maximum = 1.0
    self.sliceFill2DSlider.singleStep = 0.1
    self.maskGroup.layout().addRow("Slice 2D fill:", self.sliceFill2DSlider)

    self.sliceOutline2DSlider = slicer.qMRMLSliderWidget()
    self.sliceOutline2DSlider.minimum = 0.0
    self.sliceOutline2DSlider.maximum = 1.0
    self.sliceOutline2DSlider.singleStep = 0.1
    self.sliceOutline2DSlider.value = 1.0
    self.maskGroup.layout().addRow("Slice 2D outline:", self.sliceOutline2DSlider)

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

    #
    # Collapsible Button group for enabling only one at a time
    #
    self.collapsibleButtonGroup = qt.QButtonGroup()
    self.collapsibleButtonGroup.setExclusive(True)
    self.collapsibleButtonGroup.addButton(self.inputDataCollapsibleButton)
    self.collapsibleButtonGroup.addButton(self.parametersCollapsibleButton)
    self.collapsibleButtonGroup.addButton(self.visualizationPropertiesCollapsibleButton)

    self.layout.addStretch(1)

    #
    # Connect buttons to functions
    #
    self.modeComboBox.currentTextChanged.connect(self.onModeSelected)
    self.previousButton.connect('clicked(bool)', self.onPrevious)
    self.nextButton.connect('clicked(bool)', self.onNext)
    self.resetButton.connect('clicked(bool)', self.onReset)
    self.sliceFill2DSlider.valueChanged.connect(self.updateSegmentationProperties)
    self.sliceOutline2DSlider.valueChanged.connect(self.updateSegmentationProperties)

    if len(modes) == 1:
      self.modeComboBox.hide()
      self.onModeSelected(modes[1])

    self._setGUIstate(csv_loaded=False)

  def setupViewSettingsArea(self):
    self.fourUpSliceLayoutButton = FourUpLayoutButton()
    self.fourUpSliceTableViewLayoutButton = FourUpTableViewLayoutButton()
    self.crosshairButton = CrosshairButton()
    self.crosshairButton.setSliceIntersectionEnabled(True)

    hbox = ModuleWidgetMixin.createHLayout([self.fourUpSliceLayoutButton,
                                            self.fourUpSliceTableViewLayoutButton, self.crosshairButton])
    self.layout.addWidget(hbox)

  # ------------------------------------------------------------------------------
  def enter(self):
    if hasattr(self, 'inputWidget'):
      self.inputWidget.enter()

  # ------------------------------------------------------------------------------
  def onModeSelected(self, mode):
    # Setup the widget for CSV table input
    self.inputWidget = IteratorFactory.getIteratorWidget(mode)()
    self.inputWidget.validationHandler = self.onValidateInput

    inputDataFormLayout = qt.QFormLayout(self.inputDataCollapsibleButton)
    self.inputParametersGroupBox = self.inputWidget.setup()
    inputDataFormLayout.addRow(self.inputParametersGroupBox)

    self.modeGroup.hide()
    self.inputDataCollapsibleButton.click()

  # ------------------------------------------------------------------------------
  def onValidateInput(self, is_valid):
    self.resetButton.enabled = is_valid

  # ------------------------------------------------------------------------------
  def updateSegmentationProperties(self, value=None):
    def update(segNode):
      try:
        segNode.GetDisplayNode().SetOpacity2DFill(self.sliceFill2DSlider.value)
        segNode.GetDisplayNode().SetOpacity2DOutline(self.sliceOutline2DSlider.value)
      except AttributeError:
        pass

    deque(map(update, slicer.util.getNodesByClass("vtkMRMLSegmentationNode")))

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
        iterator = self.inputWidget.startBatch(reader)
        self.logic = SlicerCaseIteratorLogic(iterator,
                                             self.npStart.value)
        self.logic.start()
        self.updateSegmentationProperties()
        self._setGUIstate()
        self._unlockGUI(True)
      except Exception as e:
        if slicer.app.majorVersion * 100 + slicer.app.minorVersion < 411:
          e = e.message
        self.logger.error('Error loading batch! %s', e)
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
      self.resetButton.enabled = hasattr(self, 'inputWidget') and self.inputWidget.is_valid()
      self.resetButton.text = 'Start Batch'

      self._disconnectHandlers()

    self.progressBar.visible = csv_loaded
    self.previousButton.enabled = csv_loaded
    self.nextButton.enabled = csv_loaded

    if hasattr(self, 'inputParametersGroupBox'):
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
  """This class should implement all the actual computation done by your module. The interface
  should be such that other python code can import this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, iterator, start):
    ScriptedLoadableModuleLogic.__init__(self)

    self.logger = logging.getLogger('SlicerCaseIterator.logic')

    # Iterator class defining the iterable to iterate over cases
    assert isinstance(iterator, IteratorBase.IteratorLogicBase)
    self.iterator = iterator
    assert self.iterator.caseCount >= start, 'No cases to process (%d cases, start %d)' % (self.iterator.caseCount,
                                                                                           start)
    self.currentIdx = start - 1  # Current case index (starts at 0 for fist case, -1 means nothing loaded)

  def __del__(self):
    # Free up the references to the nodes to allow GC and prevent memory leaks
    self.logger.debug('Destroying Case Iterator Logic instance')
    self.iterator = None

  def start(self):
    self._loadCase()

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

    if self.iterator.currentIdx is not None:
      self._closeCase()

    if self.currentIdx >= self.iterator.caseCount:
      self.logger.info('########## All Done! ##########')
      return True

    self.iterator.loadCase(self.currentIdx)

    return False

  def _closeCase(self):
    self.iterator.closeCase()
