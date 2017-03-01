import os, sys

from javax.swing import (BoxLayout, DefaultListModel, ImageIcon, JButton, JFrame, JPanel,
        JPasswordField, JLabel, JTextArea, JTextField, JScrollPane,
        JList, JCheckBox, DefaultListCellRenderer,
        ListSelectionModel, SwingConstants, WindowConstants)
from java.awt import Component, GridBagLayout, GridBagConstraints, Insets, Color
from java.awt.event import WindowEvent, WindowAdapter

from ij import IJ, ImagePlus, ImageStack, ImageListener
from ij.io import DirectoryChooser, FileSaver
from ij.gui import Roi, ShapeRoi, GenericDialog
from ij.measure import ResultsTable
from ij.plugin import Duplicator, ChannelSplitter, RGBStackMerge, ContrastEnhancer, ZProjector
from ij.process import StackProcessor
from loci.plugins import BF
from loci.formats import UnknownFormatException
from fiji.threshold import Auto_Threshold
from algorithms import MandersColocalization
from gadgets import DataContainer
from gadgets import ThresholdMode
from net.imglib2 import TwinCursor
from net.imglib2.img import ImagePlusAdapter
from net.imglib2.view import Views


class MandersPlugin(ImageListener, WindowAdapter):

	def __init__(self):
		self.imp = None
		self.preview = None
		self.createMainWindow()
		self.cells = None
		self.files = []
		self.results = ResultsTable()
		ImagePlus.addImageListener(self)
		self.selectInputDir()
		self.selectOutputDir()
		self.pairs = []
		self.methods = []
		self.processNextFile()

	def selectInputDir(self):
		inputDialog = DirectoryChooser("Please select a directory contaning your images")
		inputDir = inputDialog.getDirectory()
		for imageFile in os.listdir(inputDir):
			self.files.append(inputDir + imageFile)

	def selectOutputDir(self):
		outputDialog = DirectoryChooser("Please select a directory to save your results")
		self.outputDir = outputDialog.getDirectory()
		
	def closeImage(self):
		if self.imp is not None:
			self.imp.close()
			self.imp = None
		if self.preview is not None:
			self.preview.close()
			self.preview = None

	def openImage(self, imageFile):
		try:
			images = BF.openImagePlus(imageFile)
			self.imp = images[0]
		except UnknownFormatException:
			return None
		if self.imp.getNChannels() < 2:
			IJ.error("Bad image format", "Image must contain at lease 2 channels!")
			return None
		if not self.pairs or \
			not self.methods:
			self.getOptionsDialog(self.imp)
		title = self.imp.title
		self.imp.title = title[:title.rfind('.')]
		return self.imp

	def getOptionsDialog(self, imp):
		thr_methods = ["None", "Default", "Huang", "Intermodes", "IsoData",  "Li", "MaxEntropy","Mean", "MinError(I)", "Minimum", "Moments", "Otsu", "Percentile", "RenyiEntropy", "Shanbhag" , "Triangle", "Yen"]
		gd = GenericDialog("Please select channels to collocalize")
		for i in range(1, imp.getNChannels() + 1):
			gd.addChoice("Threshold method for channel %i" % i, thr_methods, "None")
		gd.showDialog()
		if gd.wasCanceled():
			self.exit()
		channels = []
		for i in range(1, imp.getNChannels() + 1):
			method = gd.getNextChoice()
			self.methods.append(method)
			if method != "None":
				channels.append(i)
		for x in channels:
			for y in channels:
				if x < y:
					self.pairs.append((x, y))

	def processNextFile(self):
		if self.files:
			imageFile = self.files.pop(0)
			return self.processFile(imageFile)
		else:
			return False
			
	def processFile(self, imageFile):
		imp = self.openImage(imageFile)
		if imp is not None:
			cell = Cell(imp.NSlices, 1)
			self.cells = DefaultListModel()
			self.cells.addElement(cell)
			self.showMainWindow(self.cells)
			if self.checkbox3D.isSelected():
				self.displayImage(imp)
			else:
				self.displayImage(imp, False)
				self.preview = self.previewImage(imp)
				self.displayImage(self.preview)
			return True
		else:
			return self.processNextFile()
	
	def displayImage(self, imp, show = True):
		imp.setDisplayMode(IJ.COMPOSITE)
		enhancer = ContrastEnhancer()
		enhancer.setUseStackHistogram(True)
		splitter = ChannelSplitter()
		for c in range(1, imp.getNChannels() + 1):
			imp.c = c
			enhancer.stretchHistogram(imp, 0.35)
		if show:
			imp.show()

	def previewImage(self, imp):
		roi = imp.getRoi()
		splitter = ChannelSplitter()
		channels = []
		for c in range(1, imp.getNChannels() + 1):
			channel = ImagePlus("Channel %i" % c, splitter.getChannel(imp, c))
			projector = ZProjector(channel)
			projector.setMethod(ZProjector.MAX_METHOD)
			projector.doProjection()
			channels.append(projector.getProjection())
		image = RGBStackMerge.mergeChannels(channels, False)
		image.title = imp.title + " MAX Intensity"
		image.luts = imp.luts
		imp.setRoi(roi)
		return image

	def getCroppedChannels(self, imp, cell):
		splitter = ChannelSplitter()
		imp.setRoi(None)
		if cell.mode3D:
			cropRoi = cell.getCropRoi()
		else:
			cropRoi = cell.roi
		if cropRoi is None:
			return None
		crop = cropRoi.getBounds()
		channels = []
		for c in range(1, imp.getNChannels() + 1):
			slices = ImageStack(crop.width, crop.height)
			channel = splitter.getChannel(imp, c)
			for z in range(1, channel.getSize() + 1):
				zslice = channel.getProcessor(z)
				zslice.setRoi(cropRoi)
				nslice = zslice.crop()
				if cell.mode3D:
					oroi = cell.slices.get(z - 1).roi	
				else:
					oroi = cell.roi
				if oroi is not None:
					roi = oroi.clone()
					bounds = roi.getBounds()
					roi.setLocation(bounds.x - crop.x, bounds.y - crop.y)
					nslice.setColor(Color.black)
					nslice.fillOutside(roi)
					slices.addSlice(nslice)
			channels.append(ImagePlus("Channel %i" % c, slices))
		return channels

	def getThreshold(self, imp, method):
		thresholder = Auto_Threshold()
		duplicator = Duplicator()
		tmp = duplicator.run(imp)
		return thresholder.exec(tmp, method, False, False, True, False, False, True)

	def getContainer(self, impA, impB):
		imgA = ImagePlusAdapter.wrap(impA)
		imgB = ImagePlusAdapter.wrap(impB)
		return DataContainer(imgA, imgB, 1, 1, "imageA", "imageB")

	def getManders(self, imp, cell):
	
		### Crop channels according to cell mask
		channels = self.getCroppedChannels(imp, cell)
		if channels is None:
			return None
			
		### Calculate channel thresholds
		thrs = []
		thrimps = []
		for c, method in enumerate(self.methods):
			if method != "None":
				thr, thrimp = self.getThreshold(channels[c], method)
			else:
				thr, thrimp = None, None
			thrs.append(thr)
			thrimps.append(thrimp)
		
		### Calculate manders colocalization
		manders = MandersColocalization()
		raws = []
		thrds = []
		for chA, chB in self.pairs:
			container = self.getContainer(channels[chA - 1], channels[chB - 1])
			img1 = container.getSourceImage1()
			img2 = container.getSourceImage2()
			mask = container.getMask()
			cursor = TwinCursor(img1.randomAccess(), img2.randomAccess(), Views.iterable(mask).localizingCursor())
			rtype = img1.randomAccess().get().createVariable()
			raw = manders.calculateMandersCorrelation(cursor, rtype)
			rthr1 = rtype.copy()
			rthr2 = rtype.copy()
			rthr1.set(thrs[chA - 1])
			rthr2.set(thrs[chB - 1])
			cursor.reset()
			thrd = manders.calculateMandersCorrelation(cursor, rthr1, rthr2, ThresholdMode.Above)
			raws.append(raw)
			thrds.append(thrd)
		
		return (channels, thrimps, thrs, raws, thrds)

	def saveMultichannelImage(self, title, channels, luts):
		tmp = RGBStackMerge.mergeChannels(channels, False)
		tmp.luts = luts
		saver = FileSaver(tmp)
		saver.saveAsTiffStack(self.outputDir + title + ".tif")
		tmp.close()

	def createMainWindow(self):
		self.frame = JFrame('Select cells and ROIs',
			defaultCloseOperation = JFrame.DISPOSE_ON_CLOSE
		)
		self.frame.setLayout(GridBagLayout())
		self.frame.addWindowListener(self)

		self.frame.add(JLabel("Cells"),
			GridBagConstraints(0, 0, 1, 1, 0, 0,
				GridBagConstraints.CENTER, GridBagConstraints.NONE,
				Insets(5, 2, 2, 0), 0, 0
		))
		
		self.cellList = JList(DefaultListModel(),
			selectionMode = ListSelectionModel.SINGLE_SELECTION,
			cellRenderer = MyRenderer(),
			selectedIndex = 0,
			valueChanged = self.selectCell
		)
		self.frame.add(JScrollPane(self.cellList),
			GridBagConstraints(0, 1, 1, 5, .5, 1,
				GridBagConstraints.CENTER, GridBagConstraints.BOTH,
				Insets(0, 2, 2, 0), 0, 0
		))

		self.frame.add(JButton('Add cell', actionPerformed = self.addCell),
			GridBagConstraints(1, 2, 1, 2, 0, .25,
				GridBagConstraints.CENTER, GridBagConstraints.NONE,
				Insets(0, 0, 0, 0), 0, 0
		))
    	
		self.frame.add(JButton('Remove cell', actionPerformed = self.removeCell),
			GridBagConstraints(1, 4, 1, 2, 0, .25,
				GridBagConstraints.CENTER, GridBagConstraints.NONE,
				Insets(0, 5, 0, 5), 0, 0
		))
		
		self.frame.add(JLabel("Slices"),
			GridBagConstraints(0, 6, 1, 1, 0, 0,
				GridBagConstraints.CENTER, GridBagConstraints.NONE,
				Insets(5, 2, 2, 0), 0, 0
		))
		
		self.sliceList = JList(DefaultListModel(),
			selectionMode = ListSelectionModel.SINGLE_SELECTION,
			cellRenderer = MyRenderer(),
			selectedIndex = 0,
			valueChanged = self.selectSlice
		)
		self.frame.add(JScrollPane(self.sliceList),
			GridBagConstraints(0, 7, 1, 5, .5, 1,
				GridBagConstraints.CENTER, GridBagConstraints.BOTH,
				Insets(0, 2, 2, 0), 0, 0
		))

		self.frame.add(JButton('Update ROI', actionPerformed = self.updateSlice),
			GridBagConstraints(1, 8, 1, 2, 0, .25,
				GridBagConstraints.CENTER, GridBagConstraints.NONE,
				Insets(0, 0, 0, 0), 0, 0
		))

		self.frame.add(JButton('Done', actionPerformed = self.doneSelecting),
			GridBagConstraints(1, 10, 1, 2, 0, .25,
				GridBagConstraints.CENTER, GridBagConstraints.NONE,
				Insets(0, 0, 0, 0), 0, 0
		))

		self.checkbox3D = JCheckBox('3D selection mode', True, actionPerformed=self.toggle3D)
		self.frame.add(self.checkbox3D,
			GridBagConstraints(0, 13, 2, 1, 0, 1,
				GridBagConstraints.WEST, GridBagConstraints.NONE,
				Insets(0, 0, 0, 0), 0, 0
		))

	def showMainWindow(self, cells = None):
		if cells is not None:
			self.cellList.model = cells
			if cells:
				self.cellList.selectedIndex = 0
		self.frame.pack()
		self.frame.visible = True

	def hideMainWindow(self):
		self.frame.visible = False

	def closeMainWindow(self):
		self.frame.dispose()

	def toggle3D(self, event):
		mode3D = self.checkbox3D.isSelected()
		if mode3D:
			self.sliceList.enabled = True
			if self.imp is not None:
				self.imp.show()
			if self.preview is not None:
				self.preview.hide()
		else:
			self.sliceList.enabled = False
			if self.preview is None:
				self.preview = self.previewImage(self.imp)
				self.displayImage(self.preview)
			else:
				self.preview.show()
			if self.imp is not None:
				self.imp.hide()
		selectedCell = self.cellList.selectedIndex
		if selectedCell >= 0:
			cell = self.cells.get(selectedCell)
			self.sliceList.model = cell.slices
			self.sliceList.selectedIndex = 0
		
	def addCell(self, event):
		size = self.cells.size()
		if (size > 0):
			last = self.cells.get(size - 1)
			n = last.n + 1
		else:
			n = 1
		self.cells.append(Cell(self.imp.NSlices, n))
		self.cellList.selectedIndex = size

	def removeCell(self, event):
		selected = self.cellList.selectedIndex
		if selected >= 0:
			self.cells.remove(self.cells.get(selected))
			if (selected >= 1):
				self.cellList.selectedIndex = selected - 1
			else:
				self.cellList.selectedIndex = 0

	def selectCell(self, event):
		selected = self.cellList.selectedIndex
		if selected >= 0:
			cell = self.cells.get(selected)
			self.sliceList.model = cell.slices
			self.sliceList.selectedIndex = 0
		else:
			self.sliceList.model = DefaultListModel()
		if self.preview is not None:
			self.preview.setRoi(cell.roi)

	def selectSlice(self, event):
		selectedCell = self.cellList.selectedIndex
		selectedSlice = self.sliceList.selectedIndex
		if selectedCell >= 0 and selectedSlice >= 0:
			cell = self.cells.get(selectedCell)
			image = self.imp
			mode3D = self.checkbox3D.isSelected()
			if image is not None and cell is not None and mode3D:
				roi = cell.slices.get(selectedSlice).roi
				if (image.z - 1 != selectedSlice):
					image.z = selectedSlice + 1				
				image.setRoi(roi, True)
			if self.preview is not None and not mode3D:
				self.preview.setRoi(cell.roi, True)

	def updateSlice(self, event):
		if self.checkbox3D.isSelected():
			self.updateSlice3D(self.imp)
		else:
			self.updateSlice2D(self.preview)

	def updateSlice3D(self, imp):
		selectedCell = self.cellList.selectedIndex
		selectedSlice = self.sliceList.selectedIndex
		if selectedCell >= 0 and selectedSlice >= 0 and imp is not None:
			cell = self.cells.get(selectedCell)
			impRoi = imp.getRoi()
			if cell is not None and impRoi is not None:
				index = selectedSlice + 1
				roi = ShapeRoi(impRoi, position = index)
				cell.mode3D = True
				cell.name = "Cell %i (3D)" % cell.n
				cell.slices.get(selectedSlice).roi = roi
				if (index + 1 <= cell.slices.size()):
					imp.z = index + 1			
			self.cellList.repaint(self.cellList.getCellBounds(selectedCell, selectedCell))
			self.sliceList.repaint(self.sliceList.getCellBounds(selectedSlice, selectedSlice))

	def updateSlice2D(self, imp):
		selectedCell = self.cellList.selectedIndex
		if selectedCell >= 0 and imp is not None:
			cell = self.cells.get(selectedCell)
			impRoi = imp.getRoi()
			if cell is not None and impRoi is not None:
				roi = ShapeRoi(impRoi, position = 1)
				cell.mode3D = False
				cell.name = "Cell %i (2D)" % cell.n
				cell.roi = roi	
			self.cellList.repaint(self.cellList.getCellBounds(selectedCell, selectedCell))
	
	def imageOpened(self, imp):
		pass

	def imageClosed(self, imp):
		pass

	def imageUpdated(self, imp):
		if self.checkbox3D.isSelected():
			if imp is not None:
				selectedCell = self.cellList.selectedIndex
				selectedSlice = imp.z - 1
			if imp == self.imp and selectedSlice != self.sliceList.selectedIndex:
				self.sliceList.selectedIndex = selectedSlice

	def doneSelecting(self, event):
		oluts = self.imp.luts
		luts = []
		channels = []
		for c, method in enumerate(self.methods):
			if method != "None":
				luts.append(oluts[c])
				channels.append(c)
		for cell in self.cells.toArray():
			manders = self.getManders(self.imp, cell)
			if manders is not None:
				chimps, thrimps, thrs, raws, thrds = manders
				index = self.cells.indexOf(cell) + 1
				title = "Cell_%i-" % index + self.imp.title
				self.saveMultichannelImage(title, chimps, oluts)
				title = "Cell_%i_thrd-" % index + self.imp.title
				self.saveMultichannelImage(title, thrimps, luts)
				self.results.incrementCounter()
				row = self.results.getCounter() - 1
				for i, thr in enumerate(thrs):
					if thr is not None:
						self.results.setValue("Threshold %i" % (i + 1), row, int(thr))
				for i, pair in enumerate(self.pairs):
					self.results.setValue("%i-%i M1 raw" % pair, row, float(raws[i].m1))
					self.results.setValue("%i-%i M2 raw" % pair, row, float(raws[i].m2))
					self.results.setValue("%i-%i M1 thrd" % pair, row, float(thrds[i].m1))
					self.results.setValue("%i-%i M2 thrd" % pair, row, float(thrds[i].m2))
		self.closeImage()
		if not self.processNextFile():
			print "All done - happy analysis!"
			self.results.show("Manders collocalization results")
			self.exit()

	def windowClosing(self, e):
		print "Closing plugin - BYE!!!"
		self.exit()

	def exit(self):
		ImagePlus.removeImageListener(self)
		self.closeImage()
		self.closeMainWindow()


