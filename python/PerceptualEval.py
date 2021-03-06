import tensorflow as tf
import scipy
import IGAN, PGAN, DataLoader
from train import create_pipeline, init_model, mkdir
import argparse


class Percept_eval():
    def __init__(self, model, result_directory, sr):
        self.model = model.generator
        self.slice_size = self.model.layers[-1].output_shape[1]
        self.res_dir = result_directory
        self.sr = sr
        if isinstance(model, IGAN.IGAN):
            self.model_name ='igan'
        if isinstance(model, PGAN.PGAN):
            self.model_name ='pgan'
    def pred_spec_chaining(self, spectrum):
        """Split the spectrum on slice of slice size and perform prediction on each spectrum slice given the adjacent slice."""
        shape = spectrum.shape
        idx_to_keep = shape[0] - shape[0] % self.slice_size
        spectrum = spectrum[:idx_to_keep, :, :]
        prev = tf.stack(tf.split(spectrum, shape[0] // self.slice_size), axis=0)
        next = prev[2:]
        prev = prev[:tf.shape(next)[0], :, :, :]
        if self.model_name == 'igan':
            predictions = self.model.predict((prev, next))
        if self.model_name == 'pgan':
            predictions = self.model.predict(prev)
        out = predictions.reshape((tf.shape(predictions)[0] * tf.shape(predictions)[1], shape[1], 1))
        return out

    def encode(self, audio):
        return tf.audio.encode_wav(audio, self.sr)

    def write_batch(self, rec_waves, or_waves, batch_idx, write_hole=True):
        or_hole = or_waves
        mask1 = tf.ones(tf.shape(or_hole[:, 0: int(0.5 * self.sr)]))
        mask2 = tf.zeros(tf.shape(or_hole[:, int(0.5 * self.sr): int(0.5 * self.sr + 0.064 * self.sr)]))
        mask3 = tf.ones(tf.shape(or_hole[:, int(0.5 * self.sr + 0.064 * self.sr):]))
        or_hole = or_hole * tf.concat((mask1, mask2, mask3), 1)
        or_waves = tf.map_fn(self.encode, tf.expand_dims(or_waves, -1), dtype=tf.string)
        rec_waves = tf.map_fn(self.encode, tf.expand_dims(rec_waves, -1), dtype=tf.string)
        or_hole = tf.map_fn(self.encode, tf.expand_dims(or_hole, -1), dtype=tf.string)

        for i in range(rec_waves.shape[0]):
            tf.io.write_file(self.res_dir + 'or_' + 'batch_' + str(batch_idx) + '_sample_' + str(i) + '.wav',
                             or_waves[i])
            tf.io.write_file(self.res_dir + 'rec_' + 'batch_' + str(batch_idx) + '_sample_' + str(i) + '.wav',
                             rec_waves[i])
            if write_hole:
                tf.io.write_file(self.res_dir + 'hole_' + 'batch_' + str(batch_idx) + '_sample_' + str(i) + '.wav', or_hole[i])

    def prediction_chaining(self, dataset, gen, length):
        idx = 0
        length = int(length)
        print(length)
        for audio_batch in dataset:
            for i in range(audio_batch.shape[0]):
                audio = audio_batch[i, :]
                to_keep = int(audio.shape[0] - (audio.shape[0] % length))
                audio = audio[:to_keep]
                splitted_audio = tf.stack(tf.split(audio, int(audio.shape[0] // length), 0))
                prev_audio_frame = tf.reshape(splitted_audio[:-2], (-1, length))
                next_audio_frame = tf.reshape(splitted_audio[2:], (-1, length))
                print("prev_audio frame shape: " + str(prev_audio_frame.shape))
                print("next_audio frame shape: " + str(next_audio_frame.shape))
                prev_frame = gen.process_data(prev_audio_frame)
                next_frame = gen.process_data(next_audio_frame)
                print("prev_frame shape: " + str(prev_frame.shape))
                print("next frame shape: " + str(next_frame.shape))
                predic_spec = self.model.predict((prev_frame, next_frame))
                print("predic shape " + str(predic_spec.shape))
                predic_audio =  gen.to_audio(predic_spec)
                print("predic_audio shape: " + str(predic_audio.shape))
                audio = tf.expand_dims(audio[length:-length], -1)
                rec_audio = tf.reshape(predic_audio, audio.shape)
                print("rec_audio shape: " + str(rec_audio.shape))
                rec_audio = self.encode(rec_audio)
                audio = self.encode(audio)
                tf.io.write_file(self.res_dir + 'or_chaining_' + str(idx) + '.wav', audio)
                tf.io.write_file(self.res_dir + 'rec_chaining_' + str(idx) + '.wav', rec_audio)
                idx += 1

    def eval_on_1_hole(self, dataset, gen, length):
        hole_start_idx = int(0.5 * self.sr)
        frame_length = int(self.sr * length)
        hole_last_idx = hole_start_idx + frame_length

        idx_to_keep = 2 * self.sr
        batch_idx = 0
        for audio_batch in dataset:
            or_audio = audio_batch[:, :idx_to_keep]
            prev_frame = audio_batch[:, hole_start_idx - frame_length:hole_start_idx]
            prev_frame = gen.process_data(tf.squeeze(prev_frame))
            if self.model_name == 'igan':
                next_frame = audio_batch[:, hole_start_idx - frame_length:hole_start_idx]
                next_frame = gen.process_data(tf.squeeze(next_frame))
                predictions = self.model.predict((prev_frame, next_frame))
            if self.model_name == 'pgan':
                predictions = self.model.predict(prev_frame)
            predictions = gen.to_audio(predictions)
            rec_audio = tf.concat(
                (audio_batch[:, :hole_start_idx], predictions[:, :, 0], audio_batch[:, hole_last_idx:idx_to_keep]), 1)
            batch_idx += 1
            print("batch " + str(batch_idx) + " done ")
            self.write_batch(rec_waves=rec_audio, or_waves=or_audio, batch_idx=batch_idx)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    help_ = "Path to Checkpoint folder"
    parser.add_argument("-c", "--ckpt", help=help_)
    help_ = "Model type. choose between igan or pgan"
    parser.add_argument("-m", "--model", help=help_)
    help_ = "path to data"
    parser.add_argument("-d", "--data", help=help_)
    help_ = "target directory"
    parser.add_argument("-t", "--target", help=help_)
    help_ = "Evaluation type: choose between chaining or single_hole"
    parser.add_argument("-me", "--method", help=help_)
    help_ = "audio frame length in second"
    parser.add_argument("-l", "--length", type=float, help=help_)
    help_ = "batch size"
    parser.add_argument("-b", "--batch", type=int, help=help_)
    args = parser.parse_args()

    batch_size = 256
    if args.batch:
        batch_size = args.batch
    model_name = 'igan'
    if args.model:
        model_name = args.model
    data = '../fma_dataset/test.tfrecord'
    if args.data:
        data = args.data
    ckpt = 'ckpt/' + model_name + '/0.064/'
    if args.ckpt:
        ckpt = args.ckpt
    target = '../reconstruction/' + ckpt[4:] + 'percept_eval/'
    mkdir(target)
    if args.target:
        target = args.target
    method = "single_hole"
    if args.method:
        method = args.method
    pipeline = None
    sr= 16000
    split_ckpt = ckpt.split('/')
    audio_length = 0.064
    if args.length:
        audio_length = args.length
    if model_name == 'igan':
        pipeline, sr = create_pipeline(data, batch_size, 3*audio_length, prediction_only=False)
    if model_name == 'pgan':
        pipeline, sr = create_pipeline(data, batch_size, 3*audio_length, prediction_only=True)
    model = init_model(ckpt, pipeline, model_name)
    evaluator = Percept_eval(model, target, sr)
    dataloader = DataLoader.LoadData(data, repeat=False, audio_frame_length=2.220, batch_size=batch_size)
    dataset = dataloader.create_dataset()
    if method == 'chaining':
        evaluator.prediction_chaining(dataset, pipeline, length=audio_length*sr)
    if method == 'single_hole':
        evaluator.eval_on_1_hole(dataset, pipeline, length=audio_length)
