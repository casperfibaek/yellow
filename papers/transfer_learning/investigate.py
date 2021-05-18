yellow_follow = "C:/Users/caspe/Desktop/buteo/"
import sys

from tensorflow.python.keras.layers.pooling import AveragePooling2D

sys.path.append(yellow_follow)

import os
import time
import numpy as np

import tensorflow as tf
from tensorflow.keras.utils import Sequence
from tensorflow.keras import Model, Input
from tensorflow.keras.layers import (
    Conv2D,
    MaxPooling2D,
    Conv2DTranspose,
    Concatenate,
)
from tensorflow.keras.callbacks import EarlyStopping, LearningRateScheduler
from tensorflow.keras import mixed_precision
from buteo.machine_learning.ml_utils import load_mish, create_step_decay
from buteo.utils import timing
from utils import preprocess_optical

np.set_printoptions(suppress=True)
os.environ["TF_FORCE_GPU_ALLOW_GROWTH"] = "true"
mixed_precision.set_global_policy("mixed_float16")

folder = "C:/Users/caspe/Desktop/paper_3_Transfer_Learning/data/machine_learning_data/"

load_mish()

start = time.time()


def reduction_block(
    inputs, size=32, activation="relu", kernel_initializer="glorot_normal"
):
    track1 = MaxPooling2D(pool_size=(2, 2), padding="same")(inputs)
    track2 = Conv2D(
        size,
        kernel_size=3,
        padding="same",
        strides=(2, 2),
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(inputs)
    track3 = Conv2D(
        size - 16,
        kernel_size=1,
        padding="same",
        strides=(1, 1),
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(inputs)
    track3 = Conv2D(
        size - 8,
        kernel_size=3,
        padding="same",
        strides=(1, 1),
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(track3)
    track3 = Conv2D(
        size,
        kernel_size=3,
        padding="same",
        strides=(2, 2),
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(track3)

    return Concatenate()([track1, track2, track3])


def expansion_block(
    inputs, size=32, activation="relu", kernel_initializer="glorot_normal"
):
    track1 = Conv2DTranspose(
        size,
        kernel_size=3,
        strides=(2, 2),
        kernel_initializer=kernel_initializer,
        activation=activation,
        padding="same",
    )(inputs)

    track2 = Conv2DTranspose(
        size,
        kernel_size=1,
        strides=(2, 2),
        kernel_initializer=kernel_initializer,
        activation=activation,
        padding="same",
    )(inputs)

    return Concatenate()([track1, track2])


def inception_block(
    inputs, size=32, activation="relu", kernel_initializer="glorot_normal"
):
    track1 = MaxPooling2D(pool_size=3, strides=1, padding="same")(inputs)
    track2 = Conv2D(
        size,
        kernel_size=1,
        padding="same",
        strides=(1, 1),
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(inputs)
    track3 = Conv2D(
        size - 8,
        kernel_size=1,
        padding="same",
        strides=(1, 1),
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(inputs)
    track3 = Conv2D(
        size,
        kernel_size=3,
        padding="same",
        strides=(1, 1),
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(track3)
    track4 = Conv2D(
        size - 16,
        kernel_size=1,
        padding="same",
        strides=(1, 1),
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(inputs)
    track4 = Conv2D(
        size - 8,
        kernel_size=3,
        padding="same",
        strides=(1, 1),
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(track4)
    track4 = Conv2D(
        size,
        kernel_size=3,
        padding="same",
        strides=(1, 1),
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(track4)

    return Concatenate()([track1, track2, track3, track4])


def define_model(
    shape_rgbn,
    shape_swir,
    shape_sar,
    name,
    activation="relu",
    kernel_initializer="glorot_normal",
    sizes=[32, 48, 64],
):
    # RGBN RGBN RGBN RGBN RGBN RGBN RGBN RGBN RGBN RGBN RGBN RGBN
    rgbn_input = Input(shape=shape_rgbn, name="rgbn")
    rgbn_skip1 = Conv2D(
        sizes[0],
        kernel_size=5,
        padding="same",
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(rgbn_input)
    rgbn = inception_block(rgbn_skip1, size=sizes[0])
    rgbn = reduction_block(rgbn, size=sizes[1])
    rgbn_skip2 = inception_block(rgbn, size=sizes[1])
    rgbn = reduction_block(rgbn_skip2, size=sizes[2])
    rgbn = inception_block(rgbn, size=sizes[2])
    rgbn = expansion_block(rgbn, size=sizes[1])
    rgbn = Concatenate()([rgbn_skip2, rgbn])
    rgbn = inception_block(rgbn, size=sizes[1])

    # SWIR SWIR SWIR SWIR SWIR SWIR SWIR SWIR SWIR SWIR SWIR SWIR
    swir_input = Input(shape=shape_swir, name="swir")
    swir_skip1 = Conv2D(
        sizes[0],
        kernel_size=3,
        padding="same",
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(swir_input)
    swir = inception_block(swir_skip1, size=sizes[0])
    swir = reduction_block(swir, size=sizes[1])
    swir = inception_block(swir, size=sizes[2])
    swir = expansion_block(swir, size=sizes[1])
    swir = Concatenate()([swir_skip1, swir])
    swir = inception_block(swir, size=sizes[0])

    # CONCATENATE
    model = Concatenate()([rgbn, swir])
    model = inception_block(model, size=sizes[0])
    model = expansion_block(model, size=sizes[0])
    model = Concatenate()([rgbn_skip1, model])
    model = inception_block(model, size=sizes[0])

    # SAR  SAR  SAR  SAR  SAR  SAR  SAR  SAR  SAR  SAR  SAR  SAR
    sar_input = Input(shape=shape_sar, name="sar")
    sar_skip1 = Conv2D(
        sizes[0],
        kernel_size=5,
        padding="same",
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(sar_input)
    sar = inception_block(sar_skip1, size=sizes[0])
    sar = reduction_block(sar, size=sizes[1])
    sar_skip2 = inception_block(sar, size=sizes[1])
    sar = reduction_block(sar_skip2, size=sizes[2])
    sar = inception_block(rgbn, size=sizes[2])
    sar = expansion_block(rgbn, size=sizes[1])
    sar = Concatenate()([sar_skip2, rgbn])
    sar = inception_block(rgbn, size=sizes[1])
    sar = expansion_block(sar, size=sizes[0])
    sar = Concatenate()([sar_skip1, sar])
    sar = inception_block(sar, size=sizes[0])

    model = Concatenate()([model, sar])

    # TAIL
    model = inception_block(model, size=sizes[2])
    model = inception_block(model, size=sizes[2])

    model = Conv2D(
        sizes[2],
        kernel_size=3,
        padding="same",
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(model)

    model = Conv2D(
        1,
        kernel_size=1,
        padding="same",
        activation="relu",
        kernel_initializer=kernel_initializer,
    )(model)

    model = Conv2D(
        sizes[2],
        kernel_size=3,
        padding="same",
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(model)

    model = Conv2D(
        sizes[2],
        kernel_size=3,
        padding="same",
        activation=activation,
        kernel_initializer=kernel_initializer,
    )(model)

    output = Conv2D(
        1,
        kernel_size=3,
        padding="same",
        activation="relu",
        kernel_initializer=kernel_initializer,
    )(model)

    return Model(inputs=[rgbn_input, swir_input, sar_input], outputs=output)


x_train_rgbn = np.load(folder + "000_RGBN.npy")
x_train_swir = np.load(folder + "000_SWIR.npy")
x_train_sar = np.load(folder + "000_SAR.npy")

y_train = np.load(folder + "000_LABELS.npy")[:, :, :, 0]

shuffle_mask = np.random.permutation(x_train_rgbn.shape[0])

x_train_rgbn = x_train_rgbn[shuffle_mask]
x_train_swir = x_train_swir[shuffle_mask]
x_train_sar = x_train_sar[shuffle_mask]
y_train = y_train[shuffle_mask]

x_test_rgbn = preprocess_optical(np.load(folder + "851_RGBN.npy"))
x_test_swir = preprocess_optical(np.load(folder + "851_SWIR.npy"))
x_test_sar = preprocess_optical(np.load(folder + "851_SAR.npy"))
y_test = np.load(folder + "851_LABELS.npy")[:, :, :, 0]


def create_model(
    shape_rgbn,
    shape_swir,
    shape_sar,
    name="investigating",
    kernel_initializer="normal",
    activation="relu",
    learning_rate=0.001,
):
    model = define_model(
        shape_rgbn,
        shape_swir,
        shape_sar,
        name=name,
        kernel_initializer=kernel_initializer,
        activation=activation,
    )

    optimizer = tf.keras.optimizers.Adam(
        learning_rate=learning_rate,
        epsilon=1e-07,
        amsgrad=False,
        name="Adam",
    )

    model.compile(
        optimizer=optimizer,
        loss="mse",
        metrics=["mse", "mae"],
    )

    return model


with tf.device("/device:GPU:0"):
    lr = 0.001
    epochs = [10, 40]
    bs = [32, 16]

    model = create_model(
        (128, 128, 4),
        (64, 64, 2),
        (128, 128, 2),
        kernel_initializer="glorot_normal",
        activation="Mish",
        learning_rate=lr,
    )

    print(model.summary())

    model.fit(
        x=[x_train_rgbn, x_train_swir, x_train_sar],
        y=y_train,
        validation_split=0.2,
        epochs=epochs[0],
        verbose=1,
        batch_size=bs[0],
        use_multiprocessing=True,
        workers=0,
        shuffle=True,
    )

    model.fit(
        x=[x_train_rgbn, x_train_swir, x_train_sar],
        y=y_train,
        validation_split=0.2,
        epochs=epochs[1],
        initial_epoch=10,
        verbose=1,
        batch_size=bs[1],
        callbacks=[
            LearningRateScheduler(
                create_step_decay(
                    learning_rate=lr,
                    drop_rate=0.5,
                    epochs_per_drop=5,
                )
            ),
            EarlyStopping(
                monitor="val_loss",
                patience=10,
                min_delta=0.1,
                restore_best_weights=True,
            ),
        ],
        use_multiprocessing=True,
        workers=0,
        shuffle=True,
    )

    print(f"Batch_size: {str(bs)}")
    loss, mse, mae = model.evaluate(
        x=[x_test_rgbn, x_test_swir, x_test_sar],
        y=y_test,
        verbose=1,
        batch_size=bs[0],
        use_multiprocessing=True,
    )

    print(f"Mean Square Error:      {round(mse, 3)}")
    print(f"Mean Absolute Error:    {round(mae, 3)}")
    print("")


# 10 Epochs baseline (mse loss, relu, 32 min)
# Mean Square Error:      65.925
# Mean Absolute Error:    2.222

# 10 Epochs (mse loss, mish, 16 min) 0h 5m 14.45s
# Mean Square Error:      56.484
# Mean Absolute Error:    1.798

# 10 Epochs (mse loss, mish, 16 min, reduction_blocks) 0h 7m 14.29s
# Mean Square Error:      54.795
# Mean Absolute Error:    1.695

# 10 Epochs (mse loss, mish, 32 min, reduction_blocks) 0h 6m 38.52s
# Mean Square Error:      56.03
# Mean Absolute Error:    1.736

# 10 Epochs (mse loss, mish, 32 min, reduction_blocks, inception_blocks) 0h 11m 16.59s
# Mean Square Error:      53.597
# Mean Absolute Error:    1.627

# 10 Epochs (mse loss, mish, 32 min, reduction_blocks, inception_blocks, expansion_blocks) 0h 12m 39.16s
# Mean Square Error:      54.442
# Mean Absolute Error:    1.704

# 10 Epochs massive
# Mean Square Error:      117.87
# Mean Absolute Error:    1.866

model.save(folder + "models/denmark_03", save_format="tf")

timing(start)
