"""
APPROACH 1: STATEFUL ENTITY RECOGNIZER (EntityRecognizer with ConversationContextTracker)
Uses context_tracker.update_from_agent() for stateful detection.
NO previous turns text concatenation - only uses stateful tracker.
"""
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
# Import ONLY entity recognizers (stateful approach)
from utils.entity_recognizers import (
    ConversationContextTracker,
    StatefulReferenceNumberRecognizer,
    StatefulBankDigitsRecognizer,
    StatefulCardDigitsRecognizer,
    StatefulNameRecognizer,
    StatefulAddressRecognizer,
    StatefulPostcodeRecognizer,
    StatefulEmailRecognizer,
    StatefulPasswordRecognizer
)


def load_config(config_path):
    """Load configuration from the given config path"""
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


class EntityRecognizerPIITransform(beam.DoFn):
    """
    STATEFUL APPROACH: Uses ConversationContextTracker for ALL recognizers.
    NO previous turns concatenation - pure stateful detection.
    """
    def __init__(self, config):
        self.config = config
        self.analyzer = None
        self.anonymizer = None
        self.operators = {}
        self.context_tracker = None

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
        
        # Load deny_list from YAML for post-processing filter
        self.deny_list = self._load_deny_list(config_path)
        
        # Initialize conversation context tracker
        self.context_tracker = ConversationContextTracker()

        # Register ONLY stateful EntityRecognizers (all use context_tracker)
        try:
            self.analyzer.registry.add_recognizer(StatefulReferenceNumberRecognizer(self.context_tracker))
            self.analyzer.registry.add_recognizer(StatefulBankDigitsRecognizer(self.context_tracker))
            self.analyzer.registry.add_recognizer(StatefulCardDigitsRecognizer(self.context_tracker))
            self.analyzer.registry.add_recognizer(StatefulNameRecognizer(self.context_tracker))
            self.analyzer.registry.add_recognizer(StatefulAddressRecognizer(self.context_tracker))
            self.analyzer.registry.add_recognizer(StatefulPostcodeRecognizer(self.context_tracker))
            self.analyzer.registry.add_recognizer(StatefulEmailRecognizer(self.context_tracker))
            self.analyzer.registry.add_recognizer(StatefulPasswordRecognizer(self.context_tracker))
            logging.info("✅ Stateful EntityRecognizers registered (using context_tracker)")
        except Exception as e:
            logging.warning("Could not register recognizer: %s", e)

    def _load_deny_list(self, config_path):
        """Load deny_list from YAML configuration file for post-processing filter."""
        import yaml
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                deny_list = config.get('deny_list', [])
                # Convert to uppercase for case-insensitive matching
                return [word.upper() for word in deny_list]
        except Exception as e:
            logging.warning(f"Could not load deny_list from YAML: {e}")
            return []


    def process(self, element):
        """Process each conversation turn with STATEFUL approach only"""
        conversation = element.get("conversation_transcript", [])
        redacted_conversation = []
        redacted_entity_rows = []
        
        for turn in conversation:
            if isinstance(turn, dict) and 'content' in turn:
                content = turn.get('content', '')
                role = turn.get('role', '')
                
                # DON'T convert spoken numbers to digits - keep original text
                # This is important for recognizing spelled-out numbers
                
                # STATEFUL APPROACH: Analyze current turn FIRST (uses context from previous turn)
                # Recognizers use context_tracker state set by PREVIOUS turn
                analyzer_result = self.analyzer.analyze(text=content, language="en")
                
                # Filter results by score AND deny_list
                # Remove false positives using deny_list from YAML
                filtered_results = []
                for r in analyzer_result:
                    matched_text = content[r.start:r.end].upper()
                    
                    # Skip if text is in deny_list (case-insensitive)
                    if matched_text in self.deny_list:
                        continue
                    
                    # Skip if score is too low
                    if r.score > 0.7:
                        filtered_results.append(r)
                
                # Log matched entities for audit trail
                for result in filtered_results:
                    matched_text = content[result.start:result.end]
                    redacted_entity_rows.append(f"[{role}] {result.entity_type}: {matched_text} (score: {result.score:.2f})")

                # Anonymize the detected PII
                anonymizer_result = self.anonymizer.anonymize(
                    text=content,
                    analyzer_results=filtered_results,
                    operators=self.operators,
                )
                
                # Create redacted turn
                redacted_turn = {
                    'role': role,
                    'content': anonymizer_result.text
                }
                redacted_conversation.append(redacted_turn)
                
                # Update context tracker AFTER analysis for NEXT turn
                # This sets expectations based on current turn for the following turn
                if self.context_tracker:
                    self.context_tracker.update_context(content)
            else:
                # Preserve non-dict elements as-is
                redacted_conversation.append(turn)

        # Update element with redacted conversation
        element["conversation_transcript"] = redacted_conversation
        element["redacted_transcript"] = deconstruct_transcript(redacted_conversation)
        element["redacted_entity"] = "; ".join(redacted_entity_rows)
        yield element


