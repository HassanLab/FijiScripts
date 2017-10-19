#!/bin/bash

ImageJ --headless --run ~/src/Fiji/FijiScripts/ato-ipc/Preprocessing.py \
    "images_sequence_dir='$1',image_extension='.tif',channel_ids='561 488 637'"
ilastik --headless --project=/Users/radoslaw.ejsmont/Desktop/Natalia/NataliaVideoSegmentation.ilp --export_source="Pixel Probabilities" /Users/radoslaw.ejsmont/Desktop/Natalia/Latest\ video/Latest\ video\ -\ Ilastik\ Raw\ Input.h5
