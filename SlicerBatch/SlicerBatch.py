#!/usr/bin/env python

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

import csv
from collections import OrderedDict
import logging
import os

import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *


#
# SlicerBatch
#

class SlicerBatch(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = 'SlicerBatch'
    self.parent.categories = ['Informatics']
    self.parent.dependencies = []
    self.parent.contributors = ["Joost van Griethuysen (AVL-NKI)"]
    self.parent.helpText = """
    This is a scripted loadable module to process a batch of images for segmentation.
    """
    self.parent.acknowledgementText = ""


#
# SlicerBatchWidget
#

class SlicerBatchWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  # New feature: load the input as a table and show in in de module panel
  # tableNode = slicer.vtkMRMLTableNode()
  # slicer.mrmlScene.AddNode(tableNode)

  # tableView=slicer.qMRMLTableView()
  # tableView.setMRMLTableNode(tableNode)
  # tableView.show()

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Setup a logger for the extension log messages
    self.logger = logging.getLogger('slicerBatch')

    # Instantiate some variables used during iteration
    self.csv_dir = None  # Directory containing the file specifying the cases, needed when using relative paths
    self.cases = None  # Holds the generator to iterate over all cases
    self.currentCase = None  # Represents the currently loaded case
    self.caseCount = 0
    self.currentIdx = -1

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

    #
    # Input CSV Path
    #
    self.inputPathSelector = ctk.ctkPathLineEdit()
    self.inputPathSelector.toolTip = 'Location of the CSV file containing the cases to process'
    inputDataFormLayout.addRow('input CSV path', self.inputPathSelector)

    self.loadBatchButton = qt.QPushButton('Load Input Data')
    self.loadBatchButton.enabled = False
    self.loadBatchButton.toolTip = 'Load the select file into the input Table'
    inputDataFormLayout.addRow(self.loadBatchButton)

    self.batchTableSelector = slicer.qMRMLNodeComboBox()
    self.batchTableSelector.nodeTypes = ['vtkMRMLTableNode']
    self.batchTableSelector.addEnabled = True
    self.batchTableSelector.selectNodeUponCreation = True
    self.batchTableSelector.renameEnabled = True
    self.batchTableSelector.removeEnabled = True
    self.batchTableSelector.noneEnabled = False
    self.batchTableSelector.setMRMLScene(slicer.mrmlScene)
    self.batchTableSelector.toolTip = 'Select the table representing the cases to process.'
    inputDataFormLayout.addRow(self.batchTableSelector)

    self.batchTableView = slicer.qMRMLTableView()
    inputDataFormLayout.addRow(self.batchTableView)
    self.batchTableView.show()

    #
    # Parameters Area
    #
    self.parametersCollapsibleButton = ctk.ctkCollapsibleButton()
    self.parametersCollapsibleButton.text = 'Parameters'
    self.layout.addWidget(self.parametersCollapsibleButton)

    # Layout within the dummy collapsible button
    parametersFormLayout = qt.QFormLayout(self.parametersCollapsibleButton)

    #
    # Input parameters GroupBox
    #

    self.inputParametersGroupBox = qt.QGroupBox('Input parameters')
    parametersFormLayout.addRow(self.inputParametersGroupBox)

    inputParametersFormLayout = qt.QFormLayout(self.inputParametersGroupBox)

    #
    # Start position
    #
    self.npStart = qt.QSpinBox()
    self.npStart.minimum = 1
    self.npStart.maximum = 999999
    self.npStart.value = 1
    self.npStart.toolTip = 'Start position in the CSV file (1 = first patient)'
    inputParametersFormLayout.addRow('start position', self.npStart)

    #
    # Root Path
    #
    self.rootSelector = qt.QLineEdit()
    self.rootSelector.text = 'path'
    self.rootSelector.toolTip = 'Location of the root directory to load form, or the column name specifying said' \
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
    # Output parameters GroupBox
    #

    self.outputParametersGroupBox = qt.QGroupBox('Output')
    parametersFormLayout.addRow(self.outputParametersGroupBox)

    outputParametersFormLayout = qt.QFormLayout(self.outputParametersGroupBox)

    #
    # Reader Name
    #
    self.txtReaderName = qt.QLineEdit()
    self.txtReaderName.text = ''
    self.txtReaderName.toolTip = 'Name of the current reader; if not empty, this name will be added to the filename' \
                                 'of saved masks'
    outputParametersFormLayout.addRow('Reader name', self.txtReaderName)

    #
    # Auto-redirect to Editor
    #

    self.chkAutoRedirect = qt.QCheckBox()
    self.chkAutoRedirect.checked = 1
    self.chkAutoRedirect.toolTip = 'Automatically switch module to "Editor" when each case is loaded'
    outputParametersFormLayout.addRow('Go to editor', self.chkAutoRedirect)

    #
    # Save masks
    #
    self.chkSaveMasks = qt.QCheckBox()
    self.chkSaveMasks.checked = 0
    self.chkSaveMasks.toolTip = 'save all intially loaded masks when proceeding to next case'
    outputParametersFormLayout.addRow('Save loaded masks', self.chkSaveMasks)

    #
    # Save masks
    #
    self.chkSaveNewMasks = qt.QCheckBox()
    self.chkSaveNewMasks.checked = 1
    self.chkSaveNewMasks.toolTip = 'save all newly generated masks when proceeding to next case'
    outputParametersFormLayout.addRow('Save new masks', self.chkSaveNewMasks)

    #
    # Previous Case
    #

    self.previousButton = qt.QPushButton('Previous Case')
    self.previousButton.visible = False
    self.layout.addWidget(self.previousButton)

    #
    # Load CSV / Next Case
    #
    self.nextButton = qt.QPushButton('Next Case')
    self.nextButton.visible = False
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

    self.previousButton.connect('clicked(bool)', self.onPrevious)
    self.nextButton.connect('clicked(bool)', self.onNext)
    self.resetButton.connect('clicked(bool)', self.onReset)

    self._setGUIstate(csv_loaded=False)

  def cleanup(self):
    if self.cases is not None:
      self._setGUIstate(csv_loaded=False)  # Reset the GUI to ensure observers and shortcuts are removed
      self.currentCase = None
      self.cases = None
      self.currentIdx = -1

  def onReset(self):
    if self.cases is None:
      # Lock GUI during loading
      self.previousButton.enabled = False
      self.nextButton.enabled = False
      self.resetButton.enabled = False
      self.nextButton.text = 'Loading...'

      self.logger.info('Loading %s...' % self.inputPathSelector.currentPath)
      if self._loadBatch(self.inputPathSelector.currentPath, start=self.npStart.value):
        self.loadCase(0)  # Load the currently selected case
    else:
      self._setGUIstate(csv_loaded=False)
      self.currentCase = None
      self.cases = None
      self.currentIdx = -1

  def onPrevious(self):
    if self.cases is None:
      return

    self.loadCase(-1)

  def onNext(self):
    if self.cases is None:
      return

    self.loadCase(1)

  def onEndClose(self, caller, event):
    if self.currentCase is not None:
      self.currentCase = None
      self.logger.info('case closed')

  def loadCase(self, idx_change):
    """
    If a batch of cases is loaded, this function proceeds to the next case. If a current case is open, it is saved
    and closed. Next, a new case is obtained from the generator, which is then loaded as the new ``currentCase``.
    If the last case was loaded, the generator will raise an StopIteration exception, which is handled by this function
    and used to reset the GUI to allow for loading a new batch of cases.
    """
    if self.cases is None:
      return

    if self.currentIdx + idx_change < 0:
      # Cannot select a negative index, so give a warning and exit the function
      self.logger.warning('First case selected, cannot select previous case!')
      return

    # If a case is open, save it and close it before attempting to load a new case
    if self.currentCase is not None:
      self.currentCase.closeCase(save_loaded_masks=(self.chkSaveMasks.checked == 1),
                                 save_new_masks=(self.chkSaveNewMasks.checked == 1),
                                 reader_name=self.txtReaderName.text)

    # Attempt to load a new case. If the current case was the last one, a
    # StopIteration exception will be raised and handled, which resets the
    # GUI to allow loading another batch of cases

    self.currentIdx += idx_change
    if self.currentIdx >= self.caseCount:
      self._setGUIstate(csv_loaded=False)
      self.cases = None
      self.currentIdx = -1
      self.logger.info('########## All Done! ##########')
      return

    # Lock GUI during loading
    self.previousButton.enabled = False
    self.nextButton.enabled = False
    self.resetButton.enabled = False
    self.nextButton.text = 'Loading...'

    newCase = self.cases[self.currentIdx]

    patient = newCase.get('patient', None)
    if patient is None:
      self.logger.info('Loading next patient (%d/%d)...', self.currentIdx + 1, self.caseCount)
    else:
      self.logger.info('Loading next patient (%d/%d): %s...', self.currentIdx + 1, self.caseCount, patient)
    settings = {}
    settings['root'] = self.rootSelector.text
    settings['image'] = self.imageSelector.text
    settings['mask'] = self.maskSelector.text
    settings['addIms'] = [im.strip() for im in str(self.addImsSelector.text).split(',')]
    settings['addMas'] = [ma.strip() for ma in str(self.addMasksSelector.text).split(',')]
    settings['csv_dir'] = self.csv_dir
    settings['redirect'] = (self.chkAutoRedirect.checked == 1)

    self.currentCase = SlicerBatchLogic(newCase, **settings)

    # Unlock GUI
    self.previousButton.enabled = True
    self.nextButton.enabled = True
    self.resetButton.enabled = True
    self.nextButton.text = 'Next Case'

  def _loadBatch(self, csv_file, start=1):
    """
    This function reads the provided CSV file (after checking it exists) and returns a generator to iterate over
    the cases, starting at the specified start position. If cases are loaded successfully, but no cases are available
    to iterate over (less cases than specified start position), an empty generator will be returned. This is a valid
    generator, but will raise the StopIteration exception on the first call to ``next()``.

    :param csv_file: Path to the csv file containing the cases. If the file doesn't exist, an empty generator is
      returned.
    :param start: Position to start the iteration at. Start = 1 (default) starts iteration at first case.
    :return: True if successfully loaded some cases, False otherwise
    """
    if not os.path.isfile(csv_file):
      self.logger.warning('Your input does not exist. Try again...')
      return False

    # Load cases
    self.cases = []
    try:
      with open(csv_file) as open_csv_file:
        self.logger.info('Reading File')
        csv_reader = csv.DictReader(open_csv_file)
        for row in csv_reader:
          self.cases.append(row)
      self.csv_dir = os.path.dirname(csv_file)
      self.logger.info('file loaded, %d cases' % len(self.cases))
    except:
      self.logger.error('DOH!! something went wrong!', exc_info=True)
      self.cases = None
      return False

    # Return generator to iterate over all cases
    if len(self.cases) < start:
      self.logger.warning('No cases to process (%d cases, start %d)', len(self.cases), start)
      self.cases = None
      return False

    self._setGUIstate()
    self.caseCount = len(self.cases)
    self.currentIdx = start - 1
    print('starting at case %d' % start)
    return True

  def _setGUIstate(self, csv_loaded=True):
    if csv_loaded:
      self.resetButton.text = 'Reset'

      # Collapse input parameter sections
      self.inputDataCollapsibleButton.collapsed = True
      self.parametersCollapsibleButton.collapsed = True

      # Connect the CTRL + N Shortcut
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
    else:
      # reset Button is locked when loading cases, ensure it is unlocked to load new batch
      self.resetButton.enabled = True
      self.resetButton.text = 'Start Batch'

      # Remove the keyboard shortcut
      for sc in self.shortcuts:
        sc.disconnect('activated()')
        sc.setParent(None)
      self.shortcuts = []

      # Remove the event observer
      for obs in self.observers:
        slicer.mrmlScene.RemoveObserver(obs)
      self.observers = []

    self.previousButton.visible = csv_loaded
    self.nextButton.visible = csv_loaded

    self.inputPathSelector.enabled = not csv_loaded
    self.loadBatchButton.enabled = not csv_loaded
    self.batchTableSelector.enabled = not csv_loaded
    self.batchTableView.enabled = not csv_loaded
    self.inputParametersGroupBox.enabled = not csv_loaded


#
# SlicerBatchLogic
#

class SlicerBatchLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, newCase, **kwargs):
    self.logger = logging.getLogger('slicerbatch')

    self.case = newCase

    root = kwargs.get('root', None)
    csv_dir = kwargs.get('csv_dir', None)
    self.root = None
    if root is not None:  # Root is specified as a directory
      if os.path.isdir(root):
        self.root = root
      elif root in self.case:  # Root points to a column in csv file
        if os.path.isabs(self.case[root]):  # Absolute path, use as it is
          self.root = self.case[root]
        elif csv_dir is not None:  # If it is a relative path, assume it is relative to the csv file location
          self.root = os.path.join(csv_dir, self.case[root])

        if not os.path.isdir(self.root):
          self.root = None

    self.addIms = kwargs.get('addIms', [])
    self.addMas = kwargs.get('addMas', [])
    self.image = kwargs.get('image', None)
    self.mask = kwargs.get('mask', None)

    self.GenerateMasks = kwargs.get('GenerateMasks', True)
    self.GenerateAddMasks = kwargs.get('GenerateAddMasks', True)

    self.redirect = kwargs.get('redirect', True)

    self.image_nodes = OrderedDict()
    self.mask_nodes = OrderedDict()

    # Load images (returns True if loaded correctly) and check redirect:
    # if redirect = True, switch to Editor module or refresh to ensure user is prompted to add new segementation
    if self._loadImages() and self.redirect:
      if slicer.util.selectedModule() == 'Editor':
        slicer.modules.EditorWidget.enter()
      else:
        slicer.util.selectModule('Editor')

    self.logger.debug('Case initialized (settings: %s)' % kwargs)

  def _loadImages(self):
    if self.root is None:
      self.logger.error('Missing root path, cannot load case!')
      return False

    if self.image is not None:
      self.addIms.append(self.image)
    if self.mask is not None:
      self.addMas.append(self.mask)

    im_filepath = None
    for im in self.addIms:
      if im == '':
        continue
      if im not in self.case:
        self.logger.warning('%s not found in this case, skipping...', im)
        continue
      if self.case[im] == '':
        continue
      im_filepath = os.path.join(self.root, self.case[im])
      if not os.path.isfile(im_filepath):
        self.logger.warning('image file for %s does not exist, skipping...', im)
      load_success, im_node = slicer.util.loadVolume(im_filepath, returnNode=True)
      if not load_success:
        self.logger.warning('Failed to load ' + im_filepath)
        continue
      im_node.SetName(os.path.splitext(os.path.basename(im_filepath))[0])
      if im_node is not None:
        self.image_nodes[im] = im_node

    self.logger.debug('Loaded %d image(s)' % len(self.image_nodes))

    for ma in self.addMas:
      if ma == '':
        continue
      if ma not in self.case:
        self.logger.warning('%s not found in this case, skipping...', ma)
        continue
      if self.case[ma] == '':
        continue
      ma_filepath = os.path.join(self.root, self.case[ma])
      if not os.path.isfile(ma_filepath):
        self.logger.warning('image file for %s does not exist, skipping...', ma)
      load_success, ma_node = slicer.util.loadLabelVolume(ma_filepath, returnNode=True)
      if not load_success:
        self.logger.warning('Failed to load ' + ma_filepath)
        continue
      ma_node.SetName(os.path.splitext(os.path.basename(ma_filepath))[0])
      if ma_node is not None:
        self.mask_nodes[ma] = ma_node

    self.logger.debug('Loaded %d mask(s)' % len(self.mask_nodes))

    if len(self.image_nodes) > 0:
      self.image_root = os.path.dirname(im_filepath)  # store the directory of the last loaded image (main image)
      self._rotateToVolumePlanes(self.image_nodes.values()[-1])

    if len(self.image_nodes) > 1:
      slicer.app.layoutManager().sliceWidget('Red').sliceLogic().GetSliceCompositeNode().SetForegroundVolumeID(
        self.image_nodes.values()[-2].GetID())
      slicer.app.layoutManager().sliceWidget('Green').sliceLogic().GetSliceCompositeNode().SetForegroundVolumeID(
        self.image_nodes.values()[-2].GetID())
      slicer.app.layoutManager().sliceWidget('Yellow').sliceLogic().GetSliceCompositeNode().SetForegroundVolumeID(
        self.image_nodes.values()[-2].GetID())

    return True

  def closeCase(self, save_loaded_masks=False, save_new_masks=False, reader_name=None):

    # Save the results (label maps reviewed or created)
    if reader_name == '':
      reader_name = None

    loaded_masks = {node.GetName(): node for node in self.mask_nodes.values()}
    new_masks = {node.GetName(): node for node in slicer.util.getNodesByClass('vtkMRMLLabelMapVolumeNode')
                 if node.GetName() not in loaded_masks.keys()}

    # If enabled, save label maps
    if save_loaded_masks:
      if len(loaded_masks) == 0:
        self.logger.debug('No loaded masks to save...')
      else:
        self.logger.info('Saving %d loaded masks...', len(loaded_masks))
        self._saveMasks(loaded_masks, self.image_root, reader_name)
    if save_new_masks:
      if len(new_masks) == 0:
        self.logger.debug('No new masks to save...')
      else:
        self.logger.info('Saving %d new masks...', len(new_masks))
        self._saveMasks(new_masks, self.image_root, reader_name)

    # Close the scene and start a fresh one
    if slicer.util.selectedModule() == 'Editor':
      slicer.modules.EditorWidget.exit()

    slicer.mrmlScene.Clear(0)
    node = slicer.vtkMRMLViewNode()
    slicer.mrmlScene.AddNode(node)

  def _rotateToVolumePlanes(self, referenceVolume):
    sliceNodes = slicer.util.getNodes('vtkMRMLSliceNode*')
    for name, node in sliceNodes.items():
      node.RotateToVolumePlane(referenceVolume)
    # snap to IJK to try and avoid rounding errors
    sliceLogics = slicer.app.layoutManager().mrmlSliceLogics()
    numLogics = sliceLogics.GetNumberOfItems()
    for n in range(numLogics):
      l = sliceLogics.GetItemAsObject(n)
      l.SnapSliceOffsetToIJK()

  def _saveMasks(self, nodes, folder, reader_name=None):
    for nodename, node in nodes.iteritems():
      # Add the readername if set
      if reader_name is not None:
        nodename += '_' + reader_name
      filename = os.path.join(folder, nodename)

      # Prevent overwriting existing files
      if os.path.exists(filename + '.nrrd'):
        self.logger.debug('Filename exists! Generating unique name...')
        idx = 1
        filename += '(%d).nrrd'
        while os.path.exists(filename % idx):
          idx += 1
        filename = filename % idx
      else:
        filename += '.nrrd'

      # Save the node
      slicer.util.saveNode(node, filename)
      self.logger.info('Saved node %s in %s', nodename, filename)
