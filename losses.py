import tensorflow as tf
from sklearn.utils.extmath import cartesian
import numpy as np
import logging

tf.keras.backend.set_learning_phase(1)

def generaliz_mean(tensor, dim, p=-9, keepdims=False):
    """
        Soft-min function, similar to softmax but min
    """
    res = (tensor+1e-6)**p
    res = tf.reduce_mean(res, axis=dim, keepdims=keepdims)
    res = res ** (1./p)
    return res

def cdist(a, b):
    """
        Caculate the euclid distance of every point in a to every point in b
        |a| = n, |b|=m 
        the expected returned matrix => [mxn]
    """
    a = tf.cast(a, tf.float32)
    b = tf.cast(b, tf.float32)


    diff = tf.expand_dims(a, 1)-tf.expand_dims(b, 0)
    distance = tf.sqrt(tf.reduce_sum(diff**2, -1))
    return distance

def trim_invalid_value(tensor):
    """
        When batching we add dummy value (-1), this function remove padded value for each sample 
        Args:
            tensor: a sample of a batch with padded value
        return: tensor without padded value    
    """
    mask = tf.reduce_mean(tf.cast(tensor>0, tf.float32), axis=-1)
    tensor = tf.boolean_mask(tensor, mask)
    return tensor

class WeightedHausdorffDistance():
    def __init__(self,resized_height, resized_width, p=-9, return_2_terms=False):
    
        self.height, self.width = resized_height, resized_width
        self.all_img_locations = cartesian([np.arange(self.height), np.arange(self.width)])
        self.all_img_locations = tf.convert_to_tensor(self.all_img_locations, dtype=tf.float32)
        self.max_dist = tf.sqrt(tf.convert_to_tensor(self.height, tf.float32)**2 \
                                       +tf.convert_to_tensor(self.width, tf.float32)**2)
        self.p = p
        self.return_2_terms = return_2_terms
    
    def forward_one_sample(self, prob_map_b, gt_b):
        
        prob_map_flat = tf.reshape(prob_map_b, [-1])
        
        normalized_y = gt_b
        normalized_x = self.all_img_locations
        d_matrix = cdist(normalized_x, normalized_y)
        #---term 1
        prob_map_flat = tf.reshape(prob_map_b, [-1])
        n_est_pts = tf.reduce_sum(prob_map_flat)
        d_matrix_reduce = tf.reduce_min(d_matrix, 1)
        term_1 = 1 / (n_est_pts+1e-6) * tf.reduce_sum(prob_map_flat*d_matrix_reduce)
        #----term 2
        p_replicated = tf.tile(tf.expand_dims(prob_map_flat, 1), [1, tf.shape(normalized_y)[0]])
        weighted_d_matrix = (1 - p_replicated)*self.max_dist + p_replicated*d_matrix

        minn = generaliz_mean(weighted_d_matrix,
                                  p=self.p,
                                  dim=0, keepdims=False)
        term_2 = tf.reduce_mean(minn)
        #----- term3
        total_pred = tf.reduce_mean(prob_map_b)
        total_gt = tf.shape(gt_b)[0]
        term_3 = tf.abs(total_pred-total_gt)
        

        return term_1, term_2, term_3

    def __call__(self, prob_map, labels):
        """
            prob_map: [batch_size, 256, 256, 1]
            labels: [batch_size, None, 2] (list of x, y)
        """
        i = 0
        term_1_init = tf.convert_to_tensor(0, dtype=tf.float32)
        term_2_init = tf.convert_to_tensor(0, dtype=tf.float32)
        term_3_init = tf.convert_to_tensor(0, dtype=tf.float32)
        batch_size = tf.shape(prob_map)[0]
        cond = lambda i, term_1_init, term_2_init: tf.less(i, batch_size)
        def body(i, term_1_init, term_2_init):
            prob_map_b, normalized_y = prob_map[i], labels[i]
            normalized_y = trim_invalid_value(normalized_y)
            term_1, term_2, term_3 = self.forward_one_sample(prob_map_b, normalized_y)
            return i+1, term_1_init+term_1, term_2_init+term_2, term_3_init+term_3

        i, term_1, term_2, term_3 = tf.while_loop(
            cond,
            body,
            [i, term_1_init, term_2_init, term_3_init],
        )
        
        term_1 = term_1 / tf.cast(batch_size, tf.float32) 
        term_2 = term_2 / tf.cast(batch_size, tf.float32) 
        term_3 = term_3 / tf.cast(batch_size, tf.float32) 
        
        if self.return_2_terms:
            return term_1, term_2, term_3
        else:
            return term_1 + term_2 + term_3

    
