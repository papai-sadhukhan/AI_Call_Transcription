# Local Development Guide

## Usage Examples


### Run with BigQuery (dev/prod config)
You must now specify the config file using `--config_path`:

**For development:**
```bash
python main.py --config_path config_dev.json --runner DataflowRunner
```

**For production:**
```bash
python main.py --config_path config_prod.json --runner DataflowRunner
```

The pipeline reads from the configured BigQuery table in the selected config file.

## Overview
This folder contains the PII redaction pipeline configured for local development and testing. It's essentially the same as the main production pipeline but with updated table names and the ability to run locally using DirectRunner.

## Quick Start

Install latest Presidio:
pip install --upgrade git+https://github.com/microsoft/presidio.git#subdirectory=presidio-analyzer
pip install --upgrade git+https://github.com/microsoft/presidio.git#subdirectory=presidio-anonymizer


### 1. Setup Environment
```bash
# Navigate to the local_run directory
cd local_run

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Download spaCy model
python -m spacy download en_core_web_lg
```


### 2. Run Local Pipeline
```bash
python main.py --config_path config_dev.json --runner DirectRunner
```

## What's Different from Production

| Production (Parent Directory) | Local Development (This Folder) |
|-------------------------------|----------------------------------|
| **Tables**: Original production tables | **Tables**: Experiment tables (td_verint_transcription_raw → td_verint_transcription_redacted_temp) |
| **Project**: skyuk-uk-customer-tds-dev | **Project**: skyuk-uk-reg-expmnt-prod |
| **Default Runner**: DataflowRunner | **Flexible Runner**: DirectRunner (local) or DataflowRunner (cloud) |
| **Usage**: Fixed configuration | **Usage**: Command-line configurable |

## Files in This Directory

### `main.py`
- **Purpose**: Configurable pipeline for conversation transcript redaction
- **Key Features**:
  - Configuration-driven (uses `config.json`)
  - Handles conversation transcript format with role/content structure
  - Command-line runner selection (DirectRunner/DataflowRunner)
  - Same PII detection logic as production
  - Flexible table and column mapping

### `config.json`
- **Purpose**: Central configuration file for all pipeline settings
- **Contains**:
  - Project and dataset configurations
  - Table names and column mappings
  - PII entity replacement rules
  - Processing parameters (limits, batch sizes)
  - Dataflow execution settings

### `requirements.txt`
- **Purpose**: All dependencies needed for local development
- **Includes**:
  - Apache Beam
  - Presidio libraries
  - spaCy
  - Development tools

### `README.md`
- **Purpose**: This documentation file

## Configuration

All settings are now managed through `config.json`:

### Data Sources
- **Source**: Configured in `config.json` under `tables.source`
- **Target**: Configured in `config.json` under `tables.target`
- **Project**: Configurable project ID and datasets

### Table Structure

**Input Table** (`td_verint_transcription_raw`):
- `transaction_id`: Transaction identifier  
- `transcription_file_dt`: Transcript file date/time
- `conversation_transcript_json`: JSON array of conversation turns

**Output Table** (`td_verint_transcription_redacted_temp`):
- `transaction_id`: Transaction identifier (copied from input)
- `transcription_file_dt`: Transcript file date/time (copied from input)  
- `conversation_transcript_json`: JSON array with PII redacted using `#####`

### Conversation Format
The pipeline handles conversation transcripts with this structure:
```json
[
  {"role":"agent","content":"THANK YOU FOR CALLING ABC YOU'RE SPEAKING WITH AGENT_X"},
  {"role":"customer","content":"HELLO"},
  {"role":"agent","content":"YES HELLO"}
]
```

**After PII redaction:**
```json
[
  {"role":"agent","content":"THANK YOU FOR CALLING ABC YOU'RE SPEAKING WITH #####"},
  {"role":"customer","content":"HELLO"}, 
  {"role":"agent","content":"YES HELLO"}
]
```

## Usage Options


