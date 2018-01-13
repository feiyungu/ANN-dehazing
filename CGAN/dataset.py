import numpy as np
import os
import cv2
import random

class DataSet(object):
    def __init__(self, data_dir, batch_size, max_size=-1):
        self.DATA_SIZE = 224
        self.data_dir = data_dir
        self.batch_size = batch_size
        self.max_size = max_size
        self.gen_image_list()
        self.cur_index = 0

    def gen_image_list(self):
        self.image_list = []
        self.total_images = 0
        for file_name in os.listdir(self.data_dir):
            if (file_name.endswith("jpg")):
                self.image_list.append(file_name)
                self.total_images += 1
                if (self.max_size > 0 and self.total_images >= self.max_size):
                    break

        self.total_batches = (self.max_size // self.batch_size) if self.max_size > 0 else (self.total_images // self.batch_size)

    def read_image(self, image_name):
        image_path = os.path.join(self.data_dir, image_name)
        img_data = cv2.imread(image_path)
        height, weight, channels = img_data.shape

        dif = (weight//2 - height) // 2
        original_img_large = img_data[0:height, dif:(weight//2-dif), 0:channels]
        hazed_img_large = img_data[0:height, (weight//2+dif):(weight-dif), 0:channels]
        # print original_img_large.shape, hazed_img_large.shape

        original_img = cv2.resize(original_img_large, (self.DATA_SIZE, self.DATA_SIZE)) / 255.0
        hazed_img = cv2.resize(hazed_img_large, (self.DATA_SIZE, self.DATA_SIZE)) / 255.0

        original_img = original_img * 2 - 1
        hazed_img = hazed_img * 2 - 1

        return original_img, hazed_img 

    def shuffle_data(self):
        random.shuffle(self.image_list)

    def next_batch(self):
        self.end_index = min([self.cur_index + self.batch_size, self.total_images])
        array_hazed_img = []
        array_original_img = []
        for i in range(self.cur_index, self.end_index):
            # print(self.image_list[i])
            original_img, hazed_img = self.read_image(self.image_list[i])

            array_hazed_img.append(hazed_img)
            array_original_img.append(original_img)

        self.cur_index += self.batch_size
        if (self.cur_index >= self.total_images):
            self.cur_index = 0
            self.shuffle_data()
        return np.array(array_hazed_img), np.array(array_original_img)

if __name__ == "__main__":
    dataset = DataSet("../data/output/", 2)

    for i in range(10):
        hazed_img, original_img = dataset.next_batch()
        print(hazed_img.shape, original_img.shape)
