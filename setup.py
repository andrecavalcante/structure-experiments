import torch
import socket
import argparse
import json
import glob
import os
import shutil

from torchvision import datasets, transforms
from util import *

hostname = socket.gethostname()

def make_result_folder(opt, location):
    if not os.path.exists(location):
        os.makedirs(location)
    else:
        filelist = glob.glob(location + "/*")
        if len(filelist) > 0:
            clear = query_yes_no(
                "This network name is already in use. "
                "Continuing will delete all of the files in the directory.\n"
                "Files: \n" + "\n".join(filelist) + "\n\n"
                "Continue?")
            if not clear:
                print("Not deleting anything. Quitting instead.")
                exit()
            for f in filelist:
                if os.path.isdir(f):
                    shutil.rmtree(f)
                else:
                    os.remove(f)

    # copy over the old results if we're resuming
    if hasattr(opt, 'resume') and opt.resume:
        shutil.copyfile(
            cp_opt['save'] + '/results.csv', opt.save + '/results.csv')

def write_options(opt, location):
    with open(location + "/opt.json", 'w') as f:
        serial_opt = json.dumps(vars(opt), indent=4, sort_keys=True)
        print(serial_opt)
        f.write(serial_opt)
        f.flush()

def load_checkpoint(opt):
    checkpoint = torch.load('results/' + opt.load + '/model.t7')
    model = checkpoint['model'].type(dtype)
    i = checkpoint['i']
    cp_opt = checkpoint['opt']

    # we're strictly trying to pick up where we left off
    # load everything just as it was (but rename)
    if opt.resume:
        setattrs(opt, cp_opt, exceptions=['load', 'resume', 'use_loaded_opt'])
        opt.name = cp_opt['name'] + '_'

    # if we want to use the options from the checkpoint, load them in
    # (skip the ones that don't make sense to load)
    if opt.use_loaded_opt:
        setattrs(opt, cp_opt, exceptions=[
            'name', 'load', 'sanity', 'resume', 'use_loaded_opt'
        ])
    return i, model

def load_dataset(opt):
    if opt.resume:
        data_path = 'results/' + opt.load + '/dataset.t7'
        print("Loading stored dataset from {}".format(data_path))
        data_checkpoint = torch.load(data_path)
        train_data = data_checkpoint['train_data']
        test_data = data_checkpoint['test_data']

    else:
        if hostname == 'zaan':
            data_path = '/speedy/data/' + opt.data
            # data_path = '/speedy/data/urban/5th_ave'
        else:
            data_path = '/misc/vlgscratch3/FergusGroup/wwhitney/' + opt.data
            # data_path = '/misc/vlgscratch3/FergusGroup/wwhitney/urban/5th_ave'

        # 'urban' datasets are in-memory stores
        if data_path.find('urban') >= 0:
            if not data_path[-3:] == '.t7':
                data_path = data_path + '/dataset.t7'

            print("Loading stored dataset from {}".format(data_path))
            data_checkpoint = torch.load(data_path)
            train_data = data_checkpoint['train_data']
            test_data = data_checkpoint['test_data']

            train_data.seq_len = opt.seq_len
            test_data.seq_len = opt.seq_len

            load_workers = 0

        elif opt.data == 'atari':
            train_data = AtariData(
                opt.game, 'train', opt.seq_len, opt.image_width)
            test_data = AtariData(
                opt.game, 'test', opt.seq_len, opt.image_width)
            load_workers = 0

        elif opt.data == 'balls':
            train_data = BounceData(
                opt.seq_len, opt.balls, opt.colors, opt.image_width)
            test_data = BounceData(
                opt.seq_len, opt.balls, opt.colors, opt.image_width)
            load_workers = 0

        elif opt.data == '1d_balls':
            train_data = HorizontalBounceData(
                opt.seq_len, opt.balls, opt.colors, opt.image_width)
            test_data = HorizontalBounceData(
                opt.seq_len, opt.balls, opt.colors, opt.image_width)
            load_workers = 0

        elif opt.data == 'mnist':
            train_data = datasets.MNIST('../data', train=True, download=True,
                transform=transforms.Compose([
                    transforms.Scale(opt.image_width),
                    transforms.ToTensor()]))
            test_data = datasets.MNIST('../data', train=False, 
                transform=transforms.Compose([
                    transforms.Scale(opt.image_width),
                    transforms.ToTensor()]))
            load_workers = 1

        # other video datasets are big and stored as chunks
        else:
            if hostname != 'zaan':
                scratch_path = '/scratch/wwhitney/' + opt.data
                vlg_path = '/misc/vlgscratch4/FergusGroup/wwhitney/' + opt.data

                data_path = vlg_path
                # if os.path.exists(scratch_path):
                #     data_path = scratch_path
                # else:
                #     data_path = vlg_path

            print("Loading stored dataset from {}".format(data_path))
            train_data, test_data = load_disk_backed_data(data_path)

            if opt.data_sparsity > 1:
                train_data.videos = [train_data.videos[i]
                                     for i in range(len(train_data.videos))
                                     if i % opt.data_sparsity == 0]
            load_workers = 4

            train_data.framerate = opt.fps
            test_data.framerate = opt.fps

            train_data.seq_len = opt.seq_len
            test_data.seq_len = opt.seq_len
    return train_data, test_data, load_workers