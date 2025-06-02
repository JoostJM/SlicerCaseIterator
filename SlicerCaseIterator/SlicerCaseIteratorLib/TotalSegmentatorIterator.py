import fnmatch
import os
import logging
import slicer
import vtk
import glob
from .IteratorBase import IteratorWidgetBase, IteratorLogicBase, IteratorEventHandlerBase

class TotalSegmentatorIteratorWidget(IteratorWidgetBase):
    def __init__(self):
        super(TotalSegmentatorIteratorWidget, self).__init__()
        self.inputDirectory = None
        self.caseFolders = []
        self.settings = slicer.app.settings()

    def setup(self):
        import qt
        import ctk
        groupBox = qt.QGroupBox("TotalSegmentator Iterator")
        layout = qt.QFormLayout(groupBox)

        # Input directory selection
        self.inputDirectoryButton = ctk.ctkPathLineEdit()
        self.inputDirectoryButton.filters = ctk.ctkPathLineEdit.Dirs
        self.inputDirectoryButton.settingKey = "CaseIterator/TotalSegmentatorIterator/InputDirectory"
        self.inputDirectoryButton.connect('currentPathChanged(QString)', self.onInputDirectoryChanged)
        layout.addRow("Data directory:", self.inputDirectoryButton)

        # Case subfolder pattern input
        self.caseSubfolderPatternEdit = qt.QLineEdit()
        self.caseSubfolderPatternEdit.setText(self.settings.value("CaseIterator/TotalSegmentatorIterator/CaseSubfolderPattern", "*/*"))
        self.caseSubfolderPatternEdit.setToolTip("Glob pattern to match case folders (e.g., 'case_*', '*/*' for subfolders, or '*_data'). Use '*' to match all folders.")
        layout.addRow("Case folder pattern:", self.caseSubfolderPatternEdit)

        # Image filename input
        self.imageFilenameEdit = qt.QLineEdit()
        self.imageFilenameEdit.setText(self.settings.value("CaseIterator/TotalSegmentatorIterator/ImageFilename", "ct.nii.gz"))
        self.imageFilenameEdit.setToolTip("Name of the image file to load from each case folder")
        layout.addRow("Image filename:", self.imageFilenameEdit)

        # Segmentation subfolder input
        self.segmentationSubfolderEdit = qt.QLineEdit()
        self.segmentationSubfolderEdit.setText(self.settings.value("CaseIterator/TotalSegmentatorIterator/SegmentationSubfolder", "roi"))
        self.segmentationSubfolderEdit.setToolTip("Name of the subfolder containing segmentation files in each case folder")
        layout.addRow("Segmentation subfolder:", self.segmentationSubfolderEdit)

        # Optional segment list
        self.segmentNamesEdit = qt.QLineEdit()
        self.segmentNamesEdit.setText(self.settings.value("CaseIterator/TotalSegmentatorIterator/SegmentNames", ""))
        self.segmentNamesEdit.setPlaceholderText("all segments")
        self.segmentNamesEdit.setToolTip("Optional: Comma-separated list of segments to process, wildcards are supported (e.g., 'segment1,segment2'). If empty, all segments will be processed.")
        layout.addRow("Segment names:", self.segmentNamesEdit)

        self.onInputDirectoryChanged(self.inputDirectoryButton.currentPath)

        return groupBox

    def onInputDirectoryChanged(self, inputDir):
        if inputDir:
            self.inputDirectory = inputDir
            pattern = self.caseSubfolderPatternEdit.text
            # Use glob to find matching directories, including subdirectories
            globPattern = os.path.join(inputDir, pattern)
            self.caseFolders = [os.path.relpath(f, inputDir) for f in glob.glob(globPattern)
                              if os.path.isdir(f)]
            self.validate()

    def is_valid(self):
        return self.inputDirectory is not None and len(self.caseFolders) > 0

    def startBatch(self, reader=None):
        self.inputDirectoryButton.addCurrentPathToHistory()
        if not self.is_valid():
            return None

        # Save current settings
        self.settings.setValue("CaseIterator/TotalSegmentatorIterator/CaseSubfolderPattern", self.caseSubfolderPatternEdit.text)
        self.settings.setValue("CaseIterator/TotalSegmentatorIterator/ImageFilename", self.imageFilenameEdit.text)
        self.settings.setValue("CaseIterator/TotalSegmentatorIterator/SegmentationSubfolder", self.segmentationSubfolderEdit.text)
        self.settings.setValue("CaseIterator/TotalSegmentatorIterator/SegmentNames", self.segmentNamesEdit.text)

        self._iterator = TotalSegmentatorIteratorLogic(
            self.inputDirectory,
            self.caseFolders,
            reader,
            self.segmentNamesEdit.text,
            self.imageFilenameEdit.text,
            self.segmentationSubfolderEdit.text
        )
        self._iterator.registerEventListener(TotalSegmentatorEventHandler())
        return self._iterator

    def cleanupBatch(self):
        self._iterator = None

