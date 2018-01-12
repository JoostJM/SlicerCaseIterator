cmake_minimum_required(VERSION 3.5)

project(SlicerBatch)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "http://slicer.org/slicerWiki/index.php/Documentation/Nightly/Extensions/SlicerBatch")
set(EXTENSION_CATEGORY "Examples")
set(EXTENSION_CONTRIBUTORS "Joost van Griethuysen (AVL-NKI)")
set(EXTENSION_DESCRIPTION "This is a scripted loadable module to process a batch of images for segmentation.")
set(EXTENSION_ICONURL "http://www.example.com/Slicer/Extensions/SlicerBatch.png")
set(EXTENSION_SCREENSHOTURLS "http://www.example.com/Slicer/Extensions/SlicerBatch/Screenshots/1.png")
set(EXTENSION_DEPENDS "NA") # Specified as a space separated string, a list or 'NA' if any

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(SlicerBatch)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
