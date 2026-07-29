# Contributing

How to contribute to easyeda project.

## Fork this repository

**Fork this repository before contributing**. It is a better practice, possibly even enforced, that only Pull Request from forks are accepted - consider a case where there are several main maintainers.

## Clone your fork

Next, clone your fork to your local machine, keep it up to date with the upstream, and update the online fork with those updates.

```bash
git clone https://github.com/YOUR-USERNAME/easyeda2kicad.py.git
cd easyeda2kicad.py
git remote add upstream https://github.com/uPesy/easyeda2kicad.py.git
git fetch upstream
git merge upstream/dev
git pull origin dev
```

**Note that PR should be done on the dev branch**

## Install for developers

Create a dedicated Python environment where to develop the project.


If you are using pip follow the official instructions on [Installing packages using pip and virtual environments](https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/#creating-a-virtual-environment), most likely what you want is:

```bash
python -m venv env
source env/bin/activate
```

Where `env` is the name you wish to give to the environment dedicated to this project.

Install the package in develop mode.

```bash
python setup.py develop
```

## Keep README.md aligned with features

The `README consistency monitor` workflow runs after pushes to the default
branch. It detects new public CLI options, added user-facing package modules,
and feature-style commit subjects such as `feat:` or `Add ...`. If a new CLI
option is absent from `README.md`, or a feature signal has no accompanying
README update, the workflow opens one deduplicated GitHub Issue for that pushed
revision range.

Run the same check before opening a pull request:

```bash
git fetch origin
python tools/readme_consistency.py \
  --base "$(git merge-base HEAD origin/HEAD)" \
  --head HEAD
```

Exit status `0` means aligned, `1` means an actionable documentation gap was
found, and `2` means the checker itself could not inspect the repository. The
feature detection is intentionally heuristic. If it flags a purely internal
change, record that reason on the generated Issue and close it.