### Local Execution (DirectRunner)
```bash
python main.py --config_path config_dev.json --runner DirectRunner
```
- Runs on your local machine
- Good for testing and development
- Processes smaller datasets efficiently

### Cloud Execution (DataflowRunner)
```bash
python main.py --config_path config_prod.json --runner DataflowRunner
```
- Runs on Google Cloud Dataflow
- Scalable for large datasets
- Requires Google Cloud authentication

## Usage Examples


### Run with BigQuery
```bash
python main.py --config_path config_dev.json --runner DirectRunner
```


### Run with Local Excel File
```bash
python main.py --config_path config_dev.json --runner DirectRunner --input=Local --local_file=local_test/sample_transcript_data.xlsx --output_file=local_test/output_redacted_data.xlsx
```

- For BigQuery, the pipeline reads from the configured table in `config.json`.
- For Local, the pipeline reads from the specified Excel file and writes output to the specified Excel file.

## Customization

### Modifying Configuration
Edit `config.json` to change:


**Table Names:**
```json
{
  "tables": {
    "source": {"name": "your_source_table"},
    "target": {"name": "your_target_table"}
  }
}
```

**Column Mapping:**
```json
{
  "tables": {
    "source": {
      "columns": {
        "transaction_id": "your_id_column",
        "transcription_file_dt": "your_date_column",
        "conversation_transcript_json": "your_json_column"
      }
    }
  }
}
```

**PII Replacements:**
```json
{
  "pii_entities": {
    "PERSON": "#####",
    "PHONE_NUMBER": "#####",
    "EMAIL_ADDRESS": "#####"
  }
}
```

### Command Line Options
You can pass any Apache Beam pipeline options:
```bash
# Local execution with specific worker count
python

The pipeline uses the `redactConfig.yaml` file from the parent directory, so any changes to entity mappings or NLP settings will be reflected in local runs.

## Selecting Environment

You can now select the environment config file at runtime:

- For development: `--config_path config_dev.json`
- For production: `--config_path config_prod.json`

This allows you to switch between dev and prod settings without changing code.

## Troubleshooting

### Common Issues

#### Import Errors
```bash
# Make sure virtual environment is activated
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

# Reinstall dependencies
pip install -r requirements.txt
```

#### spaCy Model Missing
```bash
python -m spacy download en_core_web_lg

# Verify installation
python -c "import spacy; spacy.load('en_core_web_lg')"
```

#### Configuration File Not Found
The pipeline looks for `redactConfig.yaml` in the parent directory. Make sure you're running from the correct location:
```bash
# Should be in: .../redaction/local_run/
pwd  # or cd on Windows
ls ..  # Should show redactConfig.yaml
```

#### Memory Issues
If you encounter memory issues:
```python
# In main.py, modify pipeline options:
options = PipelineOptions([
    '--runner=DirectRunner',
    '--direct_num_workers=1',  # Reduce workers
    '--direct_running_mode=in_memory'  # Use in-memory processing
])
```

## Development Workflow

1. **Edit Code**: Make changes to `main.py`
2. **Test**: Run `python test_setup.py`
3. **Execute**: Run `python main.py`
4. **Debug**: Check console output and logs
5. **Iterate**: Repeat until satisfied

## Moving to Production

When you're ready to deploy changes to production:

1. **Update Production Code**: Apply your changes to `../main.py`
2. **Test Locally**: Run the modified production code with DirectRunner
3. **Build Containers**: Use the Cloud Build configuration
4. **Deploy**: Submit to Google Cloud Dataflow

## Performance Notes

- **Local execution** is great for development but limited by single-machine resources
- **Sample data** processes in seconds
- **Real BigQuery data** (if you run `../main.py` locally) will take longer
- **Production deployment** handles large-scale data efficiently

## Next Steps

1. Run `python test_setup.py` to verify setup
2. Run `python main.py` to see PII redaction in action
3. Experiment with the sample data and configuration
4. When ready, move to production deployment in the parent directory