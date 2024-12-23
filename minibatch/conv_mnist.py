import argparse
import os
from time import time

import matplotlib.pyplot as plt
import torch
from bindsnet.analysis.plotting import plot_conv2d_weights
from bindsnet.datasets import MNIST, DataLoader
from bindsnet.encoding import PoissonEncoder
from bindsnet.learning import PostPre
from bindsnet.network import Network
from bindsnet.network.monitors import Monitor
from bindsnet.network.nodes import DiehlAndCookNodes, Input
from bindsnet.network.topology import Connection, Conv2dConnection
from torchvision import transforms
from tqdm import tqdm

from minibatch import ROOT_DIR


def process_variance_buffers(variance_buffers):
    for k in variance_buffers.keys():
        print("Variance statistics ", k)
        vb = variance_buffers[k]
        variance = (
            vb["sum_squares"] - (vb["sum"] * vb["sum"]) / float(vb["count"])
        ) / float(vb["count"])

        mean = vb["sum"] / float(vb["count"])

        print("Mean update %f" % mean.mean())
        print("Min of variance %f" % variance.min())
        print("Max of variance %f" % variance.max())
        print("Mean of variance %f" % variance.mean())
        print("Variance of variance %f" % variance.std())


def max_without_indices(inputs, dim=0):
    return torch.max(inputs, dim=dim)[0]


def main(args):
    if args.gpu:
        torch.cuda.manual_seed_all(args.seed)
    else:
        torch.manual_seed(args.seed)

    conv_size = int((28 - args.kernel_size + 2 * args.padding) / args.stride) + 1

    # Build network.
    network = Network()
    input_layer = Input(n=784, shape=(1, 28, 28), traces=True)

    conv_layer = DiehlAndCookNodes(
        n=args.n_filters * conv_size * conv_size,
        shape=(args.n_filters, conv_size, conv_size),
        traces=True,
    )

    conv_conn = Conv2dConnection(
        input_layer,
        conv_layer,
        kernel_size=args.kernel_size,
        stride=args.stride,
        update_rule=PostPre,
        norm=0.4 * args.kernel_size**2,
        nu=[0, args.lr],
        reduction=max_without_indices,
        wmax=1.0,
    )

    w = torch.zeros(
        args.n_filters, conv_size, conv_size, args.n_filters, conv_size, conv_size
    )
    for fltr1 in range(args.n_filters):
        for fltr2 in range(args.n_filters):
            if fltr1 != fltr2:
                for i in range(conv_size):
                    for j in range(conv_size):
                        w[fltr1, i, j, fltr2, i, j] = -100.0

    w = w.view(
        args.n_filters * conv_size * conv_size, args.n_filters * conv_size * conv_size
    )
    recurrent_conn = Connection(conv_layer, conv_layer, w=w)

    network.add_layer(input_layer, name="X")
    network.add_layer(conv_layer, name="Y")
    network.add_connection(conv_conn, source="X", target="Y")
    network.add_connection(recurrent_conn, source="Y", target="Y")

    # Voltage recording for excitatory and inhibitory layers.
    voltage_monitor = Monitor(network.layers["Y"], ["v"], time=args.time)
    network.add_monitor(voltage_monitor, name="output_voltage")

    if args.gpu:
        network.to("cuda")

    # Load MNIST data.
    train_dataset = MNIST(
        PoissonEncoder(time=args.time, dt=args.dt),
        None,
        os.path.join(ROOT_DIR, "data", "MNIST"),
        download=True,
        train=True,
        transform=transforms.Compose(
            [transforms.ToTensor(), transforms.Lambda(lambda x: x * args.intensity)]
        ),
    )

    spikes = {}
    for layer in set(network.layers):
        spikes[layer] = Monitor(network.layers[layer], state_vars=["s"], time=args.time)
        network.add_monitor(spikes[layer], name="%s_spikes" % layer)

    voltages = {}
    for layer in set(network.layers) - {"X"}:
        voltages[layer] = Monitor(
            network.layers[layer], state_vars=["v"], time=args.time
        )
        network.add_monitor(voltages[layer], name="%s_voltages" % layer)

    # Train the network.
    print("Begin training.\n")
    start = time()

    weights_im = None

    for epoch in range(args.n_epochs):
        if epoch % args.progress_interval == 0:
            print(
                "Progress: %d / %d (%.4f seconds)"
                % (epoch, args.n_epochs, time() - start)
            )
            start = time()

        train_dataloader = DataLoader(
            train_dataset,
            batch_size=args.batch_size,
            shuffle=True,
            num_workers=0,
            pin_memory=args.gpu,
        )

        variance_buffers = {}
        for k in network.connections.keys():
            variance_buffers[k] = {}
            variance_buffers[k]["prev"] = network.connections[k].w.clone()
            variance_buffers[k]["sum"] = torch.zeros_like(
                variance_buffers[k]["prev"], dtype=torch.double
            )
            variance_buffers[k]["sum_squares"] = torch.zeros_like(
                variance_buffers[k]["prev"], dtype=torch.double
            )
            variance_buffers[k]["count"] = 0

        for step, batch in enumerate(tqdm(train_dataloader)):
            # Get next input sample.
            inputs = {"X": batch["encoded_image"]}
            if args.gpu:
                inputs = {k: v.cuda() for k, v in inputs.items()}

            # Run the network on the input.
            network.run(inputs=inputs, time=args.time, input_time_dim=0)

            # manually compute the total update from this run
            for k in network.connections.keys():
                cur = network.connections[k].w.clone()
                weight_update = (cur - variance_buffers[k]["prev"]).double()
                variance_buffers[k]["sum"] += weight_update
                variance_buffers[k]["sum_squares"] += weight_update * weight_update
                variance_buffers[k]["count"] += 1
                variance_buffers[k]["prev"] = cur

            if step % 1000 == 999:
                process_variance_buffers(variance_buffers)

            # Decay learning rate.
            network.connections["X", "Y"].nu[1] *= 0.99

            # Optionally plot various simulation information.
            if args.plot:
                weights = conv_conn.w
                weights_im = plot_conv2d_weights(weights, im=weights_im)

                plt.pause(1e-8)

            network.reset_state_variables()  # Reset state variables.

    print(
        "Progress: %d / %d (%.4f seconds)\n"
        % (args.n_epochs, args.n_epochs, time() - start)
    )
    print("Training complete.\n")
    process_variance_buffers(variance_buffers)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--kernel-size", type=int, default=10)
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--n-filters", type=int, default=25)
    parser.add_argument("--padding", type=int, default=0)
    parser.add_argument("--time", type=int, default=100)
    parser.add_argument("--dt", type=int, default=1.0)
    parser.add_argument("--lr", type=float, default=0.005)
    parser.add_argument("--intensity", type=float, default=128.0)
    parser.add_argument("--progress-interval", type=int, default=10)
    parser.add_argument("--train", dest="train", action="store_true")
    parser.add_argument("--test", dest="train", action="store_false")
    parser.add_argument("--plot", dest="plot", action="store_true")
    parser.add_argument("--gpu", dest="gpu", action="store_true")
    parser.set_defaults(plot=False, gpu=False, train=True)
    return parser.parse_args()


if __name__ == "__main__":
    main(parse_args())
