import logging
logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)
logging.getLogger('apache_beam.io.gcp.bigquery').setLevel(logging.ERROR)
import json
from copy import deepcopy
import datetime
import os
import argparse
import pandas as pd
import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions, TypeOptions, GoogleCloudOptions, WorkerOptions
from apache_beam.io.gcp.internal.clients import bigquery
import re
from utils.spoken_to_numeric import spoken_to_numeric
from utils.customer_registry import SpokenAddressRecognizer, VerificationCodeRecognizer, BankLastDigitsRecognizer

def load_config():
    """Load configuration from config.json"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    with open(config_path, 'r') as f:
        return json.load(f)



def deconstruct_transcript(conversation_transcript: list) -> str:
    """
    Deconstructs a conversation transcript into a single string.
    Each conversation turn has role (agent/customer) and content.
    Format: [{"role":"agent","content":"text"}, {"role":"customer","content":"text"}]
    """
    if not conversation_transcript:
        return ""
    
    content_parts = []
    for turn in conversation_transcript:
        if isinstance(turn, dict) and 'content' in turn:
            content_parts.append(turn['content'])
    
    return " ".join(content_parts)


class DirectPIITransform(beam.DoFn):
    """
    Directly redacts PII from conversation structure without deconstructing.
    Processes each conversation turn individually to preserve structure.
    """
    def __init__(self, config):
        self.config = config
        self.analyzer = None
        self.anonymizer = None
        self.operators = {}

    def setup(self):
        # local imports for Presidio

        from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
        from presidio_anonymizer import AnonymizerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        from presidio_anonymizer.entities import OperatorConfig

        # Build operators from config
        for entity_type, replacement in self.config.get('pii_entities', {}).items():
            self.operators[entity_type] = OperatorConfig("replace", {
                "new_value": replacement
            })

        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "redactConfig.yaml")
        provider = NlpEngineProvider(conf_file=config_path)

        self.analyzer = AnalyzerEngine(nlp_engine=provider.create_engine())
        self.anonymizer = AnonymizerEngine()

        # Register custom recognizers from utils.customer_registry
        try:
            self.analyzer.registry.add_recognizer(SpokenAddressRecognizer())
            self.analyzer.registry.add_recognizer(VerificationCodeRecognizer())
            self.analyzer.registry.add_recognizer(BankLastDigitsRecognizer())
        except Exception as e:
            logging.warning("Could not register custom recognizer: %s", e)



    def process(self, element):
        """Process each conversation turn directly for PII redaction"""
        # element expected to be a dict with "conversation_transcript": [...]
        conversation = element.get("conversation_transcript", [])
        redacted_conversation = []
        debug_rows = []
        for turn in conversation:
            if isinstance(turn, dict) and 'content' in turn:
                content = turn.get('content', '')
                role = turn.get('role', '')
                # Convert spelled numbers and merge spelled letters
                converted_content = spoken_to_numeric(content)
                # Analyze and redact PII in this turn's content
                analyzer_result = self.analyzer.analyze(text=converted_content, language="en")
                # Filter entities by score > 0.7
                filtered_results = [r for r in analyzer_result if r.score > 0.7]
                # Collect debug info for matched entities
                for result in filtered_results:
                    matched_text = converted_content[result.start:result.end]
                    debug_rows.append(f"Matched entity: {result.entity_type}, text: {matched_text}, score: {result.score}")

                anonymizer_result = self.anonymizer.anonymize(
                    text=converted_content,
                    analyzer_results=filtered_results,
                    operators=self.operators,
                )
                # Create redacted turn without debug field
                redacted_turn = {
                    'role': role,
                    'content': anonymizer_result.text
                }
                redacted_conversation.append(redacted_turn)
            else:
                # Preserve non-dict elements as-is
                redacted_conversation.append(turn)

        # Update the element with redacted conversation
        element["conversation_transcript"] = redacted_conversation
        # Also create a flattened redacted transcript for compatibility
        element["redacted_transcript"] = deconstruct_transcript(redacted_conversation)
        # Add row-level debug string
        element["debug"] = "; ".join(debug_rows)
        yield element


def run(argv=None):

    # Only support BigQuery mode
    config = load_config()
    options = PipelineOptions(argv)

    print(f"🔄 Running in BIGQUERY mode")
    if not options.get_all_options().get('runner') or options.get_all_options().get('runner') == 'DataflowRunner':
        options.view_as(StandardOptions).runner = 'DataflowRunner'
        google_cloud_options = options.view_as(GoogleCloudOptions)
        google_cloud_options.project = config['project']['id']
        google_cloud_options.region = config['project']['region']
        google_cloud_options.staging_location = config['project']['staging_location']
        google_cloud_options.subnetwork = config['project']['subnetwork']
        google_cloud_options.job_name = config['project']['job_name']
        dataflow_options = options.view_as(WorkerOptions)
        dataflow_options.experiments = config['dataflow']['experiments']

    with beam.Pipeline(options=options) as p:
        input_table = f"{config['project']['id']}.{config['dataset']['input']}.{config['tables']['source']['name']}"
        output_table = f"{config['project']['id']}.{config['dataset']['output']}.{config['tables']['target']['name']}"
        select_fields = config['processing']['selected_fields']
        condition = config['processing']['condition']
        dataset_ref = bigquery.DatasetReference()
        dataset_ref.projectId = config['project']['id']
        input_query = f"""
        SELECT {', '.join(select_fields)}
        FROM {input_table}
        WHERE {condition}
        LIMIT {config['processing']['limit']}
        """
        print("Input Query for BigQuery:")
        print(input_query)

        def process_row(row):
            # Get the source column name for transcript (always string)
            transcript_src_col = config['tables']['source']['columns']['conversation_transcript_json']
            conversation_json = row.get(transcript_src_col)
            row["transcript_original"] = conversation_json
            try:
                conversation_transcript = json.loads(conversation_json)
            except Exception:
                conversation_transcript = conversation_json
            row["conversation_transcript"] = conversation_transcript
            return row

        def prepare_output_row(row):
            row[config['tables']['target']['columns']['conversation_transcript_json']] = json.dumps(row["conversation_transcript"], separators=(",", ":"))
            output_row = {}
            for col_key, col_name in config['tables']['target']['columns'].items():
                if col_name in row:
                    output_row[col_name] = row[col_name]
                elif col_key == 'transcription_file_dt':
                    source_col = config['tables']['source']['columns'][col_key]
                    output_row[col_name] = row.get(source_col)
                elif col_key == 'transaction_id':
                    source_col = config['tables']['source']['columns'][col_key]
                    output_row[col_name] = row[source_col]
            # Always include transcript_original from row, regardless of mapping
            output_row['transcript_original'] = row.get('transcript_original')
            output_row['load_datetime'] = datetime.datetime.now().isoformat()
            # Use row-level debug info
            output_row['debug'] = row.get('debug', '')
            return output_row

        bigquery_data = p | "Read from BigQuery Table" >> beam.io.ReadFromBigQuery(
            query=input_query,
            method="DIRECT_READ",
            use_standard_sql=True,
            project = config['project']['id'],
        )

        result = (
            bigquery_data
            | "Parse Conversation" >> beam.Map(process_row)
            | "Direct PII Redaction" >> beam.ParDo(DirectPIITransform(config))
            | "Prepare Output" >> beam.Map(prepare_output_row)
        )

        # Count records processed
        record_count = result | "Count Records" >> beam.combiners.Count.Globally()
        def print_count(count):
            print(f"✅ {count} records inserted into BigQuery.")
        record_count | "Print Count" >> beam.Map(print_count)

        write_method = config['dataflow'].get('write_method', 'STREAMING_INSERTS')

        result | "Write to BigQuery" >> beam.io.WriteToBigQuery(
            output_table,
            schema=config['tables']['target']['schema'],
            write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
            create_disposition=beam.io.BigQueryDisposition.CREATE_IF_NEEDED,
            method=write_method,
            batch_size=config['processing'].get('batch_size', None),
        )


if __name__ == "__main__":
    run()
