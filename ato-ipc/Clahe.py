from ij import IJ, ImagePlus, ImageStack
from ij.plugin import Duplicator
from ij.plugin.filter import GaussianBlur, RankFilters
from java.lang import Runtime
from mcib3d.image3d.processing import FastFilters3D
from mpicbg.ij.clahe import Flat


sigma = 10
zsigma = 2.5
blocksize = 50
maximum_slope = 10

#sigma = 5
#blocksize = 20
#maximum_slope = 20
histogram_bins = 256
composite = False
mask = None

duplicator = Duplicator()
filters = FastFilters3D()

image = IJ.getImage()
image = duplicator.run(image)
stack = filters.filterImageStack(image.getStack(), FastFilters3D.MEDIAN, sigma, sigma, zsigma, Runtime.getRuntime().availableProcessors() - 2, True)
n_slices = stack.getSize()

processed = ImageStack(image.getWidth(), image.getHeight())

for index in range(1, n_slices+1):
  print "Processing slice " + str(index)
  ip = stack.getProcessor(index)
  img = ImagePlus("slice", ip)
  Flat.getInstance().run(img, blocksize, histogram_bins, maximum_slope, mask, composite)
  processed.addSlice(img.getProcessor())

image = ImagePlus("result", processed)
binary = duplicator.run(image)
IJ.run(binary, "Make Binary", "method=Yen background=Dark calculate black");
image.show()
binary.show()