def run(argv=None):
    parser = argparse.ArgumentParser(description="Run the data pipeline with STATEFUL EntityRecognizer approach.")
    parser.add_argument('--config_path', type=str, required=True, help='Path to the config file (e.g., config_dev.json or config_prod.json)')
    parser.add_argument('--runner', type=str, default='DataflowRunner', help='Pipeline runner (default: DataflowRunner)')
    args, pipeline_args = parser.parse_known_args(argv)

    config = load_config(args.config_path)

    # Add Dataflow experiments to pipeline_args before constructing PipelineOptions
    if 'experiments' in config.get('dataflow', {}):
        for exp in config['dataflow']['experiments']:
            pipeline_args.append(f'--experiments={exp}')

    # Ensure runner is set
    pipeline_args.append(f'--runner={args.runner}')

    options = PipelineOptions(pipeline_args)

    print(f"🔄 Running STATEFUL ENTITY RECOGNIZER approach with config: {args.config_path}")
    # Set Dataflow job project
    if not options.get_all_options().get('runner') or options.get_all_options().get('runner') == 'DataflowRunner':
        options.view_as(StandardOptions).runner = 'DataflowRunner'
        google_cloud_options = options.view_as(GoogleCloudOptions)
        google_cloud_options.project = config['project']['dataflow_project_id']
        google_cloud_options.region = config['project']['region']
        google_cloud_options.staging_location = config['project']['staging_location']
        google_cloud_options.job_name = config['project']['job_name']

    with beam.Pipeline(options=options) as p:
        # Use BigQuery project for table references and queries
        input_table = f"{config['project']['bigquery_project_id']}.{config['dataset']['input']}.{config['tables']['source']['name']}"
        output_table = f"{config['project']['bigquery_project_id']}.{config['dataset']['output']}.{config['tables']['target']['name']}"
        select_fields = config['processing']['selected_fields']
        condition = config['processing']['condition']
        bigquery_project = config['project']['bigquery_project_id']
        dataset_ref = bigquery.DatasetReference()
        dataset_ref.projectId = config['project']['bigquery_project_id']
        dataset_ref.datasetId = config['project']['temp_bigquery_dataset']
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
            transcript_src_col = config['tables']['source']['columns'].get('input_transcript')
            conversation_json = row.get(transcript_src_col)
            row["transcript_original"] = conversation_json
            try:
                conversation_transcript = json.loads(conversation_json)
            except Exception:
                conversation_transcript = conversation_json
            row["conversation_transcript"] = conversation_transcript
            return row

        def prepare_output_row(row):
            # Write redacted transcript to transcription_redacted column
            row[config['tables']['target']['columns'].get('transcription_redacted')] = json.dumps(row["conversation_transcript"], separators=(",", ":"))
            output_row = {}
            # Only output the required BQ target columns
            output_row['file_date'] = row.get('file_date')
            output_row['transaction_id'] = row.get('transaction_id')
            output_row['transaction_identifier'] = row.get('transaction_identifier')
            output_row['transcription_redacted'] = row.get('transcription_redacted')
            output_row['redacted_entity'] = row.get('redacted_entity', '')
            output_row['load_dt'] = datetime.datetime.now().isoformat()
            return output_row

        bigquery_data = p | "Read from BigQuery Table" >> beam.io.ReadFromBigQuery(
            query=input_query,
            method="DIRECT_READ",
            use_standard_sql=True,
            project=bigquery_project,
            temp_dataset=dataset_ref,
        )
        # bigquery_data | "Print Read Row" >> beam.Map(lambda row: print(f"Read from BigQuery: {row}"))

        result = (
            bigquery_data
            | "Parse Conversation" >> beam.Map(process_row)
            | "Stateful Entity Recognition" >> beam.ParDo(EntityRecognizerPIITransform(config))
            | "Prepare Output" >> beam.Map(prepare_output_row)
        )
        # result | "Print Output Row" >> beam.Map(print)
        # Count records processed
        record_count = result | "Count Records" >> beam.combiners.Count.Globally()
        def print_count(count):
            print(f"✅ {count} records inserted into BigQuery.")
        record_count | "Print Count" >> beam.Map(print_count)

        write_method = config['dataflow'].get('write_method', 'STREAMING_INSERTS')

        result | "Write to BigQuery" >> beam.io.WriteToBigQuery(
            output_table,
            write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
            create_disposition=beam.io.BigQueryDisposition.CREATE_IF_NEEDED,
            method=write_method,
            batch_size=config['processing'].get('batch_size', None),
        )


if __name__ == "__main__":
    import sys
    run(sys.argv[1:])
