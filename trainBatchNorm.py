import time
import uuid
import os
import tensorflow as tf
from lstm import BNLSTMCell, orthogonal_initializer
from tensorflow.examples.tutorials.mnist import input_data

tf.app.flags.DEFINE_float("learning_rate", 0.01, "Learning rate.")
tf.app.flags.DEFINE_float("dropout", 0.5,
	"For Dropout: how much to keep when using dropout?")
tf.app.flags.DEFINE_float("clipping", 1.0,
	"Maximum absolute value of the gradients.")
tf.app.flags.DEFINE_integer("batch_size", 128,
	"Batch size to use during training.")
tf.app.flags.DEFINE_integer("size", 128, "Size of each model layer.")
tf.app.flags.DEFINE_integer("n_layers", 10, "Number of layers in the model.")
tf.app.flags.DEFINE_string("train_dir", "/tmp", "Training directory.")
tf.app.flags.DEFINE_integer("steps_per_checkpoint", 500,
	"How many training steps to do per checkpoint.")
tf.app.flags.DEFINE_boolean("self_test", False,
	"Run a self-test if this is set to True.")
tf.app.flags.DEFINE_boolean("train", True,
	"Run a train if this is set to True.")
tf.app.flags.DEFINE_boolean("tie_weights", False,
	"Use the same weights in all layers if set true.")
tf.app.flags.DEFINE_integer("n_epochs", 3,
	"Number of epochs to run the training procedure.")
#tf.app.flags.DEFINE_integer("n_itr", 100000,
#	"Number of training iterations.")
tf.app.flags.DEFINE_string("log_dir", "/tmp",
	"Tensorboard log directory.")
tf.app.flags.DEFINE_string("data_dir", "/tmp",
	"training data directory.")
FLAGS = tf.app.flags.FLAGS


def data_prep():
	mnist = input_data.read_data_sets("MNIST_data/", one_hot=True)
	return mnist


def create_model(input_size, output_size,
		 batch_size=128, hidden_size=128, n_layers=10,
		 clipping=1.0, tie_weights=False):
	x = tf.placeholder(tf.float32, [None, input_size])
	training = tf.placeholder(tf.bool)

	keep_prob = tf.placeholder(tf.float32)

	initialState = (tf.random_normal([batch_size, hidden_size],
		stddev=0.1),
			tf.random_normal([batch_size, hidden_size],
				stddev=0.1))

	list_layers = []
	id = 1
	cell_1 = BNLSTMCell(hidden_size, training=training)
	new_h, new_state = cell_1(x, initialState, keep_prob, id, first=True)

	layers = [cell_1]
	prev_cell = cell_1
	prev_cell_w = prev_cell.W_hh
	prev_cell_b = prev_cell.bias
	for l in range(1, (n_layers - 1)):
		if not tie_weights:
			prev_cell_w = None
			prev_cell_b = None
		id += 1
		next_cell = BNLSTMCell(hidden_size, training=training)
		next_new_h, next_new_state = next_cell(prev_cell.new_h,
			prev_cell.state,
			keep_prob, id,
			first=False,
			tied_weights=prev_cell_w,
			tied_bias=prev_cell_b)
		layers.append(next_cell)
		prev_cell = layers[-1]
		prev_cell_w = prev_cell.W_xh

	outputs, state = layers, prev_cell.state

	_, final_hidden = state

	W = tf.get_variable('W', [hidden_size, output_size],
		initializer=orthogonal_initializer())
	b = tf.get_variable('b', [output_size])

	y = tf.nn.softmax(tf.matmul(final_hidden, W) + b)

	y_ = tf.placeholder(tf.float32, [None, output_size])

	cross_entropy = tf.reduce_mean(
		-tf.reduce_sum(y_ * tf.log(y), reduction_indices=[1]))

	optimizer = tf.train.AdamOptimizer(learning_rate=FLAGS.learning_rate)
	gvs = optimizer.compute_gradients(cross_entropy)
	capped_gvs = [(None if grad is None
		       else tf.clip_by_value(grad, -1. * clipping, clipping),
		       var)
		      for grad, var in gvs]
	train_step = optimizer.apply_gradients(capped_gvs)

	correct_prediction = tf.equal(tf.argmax(y, 1), tf.argmax(y_, 1))
	accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))

	# Summaries
	tf.scalar_summary("accuracy", accuracy)
	tf.scalar_summary("xe_loss", cross_entropy)
	for (grad, var), (capped_grad, _) in zip(gvs, capped_gvs):
		if grad is not None:
			tf.histogram_summary('grad/{}'.format(var.name),
				capped_grad)
			tf.histogram_summary(
				'capped_fraction/{}'.format(var.name),
				tf.nn.zero_fraction(grad - capped_grad))
			tf.histogram_summary('weight/{}'.format(var.name), var)


	w_i, w_j, w_f, w_o = tf.split(1, 4, outputs[0].W_xh)
	w_i = tf.transpose(w_i)
	print( w_i.get_shape().as_list())
	w_i = tf.reshape(w_i, (
		1, 28*FLAGS.size,
		28,
		1))
	tf.image_summary("layer_w_o", w_i)
	'''
	w_j = tf.reshape(w_j, (
		1, w_j.get_shape().as_list()[0],
		w_j.get_shape().as_list()[1],
		1))
	w_f = tf.reshape(w_f, (
		1, w_f.get_shape().as_list()[0],
		w_f.get_shape().as_list()[1],
		1))
	w_o = tf.reshape(w_o, (
		1, w_o.get_shape().as_list()[0],
		w_o.get_shape().as_list()[1],
		1))


	tf.image_summary("layer_{}_w_j".format(k), w_j)
	tf.image_summary("layer_{}_w_f".format(k), w_f)
	tf.image_summary("layer_{}_w_o".format(k), w_o)
	'''


	merged = tf.merge_all_summaries()
	return merged, train_step, cross_entropy, x, y_, training, accuracy, \
	       keep_prob


