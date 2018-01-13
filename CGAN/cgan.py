import tensorflow as tf
import tensorlayer as tl
import os
import time
import math
import numpy as np
import vgg16
from dataset import DataSet
from utils import *
if "concat_v2" in dir(tf):
    def concat(tensors, axis, *args, **kwargs):
        return tf.concat_v2(tensors, axis, *args, **kwargs)
else:
    def concat(tensors, axis, *args, **kwargs):
        return tf.concat(tensors, axis, *args, **kwargs)

class CGAN(object):
    def __init__(self, sess, epoch, batch_size, z_dim, checkpoint_dir, model_name, model_dir, result_dir, log_dir, learning_rate=0.0001, lambda_d=1, lambda_p=1e-4, lambda_e=1, lambda_t=1):
        self.sess = sess
        self.epoch = epoch
        self.batch_size = batch_size
        self.z_dim = z_dim # dimension of noise vector
        self.learning_rate = learning_rate
        self.lambda_p = lambda_p
        self.lambda_d = lambda_d
        self.lambda_e = lambda_e
        self.beta1 = 0.5 # ???
        self.input_height = 224
        self.input_weight = 224
        self.input_channel = 3
        self.model_name = model_name

        self.log_dir = log_dir
        self.result_dir = result_dir
        self.checkpoint_dir = checkpoint_dir
        self.model_dir = model_dir
        self.test_set = DataSet("../data/testset", self.batch_size)
        self.train_set = DataSet("../data/output", self.batch_size)
        # self.data_X, self.data_Y = load_data()
        # self.num_batches = len(self.data_X) // self.batch_size
        self.num_batches = self.train_set.total_batches

    def Conv_BN_PReLu(self, network, input_channel, output_channel, scope, reuse, is_training, kernel_size=3):
        input_channel = int(input_channel)
        output_channel = int(output_channel)
        with tf.variable_scope(scope, reuse=reuse):
            tl.layers.set_name_reuse(reuse)
            network = tl.layers.Conv2dLayer(network,
                                shape=[kernel_size, kernel_size, input_channel, output_channel],
                                strides=[1, 1, 1, 1],
                                padding='SAME',
                                W_init=tf.truncated_normal_initializer(stddev=0.02),
                                b_init=tf.constant_initializer(value=0.0),
                                name=scope+'/conv')
            network = tl.layers.BatchNormLayer(network, is_train=is_training, name=scope+'/bn')
            network = tl.layers.PReluLayer(network, a_init=tf.constant_initializer(value=0.2), channel_shared=True, name=scope+'/pReLu')
            return network

    def DeConv_BN_ReLu(self, network, input_channel, output_channel, scope, reuse, is_training, kernel_size=3):
        input_channel = int(input_channel)
        output_channel = int(output_channel)
        with tf.variable_scope(scope, reuse=reuse):
            tl.layers.set_name_reuse(reuse)
            network = tl.layers.DeConv2dLayer(network,
                                              shape=[kernel_size, kernel_size, output_channel, input_channel],
                                              output_shape=[network.outputs.get_shape().as_list()[0], network.outputs.get_shape().as_list()[1], network.outputs.get_shape().as_list()[2], output_channel],
                                              strides=[1, 1, 1, 1],
                                              padding='SAME',
                                              W_init=tf.truncated_normal_initializer(stddev=0.02),
                                              b_init=tf.constant_initializer(value=0.0),
                                              name=scope + '/deconv')
            network = tl.layers.BatchNormLayer(network, act=tf.nn.relu, is_train=is_training, name=scope+'/bn')
            return network

    def discriminator(self, y, x, ndf=48, is_training=True, reuse=False):
        with tf.variable_scope("discriminator", reuse=reuse):

            # merge image and label

            '''
            y = tf.reshape(y, [self.batch_size, 1, 1, self.y_dim])
            x = conv_cond_concat(x, y)

            net = lrelu(conv2d(x, 64, 4, 4, 2, 2, name='d_conv1'))
            net = lrelu(bn(conv2d(net, 128, 4, 4, 2, 2, name='d_conv2'), is_training=is_training, scope='d_bn2'))
            net = tf.reshape(net, [self.batch_size, -1])
            net = lrelu(bn(linear(net, 1024, scope='d_fc3'), is_training=is_training, scope='d_bn3'))
            out_logit = linear(net, 1, scope='d_fc4')
            out = tf.nn.sigmoid(out_logit)

            return out, out_logit, net
            '''
            y = concat([x, y], 3)
            tl.layers.set_name_reuse(reuse)
            Input = tl.layers.InputLayer(y, "d_Input")
            CB_K = tl.layers.Conv2dLayer(Input,
                                        shape=[3, 3, 6, ndf],
                                        strides=[1, 1, 1, 1],
                                        padding='SAME',
                                        W_init=tf.truncated_normal_initializer(stddev=0.02),
                                        b_init=tf.constant_initializer(value=0.0),
                                        name='d_CB_K')
            CB_K = tl.layers.BatchNormLayer(CB_K, is_train=is_training, name="d_CB_K_BN")
            CBP_2K = self.Conv_BN_PReLu(CB_K, ndf, 2 * ndf, "d_CBP_2K", reuse, is_training)
            CBP_4K = self.Conv_BN_PReLu(CBP_2K, 2 * ndf, 4 * ndf, "d_CBP_4K", reuse, is_training)
            CBP_8K = self.Conv_BN_PReLu(CBP_4K, 4 * ndf, 8 * ndf, "d_CBP_8K", reuse, is_training)
            Conv_1 = tl.layers.Conv2dLayer(CBP_8K,
                                        shape=[3, 3, 8 * ndf, 1],
                                        strides=[1, 1, 1, 1],
                                        padding='SAME',
                                        W_init=tf.truncated_normal_initializer(stddev=0.02),
                                        b_init=tf.constant_initializer(value=0.0),
                                        name='d_Conv_1')
            out = tf.nn.sigmoid(Conv_1.outputs, name = "d_out")
            return out, Conv_1.outputs, Conv_1

    def generator(self, z, x, ngf=64, is_training=True, reuse=False):
        with tf.variable_scope("generator", reuse=reuse):
            # merge noise and label
            '''
            z = concat([z, x], 1)

            net = tf.nn.relu(bn(linear(z, 1024, scope='g_fc1'), is_training=is_training, scope='g_bn1'))
            net = tf.nn.relu(bn(linear(net, 128 * 7 * 7, scope='g_fc2'), is_training=is_training, scope='g_bn2'))
            net = tf.reshape(net, [self.batch_size, 7, 7, 128])
            net = tf.nn.relu(
                bn(deconv2d(net, [self.batch_size, 14, 14, 64], 4, 4, 2, 2, name='g_dc3'), is_training=is_training,
                   scope='g_bn3'))

            out = tf.nn.sigmoid(deconv2d(net, [self.batch_size, 28, 28, 1], 4, 4, 2, 2, name='g_dc4'))
//
            return out
        '''
            #z = concat([z, x], 3)
            tl.layers.set_name_reuse(reuse)
            Input = tl.layers.InputLayer(x, "g_Input")
            G_CBP_K1 = self.Conv_BN_PReLu(Input, 3, ngf, "g_CBPK_1", reuse, is_training)
            G_CBP_K2 = self.Conv_BN_PReLu(G_CBP_K1, ngf, ngf, "g_CBPK_2", reuse, is_training)
            G_CBP_K3 = self.Conv_BN_PReLu(G_CBP_K2, ngf, ngf, "g_CBPK_3", reuse, is_training)
            G_CBP_K4 = self.Conv_BN_PReLu(G_CBP_K3, ngf, ngf, "g_CBPK_4", reuse, is_training)
            G_CBP_K_div_2 = self.Conv_BN_PReLu(G_CBP_K4, ngf, ngf / 2, "g_CBPK/2", reuse, is_training)
            G_CBP_1 = self.Conv_BN_PReLu(G_CBP_K_div_2, ngf / 2, 1, "g_CBP1", reuse, is_training)
            G_DBR_K_div_2 = self.DeConv_BN_ReLu(G_CBP_1, 1, ngf / 2, "g_DBRK/2", reuse, is_training)
            G_DBR_K1 = self.DeConv_BN_ReLu(G_DBR_K_div_2, ngf / 2, ngf, "g_DBRK_1", reuse, is_training)
            G_DBR_K1.outputs = G_DBR_K1.outputs + G_CBP_K4.outputs
            G_DBR_K2 = self.DeConv_BN_ReLu(G_DBR_K1, ngf, ngf, "g_DBRK_2", reuse, is_training)
            G_DBR_K3 = self.DeConv_BN_ReLu(G_DBR_K2, ngf, ngf, "g_DBRK_3", reuse, is_training)
            G_DBR_K3.outputs = G_DBR_K3.outputs + G_CBP_K2.outputs
            G_DBR_K4 = self.DeConv_BN_ReLu(G_DBR_K3, ngf, ngf, "g_DBRK_4", reuse, is_training)
            G_DBR_3 = self.DeConv_BN_ReLu(G_DBR_K4, ngf, 3, "g_DBR3", reuse, is_training)
            G_DBR_3.outputs = G_DBR_3.outputs + x
            out = tf.nn.tanh(G_DBR_3.outputs, name="g_out")
            return out

    def getA(self, t):
        neg_t = -tf.reshape(t, [batch_size, -1], name='g_neg_t')
        numpx = math.floor(self.input_height * self.input_weight / 1000.0)
        A = -tf.reduce_mean(tf.nn.top_k(neg_t, numpx), axis=1, name='g_A')
        return A
    

    def build_model(self):
        # shpae = N*H*W*C
        # x : hazed images, labels
        # y : ground truth images, inputs
        # z : noise vector
        # t_real : t from ground truth
        self.x = tf.placeholder(tf.float32, [self.batch_size, self.input_height, self.input_weight, self.input_channel], name='hazed_images')
        self.y = tf.placeholder(tf.float32, [self.batch_size, self.input_height, self.input_weight, self.input_channel], name='ground_truth')
        self.z = tf.placeholder(tf.float32, [self.batch_size, self.input_height, self.input_weight, self.z_dim], name='z')
        #self.A = tf.placeholder(tf.float32, [self.batch_size], name='A')
        self.t_real = tf.placeholder(tf.float32, [self.batch_size, self.input_height, self.input_weight], name='t_real')
        # Conditional GAN
        D_real, D_real_logits, _ = self.discriminator(self.y, self.x, is_training=True, reuse=False)
        G, t = self.generator(self.z, self.x, is_training=True, reuse=False)
        D_fake, D_fake_logits, _ = self.discriminator(G, self.x, is_training=True, reuse=True)
        # ===== D loss =====
        d_loss_real = tf.reduce_mean(
            tf.nn.sigmoid_cross_entropy_with_logits(logits=D_real_logits, labels=tf.ones_like(D_real)))
        d_loss_fake = tf.reduce_mean(
            tf.nn.sigmoid_cross_entropy_with_logits(logits=D_fake_logits, labels=tf.zeros_like(D_fake)))
        self.d_loss = d_loss_real + d_loss_fake
        # ===== G loss =====
        # Euclidean Loss
        self.g_e_loss = tf.reduce_mean(tf.square(self.y - G))
        # Perceptual Loss
        vgg_y = vgg16.Vgg16()
        vgg_y.build(self.y)
        vgg_G = vgg16.Vgg16()
        vgg_G.build(G)
        self.g_p_loss = tf.reduce_mean(tf.square(vgg_y.conv2_2 - vgg_G.conv2_2))
        # Discriminator Loss
        self.g_loss_from_d = tf.reduce_mean(
            tf.nn.sigmoid_cross_entropy_with_logits(logits=D_fake_logits, labels=tf.ones_like(D_fake)))
        # t loss
        self.g_t_loss = tf.reduce_mean(tf.square(self.t_real - t))
        self.g_loss = self.lambda_e * self.g_e_loss + self.lambda_p * self.g_p_loss + self.lambda_d * self.g_loss_from_d + lambda_t * self.g_t_loss

        # for test      
        self.fake_images = self.generator(self.z, self.x, is_training=False, reuse=True)

        """ Training """
        # divide trainable variables into a group for D and a group for G
        t_vars = tf.trainable_variables()
        d_vars = [var for var in t_vars if 'd_' in var.name]
        g_vars = [var for var in t_vars if 'g_' in var.name]

        # optimizers
        with tf.control_dependencies(tf.get_collection(tf.GraphKeys.UPDATE_OPS)):
            self.d_optim = tf.train.AdamOptimizer(self.learning_rate, beta1=self.beta1) \
                      .minimize(self.d_loss, var_list=d_vars)
            self.g_optim = tf.train.AdamOptimizer(self.learning_rate, beta1=self.beta1) \
                      .minimize(self.g_loss, var_list=g_vars) # lr *5 beta1 ????
        
        """ Summary """
        d_loss_real_sum = tf.summary.scalar("d_loss_real", d_loss_real)
        d_loss_fake_sum = tf.summary.scalar("d_loss_fake", d_loss_fake)
        d_loss_sum = tf.summary.scalar("d_loss", self.d_loss)

        p_loss_sum = tf.summary.scalar("p_loss", self.g_p_loss)
        e_loss_sum = tf.summary.scalar("e_loss", self.g_e_loss)
        g_loss_from_d_sum = tf.summary.scalar("g_loss_from_d", self.g_loss_from_d)
        t_loss_sum = tf.summary.scalar("t_loss", self.g_t_loss)
        g_loss_sum = tf.summary.scalar("g_loss", self.g_loss)

        # final summary operations
        self.g_sum = tf.summary.merge([d_loss_fake_sum, p_loss_sum, e_loss_sum, g_loss_from_d_sum, t_loss_sum, g_loss_sum])
        self.d_sum = tf.summary.merge([d_loss_real_sum, d_loss_sum])

    def train(self):
        
        # initialize all variables
        tf.global_variables_initializer().run()

        # graph inputs for visualize training results
        self.sample_z = np.random.uniform(-1, 1, size=(self.batch_size , self.input_height, self.input_weight, self.z_dim))
        self.test_hazed_img, _ = self.test_set.next_batch()
        # self.test_hazed_img = self.data_x[0:self.batch_size]

        # saver to save model
        self.saver = tf.train.Saver()

        # summary writer
        self.writer = tf.summary.FileWriter(self.log_dir + '/' + self.model_name, self.sess.graph)

        # restore check-point if it exits
        could_load, checkpoint_counter = self.load(self.checkpoint_dir)
        if could_load:
            start_epoch = (int)(checkpoint_counter / self.num_batches)
            start_batch_id = checkpoint_counter - start_epoch * self.num_batches
            counter = checkpoint_counter
            print(" [*] Load SUCCESS")
        else:
            start_epoch = 0
            start_batch_id = 0
            counter = 1
            print(" [!] Load failed...")
        
        # loop for epoch
        start_time = time.time()
        for epoch in range(start_epoch, self.epoch):

            # get batch data
            for idx in range(start_batch_id, self.num_batches):
                batch_hazed_img, batch_ground_truth, batch_t = self.train_set.next_batch()
                batch_z = np.random.uniform(-1, 1, [self.batch_size, self.input_height, self.input_weight, self.z_dim]).astype(np.float32)
                
                # update D network
                _, summary_str, d_loss = self.sess.run([self.d_optim, self.d_sum, self.d_loss],
                                                       feed_dict={self.x: batch_hazed_img, self.y: batch_ground_truth,
                                                                  self.z: batch_z, self.t: batch_t})
                self.writer.add_summary(summary_str, counter)

                # update G network
                _, summary_str, g_loss = self.sess.run([self.g_optim, self.g_sum, self.g_loss],
                                                       feed_dict={self.x: batch_hazed_img, self.y: batch_ground_truth,
                                                                  self.z: batch_z, self.t: batch_t})
                self.writer.add_summary(summary_str, counter)
                
                # display training status
                counter += 1
                print("Epoch: [%2d] [%4d/%4d] time: %4.4f, d_loss: %.8f, g_loss:%.8f" \
                      % (epoch, idx, self.num_batches, time.time() - start_time, d_loss, g_loss))
                #print(vgg_y)
                #print(vgg_G)

                # save training results for every 300 steps
                if np.mod(counter, 40) == 0:
                    samples = self.sess.run(self.fake_images,
                                            feed_dict={self.z: batch_z, self.x: batch_hazed_img})
                    tot_num_samples = self.batch_size
                    manifold_h = int(np.floor(np.sqrt(tot_num_samples)))
                    manifold_w = int(np.floor(np.sqrt(tot_num_samples)))
                    save_images(samples[:manifold_h * manifold_w, :, :, :], [manifold_h, manifold_w],
                                './' + check_folder(self.result_dir + '/' + self.model_dir) + '/' + self.model_name + '_train_{:02d}_{:04d}.png'.format(
                                    epoch, idx))

                if np.mod(counter, 500) == 0:
                    self.save(self.checkpoint_dir, counter)
            # After an epoch, start_batch_id is set to zero
            # non-zero value is only for the first epoch after loading pre-trained model
            start_batch_id = 0

            # save model
            # self.save(self.checkpoint_dir, counter)

            # show temporal results
            # self.visualize_results(epoch)

        # save model for final step
        self.save(self.checkpoint_dir, counter)

    def load(self, checkpoint_dir):
        import re
        print(" [*] Reading checkpoints...")
        checkpoint_dir = os.path.join(checkpoint_dir, self.model_dir, self.model_name)

        ckpt = tf.train.get_checkpoint_state(checkpoint_dir)
        if ckpt and ckpt.model_checkpoint_path:
            ckpt_name = os.path.basename(ckpt.model_checkpoint_path)
            self.saver.restore(self.sess, os.path.join(checkpoint_dir, ckpt_name))
            counter = int(next(re.finditer("(\d+)(?!.*\d)",ckpt_name)).group(0))
            print(" [*] Success to read {}".format(ckpt_name))
            return True, counter
        else:
            print(" [*] Failed to find a checkpoint")
            return False, 0
    
    def save(self, checkpoint_dir, step):
        checkpoint_dir = os.path.join(checkpoint_dir, self.model_dir, self.model_name)
        print("[*] Saving model at " + checkpoint_dir)
        if not os.path.exists(checkpoint_dir):
            os.makedirs(checkpoint_dir)

        self.saver.save(self.sess,os.path.join(checkpoint_dir, self.model_name+'.model'), global_step=step)

    def save_images(images, size, image_path):
        return imsave(inverse_transform(images), size, image_path)
