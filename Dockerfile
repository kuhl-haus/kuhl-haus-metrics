ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

RUN pip install --no-cache-dir pdm

WORKDIR /libs/metrics
COPY . /libs/metrics/

# Install dependencies and build/install package
RUN pdm install -G testing

# Run tests
RUN pdm run pytest tests -v

# Build wheel
RUN pdm build

# Install into site-packages from wheel
RUN pip install --no-cache-dir /libs/metrics/dist/*.whl