class TotalSegmentatorIteratorLogic(IteratorLogicBase):
    def __init__(self, inputDirectory, caseFolders, reader=None, segmentNamesPattern=None, imageFilename=None, segmentationSubfolder="segmentations"):
        super(TotalSegmentatorIteratorLogic, self).__init__()
        self.imageFilename = "ct.nii.gz" if imageFilename is None else imageFilename
        self.fileExtension = ".nii.gz"
        self.forceImageGeometryToSegmentation = True
        self.inputDirectory = inputDirectory
        self.caseFolders = caseFolders
        self.reader = reader
        self.segmentNamesPattern = segmentNamesPattern
        self.segmentationSubfolder = "segmentations" if segmentationSubfolder is None else segmentationSubfolder
        self.caseCount = len(caseFolders)
        self.currentCaseFolder = None
        self.currentImageNode = None
        self.currentSegmentationNode = None

    def loadCase(self, case_idx):
        if case_idx < 0 or case_idx >= self.caseCount:
            return None

        # Close previous case if exists
        if self.currentIdx is not None:
            self.closeCase()

        self.currentIdx = case_idx
        self.currentCaseFolder = self.caseFolders[case_idx]
        casePath = os.path.join(self.inputDirectory, self.currentCaseFolder)

        # Load CT image
        ctPath = os.path.join(casePath, self.imageFilename)
        if not os.path.exists(ctPath):
            raise RuntimeError(f"CT image not found at {ctPath}")

        # Load image
        self.currentImageNode = slicer.util.loadVolume(ctPath)

        imageName = self.imageFilename.removesuffix(self.fileExtension)
        self.currentImageNode.SetName(imageName)

        if self.forceImageGeometryToSegmentation:
            imageIJKToRAS = vtk.vtkMatrix4x4()
            self.currentImageNode.GetIJKToRASMatrix(imageIJKToRAS)
        else:
            imageIJKToRAS = None

        # Create segmentation node
        self.currentSegmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        self.currentSegmentationNode.SetName(f"Segmentation_{self.currentCaseFolder}")

        self.currentSegmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(self.currentImageNode)

        labelsPath = os.path.join(self.inputDirectory, "labels.csv")
        if not os.path.exists(labelsPath):
            raise RuntimeError(f"Labels file not found at {labelsPath}")

        labelsNode = slicer.util.loadNodeFromFile(labelsPath)

        # Load segmentations
        segmentationPath = os.path.join(casePath, self.segmentationSubfolder)
        if os.path.exists(segmentationPath):
            # Load all segmentation files from the segmentations folder
            with slicer.util.WaitCursor():
                with slicer.util.RenderBlocker():
                    filenames = os.listdir(segmentationPath)

                    # Filter filenames based on the segmentNamesPattern if provided
                    if self.segmentNamesPattern:
                        filtered_filenames = []
                        patterns = [pattern.strip().lower() for pattern in self.segmentNamesPattern.split(',') if pattern.strip()]
                        for filename in filenames:
                            segmentName = filename.strip().removesuffix(self.fileExtension).lower()
                            matches = any(fnmatch.fnmatchcase(segmentName, pattern) for pattern in patterns)
                            if matches:
                                filtered_filenames.append(filename)
                        filenames = filtered_filenames

                    with slicer.util.NodeModify(self.currentSegmentationNode):
                        for fileIndex, filename in enumerate(filenames):
                            if filename.endswith(self.fileExtension):
                                labelmapPath = os.path.join(segmentationPath, filename)
                                # Use filename without extension as segment name
                                segmentName = filename.removesuffix(self.fileExtension)
                                slicer.util.showStatusMessage(f"Reading segment ({fileIndex+1}/{len(filenames)}): {segmentName}")
                                slicer.app.processEvents()
                                self._addLabelmapToSegmentation(labelmapPath, segmentName, imageIJKToRAS, labelsNode)
                        slicer.util.showStatusMessage("Collapsing binary labelmaps...")
                        slicer.app.processEvents()
                        self.currentSegmentationNode.GetSegmentation().CollapseBinaryLabelmaps()

        slicer.mrmlScene.RemoveNode(labelsNode)  # Remove the temporary labels node

        slicer.util.showStatusMessage(f"Case {case_idx+1} loaded from {self.currentCaseFolder}.")

        self._eventListeners.caseLoaded(self.currentImageNode, self.currentSegmentationNode)
        return (self.currentImageNode, self.currentSegmentationNode, [], [])

    def _addLabelmapToSegmentation(self, labelmapPath, segmentName, imageIJKToRAS, labelsNode):
        # Load labelmap

        labelmapNode = slicer.util.loadNodeFromFile(labelmapPath, "VolumeFile", {'labelmap': True, 'show': False})

        if imageIJKToRAS:
            labelmapNode.SetIJKToRASMatrix(imageIJKToRAS)

        segmentation = self.currentSegmentationNode.GetSegmentation()

        # Add to segmentation
        numberOfSegmentsBefore = segmentation.GetNumberOfSegments()
        slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
            labelmapNode, self.currentSegmentationNode)
        numberOfSegmentsAfter = segmentation.GetNumberOfSegments()

        # Update the last added segment (the one we just imported)
        if numberOfSegmentsAfter > numberOfSegmentsBefore:
            segmentId = segmentation.GetNthSegmentID(segmentation.GetNumberOfSegments() - 1)
            segment = segmentation.GetSegment(segmentId)
            segment.SetName(segmentName)
            # Set segment color from labels node if available
            if labelsNode:
                labelIndex = labelsNode.GetColorIndexByName(segmentName)
                if labelIndex >= 0:
                    color = [127, 127, 127, 255]
                    labelsNode.GetColor(labelIndex, color)
                    segment.SetColor(color[0], color[1], color[2])

        # Remove temporary labelmap node
        slicer.mrmlScene.RemoveNode(labelmapNode)

    def closeCase(self):
        if self.currentSegmentationNode:
            # Export segments before removing
            if self.currentCaseFolder:
                with slicer.util.WaitCursor():
                    self._exportSegments()
            slicer.mrmlScene.RemoveNode(self.currentSegmentationNode)
            self.currentSegmentationNode = None

        if self.currentImageNode:
            slicer.mrmlScene.RemoveNode(self.currentImageNode)
            self.currentImageNode = None

        self._eventListeners.caseAboutToClose(self.parameterNode)
        self.currentIdx = None
        self.currentCaseFolder = None

    def _exportSegments(self):
        if not self.currentSegmentationNode or not self.currentCaseFolder:
            return

        outputDir = os.path.join(self.inputDirectory, self.currentCaseFolder, self.segmentationSubfolder)
        os.makedirs(outputDir, exist_ok=True)

        segmentation = self.currentSegmentationNode.GetSegmentation()

        with slicer.util.RenderBlocker():
            for i in range(segmentation.GetNumberOfSegments()):

                segmentId = segmentation.GetNthSegmentID(i)
                segment = segmentation.GetSegment(segmentId)

                # Check if segment has been modified
                if slicer.vtkSlicerSegmentationsModuleLogic.GetSegmentStatus(segment) == slicer.vtkSlicerSegmentationsModuleLogic.NotStarted:
                    continue

                segmentName = segment.GetName()

                slicer.util.showStatusMessage(f"Writing segment {i+1}/{segmentation.GetNumberOfSegments()}: {segmentName}")
                slicer.app.processEvents()

                # Create temporary labelmap node
                labelmapNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")

                # Export segment to labelmap
                slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(
                    self.currentSegmentationNode, [segmentId], labelmapNode, None, slicer.vtkSegmentation.EXTENT_REFERENCE_GEOMETRY)

                # Save labelmap
                outputPath = os.path.join(outputDir, f"{segmentName}.nii.gz")
                slicer.util.saveNode(labelmapNode, outputPath)

                # Remove temporary labelmap node
                slicer.mrmlScene.RemoveNode(labelmapNode)

        slicer.util.showStatusMessage(f"Export segments completed")


    def getCaseData(self):
        return {
            'caseFolder': self.currentCaseFolder,
            'imageNode': self.currentImageNode,
            'segmentationNode': self.currentSegmentationNode
        }


