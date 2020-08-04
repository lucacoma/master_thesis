import tensorflow as tf
import numpy as np
import os
import json
from python.plot_tool import *
from python.Processing import *
from python.metrics import *
import matplotlib.pyplot as plt
import scipy
from python.train import *


def _eval(model, gen, folder, sr, plot=False):
    result = model.evaluate(gen)
    old_get_audio = gen.get_audio
    if isinstance(result, list):
        out = dict(zip(model.metrics_names, map(str, result)))
    else:
        out = {model.metrics_names, str(result)}
    print(folder)
    with open(folder + 'loss_metrics' + '.json', 'w') as file:
        json.dump(out, file)
    gen.get_audio = True
    SNR_audio = []
    for i in range(len(gen)):
        x, y, true_audio = gen.__getitem__(0)
        pred = model.predict_on_batch(x)
        print("writing batch " + str(i))
        rec_audio = gen.to_audio(pred)
        print('rec audio shape')
        print(rec_audio.shape)
        SNR_audio.append(snr_audio_batch(np.squeeze(true_audio), np.squeeze(rec_audio)))
        if plot:
            prefix = folder + 'batch_' + str(i) + '_'
            if gen.prediction:
                predicted = pred
                truth = y
            else:
                prev, next = x
                predicted = np.concatenate((prev, pred, next), axis=1)
                truth = np.concatenate((prev, y, next), axis=1)
            plot_spectrums(predicted, truth, prefix, sr, gen._nhop, gen.prediction)
            plot_audios(rec_audio, true_audio.numpy(), prefix)
            write_audio_batch(rec_audio, true_audio.numpy(), prefix, gen.sr)

    SNR_audio = np.stack(SNR_audio)
    plt.hist(SNR_audio)
    plt.savefig(folder + "_snr_histogram.png")
    print("SNR mean: " + str(np.mean(SNR_audio)))
    print("SNR std: " + str(np.std(SNR_audio)))
    gen.get_audio = old_get_audio
    return

def evaluate(trained_model, config):
    # Set where to store the evaluation result
    result_directory = './'
    if 'result_directory' in config:
        result_directory = config['result_directory']
    sr = config['sr']
    metrics = None
    plot = True
    if 'plot' in config:
        plot = config['plot']

    if 'metrics' in config:
        metrics = config['metrics']
    trained_model.compile(optimizer="adam", loss='mse', metrics=metrics)

    if 'train_generator' in config:
        train_generator = config['train_generator']
        folder = result_directory + 'train/'
        mkdir(folder)
        _eval(trained_model, train_generator, folder, sr, plot)

    if 'val_generator' in config:
        val_generator = config['val_generator']
        folder = result_directory + 'val/'
        mkdir(folder)
        _eval(trained_model, val_generator, folder, sr, plot)

    if 'test_generator' in config:
        test_generator = config['test_generator']
        folder = result_directory + 'test/'
        mkdir(folder)
        _eval(trained_model, test_generator, folder, sr, plot)
    return

def set_option_eval():
    parser = argparse.ArgumentParser()
    help_ = "Path to Checkpoint folder"
    parser.add_argument("-c", "--ckpt", help=help_)
    help_ = "Model type. choose between igan or pgan"
    parser.add_argument("-m", "--model", help=help_)
    help_ = "path to data"
    parser.add_argument("-d", "--data", help=help_)
    help_ = "target directory"
    parser.add_argument("-t", "--target", help=help_)
    help_ = "Either to plot the waveform: choose between plot or noplot"
    parser.add_argument("-p", "--plot", help=help_)
    help_ = "audio frame length"
    parser.add_argument("-l", "--length", help=help_)
    args = parser.parse_args()

    #Default value
    model_name = 'igan'
    if args.model:
        model_name = args.model
    data = '../fma_dataset/test.tfrecord'
    if args.data:
        data = args.data
    plot = False
    if args.plot:
        if args.plot == 'plot':
            plot = True
    length = 0.064
    if args.length:
        length = args.length
    target = './reconstruction/' + ckpt[4:] + 'percept_eval/'
    mkdir(target)
    if args.target:
        target = args.target
    ckpt = 'ckpt/' + model_name + '/0.192/'
    if args.ckpt:
        ckpt = args.ckpt
    return ckpt, data, target, plot, 3*length, model_name

if __name__ == "__main__":

    ckpt, data, target, plot, length, model_name = set_option_eval()
    if model_name == 'pgan':
        test_pipeline, sr = create_pipeline(data, 256, length, prediction_only=True)
    if model_name == 'igan':
        test_pipeline, sr = create_pipeline(data, 256, length, prediction_only=False)
    model = init_model(ckpt, test_pipeline, model_name)
    res_dir = target
    config = {
        'test_generator': test_pipeline,
        'metrics': [snr_batch, tf.keras.losses.mean_squared_error],
        'result_directory': res_dir,
        'loss': tf.keras.losses.mean_squared_error,
        'plot': plot,
        'sr': sr,
    }
    if model is not None:
        evaluate(model.generator, config)
    else:
        print("Unknow model type. Exit")