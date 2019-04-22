#!/usr/bin/env python
# coding: utf-8

# In[1]:


import numpy as np
import tensorflow as tf
import random
from dataloader import Gen_Data_loader, Dis_dataloader
from generator import Generator
from discriminator import Discriminator
from rollout import ROLLOUT

import pickle
import gensim

with open('../preprocess/sentence.pickle', 'rb') as f:
    data = pickle.load(f)
sentences_data = data["Tweet"]

model = gensim.models.Word2Vec.load('../preprocess/model')

a = open('../preprocess/sentence_pos.pickle', 'rb')
sentence_pos = pickle.load(a)

b = open('../preprocess/sentence_real_data_input.pickle', 'rb')
real_data = pickle.load(b)

c = open('../preprocess/num_dic.pickle', 'rb')
vocab_to_int = pickle.load(c)

d = open('../preprocess/dic_num.pickle', 'rb')
int_to_vocab = pickle.load(d)

f = open('../preprocess/sentence_real_data_add_start_end.pickle', 'rb')
sentence_real_data_add_start_end = pickle.load(f)

g = open('../preprocess/word_embedding_matrix.pickle', 'rb')
word_embedding_matrix = pickle.load(g)
word_embedding_matrix = np.array(word_embedding_matrix)
word_embedding_matrix = word_embedding_matrix.astype(np.float32)

emotion_intensity = data.iloc[:,2:]

#########################################################################################
#  Generator  Hyper-parameters
######################################################################################
EMB_DIM = 30 # embedding dimension (pretrained: 200, pk: 30)
HIDDEN_DIM = 300 # hidden state dimension of lstm cell
SEQ_LENGTH = 41 # sequence length
START_TOKEN = 0
PRE_EPOCH_NUM = 10  # supervise (maximum likelihood estimation) epochs
SEED = 88
BATCH_SIZE = 5
TYPE_SIZE = 4
#########################################################################################
#  Discriminator  Hyper-parameters
#########################################################################################
dis_embedding_dim = EMB_DIM
dis_filter_sizes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 30]
dis_num_filters = [100, 200, 200, 200, 200, 100, 100, 100, 100, 100, 160, 160]
dis_dropout_keep_prob = 0.75
dis_l2_reg_lambda = 0.2
dis_batch_size = 64

#########################################################################################
#  Basic Training Parameters
#########################################################################################
TOTAL_BATCH = 10
positive_file = './save/positive_file.txt'
negative_file = './save/generator_sample.txt'
eval_file = './save/eval_file.txt'
generated_num = 100
sample_num = 10

def generate_samples(sess, trainable_model, batch_size, generated_num, output_file, word_embedding_matrix, type_idx):
    # Generate Samples
    generated_samples = []
    generating_types = []
    for _ in range(int(generated_num / batch_size)):
        sample = trainable_model.generate(sess, word_embedding_matrix, type_idx)
        generated_samples.extend(sample)
        generating_types.extend(type_idx)

    with open(output_file, 'w') as fout:
        for i in range(len(generated_samples)):
            buffer = str(generating_types[i])
            buffer2 = ' '.join([str(x) for x in generated_samples[i]]) + '\n'
            fout.write(buffer + ' ' + buffer2)

def pre_train_epoch(sess, trainable_model, data_loader, word_embedding_matrix):
    # Pre-train the generator using MLE for one epoch
    supervised_g_losses = []
    data_loader.reset_pointer()

    for it in range(data_loader.num_batch):  # 빨리 돌리려면 여기를 1로
        seq, type = data_loader.next_batch()
        _, g_loss = trainable_model.pretrain_step(sess, seq, word_embedding_matrix, type)
        supervised_g_losses.append(g_loss)

    return np.mean(supervised_g_losses)


def make_sample(eval_file, int_to_vocab, sample_num):
    samples = []
    types = []
    with open(eval_file, 'r') as f:
        for line in f:
            line = line.strip()
            line = line.split()
            parse_line = [int(x) for x in line]
            types.append(parse_line[0])
            samples.append(parse_line[1:])

    type_int = types[:sample_num]
    sample_int = samples[:sample_num]
    type_str = [i for i in type_int]
    sample_vocab = [[int_to_vocab[i] for i in sample] for sample in sample_int]
    sample_result = []
    for i in range(len(sample_vocab)):
        sample_result.append(str(type_str[i]) + ' ' + ' '.join(sample_vocab[i]))
    return sample_result

random.seed(SEED)
np.random.seed(SEED)
assert START_TOKEN == 0

gen_data_loader = Gen_Data_loader(BATCH_SIZE, SEQ_LENGTH)
vocab_size = len(vocab_to_int) 
print(vocab_size)
dis_data_loader = Dis_dataloader(BATCH_SIZE, SEQ_LENGTH)

generator = Generator(vocab_size, BATCH_SIZE, EMB_DIM, HIDDEN_DIM, SEQ_LENGTH, START_TOKEN, TYPE_SIZE)
discriminator = Discriminator(sequence_length=SEQ_LENGTH, batch_size=BATCH_SIZE, num_classes=2,
                              word_embedding_matrix=word_embedding_matrix,
                              embedding_size=dis_embedding_dim, filter_sizes=dis_filter_sizes,
                              num_filters=dis_num_filters, type_size=TYPE_SIZE, l2_reg_lambda=dis_l2_reg_lambda)

