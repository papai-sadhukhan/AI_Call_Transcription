# Use Google's Dataflow Flex Template base image
FROM gcr.io/dataflow-templates-base/python39-template-launcher-base

# Set environment variables
ENV FLEX_TEMPLATE_PYTHON_PY_FILE="/template/main.py"
ENV FLEX_TEMPLATE_PYTHON_SETUP_FILE="/template/config/setup.py"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create template directory
WORKDIR /template

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model (738 MB - done during build to avoid runtime download)
RUN python -m spacy download en_core_web_lg

# Copy application files
COPY main.py .
COPY utils/ utils/

# Copy config directory
COPY config/ config/

# Set the entrypoint
ENTRYPOINT ["/opt/google/dataflow/python_template_launcher"]
