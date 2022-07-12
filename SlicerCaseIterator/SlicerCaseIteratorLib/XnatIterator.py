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

import datetime
import os
import tempfile
import re

import numpy as np

import qt, ctk, slicer
import MRMLCorePython

import xnat
from xnat_nki import cohort, io_mixin, segmentation_cohort
from xnat_nki.io_mixin import slicer_mixin

from . import IteratorBase, SegmentationBackend


from typing import Optional


io_mixin.set_default(slicer_mixin.SlicerIO())


# ------------------------------------------------------------------------------
# SlicerCaseIterator CSV iterator Widget
# ------------------------------------------------------------------------------


class XnatIteratorWidget(IteratorBase.IteratorWidgetBase):

  def __init__(self, parent):
    super().__init__(parent)

    self.session = None

    self.current_project = None
    self.current_cohort: Optional[segmentation_cohort.SegmentationCohort] = None

    # Widget attributes
    self.txt_xnatServer = None  # Txtbox
    self.btn_connectXnat = None

    self.cohortConfigCollapsibleButton = None
    self.projectSelector = None  # Combobox
    self.cohortSelector = None  # Combobox
    self.sourceReaderName = None  # Combobox
    self.readerList = None

    self.chk_overwriteMask = None
    self.chk_SumTimeOnOverwrite = None


  def __del__(self):
    self.session.disconnect()

  # ------------------------------------------------------------------------------
  @classmethod
  def get_header(cls):
    return 'Xnat Iterator'

  # ------------------------------------------------------------------------------
  def setUserPreferences(self, user_preferences):
    self.txt_xnatServer.text = user_preferences.get('txt_xnatServer', self.txt_xnatServer.text)
    self.chk_overwriteMask.checked = user_preferences.get('overwriteMask', 0)
    self.chk_SumTimeOnOverwrite.checked = user_preferences.get('sumTimeOnOverwrite', 0)

    project = user_preferences.get('project', None)
    if project is not None:
      self.connectSession()
      p_idx = self.projectSelector.findText(project)
      if p_idx > -1:
        self.projectSelector.setCurrentIndex(p_idx)
      else:
        return
    else:
      return

    cohort = user_preferences.get('cohort', None)
    if cohort is not None:
      c_idx = self.cohortSelector.findText(cohort)
      if c_idx > -1:
        self.cohortSelector.setCurrentIndex(c_idx)
      else:
        return
    else:
      return

    review_reader = user_preferences.get('review_reader', None)
    if review_reader is not None:
      r_idx = self.sourceReaderName.findText(review_reader)
      if r_idx > -1:
        self.sourceReaderName.setCurrentIndex(r_idx)
      else:
        return
    else:
      return

  # ------------------------------------------------------------------------------
  def getUserPreferences(self):
    user_prefs = {
      'txt_xnatServer': self.txt_xnatServer.text,
      'overwriteMask': self.chk_overwriteMask.checked,
      'sumTimeOnOverwrite': self.chk_SumTimeOnOverwrite.checked
    }

    if self.projectSelector.currentText is not None:
      user_prefs['project']= self.projectSelector.currentText
    if self.cohortSelector.currentText is not None:
      user_prefs['cohort'] = self.cohortSelector.currentText
    if self.sourceReaderName.currentText is not None:
      user_prefs['review_reader'] = self.sourceReaderName.currentText

    return user_prefs

  # ------------------------------------------------------------------------------
  def setup(self):
    self.layout = qt.QGroupBox('Xnat Iterator')

    InputLayout = qt.QFormLayout(self.layout)

    self.txt_xnatServer = qt.QLineEdit()
    self.txt_xnatServer.text = 'http://poc-xnat.nki.nl/xnat'
    self.txt_xnatServer.toolTip = 'Server hosting XNAT to use'
    InputLayout.addRow('Xnat Server', self.txt_xnatServer)

    self.btn_connectXnat = qt.QPushButton('Connect Xnat')
    self.btn_connectXnat.toolTip = 'Connect to the configured Xnat server'
    InputLayout.addRow(self.btn_connectXnat)

    #
    # Cohort Config Area
    #
    self.cohortConfigCollapsibleButton = ctk.ctkCollapsibleButton()
    self.cohortConfigCollapsibleButton.collapsed = True
    self.cohortConfigCollapsibleButton.enabled = False
    self.cohortConfigCollapsibleButton.text = 'Cohort selction and config'
    InputLayout.addRow(self.cohortConfigCollapsibleButton)

    # Layout within the dummy collapsible button
    cohortConfigFormLayout = qt.QFormLayout(self.cohortConfigCollapsibleButton)

    cohortConfigHLayout = qt.QHBoxLayout()
    cohortConfigFormLayout.addRow(cohortConfigHLayout)

    self.cohortConfigGroupBox = qt.QGroupBox("Cohort")
    cohortConfigHLayout.layout().addWidget(self.cohortConfigGroupBox)

    cohortConfigLayout = qt.QFormLayout(self.cohortConfigGroupBox)

    self.projectSelector = qt.QComboBox()  # Combobox
    self.projectSelector.toolTip = 'Xnat Project containing the cohort to segment'
    cohortConfigLayout.addRow('Project', self.projectSelector)

    self.cohortSelector = qt.QComboBox()  # Combobox
    self.cohortSelector.toolTip = 'Cohort to segment'
    cohortConfigLayout.addRow('Cohort', self.cohortSelector)

    self.readerList = qt.QListWidget()
    self.readerList.setSelectionMode(qt.QListWidget.SingleSelection)
    self.readerList.toolTip = 'Readers already segmenting this cohort'
    cohortConfigLayout.addRow('Available Readers', self.readerList)

    self.sourceReaderName = qt.QComboBox()  # Combobox
    self.sourceReaderName.toolTip = 'Source mask to review (none, cohort-defined or review other reader)'
    cohortConfigLayout.addRow('Source Reader', self.sourceReaderName)


    #self.txtReaderName = qt.QLineEdit()
    #self.txtReaderName.text = ''
    #self.txtReaderName.toolTip = 'Reader name for new/updated segmentations'
    #cohortConfigLayout.addRow('Reader', self.txtReaderName)

    self.chk_overwriteMask = qt.QCheckBox()
    self.chk_overwriteMask.checked = 0
    self.chk_overwriteMask.toolTip = 'Overwrite existing masks'
    cohortConfigLayout.addRow('Overwrite existing masks', self.chk_overwriteMask)

    self.chk_SumTimeOnOverwrite = qt.QCheckBox()
    self.chk_SumTimeOnOverwrite.checked = 0
    self.chk_SumTimeOnOverwrite.toolTip = 'When overwriting an existing mask, sum up the duration for creation.'
    cohortConfigLayout.addRow('Sum time on overwrite', self.chk_SumTimeOnOverwrite)

    #
    # Connect Event Handlers
    #

    self.btn_connectXnat.connect('clicked(bool)', self.connectSession)
    self.projectSelector.connect('currentIndexChanged(int)', self.onProjectChanged)
    self.cohortSelector.connect('currentIndexChanged(int)', self.onCohortChanged)

    self.readerList.connect('currentItemChanged(QListWidgetItem*, QListWidgetItem*)', self.onCurrentReaderItemChanged)

    return self.layout

  # ------------------------------------------------------------------------------
  def connectSession(self):
    if self.session is not None:
      self.session.disconnect()
      self.session = None

      self.projectSelector.setCurrentIndex(-1)
      self.projectSelector.clear()

      self.cohortConfigCollapsibleButton.enabled = False
      self.cohortConfigCollapsibleButton.collapsed = True
      self.txt_xnatServer.enabled = True
      self.btn_connectXnat.text = 'Connect to server'

    else:
      if self.txt_xnatServer.text == '':
        self.logger.error('Need to set the server address first!')
        return
      try:
        self.session = xnat.connect(self.txt_xnatServer.text)
      except Exception:
        self.logger.error('Error connecting to Xnat server', exc_info=True)
        return
      self.cohortConfigCollapsibleButton.enabled = True
      self.cohortConfigCollapsibleButton.collapsed = False
      self.txt_xnatServer.enabled = False
      self.btn_connectXnat.text = 'Disconnect from server'

      self.loadProjects()

  # ------------------------------------------------------------------------------
  def loadProjects(self):
    self.projectSelector.setCurrentIndex(-1)
    self.projectSelector.clear()
    for p in self.session.projects:
      self.projectSelector.addItem(p)

  def onProjectChanged(self, index=None):
    self.logger.debug('Project changed to %s', index)
    self.loadCohorts()

  # ------------------------------------------------------------------------------
  def loadCohorts(self):
    self.cohortSelector.setCurrentIndex(-1)
    self.cohortSelector.clear()
    if self.projectSelector.currentIndex == -1:
      self.cohortSelector.enabled = False
      self.current_project = None
    else:
      self.cohortSelector.enabled = True
      self.current_project = self.session.projects[self.projectSelector.currentText]
      for c in cohort.Cohort.list_cohorts(self.session.projects[self.projectSelector.currentText]):
        self.cohortSelector.addItem(c)\

  def onCohortChanged(self, index=None):
    self.logger.debug('Cohort changed to %s', index)
    self.loadCohort()
    self.validate()

  # ------------------------------------------------------------------------------
  def loadCohort(self):
    self.sourceReaderName.setCurrentIndex(-1)
    self.sourceReaderName.clear()
    self.readerList.clear()
    if self.cohortSelector.currentIndex == -1:
      self.sourceReaderName.enabled = False
      self.readerList.enabled = False
      self.current_cohort = None
    else:
      self.sourceReaderName.enabled = True
      self.readerList.enabled = True
      self.current_cohort = segmentation_cohort.SegmentationCohort.load(
        self.current_project, self.cohortSelector.currentText
      )

      self.sourceReaderName.addItem('None')
      if self.current_cohort.has_masks():
        self.sourceReaderName.addItem('Cohort_Masks')
      i = 0
      cur_reader_idx = None
      for r in self.current_cohort.readers():
        self.sourceReaderName.addItem(r)
        self.readerList.addItem(r)
        if r == self.parent.txtReaderName.text:
          self.logger.debug('Currently set reader (%s) exists in cohort', r)
          cur_reader_idx = i
        i += 1
      if cur_reader_idx is not None:
        self.readerList.setCurrentRow(cur_reader_idx)

  def onCurrentReaderItemChanged(self, current, previous):
    cur_text = current.text() if current is not None else None
    prev_text = previous.text() if previous is not None else None
    self.logger.info('Selection reader %s (was %s)', cur_text, prev_text)
    if current is not None:
      self.parent.txtReaderName.text = cur_text
      df = self.current_cohort.records[[]].join(self.current_cohort.segmentation_records)
      start = np.where(df[cur_text + '_mask'].isnull())[0]
      if start.shape[0] > 0:
        start = start.min()
      else:
        start = 0
      self.logger.debug('Setting start to %i', start + 1)
      self.parent.npStart.value = start + 1

  # ------------------------------------------------------------------------------
  def onLoadBatch(self):
    pass

  # ------------------------------------------------------------------------------
  def onEndClose(self):
    pass

  # ------------------------------------------------------------------------------
  def is_valid(self):
    """
    This function checks the current config to decide whether a batch can be started. This is used to enable/disable
    the "start batch" button.
    :return: boolean specifying if the current setting is valid and a batch may be started
    """
    return self.cohortSelector.currentIndex >= 0

  # ------------------------------------------------------------------------------
  def startBatch(self, reader):
    """
    Function to start the batch. In the derived class, this should store relevant nodes to keep track of important data
    :return: instance of an Iterator class defining the dataset to iterate over, and function for loading/storing a case
    """
    assert reader is not None, "Need a reader to be set!"

    self.btn_connectXnat.enabled = False
    self.cohortConfigGroupBox.enabled = False

    cohortMask = False
    reviewReader = None

    if self.sourceReaderName.currentIndex == 1:
      cohortMask = True
    elif self.sourceReaderName.currentIndex > 1:
      reviewReader = self.sourceReaderName.currentText

    return XnatIteratorLogic(
      self.current_cohort,
      reader,
      cohortMask,
      reviewReader,
      self.chk_overwriteMask.checked == 1,
      self.chk_SumTimeOnOverwrite.checked == 1
    )

  def cleanupBatch(self):
    self.btn_connectXnat.enabled = True
    self.cohortConfigGroupBox.enabled = True

