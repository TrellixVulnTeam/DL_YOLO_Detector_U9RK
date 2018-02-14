import numpy as np
import xml.etree.ElementTree as ET
import cv2
import pickle
from sklearn.utils import shuffle
import os
def xml_as_tensor(xml_path, dst_img_size, name_converter, classes):
    """
    Returns presence tensor [img-size, img_size, C] encoded as one hot, where objects are present
    """
    tree = ET.parse(xml_path)
    size = tree.find('size')
    width = int(size.find('width').text)
    height = int(size.find('height').text)
    if height == 0 or width == 0:
        raise Exception

    h_ratio = dst_img_size / height
    w_ratio = dst_img_size / width

    label = np.zeros(shape=[dst_img_size, dst_img_size, len(classes)], dtype=np.float32)
    objs = tree.findall('object')

    for obj in objs:
        bbox = obj.find('bndbox')
        xmin = int(float(bbox.find('xmin').text) * w_ratio)
        xmax = int(float(bbox.find('xmax').text) * w_ratio)
        ymin = int(float(bbox.find('ymin').text) * h_ratio)
        ymax = int(float(bbox.find('ymax').text) * h_ratio)
        class_index = classes.index(name_converter[obj.find('name').text.lower().strip()])
        label[ymin: ymax, xmin: xmax, class_index] = 1

    return label

def generate_cell_net_data(root_folder, img_size, name_converter, classes):
    images_path = 'data/imagenet/detection_images/'
    xmls_path = 'data/imagenet/detection_annotations/'

    t_images_dir = os.path.join(root_folder, 'train_images')
    t_labels_dir = os.path.join(root_folder, 'train_labels')
    v_images_dir = os.path.join(root_folder, 'val_images')
    v_labels_dir = os.path.join(root_folder, 'val_labels')

    if not os.path.isdir(t_images_dir):
        os.mkdir(t_images_dir)
    if not os.path.isdir(t_labels_dir):
        os.mkdir(t_labels_dir)
    if not os.path.isdir(v_images_dir):
        os.mkdir(v_images_dir)
    if not os.path.isdir(v_labels_dir):
        os.mkdir(v_labels_dir)

    # # one time process, don't use it
    # images_filenames = sorted([images_path + name for name in os.listdir(images_path)])
    # xmls_filenames = sorted([xmls_path + name for name in os.listdir(xmls_path)])
    # images_filenames, xmls_filenames = shuffle(images_filenames, xmls_filenames)
    # t_images_filenames = images_filenames[:int(0.9 * len(images_filenames))]
    # t_xmls_filenames = xmls_filenames[:int(0.9 * len(xmls_filenames))]
    # v_images_filenames = images_filenames[int(0.9 * len(images_filenames)):]
    # v_xmls_filenames = xmls_filenames[int(0.9 * len(xmls_filenames)):]
    # pickle.dump([t_images_filenames, t_xmls_filenames, v_images_filenames, v_xmls_filenames], open(os.path.join(root_folder, 'dataset_info.p'), 'wb'))

    t_images_filenames, t_xmls_filenames, v_images_filenames, v_xmls_filenames = pickle.load(open(os.path.join(root_folder, 'dataset_info.p'), 'rb'))

    # train data
    for i, (imagename, xmlname) in enumerate(zip(t_images_filenames, t_xmls_filenames)):
        print('\rTraining data: %d of %d' % (i, len(t_images_filenames)), end='', flush=True)
        img = cv2.imread(imagename)
        img = cv2.resize(img, dsize=(img_size, img_size))
        label = xml_as_tensor(xmlname, img_size, name_converter, classes)

        cv2.imwrite(os.path.join(t_images_dir, str(i) + '.jpg'), img)
        np.save(os.path.join(t_labels_dir, str(i) + '.npy'), label)

    # validation data
    for i, (imagename, xmlname) in enumerate(zip(v_images_filenames, v_xmls_filenames)):
        print('\rValidation data: %d of %d' % (i, len(v_images_filenames)), end='', flush=True)
        img = cv2.imread(imagename)
        img = cv2.resize(img, dsize=(img_size, img_size))
        label = xml_as_tensor(xmlname, img_size, name_converter, classes)

        cv2.imwrite(os.path.join(v_images_dir, str(i) + '.jpg'), img)
        np.save(os.path.join(v_labels_dir, str(i) + '.npy'), label)



def resize_label(label, S, C, src_img_size, threshold_area):
    resized_label = np.zeros([S, S, C], dtype=np.float32)
    for y in range(S):
        for x in range(S):
            x_s = int(x * src_img_size / S)
            x_e = int((x + 1) * src_img_size / S)
            y_s = int(y * src_img_size / S)
            y_e = int((y + 1) * src_img_size / S)
            column = label[y_s: y_e, x_s: x_e]
            sums = np.sum(np.sum(column, axis=0), axis=0)
            sums[sums < threshold_area] = 0
            sums[sums >= threshold_area] = 1
            resized_label[y, x] = sums
    return resized_label

def image_read(imgname):
    image = cv2.imread(imgname)
    image = (image / 255.0) * 2.0 - 1.0
    return image

def embed_output(float_img, logits, threshold, S, src_img_size):
    logits[logits >= threshold] = 1
    logits[logits < threshold] = 0
    # tymczasowo scalam wszystko do jednego, dla celow debugowania
    overlay = np.max(logits, axis = 2)
    output = np.ones_like(float_img)[..., 0]
    for y in range(S):
        for x in range(S):
            x_s = int(x * src_img_size / S)
            x_e = int((x + 1) * src_img_size / S)
            y_s = int(y * src_img_size / S)
            y_e = int((y + 1) * src_img_size / S)
            output[y_s: y_e, x_s: x_e] *= overlay[y, x]
    output = np.stack([np.zeros_like(output), output, np.zeros_like(output)], axis=2)
    return cv2.addWeighted(float_img, 0.6, output, 0.4, 0)

def possibly_create_dirs(embedded_images_path, model_to_save_path):
    if not os.path.isdir(embedded_images_path):
        os.mkdir(embedded_images_path)
    if not os.path.isdir(model_to_save_path):
        os.mkdir(model_to_save_path)