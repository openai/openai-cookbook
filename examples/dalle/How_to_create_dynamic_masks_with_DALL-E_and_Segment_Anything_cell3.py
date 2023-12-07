import cv2
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib import rcParams
import numpy as np
import openai
import os
from PIL import Image
import requests
from segment_anything import sam_model_registry, SamAutomaticMaskGenerator, SamPredictor
import torch

# Set directories for generation images and edit images
base_image_dir = os.path.join("images", "01_generations")
mask_dir = os.path.join("images", "02_masks")
edit_image_dir = os.path.join("images", "03_edits")

# Point to your downloaded SAM model
sam_model_filepath = "./sam_vit_h_4b8939.pth"

# Initiate SAM model
sam = sam_model_registry["default"](checkpoint=sam_model_filepath)