ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

WORKDIR /libs/metrics
COPY . /libs/metrics/
RUN pip install --no-cache-dir --upgrade -r /libs/metrics/requirements.txt
RUN pip install --no-cache-dir .
RUN pytest /libs/metrics/tests -v