class Cell(object):

	def __init__(self, nslices, n, mode3D = True):
		self.n = n
		self.roi = None
		self.slices = DefaultListModel()
		self.initSlices(nslices)
		self.name = "Cell %i (none)" % self.n
		self.mode3D = mode3D
	
	def initSlices(self, nslices):
		for i in range(1, nslices + 1):
			aslice = Slice("Slice %i" % i)
			self.slices.addElement(aslice)

	def isDefined(self):
		if self.mode3D:
			size = self.slices.size()
			if size <= 0:
				return False
			for i in range(0, size):
				aslice = self.slices.get(i)
				if not aslice.isDefined():
					return False
		else:
			if self.roi is None:
				return False
		return True
			
	def getCropRoi(self):
		crop = None
		for aslice in self.slices.toArray():
			roi = aslice.roi
			if roi is not None:
				if crop is None:
					crop = roi.clone()
				else:
					crop.or(roi)
		return crop

		
class Slice(object):

	def __init__(self, name):
		self.roi = None
		self.name = name

	def isDefined(self):
		return self.roi is not None


class MyRenderer(DefaultListCellRenderer):

	def getListCellRendererComponent(self, list, value, index, isSelected, cellHasFocus):
		c = DefaultListCellRenderer.getListCellRendererComponent(
			self, list, value, index, isSelected, cellHasFocus
		)
		self.setText(value.name)
		if isSelected and not value.isDefined():
			self.setBackground(Color.red)
		if not isSelected and not value.isDefined():
			self.setForeground(Color.red)
		
		return c


colocalizer = MandersPlugin()
