# @File(label="Classifier to use") classifier
# @File(label="Image to classify") imagefile
# @String(label="Dataset to open", default="") dataset

# @IOService io
# @OpService ops
# @ConvertService cs
# @DatasetService ds

import time, csv, os, sys
from jarray import array

from ij import IJ, ImagePlus
from java.lang import System as javasystem
from net.imagej import Dataset, ImgPlus
from net.imagej.axis import Axes
from net.imglib2 import FinalInterval
from sc.fiji.hdf5 import HDF5ImageJ
from trainableSegmentation import WekaSegmentation, FeatureStack3D


def create_interval(sx, sy, lx, ly, image):
    dims = image.numDimensions()
    interval_s = []
    interval_e = []
    for d in range(0, dims):
        if image.axis(d).type() == Axes.X:
            interval_s.append(sx)
            interval_e.append(lx)
        elif image.axis(d).type() == Axes.Y:
            interval_s.append(sy)
            interval_e.append(ly)
        else:
            interval_s.append(image.min(d))
            interval_e.append(image.max(d) + 1)
    intervals = interval_s + interval_e
    return FinalInterval.createMinSize(*intervals)

def compute_split(func, divX, divY, margin, imp, fargs):
    image = cs.convert(imp, Dataset)
    sizeX = image.dimension(Axes.X)
    sizeY = image.dimension(Axes.Y)
    sizeZ = image.dimension(Axes.Z)
    cropX = int(sizeX / divX)
    cropY = int(sizeY / divY)
    merged = None
    processed = 1
    for k in range(0, divX):
        for l in range (0, divY):
            print "\tComputing split image (" + str(processed) + "/" + str(divX * divY) + ")..."
            processed = processed + 1
            ox = margin if k > 0 else 0
            oy = margin if l > 0 else 0
            bx = k * cropX - ox
            by = l * cropY - oy
            lx = cropX + (0 if (divX - 1 == 0) else (1 if (k == 0 or k == divX - 1) else 2)) * margin
            ly = cropY + (0 if (divY - 1 == 0) else (1 if (l == 0 or l == divY - 1) else 2)) * margin
            px = -(k * cropX)
            py = -(l * cropY)
            region = create_interval(bx, by, lx, ly, image)
            inputimg = cs.convert(ds.create(ops.run("crop", image, region)), ImagePlus)
            resultimp = func(inputimg, *fargs)
            resultimg = cs.convert(resultimp, Dataset)
            region = create_interval(ox, oy, cropX, cropY, resultimg)
            computed = ds.create(ops.run("crop", resultimg, region))
            extended = ops.run("transform.extendZeroView", computed)
            padding = create_interval(px, py, sizeX, sizeY, computed)
            padded = ops.run("zeroMinView", ops.run("transform.intervalView", extended, padding))
            merged = padded if merged is None else ops.run("math.add", merged, padded)
            resultimp.close()
    result = cs.convert(ds.create(merged), ImagePlus)
    return result

def apply_classifier(imp, weka, min_sigma, max_sigma, features):
    fs3d = FeatureStack3D(imp)
    fs3d.setMinimumSigma(min_sigma)
    fs3d.setMaximumSigma(max_sigma)
    fs3d.setEnableFeatures(features)
    computed = False
    attempts = 0
    while not computed:
        attempts = attempts + 1
        print "\t\tAttempting to compute features (" + str(attempts) + ")..."
        try:
            computed = fs3d.updateFeaturesMT()
        except Exception:
            computed = False
    fsa = fs3d.getFeatureStackArray()
    print "\t\tApplying classifier..."
    result = weka.applyClassifier(fsa, 0, True)
    result.setDimensions(weka.getNumOfClasses(), imp.getNSlices(), imp.getNFrames())
    result.setOpenAsHyperStack(True)
    fs3d = None
    fsa = None
    javasystem.gc()
    return result

def classify_image(weka, weka_params, imagefile, dataset = None):
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
        (min_sigma, max_sigma, features) = weka_params
        pmap = compute_split(apply_classifier, 2, 2, 32, imp, (weka, min_sigma, max_sigma, features))
        pmap.setDimensions(weka.getNumOfClasses(), imp.getNSlices(), imp.getNFrames())
        pmap.setOpenAsHyperStack(True)
        pmap.copyScale(imp)
    else:
        raise Exception("Error opening image!")
    if pmap:
        print "Image has been classified. Execution time: %.3f seconds" % abs(start - time.time())
        HDF5ImageJ.hdf5write(pmap, outfile, '/weka/pmap{c}', '%d', '%d', 0, False)
        pmap.close()
        imp.close()
    else:
        raise Exception("Error classifying image!")

def get_parameters(weka):
    header = weka.getTrainHeader()
    attributes = header.enumerateAttributes()
    delimiter = "_"
    features = [False] * len(FeatureStack3D.availableFeatures)
    min_sigma = sys.maxsize
    max_sigma = 0
    while attributes.hasMoreElements():
         a = attributes.nextElement()
         name = a.name()
         for key, feature in enumerate(FeatureStack3D.availableFeatures):
            if name.startswith(feature):
                features[key] = True
                if feature in ["Gaussian_blur", "Derivatives", "Difference_of_Gaussian", "Laplacian",
                              "Edges", "Minimum", "Maximum", "Mean", "Median", "Variance"]:
                    sigma = float(name.split(delimiter)[-1])
                    min_sigma = sigma if sigma < min_sigma else min_sigma
                    max_sigma = sigma if sigma > max_sigma else max_sigma
                
    return (min_sigma, max_sigma, array(features, 'z'))

if os.path.isfile(str(classifier)):
    weka = WekaSegmentation(True)
    print "Loading the classifier..."
    start = time.time()
    success = weka.loadClassifier(str(classifier))
    weka_params = get_parameters(weka)
    
    if success:
        print "Classifier has been loaded. Execution time: %.3f seconds" % abs(start - time.time())
    else:
        raise Exception("Error loading classifier!")

classify_image(weka, weka_params, str(imagefile), dataset)
