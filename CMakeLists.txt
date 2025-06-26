cmake_minimum_required(VERSION 3.5)

project(SlicerCaseIterator)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/SlicerCaseIterator")
set(EXTENSION_CATEGORY "Utilities")
set(EXTENSION_CONTRIBUTORS "Joost van Griethuysen (AVL-NKI), Christian Herz (CHOP)")
set(EXTENSION_DESCRIPTION "Scripted module for iterating over a set of cases listed in a CSV file for segmentation or review.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/JoostJM/SlicerCaseIterator/master/SlicerCaseIterator.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/JoostJM/SlicerCaseIterator/master/SlicerCaseIterator-Screenshot.png")
set(EXTENSION_DEPENDS "SlicerDevelopmentToolbox")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(SlicerCaseIterator)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
