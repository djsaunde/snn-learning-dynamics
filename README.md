# SNN Learning Dynamics

Research code for analyzing learning dynamics in spiking neural networks. This code was
adapted from the [snn-minibatch](https://github.com/BINDS-LAB-UMASS/snn-minibatch)
repository, which corresponds to the
[Minibatch Processing in Spiking Neural Networks](https://arxiv.org/abs/1909.02549)
paper.

This project is in progress.

## Setup

### Prerequisites
- `python>=3.9,<3.12`
- [uv](https://github.com/astral-sh/uv) for dependency management
- `git`

### Installation

1. Clone the repository
```bash
git clone https://github.com/djsaunde/snn-learning-dynamics.git  # https
# or
git clone git@github.com:djsaunde/snn-learning-dynamics.git  # ssh
cd snn-learning-dynamics
```

2. Create and activate virtual environment with uv
```bash
uv venv --python 3.11
source .venv/bin/activate  # On Unix/macOS
# or
.venv\Scripts\activate  # On Windows
```

To autoload the virtual environment, install [`direnv`](https://direnv.net/) and run:

```bash
echo "source .venv/bin/activate" > .envrc
direnv allow
```

3. Install dependencies
```bash
uv sync
```

4. Install development dependencies
```bash
uv sync --all-extras
```

5. Install pre-commit hooks
```bash
pre-commit install  # note: pre-commit is a dev dependency
```

## Example Usage

There are many scripts in this repo for various experiments. For example you can run
the (batched) Diehl & Cook MNIST training script with:

```bash
python -m minibatch.dac.dac_mnist --log-dir path/to/log
```

Where `path/to/log` is a relative path to the directory where the metrics for the
training run will be stored. For various experiments,

## Development

This project uses several development tools:
- `black` for code formatting
- `ruff` for linting
- `mypy` for type checking
- `pre-commit` for automated checks

All of these run automatically when you commit code. For example:

```bash
git add .
# may fail if there are formatting / linting issues
git commit -m "<commit message>"

<pre-commit runs, auto-fixes many issues>
<user manually fix formatting / linting issues>

git add .
# will succeed if all flagged issues are fixed
git commit -m "<commit message>"
```