def load_model(saver, sess, chkpnts_dir):
	ckpt = tf.train.get_checkpoint_state(chkpnts_dir)
	if ckpt and ckpt.model_checkpoint_path:
		print("Loading previously trained model: {}".format(
			ckpt.model_checkpoint_path))
		saver.restore(sess, ckpt.model_checkpoint_path)
	else:
		print("Training with fresh parameters")
		sess.run(tf.initialize_all_variables())

def monitor_progress(FLAGS, sess, mnist, loss, merged, x, y_, training,
			keep_prob, curr_iter, accuracy, writer, saver,
			step_time, save_checkpoints = True):
	batch_xs, batch_ys = mnist.validation.next_batch(
			FLAGS.batch_size)
	summary_str = sess.run(merged,
		feed_dict={
			x: batch_xs,
			y_: batch_ys,
			training: False,
			keep_prob: 1.0})
	writer.add_summary(summary_str, curr_iter)
	checkpoint_path = os.path.join("chkpnts/",
		"lstmjam.ckpt")

	if save_checkpoints:
		saver.save(sess, checkpoint_path, global_step = curr_iter)

	print(loss, step_time, curr_iter, mnist.train.epochs_completed)
	avg_acc = 0.0
	for test_itr in range(70):
		test_data, test_label = mnist.test.next_batch(
			FLAGS.batch_size)
		acc = sess.run(accuracy,
			feed_dict={
				x: test_data,
				y_: test_label,
				training: False,
				keep_prob: 1.0})
		avg_acc += acc
	# test_label = mnist.test.labels[
	# :FLAGS.batch_size]
	print("Testing Accuracy:" + str(avg_acc / 70))


def train(save_checkpoints = True):
	mnist = data_prep()

	merged, train_step, cross_entropy, x, y_, \
	training, accuracy, keep_prob = create_model(784,
		10,
		FLAGS.batch_size,
		FLAGS.size,
		FLAGS.n_layers,
		FLAGS.clipping,
		FLAGS.tie_weights)

	saver = tf.train.Saver(tf.all_variables())
	sess = tf.Session()
	checkpoints_folder = './chkpnts/'
	if not os.path.exists(checkpoints_folder):
		os.makedirs(checkpoints_folder)
	load_model(saver, sess, "chkpnts/")
	# init = tf.initialize_all_variables()
	# sess.run(init)

	logdir = 'logs/' + str(uuid.uuid4())
	os.makedirs(logdir)
	print('logging to ' + logdir)
	writer = tf.train.SummaryWriter(logdir, sess.graph)

	current_time = time.time()
	print(
		"Using population statistics (training: False) at test time gives "
		"worse results than batch statistics")

	curr_iter = 0
	while True:
		batch_xs, batch_ys = mnist.train.next_batch(FLAGS.batch_size)
		loss, _ = sess.run([cross_entropy, train_step],
			feed_dict={
				x: batch_xs, y_: batch_ys,
				training: True,
				keep_prob: FLAGS.dropout})
		step_time = time.time() - current_time
		current_time = time.time()
		if curr_iter % FLAGS.steps_per_checkpoint == 0:
			monitor_progress(FLAGS, sess, mnist, loss, merged, x, y_,
				training, keep_prob, curr_iter, accuracy,
				writer, saver, step_time, save_checkpoints)

		if (mnist.train.epochs_completed >= FLAGS.n_epochs):
			monitor_progress(FLAGS, sess, mnist, loss, merged, x, y_,
				training, keep_prob, curr_iter, accuracy,
				writer, saver, step_time, save_checkpoints)
			break
		curr_iter += 1


def test():
	mnist = data_prep()

	merged, train_step, cross_entropy, x, y_, \
	training, accuracy, keep_prob = create_model(784,
		10,
		FLAGS.batch_size,
		FLAGS.size,
		FLAGS.n_layers,
		FLAGS.clipping,
		FLAGS.tie_weights)

	saver = tf.train.Saver(tf.all_variables())
	sess = tf.Session()
	load_model(saver, sess, "chkpnts/")
	test_data = mnist.test.images
	test_label = mnist.test.labels
	print("Testing Accuracy:" + str(sess.run(accuracy, feed_dict={
		x: test_data, y_: test_label, training: False})))


def main(_):
	if FLAGS.self_test:
		pass
	elif FLAGS.train:
		train()


if __name__ == '__main__':
	tf.app.run()