# ------------------------------------------------------------------------------
# SlicerCaseIterator CSV iterator
# ------------------------------------------------------------------------------

class XnatIteratorLogic(IteratorBase.IteratorLogicBase):

  td_pattern = re.compile(r'(?P<neg>-)?(?P<days>\d+) days?, (?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d+)(\.(?P<microseconds>\d+))?')

  def __init__(self, cohort: segmentation_cohort.SegmentationCohort, reader: str, cohort_mask: bool, review_reader: Optional[str], overwrite: bool = False, update_timedelta=False):
    super().__init__(reader,
                     SegmentationBackend.SegmentEditorBackend(),
                     overwrite)

    self.cohort = cohort

    self.cohort_mask = cohort_mask
    self.review_reader = review_reader

    # Counter equalling the total number of cases
    self.caseCount = self.cohort.records.shape[0]

    self.currentCase = None  # Currently loaded case: tuple with row index and mask key
    self.im_nodes = None  # Dictionary to hold the image nodes
    self.ma_node = None  # Current main mask node

    # Variables to track amount of time needed to correct the segmentation
    self.time_delta = None
    self.time_start = None  # Holds the time the timer started. If None, timer is not running
    self.update_timedelta = update_timedelta

    # Add shortcut key to enable user to pause timing
    self.shortcutPause = qt.QShortcut(slicer.util.mainWindow())
    self.shortcutPause.setKey(qt.QKeySequence('Ctrl+T'))
    self.shortcutPause.connect('activated()', self.onTimingPause)

    self.resetGridShortCut = qt.QShortcut(slicer.util.mainWindow())
    self.resetGridShortCut.setKey(qt.QKeySequence('Alt+R'))
    self.resetGridShortCut.connect('activated()', self.onResetGrid)

    # Observe the EndCloseEvent (needed to set the current case to None)
    self.end_close_observer = slicer.mrmlScene.AddObserver(slicer.mrmlScene.EndCloseEvent, self.onEndClose)

  def _convert_to_timedelta(self, td_str: str) -> datetime.timedelta:
    m = self.td_pattern.fullmatch(td_str)
    if m is None:
      self.logger.warning('Unable to parse %s as timedelta string', td_str)
      return datetime.timedelta()
    else:
      grps = m.groupdict()
      return datetime.timedelta(
        days=int(grps['days']) ,
        hours=int(grps['hours']),
        minutes=int(grps['minutes']),
        seconds=int(grps['seconds']),
        microseconds=int(grps['microseconds']) if grps['microseconds'] is not None else 0
      ) * (1 if grps['neg'] is None else -1)

  def _get_timedelta(self) -> datetime.timedelta:
    time_clm = self.reader + '_timing'
    if time_clm not in self.cohort.segmentation_records.columns:
      return datetime.timedelta()
    td = self.cohort.segmentation_records[time_clm].get(self.currentCase)
    if td is None:
      return datetime.timedelta()
    elif isinstance(td, datetime.timedelta):
      return td
    elif isinstance(td, str):
      return self._convert_to_timedelta(td)
    else:
      self.logger.warning('Unexpected type for timing column: %s', type(td).__name__)
      return datetime.timedelta()

  # ------------------------------------------------------------------------------
  def loadCase(self, case_idx):
    assert 0 <= case_idx < self.caseCount, 'case_idx %i is out of range (n cases: %i)' % (case_idx, self.caseCount)

    self.currentCase = self.cohort.records.index[case_idx]

    self.logger.info('\nLoading case %s (%i/%i)...', self.currentCase, case_idx + 1, self.caseCount)

    self.im_nodes = self.cohort.get_images(self.currentCase)
    assert self.im_nodes[0] is not None, 'Failed to load primary image for case %s (%i/%i)' % (self.currentCase, case_idx + 1, self.caseCount)

    self.ma_node = self.cohort.get_segmentation(self.currentCase, self.reader)
    if self.ma_node is None:
      if self.cohort_mask:
        self.logger.info('Attempting to load Cohort Mask')
        self.ma_node = self.cohort.get_mask(self.currentCase)
      elif self.review_reader is not None:
        self.logger.info('Attempting to load Mask for reader %s' % self.review_reader)
        self.ma_node = self.cohort.get_segmentation(self.currentCase, self.review_reader)
    else:
      self.logger.info('Reloaded the mask for reader %s', self.reader)

    if self.ma_node is None:  # ma is None, or loading failed...
      self.ma_node = self.backend.newMask(self.im_nodes[0], self.reader)

    # Mark the start of reading for this case
    self.time_start = datetime.datetime.now()
    self.time_delta = datetime.timedelta(0)

    return self.im_nodes[0], self.ma_node, self.im_nodes[1:], []

  # ------------------------------------------------------------------------------
  def onEndClose(self, caller, event):
    self.currentCase = None

  # ------------------------------------------------------------------------------
  def should_close(self, new_case_idx):
    #if new_case_idx >= self.caseCount:
    #  return True
    #return self.currentCase is None or self.currentCase[0] != self.cases[new_case_idx][0]
    return True

  # ------------------------------------------------------------------------------
  def saveMask(self, node, overwrite_existing=False):
    if isinstance(node, MRMLCorePython.vtkMRMLSegmentationNode):
      ext = 'seg.nrrd'
    else:
      ext = 'nrrd'

    self.logger.info('Saving mask')

    measurements = {}
    if self.time_start is not None:
      # timer active, record time passed
      self.time_delta += datetime.datetime.now() - self.time_start
      self.time_start = None
      if self.update_timedelta:
        self.time_delta += self._get_timedelta()
      measurements['timing'] = self.time_delta
    with tempfile.TemporaryDirectory() as tmp:
      tmp_file = os.path.join(tmp, 'mask.' + ext)
      slicer.util.saveNode(node, tmp_file)
      self.cohort.save_segmentation(
        self.currentCase, tmp_file, self.reader, overwrite_existing, ext, **measurements
      )

  # ------------------------------------------------------------------------------
  def onTimingPause(self):
    if self.time_start is not None:
      self.time_delta += datetime.datetime.now() - self.time_start
      self.time_start = None
      self.logger.info('Paused timing')
    else:
      self.time_start = datetime.datetime.now()
      self.logger.info('Resumed timing')

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
    super().cleanupIterator()

    self.currentCase = None
    self.cohort = None

    self.ma_node = None
    self.im_nodes = None

    if hasattr(self, 'shortcutPause') and self.shortcutPause is not None:
      self.shortcutPause.disconnect('activated()')
      self.shortcutPause.setParent(None)
      self.shortcutPause = None

    if hasattr(self, 'resetGridShortCut') and self.resetGridShortCut is not None:
      self.resetGridShortCut.disconnect('activated()')
      self.resetGridShortCut.setParent(None)
      self.resetGridShortCut = None

    if hasattr(self, 'end_close_observer'):
      slicer.mrmlScene.RemoveObserver(self.end_close_observer)

