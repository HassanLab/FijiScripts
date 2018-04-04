# @File(label="Classifier to use") classifier
# @File(label="Image to classify") imagefile
# @String(label="Dataset to open", default="") dataset

# @IOService io
# @ConvertService cs

import time, csv, os
from ij import IJ, ImagePlus
from net.imagej import Dataset, ImgPlus
from net.imagej.axis import Axes
from net.imglib2 import FinalInterval
from sc.fiji.hdf5 import HDF5ImageJ
from trainableSegmentation import WekaSegmentation


def compute_split(func, divX, divY, margin, imp, fargs):
    image = cs.convert(imp, Dataset)
    sizeX = image.dimension(Axes.X)
    sizeY = image.dimension(Axes.Y)
    sizeZ = image.dimension(Axes.Z)
    cropX = int(sizeX / divX)
    cropY = int(sizeY / divY)
    merged = None
    for k in range(0, divX):
        for l in range (0, divY):
            ox = margin if k > 0 else 0
            oy = margin if l > 0 else 0
            bx = k * cropX - ox
            by = l * cropY - oy
            lx = cropX + (1 if (k == 0 or k == divX - 1) else 2) * margin
            ly = cropY + (1 if (l == 0 or l == divY - 1) else 2) * margin
            px = -(k * cropX)
            py = -(l * cropY)
            region = FinalInterval.createMinSize(bx, by, 0, lx, ly, sizeZ)
            inputimg = cs.convert(ops.run("crop", image, region), ImagePlus)
            resultimg = cs.convert(func(inputimg, *fargs), Dataset)
            region = FinalInterval.createMinSize(ox, oy, 0, cropX, cropY, sizeZ)
            computed = ops.run("crop", resultimg, region)
            extended = ops.run("transform.extendZeroView", filtered)
            padding = FinalInterval.createMinSize(px, py, 0, sizeX, sizeY, sizeZ)
            padded = ops.run("zeroMinView", ops.run("transform.intervalView", extended, padding))
            merged = padded if merged is None else ops.run("math.add", merged, padded)
    return cs.convert(merged, ImagePlus)

def classify_image(weka, imagefile, dataset = None):
    print "Opening image: " + imagefile
    if imagefile.endswith('.h5') and dataset:
        imp = HDF5ImageJ.hdf5read(str(imagefile), dataset, 'zyx')
        outfile = imagefile
    else:
        imp = cs.convert(io.open(imagefile), ImagePlus)
        name, extension = os.path.splitext(imagefile)
        outfile = imagefile.replace(extension, '.h5')
    if imp:
        print "Classifying image..."
        start = time.time()
        #pmap = weka.applyClassifier(imp, 0, True)
        pmap = compute_split(weka.applyClassifier, 2, 2, 32, imp, (0, True))
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

classify_image(weka, str(imagefile), dataset)