class TotalSegmentatorEventHandler(IteratorEventHandlerBase):

    def __init__(self):
        super(TotalSegmentatorEventHandler, self).__init__()

    def onCaseLoaded(self, caller, *args, **kwargs):
        try:
            imageNode = caller.getCaseData()['imageNode']
            segmentationNode = caller.getCaseData()['segmentationNode']

            # Set the slice viewers to the correct volumes
            slicer.util.setSliceViewerLayers(background=imageNode)

            # the following code should go somewhere in a separate class including the save part
            #if slicer.util.selectedModule() != 'SegmentEditor':
            #    slicer.util.selectModule('SegmentEditor')

            # Explicitly set the segmentation and master volume nodes
            segmentEditorNode = slicer.mrmlScene.GetSingletonNode("SegmentEditor", "vtkMRMLSegmentEditorNode")
            if segmentEditorNode:
                segmentEditorNode.SetAndObserveSegmentationNode(segmentationNode)
                segmentEditorNode.SetAndObserveSourceVolumeNode(imageNode)

            # Show segmentation in 3D view
            segmentationNode.CreateClosedSurfaceRepresentation()

            # Reset field of view in 3D view
            layoutManager = slicer.app.layoutManager()
            threeDWidget = layoutManager.threeDWidget(0)
            if threeDWidget:
                threeDView = threeDWidget.threeDView()
                threeDView.resetFocalPoint()
                threeDView.resetCamera()

        except Exception as e:
            self.logger.warning("Error setting up segment editor: %s", str(e))
            import traceback
            traceback.print_exc()
