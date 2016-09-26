import tensorflow as tf
import numpy as np
from cell import Cell

class Network(object):

  def __init__(self, n_l, n_s, n_h, n_input, n_output, input, output):

    s_first, h_first = self.initialize_cell_state(n_s, n_h)

    cell_1 = Cell(s_first, h_first, input=input, first=True)

    layers = [cell_1]
    prev_cell = cell_1
    for l in range(1, (n_l-1)):
      layers.append(Cell(prev_cell.state_next, prev_cell.h_next, first=False))
      prev_cell = layers[-1]

    w_last = tf.Variable(tf.truncated_normal(n_output, layers[-1].h_next.shape[0]))
    b_last = tf.Variable(tf.constant(0.1,shape=n_output))

    with tf.name_scope('Model'):
      self.pred = tf.matmul(w_last, layers[-1].h_next) + b_last

  def initialize_cell_state(self, n_s, n_h):
    return tf.Variable(tf.constant(0.1,shape=[n_s, 1])),\
            tf.Variable(tf.constant(0.1,shape=[n_h, 1]))
