# @File(label="Training set directory", style=directory) inputdir
# @File(label="Classifier to save") classifier
# @String(label="Features") featurestr
# @Integer(label="Minimum sigma") smin
# @Integer(label="Maximum sigma") smax
# @ConvertService convert
# @DatasetService ds
# @DisplayService display
# @OpService ops

import os
from jarray import array
from ij import IJ, ImageStack, ImagePlus
from ij.plugin.filter import ImageMath
from trainableSegmentation import WekaSegmentation, FeatureStack3D
from java.util import ArrayList
from java.lang import String
from java.io import File, FileOutputStream, ObjectOutputStream
from sc.fiji.hdf5 import HDF5ImageJ


def feature_list(features):
    farray = []
    for f in FeatureStack3D.availableFeatures:
        farray.append(f in features)
    return array(farray, 'z')
    
def load_labels(weka, image, label, features, smin, smax):
    farray = feature_list(features)
    fs3d = FeatureStack3D(image)
    fs3d.setMinimumSigma(smin)
    fs3d.setMaximumSigma(smax)
    fs3d.setEnableFeatures(farray)
    fs3d.updateFeaturesMT()
    fsa = fs3d.getFeatureStackArray()
    stack = label.getStack()
    if fsa.getSize() != stack.getSize():
        raise Exception("Feature stack and image sizes do not match!") 
    for i in range(0, stack.getSize()):
        labelip = stack.getProcessor(i + 1).convertToFloat()
        ImageMath.applyMacro(labelip, "v=v-1", False)
        histogram = labelip.getHistogram()
        if sum(histogram[1:]):
            labelimp = ImagePlus("Labels slice " + str(i + 1), labelip)
            print "Loading labels from slice " + str(i) + "."
            weka.addLabeledData(labelimp, fsa.get(i))

def load_labels_from_files(weka, imagefile, labelfile, features, smin, smax):
    print "Opening image dataset from: " + str(imagefile)
    image = convert.convert(ds.open(str(imagefile)), ImagePlus)
    print "Opening label dataset from: " + str(labelfile)
    label = HDF5ImageJ.hdf5read(str(labelfile), '/exported_data', 'zyxc')
    if image and label:
        load_labels(weka, image, label, features, smin, smax)


weka = WekaSegmentation(True)
weka.setClassLabels(array(['Background', 'Nuclei'], String))

features = featurestr.split(',')
inputdir = str(inputdir)
for imagefile in os.listdir(inputdir):
    if imagefile.endswith(".tiff"):
        labelfile = os.path.join(inputdir, imagefile.replace('.tiff', '_Labels.h5'))
        imagefile = os.path.join(inputdir, imagefile)
        if os.path.isfile(imagefile) and os.path.isfile(labelfile):
            load_labels_from_files(weka, imagefile, labelfile, features, smin, smax)

print "Training classifier..."
if weka.trainClassifier():
    print "Saving classifier..."
    weka.saveClassifier(str(classifier))
print "Classifier saved!"
