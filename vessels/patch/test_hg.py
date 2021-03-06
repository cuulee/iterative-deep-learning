# Includes
import os
import numpy as np
import bifurcations_toolbox as tb
import torch
from torch.autograd import Variable
import Nets as nt
import scipy.misc
from PIL import Image
from photutils import find_peaks
from astropy.stats import sigma_clipped_stats
import json


# Setting of parameters
# Parameters in p are used for the name of the model
p = {}
p['useRandom'] = 1  # Shuffle Images
p['useAug'] = 0  # Use Random rotations in [-30, 30] and scaling in [.75, 1.25]
p['inputRes'] = (64, 64)  # Input Resolution
p['outputRes'] = (64, 64)  # Output Resolution (same as input)
p['g_size'] = 64  # Higher means narrower Gaussian
p['trainBatch'] = 1  # Number of Images in each mini-batch
p['numHG'] = 2  # Number of Stacked Hourglasses
p['Block'] = 'ConvBlock'  # Select: 'ConvBlock', 'BasicBlock', 'BottleNeck'
p['GTmasks'] = 0 # Use GT Vessel Segmentations as input instead of Retinal Images

junctions = False
connected = True
from_same_vessel = False
bifurcations_allowed = True

# Setting other parameters
numHGScales = 4  # How many times to downsample inside each HourGlass
useTest = 1  # See evolution of the test set when training?
nTestInterval = 10  # Run on test set every nTestInterval iterations
model_dir = './results_dir_vessels/'
gpu_id = int(os.environ['SGE_GPU'])  # Select which GPU, -1 if CPU
epoch = 1800

if junctions:
    modelName = tb.construct_name(p, "HourGlass-junctions")
    db_root_dir = './results_dir_vessels/gt_test_junctions/'
    output_dir = './results_dir_vessels/results_junctions/'
else:
    if not connected:
        modelName = tb.construct_name(p, "HourGlass")
        db_root_dir = './results_dir_vessels/gt_test_not_connected/'
        output_dir = './results_dir_vessels/results_not_connected/'
    else:
        if from_same_vessel:
            if bifurcations_allowed:
                modelName = tb.construct_name(p, "HourGlass-connected-same-vessel")
                db_root_dir = './results_dir_vessels/gt_test_connected_same_vessel/'
                output_dir = './results_dir_vessels/results_connected_same_vessel/'
            else:
                modelName = tb.construct_name(p, "HourGlass-connected-same-vessel-wo-bifurcations")
                db_root_dir = './results_dir_vessels/gt_test_connected_same_vessel_wo_bifurcations/'
                output_dir = './results_dir_vessels/results_connected_same_vessel_wo_bifurcations/'
        else:
            modelName = tb.construct_name(p, "HourGlass-connected")
            db_root_dir = './results_dir_vessels/gt_test_connected/'
            output_dir = './results_dir_vessels/results_connected/'

# Define the Network and load the pre-trained weights as a CPU tensor
net = nt.Net_SHG(p['numHG'], numHGScales, p['Block'], 128, 1)
net.load_state_dict(torch.load(os.path.join(model_dir, os.path.join(model_dir, modelName+'_epoch-'+str(epoch)+'.pth')),
                               map_location=lambda storage, loc: storage))
# No need to back-propagate
for par in net.parameters():
    par.requires_grad = False

# Transfer to GPU if needed
if gpu_id >= 0:
    torch.cuda.set_device(device=gpu_id)
    net.cuda()

# Separate interactive testing
vis_res = 0

num_patches_per_image = 50
num_images = 20

for jj in range(0,num_patches_per_image):
    for ii in range(0,num_images):

        img = Image.open(os.path.join(db_root_dir, 'img_%02d_patch_%02d_img.png' %(ii+1,jj+1)))
        img = np.array(img, dtype=np.float32)

        if len(img.shape) == 2:
            image_tmp = img
            h, w = image_tmp.shape
            img = np.zeros((h, w, 3))
            img[:,:,0] = image_tmp
            img[:,:,1] = image_tmp
            img[:,:,2] = image_tmp
        img = img.transpose((2, 0, 1))
        img = torch.from_numpy(img)
        img = img.unsqueeze(0)

        inputs = img / 255 - 0.5

        # Forward pass of the mini-batch
        inputs = Variable(inputs)
        if gpu_id >= 0:
            inputs = inputs.cuda()

        output = net.forward(inputs)
        pred = np.squeeze(np.transpose(output[len(output)-1].cpu().data.numpy()[0, :, :, :], (1, 2, 0)))

        scipy.misc.imsave(output_dir + 'epoch_' + str(epoch) + '/img_%02d_patch_%02d.png' %(ii+1, jj+1), pred)
        np.save(output_dir + 'epoch_' + str(epoch) + '/img_%02d_patch_%02d.npy' %(ii+1, jj+1), pred)

        mean, median, std = sigma_clipped_stats(pred, sigma=3.0)
        threshold = median + (10.0 * std)
        sources = find_peaks(pred, threshold, box_size=3)

        data = {}
        data['peaks'] = []
        indxs = np.argsort(sources['peak_value'])
        for ii in range(0,len(indxs)):
            idx = indxs[len(indxs)-1-ii]
            data['peaks'].append({'x': sources['x_peak'][idx], 'y': sources['y_peak'][idx], 'value' : float(sources['peak_value'][idx])})

        with open(output_dir + 'epoch_' + str(epoch) + '/img_%02d_patch_%02d.json' %(ii+1, jj+1), 'w') as outfile:
            json.dump(data, outfile)