config = tf.ConfigProto()
config.gpu_options.allow_growth = True

sess = tf.Session(config=config)
saver = tf.train.Saver()
sess.run(tf.global_variables_initializer())

gen_data_loader.create_batches(positive_file)
gen_sample = open('save/pretrain_sample.txt', 'w')
print('Start pre-training...')
gen_sample.write('pre-training...\n')
for epoch in range(PRE_EPOCH_NUM): #PRE_EPOCH_NUM 으로 횟수수정
    loss = pre_train_epoch(sess, generator, gen_data_loader, word_embedding_matrix)
    if epoch % 5 == 0:
        random_type = np.random.randint(0, TYPE_SIZE, BATCH_SIZE)
        generate_samples(sess, generator, BATCH_SIZE, generated_num, eval_file, word_embedding_matrix, random_type)
        sample_vocab = make_sample(eval_file, int_to_vocab, sample_num)

        print('pre-train epoch ', epoch)

        buffer = 'epoch:\t' + str(epoch) + '\n'
        gen_sample.write(buffer)
        for sample in sample_vocab:
            print(sample)
            buffer = sample + '\n'
            gen_sample.write(buffer)

#  pre-train discriminator
print('Start pre-training discriminator...')
# Train 3 epoch on the generated data and do this for 50 times
for pdg in range(25): # 25
    print("dis_pretrain_gen: ", pdg)
    random_type = np.random.randint(0, TYPE_SIZE, BATCH_SIZE)
    generate_samples(sess, generator, BATCH_SIZE, generated_num, negative_file, word_embedding_matrix, random_type)
    dis_data_loader.load_train_data(positive_file, negative_file)
    for pd in range(3): # 3
        print("dis_pretrain: ", pd)
        dis_data_loader.reset_pointer()
        for it in range(dis_data_loader.num_batch): # 빨리 돌리려면 여기를 1로 dis_data_loader.num_batch
            seq_batch, condition_batch, label_batch = dis_data_loader.next_batch()
            feed = {
                discriminator.input_x: seq_batch,
                discriminator.input_cond: condition_batch,
                discriminator.input_y: label_batch,
                discriminator.dropout_keep_prob: dis_dropout_keep_prob
            }
            _ = sess.run(discriminator.train_op, feed)

rollout = ROLLOUT(generator, 0.8, word_embedding_matrix)

print('#########################################################################')
print('Start Adversarial Training...')
gen_sample.write('adversarial training...\n')
for total_batch in range(TOTAL_BATCH):
    # Train the generator for one step
    for it in range(1):
        random_type = np.random.randint(0, TYPE_SIZE, BATCH_SIZE)
        samples = generator.generate(sess, word_embedding_matrix, random_type)
        rewards = rollout.get_reward(sess, samples, 16, discriminator, random_type)
        feed = {generator.x: samples, generator.rewards: rewards, generator.type_index: random_type,
                generator.word_embedding_matrix: word_embedding_matrix}
        _ = sess.run(generator.g_updates, feed_dict=feed)

    # Test
    if total_batch % 5 == 0 or total_batch == TOTAL_BATCH - 1:
        generate_samples(sess, generator, BATCH_SIZE, generated_num, eval_file, word_embedding_matrix, random_type)
        sample_vocab = make_sample(eval_file, int_to_vocab, sample_num)

        print('total_batch: ', total_batch)

        buffer = 'epoch:\t' + str(total_batch) + '\n'
        gen_sample.write(buffer)
        for sample in sample_vocab:
            print(sample)
            buffer = sample + '\n'
            gen_sample.write(buffer)

    # Update roll-out parameters
    rollout.update_params()

    # Train the discriminator
    for _ in range(5): # 5
        random_type = np.random.randint(0, TYPE_SIZE, BATCH_SIZE)
        generate_samples(sess, generator, BATCH_SIZE, generated_num, negative_file, word_embedding_matrix, random_type)
        dis_data_loader.load_train_data(positive_file, negative_file)

        for _ in range(3): # 3
            dis_data_loader.reset_pointer()
            for it in range(dis_data_loader.num_batch):
                seq_batch, condition_batch, label_batch = dis_data_loader.next_batch()
                feed = {
                    discriminator.input_x: seq_batch,
                    discriminator.input_cond: condition_batch,
                    discriminator.input_y: label_batch,
                    discriminator.dropout_keep_prob: dis_dropout_keep_prob
                }
                _ = sess.run(discriminator.train_op, feed)

    if total_batch % 5 == 0 or total_batch == TOTAL_BATCH - 1:
        saver.save(sess, './checkpoint/seqGAN_ours')

gen_sample.close()

random_type = np.random.randint(0, TYPE_SIZE, BATCH_SIZE)
generate_samples(sess, generator, BATCH_SIZE, generated_num, eval_file, word_embedding_matrix, random_type)

samples = make_sample(eval_file, int_to_vocab, generated_num)
samples = [[word for word in sample.split() if word != '<unknown>'] for sample in samples]
samples = [' '.join(sample) for sample in samples]

f = open('./save/final_output_vocab.txt', 'w')
for token in samples:
    token = token + '\n'
    f.write(token)
f.close()

# write the training time
f = open('./save/_parameters.txt', 'w')
f.write("add <start> signal as zero in word2vec lookup table\n")
f.close()
writer = tf.summary.FileWriter('../../../log',sess.graph)

