# Use the official Dataflow Flex Template base image for Python 3.9
FROM gcr.io/dataflow-templates-base/python39-template-launcher-base

# Set working directory
WORKDIR /template

# Copy requirements file first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the spaCy large English model (738 MB)
# This eliminates the need to download it at worker startup time
RUN python -m spacy download en_core_web_lg

# Copy the application code
COPY main.py .
COPY setup.py .
COPY redactConfig.yaml .

# Copy the utils package
COPY utils/ utils/

# Set environment variables for Python
ENV PYTHONUNBUFFERED=1

# Set the entrypoint to the Dataflow launcher
# The launcher will handle starting the Dataflow pipeline
ENV FLEX_TEMPLATE_PYTHON_PY_FILE="/template/main.py"

# Metadata about the template
LABEL maintainer="Sky UK"
LABEL description="Dataflow Flex Template for PII Redaction Pipeline"
LABEL version="1.0.0"
