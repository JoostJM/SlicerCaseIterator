# =========================================================================
#  Copyright Joost van Griethuysen
#
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

# Adapted from
# https://github.com/pieper/CompareVolumes/blob/master/CompareVolumes.py

import numpy as np

import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *


class CaseIteratorLayoutLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget
  """

  def __init__(self):
    ScriptedLoadableModuleLogic.__init__(self)
    self.sliceViewItemPattern = """
      <item><view class="vtkMRMLSliceNode" singletontag="{viewName}">
        <property name="orientation" action="default">{orientation}</property>
        <property name="viewlabel" action="default">{viewName}</property>
        <property name="viewcolor" action="default">{color}</property>
      </view></item>
     """
    # use a nice set of colors
    self.colors = slicer.util.getNode('GenericColors')
    self.lookupTable = self.colors.GetLookupTable()

  def assignLayoutDescription(self, layoutDescription):
    """assign the xml to the user-defined layout slot"""
    layoutNode = slicer.util.getNode('*LayoutNode*')
    if layoutNode.IsLayoutDescription(layoutNode.SlicerLayoutUserView):
      layoutNode.SetLayoutDescription(layoutNode.SlicerLayoutUserView, layoutDescription)
    else:
      layoutNode.AddLayoutDescription(layoutNode.SlicerLayoutUserView, layoutDescription)
    layoutNode.SetViewArrangement(layoutNode.SlicerLayoutUserView)

  @staticmethod
  def _getOrientation(volumeNode):
    directionMatrix = vtk.vtkMatrix4x4()
    volumeNode.GetIJKToRASDirectionMatrix(directionMatrix)
    directions = np.zeros((3, 3), dtype='float')
    for i in range(3):
      for j in range(3):
        directions[i, j] = directionMatrix.GetElement(i, j)

    directions = np.abs(directions)
    if directions[0, 1] >= directions[0, 0]:  # |Xy| >= |Xx| (Saggital)
      return 'Sagittal'
    elif directions[1, 1] >= directions[1, 2]:  # |Yy| >= |Yz| (Axial)
      return 'Axial'
    else:
      return 'Coronal'

  def viewerPerVolume(self, volumeNodes=None, background=None, label=None, viewNames=[], layout=None,
                      orientation=None, opacity=0.5):
    """ Load each volume in the scene into its own
    slice viewer and link them all together.
    If background is specified, put it in the background
    of all viewers and make the other volumes be the
    forground.  If label is specified, make it active as
    the label layer of all viewers.
    Return a map of slice nodes indexed by the view name (given or generated).
    Opacity applies only when background is selected.
    """
    import math

    if orientation is not None:
      default_orientation = orientation
    else:
      default_orientation = "Axial"

    if not volumeNodes:
      volumeNodes = list(slicer.util.getNodes('*VolumeNode*').values())

    if len(volumeNodes) == 0:
      return

    if layout:
      rows = layout[0]
      columns = layout[1]
    elif len(volumeNodes) > 1:
      # make an array with wide screen aspect ratio
      # - e.g. 3 volumes in 3x1 grid
      # - 5 volumes 3x2 with only two volumes in second row
      additional_volume_cnt = len(volumeNodes) - 1

      c = math.sqrt(additional_volume_cnt)
      columns = np.floor(c)
      rows = additional_volume_cnt // columns
      if columns * rows < additional_volume_cnt:
        rows += 1
    else:
      rows = 0
      columns = 0

    #
    # construct the XML for the layout
    # - one viewer per volume
    # - default orientation as specified
    #
    actualViewNames = []
    index = 1
    layoutDescription = ''

    # Add larger viewer for main volume
    layoutDescription += '<layout type="horizontal">\n'
    try:
      viewName = viewNames[index - 1]
    except IndexError:
      viewName = 'main'
    rgb = [int(round(v * 255)) for v in self.lookupTable.GetTableValue(index)[:-1]]
    color = '#%0.2X%0.2X%0.2X' % tuple(rgb)
    layoutDescription += self.sliceViewItemPattern.format(viewName=viewName, orientation=default_orientation, color=color)
    actualViewNames.append(viewName)
    index += 1

    # Add  viewer for additional volumes
    if rows > 0:
      layoutDescription += '<item> <layout type="vertical">\n'
      for row in range(int(rows)):
        layoutDescription += ' <item> <layout type="horizontal">\n'
        for column in range(int(columns)):
          try:
            viewName = viewNames[index - 1]
          except IndexError:
            viewName = '%d_%d' % (row, column)
          rgb = [int(round(v * 255)) for v in self.lookupTable.GetTableValue(index)[:-1]]
          color = '#%0.2X%0.2X%0.2X' % tuple(rgb)
          layoutDescription += self.sliceViewItemPattern.format(viewName=viewName, orientation=orientation, color=color)
          actualViewNames.append(viewName)
          index += 1
        layoutDescription += '</layout></item>\n'
      layoutDescription += '</layout></item>\n'

    layoutDescription += '</layout>'
    self.assignLayoutDescription(layoutDescription)

    # let the widgets all decide how big they should be
    slicer.app.processEvents()

    # if background is specified, move it to the front of the list:
    #  it will show up in first slice view with itself as in foreground
    if background:
      volumeNodes = [background] + [i for i in volumeNodes if i != background]

    # put one of the volumes into each view, or none if it should be blank
    sliceNodesByViewName = {}
    layoutManager = slicer.app.layoutManager()

    orientation_reference_volumes = {}
    orientation_sliceNodes = {}

    volume_orientation = orientation
    for index in range(len(actualViewNames)):
      viewName = actualViewNames[index]
      try:
        volumeNodeID = volumeNodes[index].GetID()
        if orientation is None:
          volume_orientation = self._getOrientation(volumeNodes[index])
      except IndexError:
        volumeNodeID = ""

      sliceWidget = layoutManager.sliceWidget(viewName)
      compositeNode = sliceWidget.mrmlSliceCompositeNode()
      if background:
        compositeNode.SetBackgroundVolumeID(background.GetID())
        compositeNode.SetForegroundVolumeID(volumeNodeID)
        compositeNode.SetForegroundOpacity(opacity)
      else:
        compositeNode.SetBackgroundVolumeID(volumeNodeID)
        compositeNode.SetForegroundVolumeID("")

      if label:
        compositeNode.SetLabelVolumeID(label.GetID())
      else:
        compositeNode.SetLabelVolumeID("")

      sliceNode = sliceWidget.mrmlSliceNode()

      # If a volume is assigned to the viewer, set the orientation
      if volumeNodeID != '' and volume_orientation is not None:
        sliceNode.SetOrientation(volume_orientation)
        if volume_orientation not in orientation_reference_volumes:
          orientation_reference_volumes[volume_orientation] = volumeNodes[index]
          orientation_sliceNodes[volume_orientation] = []
        orientation_sliceNodes[volume_orientation].append(sliceNode)

      sliceWidget.fitSliceToBackground()

      # Set linked to True
      compositeNode.SetLinkedControl(True)

      sliceNodesByViewName[viewName] = sliceNode

    # Rotate the viewers to the slice plane, do this separately for each orientation
    for volume_orientation in orientation_reference_volumes:
      self.rotateToVolumePlanes(orientation_reference_volumes[volume_orientation],
                                orientation_sliceNodes[volume_orientation])
    self.snapToIJK()

    return sliceNodesByViewName

  @staticmethod
  def rotateToVolumePlanes(referenceVolume, sliceNodes=None):
    if sliceNodes is None:
      sliceNodes = slicer.util.getNodes('vtkMRMLSliceNode*')
    for node in sliceNodes:
      node.RotateToVolumePlane(referenceVolume)

  @staticmethod
  def snapToIJK():
    # snap to IJK to try and avoid rounding errors
    sliceLogics = slicer.app.layoutManager().mrmlSliceLogics()
    numLogics = sliceLogics.GetNumberOfItems()
    for n in range(numLogics):
      l = sliceLogics.GetItemAsObject(n)
      l.SnapSliceOffsetToIJK()

  @staticmethod
  def linkSlices(linked=True):
    compositeNodes = slicer.util.getNodes('SliceComposite*')
    for node in compositeNodes:
      node.SetLinkedControl(linked)

  def zoom(self, factor, sliceNodes=None):
    """Zoom slice nodes by factor.
    factor: "Fit" or +/- amount to zoom
    sliceNodes: list of slice nodes to change, None means all.
    """
    if not sliceNodes:
      sliceNodes = slicer.util.getNodes('vtkMRMLSliceNode*')
    layoutManager = slicer.app.layoutManager()
    for sliceNode in list(sliceNodes.values()):
      if factor == "Fit":
        sliceWidget = layoutManager.sliceWidget(sliceNode.GetLayoutName())
        if sliceWidget:
          sliceWidget.sliceLogic().FitSliceToAll()
      else:
        newFOVx = sliceNode.GetFieldOfView()[0] * factor
        newFOVy = sliceNode.GetFieldOfView()[1] * factor
        newFOVz = sliceNode.GetFieldOfView()[2]
        sliceNode.SetFieldOfView(newFOVx, newFOVy, newFOVz)
        sliceNode.UpdateMatrices()

  def viewersPerVolume(self, volumeNodes=None, background=None, label=None, include3D=False):
    """ Make an axi/sag/cor(/3D) row of viewers
    for each volume in the scene.
    If background is specified, put it in the background
    of all viewers and make the other volumes be the
    forground.  If label is specified, make it active as
    the label layer of all viewers.
    Return a map of slice nodes indexed by the view name (given or generated).
    """
    import math

    if not volumeNodes:
      volumeNodes = list(slicer.util.getNodes('*VolumeNode*').values())

    if len(volumeNodes) == 0:
      return

    #
    # construct the XML for the layout
    # - one row per volume
    # - viewers for each orientation
    #
    orientations = ('Axial', 'Sagittal', 'Coronal')
    actualViewNames = []
    index = 1
    layoutDescription = ''
    layoutDescription += '<layout type="vertical">\n'
    row = 0
    for volumeNode in volumeNodes:
      layoutDescription += ' <item> <layout type="horizontal">\n'
      column = 0
      for orientation in orientations:
        viewName = volumeNode.GetName() + '-' + orientation
        rgb = [int(round(v * 255)) for v in self.lookupTable.GetTableValue(index)[:-1]]
        color = '#%0.2X%0.2X%0.2X' % tuple(rgb)
        layoutDescription += self.sliceViewItemPattern.format(viewName=viewName, orientation=orientation, color=color)
        actualViewNames.append(viewName)
        index += 1
        column += 1
      if include3D:
        print('TODO: add 3D viewer')
      layoutDescription += '</layout></item>\n'
    row += 1
    layoutDescription += '</layout>'
    self.assignLayoutDescription(layoutDescription)

    # let the widgets all decide how big they should be
    slicer.app.processEvents()

    # put one of the volumes into each row and set orientations
    layoutManager = slicer.app.layoutManager()
    sliceNodesByViewName = {}
    for volumeNode in volumeNodes:
      for orientation in orientations:
        viewName = volumeNode.GetName() + '-' + orientation
        sliceWidget = layoutManager.sliceWidget(viewName)
        compositeNode = sliceWidget.mrmlSliceCompositeNode()
        compositeNode.SetBackgroundVolumeID(volumeNode.GetID())
        sliceNode = sliceWidget.mrmlSliceNode()
        sliceNode.SetOrientation(orientation)
        sliceWidget.fitSliceToBackground()
        sliceNodesByViewName[viewName] = sliceNode
    return sliceNodesByViewName

  def volumeLightbox(self, volumeNode, layout=[3, 3], orientation='Axial', padRatio=.1):
    """Display the given volumeNode in a single slice view
    in lightbox with layout defining the number of rows and
    colums in the given orientation.  The spacing of the lightbox
    cells should span the volume range in RAS"""
    # make a single viewer, just for this volume
    views = layout[0] * layout[1]
    sliceNodesByViewName = self.viewerPerVolume([volumeNode, ] * views, layout=layout, orientation=orientation)
    view = 0.
    for viewName in sorted(sliceNodesByViewName.keys()):
      sliceNode = sliceNodesByViewName[viewName]
      sliceNode.RotateToVolumePlane(volumeNode)
      layoutManager = slicer.app.layoutManager()
      sliceWidget = layoutManager.sliceWidget(sliceNode.GetLayoutName())
      sliceLogic = sliceWidget.sliceLogic()
      bounds = [0, ] * 6
      sliceLogic.GetLowestVolumeSliceBounds(bounds)
      sliceRange = (bounds[5] - bounds[4])
      slicePad = padRatio * sliceRange
      paddedRange = sliceRange - 2 * slicePad
      lowBound = bounds[4] + slicePad
      highBound = bounds[5] - slicePad
      offset = lowBound + paddedRange * view / (views - 1.)
      sliceNode.SetSliceOffset(offset)
      view += 1.
    return sliceNodesByViewName
