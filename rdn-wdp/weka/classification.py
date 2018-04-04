# @File(label="Classifier to use") classifier
# @File(label="List of images to classify") imagelist

# @IOService io
# @ConvertService cs

import time, csv, os
from ij import IJ, ImagePlus
from sc.fiji.hdf5 import HDF5ImageJ
from trainableSegmentation import WekaSegmentation

def classify_image(weka, imagefile, dataset = None):
    print "Opening image: " + imagefile
    if imagefile.endswith('.h5') and dataset:
        imp = HDF5ImageJ.hdf5read(str(imagefile), '/raw/fused/channel1', 'zyx')
        outfile = imagefile
    else:
        imp = cs.convert(io.open(imagefile), ImagePlus)
        name, extension = os.path.splitext(imagefile)
        outfile = imagefile.replace(extension, '.h5')
    if imp:
        print "Classifying image..."
        start = time.time()
        pmap = weka.applyClassifier(imp, 0, True)
    else:
        raise Exception("Error opening image!")
    if pmap:
        print "Image has been classified. Execution time: %.3f seconds" % abs(start - time.time())
        HDF5ImageJ.hdf5write(pmap, outfile, '/weka/pmap{c}', '%d', '%d', 0, False)
        pmap.close()
        imp.close()
    else:
        raise Exception("Error classifying image!")

if os.path.isfile(str(classifier)):
    weka = WekaSegmentation(True)
    print "Loading the classifier..."
    start = time.time()
    success = weka.loadClassifier(str(classifier))
    if success:
        print "Classifier has been loaded. Execution time: %.3f seconds" % abs(start - time.time())
    else:
        raise Exception("Error loading classifier!")

with open(str(imagelist), 'rb') as f:
    reader = csv.reader(f)
    for row in reader:
        imagefile = row[0]
        classify_image(weka, imagefile)

