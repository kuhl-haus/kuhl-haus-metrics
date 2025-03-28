ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

WORKDIR /libs/metrics
COPY . /libs/metrics/

# Install PDM
RUN pip install --no-cache-dir pdm

# Install the package directly from the wheel
RUN pdm build && pip install --no-cache-dir /libs/metrics/dist/*.whl

# Set entrypoint to python
ENTRYPOINT ["python"]
