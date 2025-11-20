"""
APPROACH 1: STATEFUL ENTITY RECOGNIZER (EntityRecognizer with ConversationContextTracker)
Uses context_tracker.update_from_agent() for stateful detection.
NO previous turns text concatenation - only uses stateful tracker.
"""
import logging
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
    StatefulPasswordRecognizer,
    StatefulPhoneNumberRecognizer
)
from utils.logging_config import setup_logging, get_logger


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
        self.logger = get_logger()
    
    @staticmethod
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

    def setup(self):
        # Download spaCy model if not available (for Dataflow workers)
        try:
            import spacy
            try:
                spacy.load('en_core_web_lg')
            except OSError:
                # Model not found, download it
                import subprocess
                import sys
                self.logger.info("Downloading spaCy model en_core_web_lg...")
                subprocess.check_call([sys.executable, '-m', 'spacy', 'download', 'en_core_web_lg'])
                self.logger.info("spaCy model downloaded successfully")
        except Exception as e:
            self.logger.warning(f"Could not ensure spaCy model is available: {e}")
        
        # Import entity recognizers (needed on Dataflow workers)
        from utils.entity_recognizers import (
            ConversationContextTracker,
            StatefulReferenceNumberRecognizer,
            StatefulBankDigitsRecognizer,
            StatefulCardDigitsRecognizer,
            StatefulNameRecognizer,
            StatefulAddressRecognizer,
            StatefulPostcodeRecognizer,
            StatefulEmailRecognizer,
            StatefulPasswordRecognizer,
            StatefulPhoneNumberRecognizer
        )
        
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

        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "redactConfig.yaml")
        provider = NlpEngineProvider(conf_file=config_path)

        self.analyzer = AnalyzerEngine(nlp_engine=provider.create_engine())
        self.anonymizer = AnonymizerEngine()
        
        # Load deny_list, validation config, detection scores, and shared word lists from YAML
        # Single unified configuration for all recognizers
        yaml_config = self._load_deny_list_config(config_path)
        self.deny_list = yaml_config['deny_list']
        self.person_validation_config = yaml_config['validation']
        self.detection_scores = yaml_config['detection_scores']
        
        # Store shared word lists as instance variables for reuse in process method
        self.number_words = yaml_config.get('number_words', [])
        self.filler_words = yaml_config.get('filler_words', [])
        self.name_boundaries = yaml_config.get('name_boundaries', [])
        
        # deny_list serves dual purpose:
        # 1. Exact match: if detected text exactly matches a word in deny_list, skip it
        # 2. Conversational validation: use words to calculate ratio for PERSON entity validation
        self.conversational_words = self.deny_list  # Same list, dual purpose
        
        # Get context indicators from JSON config
        context_indicators = self.config.get('context_indicators', {})
        
        # Add shared configuration to context_indicators for recognizers
        context_indicators['conversational_words'] = list(self.conversational_words)
        context_indicators['detection_scores'] = self.detection_scores
        context_indicators['number_words'] = self.number_words
        context_indicators['filler_words'] = self.filler_words
        context_indicators['name_boundaries'] = self.name_boundaries
        
        # Initialize conversation context tracker with config
        self.context_tracker = ConversationContextTracker(context_indicators)

        # Keep default recognizers for broad coverage, but we'll filter results in post-processing
        # This way we catch names that don't match our patterns, but still prevent false positives

        # Register stateful EntityRecognizers (all use context_tracker, context_indicators, and detection_scores)
        try:
            self.analyzer.registry.add_recognizer(StatefulReferenceNumberRecognizer(self.context_tracker, context_indicators))
            self.analyzer.registry.add_recognizer(StatefulBankDigitsRecognizer(self.context_tracker, context_indicators))
            self.analyzer.registry.add_recognizer(StatefulCardDigitsRecognizer(self.context_tracker, context_indicators))
            self.analyzer.registry.add_recognizer(StatefulNameRecognizer(self.context_tracker, context_indicators))
            self.analyzer.registry.add_recognizer(StatefulAddressRecognizer(self.context_tracker, context_indicators))
            self.analyzer.registry.add_recognizer(StatefulPostcodeRecognizer(self.context_tracker, context_indicators))
            self.analyzer.registry.add_recognizer(StatefulEmailRecognizer(self.context_tracker, context_indicators))
            self.analyzer.registry.add_recognizer(StatefulPasswordRecognizer(self.context_tracker, context_indicators))
            self.analyzer.registry.add_recognizer(StatefulPhoneNumberRecognizer(self.context_tracker, context_indicators))
            self.logger.info("Stateful EntityRecognizers registered (using context_tracker, context_indicators, and detection_scores from config)")
        except Exception as e:
            self.logger.warning("Could not register recognizer: %s", e)

    def _load_deny_list_config(self, config_path):
        """
        Load deny_list, validation config, detection scores, and shared word lists from YAML.
        
        Returns a dict with:
          - deny_list: Set of uppercase words for exact matching and validation
          - validation: Dict with person_entity validation settings
          - detection_scores: Dict with score thresholds for detection filtering
          - number_words: List of spoken number words (shared across recognizers)
          - filler_words: List of common filler words to skip in address/postcode detection
          - name_boundaries: List of words that typically follow names in introductions
        """
        import yaml
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                deny_list = config.get('deny_list', [])
                # Convert to uppercase set for fast lookup and case-insensitive matching
                deny_list_set = set(word.upper() for word in deny_list)
                
                # Load validation settings
                validation = config.get('validation', {})
                person_validation = validation.get('person_entity', {
                    'enabled': True,
                    'max_conversational_ratio': 0.5
                })
                
                # Load detection score settings - simplified
                detection_scores = config.get('detection_scores', {})
                scores_config = {
                    'min_score_threshold': detection_scores.get('min_score_threshold', 0.7)
                }
                
                # Load shared word lists (used across all recognizers)
                number_words = config.get('number_words', [])
                filler_words = config.get('filler_words', [])
                name_boundaries = config.get('name_boundaries', [])
                
                # Convert to uppercase for consistency and ensure all are strings
                # (YAML can interpret words like ON, OFF, YES, NO as booleans)
                number_words_list = [str(word).upper() for word in number_words]
                filler_words_list = [str(word).upper() for word in filler_words]
                name_boundaries_list = [str(word).upper() for word in name_boundaries]
                
                return {
                    'deny_list': deny_list_set,
                    'validation': person_validation,
                    'detection_scores': scores_config,
                    'number_words': number_words_list,
                    'filler_words': filler_words_list,
                    'name_boundaries': name_boundaries_list
                }
        except Exception as e:
            self.logger.warning(f"Could not load config from YAML: {e}")
            # Fallback defaults
            self.logger.warning("Could not load YAML config, using minimal defaults. Number words will not be available.")
            return {
                'deny_list': set(),
                'validation': {'enabled': True, 'max_conversational_ratio': 0.5},
                'detection_scores': {
                    'min_score_threshold': 0.7
                },
                'number_words': [],
                'filler_words': [],
                'name_boundaries': []
            }
    
    def _is_likely_false_positive(self, text_upper):
        """
        Validate if a PERSON detection from SpacyRecognizer is likely a false positive.
        Returns True if the text is primarily conversational words and should be rejected.
        
        This provides a safety net against NER model false positives while still allowing
        real names to be detected when they occur outside of expected contexts.
        
        Uses conversational_words from config for maintainability.
        """
        # Check if validation is enabled
        if not self.person_validation_config.get('enabled', True):
            return False  # Validation disabled, accept all detections
        
        words = text_upper.split()
        max_ratio = self.person_validation_config.get('max_conversational_ratio', 0.5)
        
        # If only 1-2 words, check if ALL words are conversational
        if len(words) <= 2:
            conversational_count = sum(1 for w in words if w in self.conversational_words)
            # All words are conversational = likely false positive
            return conversational_count == len(words)
        
        # For longer text (3+ words), check the ratio
        conversational_count = sum(1 for w in words if w in self.conversational_words)
        conversational_ratio = conversational_count / len(words)
        
        # If ratio exceeds threshold, likely not a real name
        # Example with default 0.5 threshold:
        #   "YOU'RE CAN'T" (100% conversational) -> rejected
        #   "JOHN SMITH PLEASE" (33% conversational) -> accepted
        return conversational_ratio > max_ratio


    def process(self, element):
        """Process each conversation turn with STATEFUL approach only"""
        # CRITICAL: Reset context tracker for each NEW conversation element
        # This prevents state leakage between different conversations on Dataflow workers
        from utils.entity_recognizers import ConversationContextTracker
        
        # Rebuild context_indicators with all config values (using cached instance variables)
        context_indicators = self.config.get('context_indicators', {})
        context_indicators['conversational_words'] = list(self.conversational_words)
        context_indicators['detection_scores'] = self.detection_scores
        context_indicators['number_words'] = self.number_words
        context_indicators['filler_words'] = self.filler_words
        context_indicators['name_boundaries'] = self.name_boundaries
        
        self.context_tracker = ConversationContextTracker(context_indicators)
        
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
                # Debug: Log context state for Customer turns when both address and postcode expected
                # if role == "Customer" and self.context_tracker.expecting_address and self.context_tracker.expecting_postcode:
                #     logging.info(f"*** ANALYZING CUSTOMER TURN WITH COMBINED ADDRESS+POSTCODE EXPECTED ***")
                #     logging.info(f"    Content: {content[:80]}...")
                #     logging.info(f"    Last agent turn: {self.context_tracker.last_turn_text[:80]}...")
                #     logging.info(f"    expecting_address: {self.context_tracker.expecting_address}")
                #     logging.info(f"    expecting_postcode: {self.context_tracker.expecting_postcode}")
                #     logging.info(f"    expecting_name: {self.context_tracker.expecting_name}")
                
                analyzer_result = self.analyzer.analyze(text=content, language="en")
                
                # Debug: Log analyzer results for combined detection case
                if role == "Customer" and self.context_tracker.expecting_address and self.context_tracker.expecting_postcode:
                    self.logger.debug(f"Analyzer returned {len(analyzer_result)} results for combined case")
                    for r in analyzer_result:
                        matched = content[r.start:r.end]
                        self.logger.debug(f"  - {r.entity_type}: '{matched[:50]}...' (score: {r.score:.2f})")
                
                # Filter results by score AND deny_list
                # Remove false positives using deny_list from YAML and intelligent validation
                filtered_results = []
                for r in analyzer_result:
                    matched_text = content[r.start:r.end].upper()
                    
                    # Debug: Log all detections before filtering
                    if role == "Customer" and self.context_tracker.expecting_address and self.context_tracker.expecting_postcode:
                        self.logger.debug(f"FILTER: Processing {r.entity_type}: '{matched_text[:50]}...'")
                    self.logger.debug(f"Detected {r.entity_type}: '{matched_text}' (score: {r.score:.2f})")
                    
                    # Apply deny_list filter ONLY to PERSON entities to prevent false positives
                    # All other entities (postcodes, passwords, emails, etc.) should not be filtered by deny_list
                    if r.entity_type == "PERSON":
                        if matched_text in self.deny_list:
                            self.logger.debug(f"Filtered PERSON by deny_list (exact match): '{matched_text}'")
                            continue
                        
                        # Also skip if ANY word in matched_text is in deny_list
                        words_in_match = matched_text.split()
                        if any(word in self.deny_list for word in words_in_match):
                            self.logger.debug(f"Filtered PERSON by deny_list (word match): '{matched_text}'")
                            continue
                    
                    # Skip if score is too low (configurable threshold)
                    min_score = self.detection_scores.get('min_score_threshold', 0.7)
                    if r.score <= min_score:
                        continue
                    
                    # SMART FILTER: For PERSON entities, validate them when NOT expecting a name
                    # This catches false positives from default recognizers (SpacyRecognizer, etc.)
                    # If we ARE expecting a name, trust all recognizers (custom + default)
                    # EXCEPTION: When BOTH address AND postcode are expected together, skip PERSON entities
                    # to allow AddressRecognizer to handle the full combined response
                    if r.entity_type == "PERSON":
                        # Skip PERSON when both address and postcode expected (combined detection)
                        if self.context_tracker.expecting_address and self.context_tracker.expecting_postcode:
                            logging.debug(f"Skipping PERSON '{matched_text}' - combined address+postcode expected")
                            continue
                        
                        # Otherwise, validate when NOT expecting name
                        if not self.context_tracker.expecting_name:
                            # Check if detection is from our custom recognizer (has analysis_explanation with recognizer attribute)
                            is_custom_recognizer = False
                            if r.analysis_explanation and hasattr(r.analysis_explanation, 'recognizer'):
                                recognizer_name = r.analysis_explanation.recognizer
                                # Our custom recognizers have "Stateful" in the name
                                is_custom_recognizer = "Stateful" in recognizer_name
                            
                            # Only validate default recognizer detections (not our custom ones)
                            if not is_custom_recognizer:
                                # Check if the matched text is mostly conversational words
                                if self._is_likely_false_positive(matched_text):
                                    logging.debug(f"Filtered false positive PERSON: '{matched_text}' (conversational ratio too high)")
                                    continue  # Skip this false positive
                    
                    filtered_results.append(r)
                
                # Debug: Log filtered results for combined case
                if role == "Customer" and self.context_tracker.expecting_address and self.context_tracker.expecting_postcode:
                    logging.info(f"*** MAIN: After filtering, {len(filtered_results)} results remain:")
                    for r in filtered_results:
                        matched = content[r.start:r.end]
                        logging.info(f"      - {r.entity_type}: '{matched[:50]}...' (score: {r.score:.2f})")
                
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
        element["redacted_transcript"] = self.deconstruct_transcript(redacted_conversation)
        element["redacted_entity"] = "; ".join(redacted_entity_rows)
        yield element


def run(argv=None):
    parser = argparse.ArgumentParser(description="Run the data pipeline with STATEFUL EntityRecognizer approach.")
    parser.add_argument('--config_path', type=str, required=True, help='Path to the config file (e.g., config_dev.json or config_prod.json)')
    parser.add_argument('--runner', type=str, default='DataflowRunner', help='Pipeline runner (default: DataflowRunner)')
    parser.add_argument('--log_level', type=str, default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], help='Logging level (default: INFO)')
    args, pipeline_args = parser.parse_known_args(argv)

    # Setup logging based on runner type
    logger = setup_logging(runner=args.runner, log_level=args.log_level)
    logger.info(f"Starting entity redaction pipeline with runner: {args.runner}")
    logger.info(f"Loading configuration from: {args.config_path}")

    config = load_config(args.config_path)

    # Add Dataflow experiments to pipeline_args before constructing PipelineOptions
    if 'experiments' in config.get('dataflow', {}):
        for exp in config['dataflow']['experiments']:
            pipeline_args.append(f'--experiments={exp}')

    # Ensure runner is set
    pipeline_args.append(f'--runner={args.runner}')
    
    # Add dataflow service options if specified in config
    if 'dataflow_service_options' in config.get('dataflow', {}):
        for option in config['dataflow']['dataflow_service_options']:
            pipeline_args.append(f'--dataflow_service_options={option}')
    
    # Add service account if specified in config
    if 'service_account_email' in config.get('project', {}):
        pipeline_args.append(f'--service_account_email={config["project"]["service_account_email"]}')
        print(f"Using service account: {config['project']['service_account_email']}")
    
    # Add setup file for custom modules and dependencies
    setup_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "setup.py")
    if os.path.exists(setup_file):
        pipeline_args.append(f'--setup_file={setup_file}')
        print(f"Using setup file: {setup_file}")

    options = PipelineOptions(pipeline_args)

    print(f"Running STATEFUL ENTITY RECOGNIZER approach with config: {args.config_path}")
    
    # Set common options for both runners
    google_cloud_options = options.view_as(GoogleCloudOptions)
    google_cloud_options.project = config['project']['dataflow_project_id']
    
    # Set temp_location for BigQuery operations (required for both DirectRunner and DataflowRunner)
    if 'staging_location' in config['project']:
        temp_location = config['project']['staging_location'].replace('/staging', '/temp')
        google_cloud_options.temp_location = temp_location
        print(f"Using temp location: {temp_location}")
    
    # Set Dataflow-specific options if using DataflowRunner
    if not options.get_all_options().get('runner') or options.get_all_options().get('runner') == 'DataflowRunner':
        options.view_as(StandardOptions).runner = 'DataflowRunner'
        google_cloud_options.region = config['project']['region']
        google_cloud_options.staging_location = config['project']['staging_location']
        google_cloud_options.job_name = config['project']['job_name']
        
        # Set subnetwork if provided in config
        if 'subnetwork' in config['project']:
            worker_options = options.view_as(WorkerOptions)
            worker_options.subnetwork = config['project']['subnetwork']
            print(f"Using subnetwork: {config['project']['subnetwork']}")
        
        # Service account already added to pipeline_args above
        if 'service_account_email' in config['project']:
            print(f"Dataflow will use service account: {config['project']['service_account_email']}")

    # Get BigQuery configuration
    bigquery_project = config['project']['bigquery_project_id']
    output_dataset = config['dataset']['output']
    target_table_name = config['tables']['target']['name']
    output_table = f"{bigquery_project}.{output_dataset}.{target_table_name}"

    # Clean up temp tables from dataflow_temp_dataset BEFORE starting the pipeline (if any exist)
    temp_dataset_id = config['project']['temp_bigquery_dataset']
    try:
        from google.cloud import bigquery as bq_client
        client = bq_client.Client(project=bigquery_project)
        
        # List all tables in temp dataset
        dataset_id = f"{bigquery_project}.{temp_dataset_id}"
        tables = list(client.list_tables(dataset_id))
        
        if tables:
            print(f"\nCleaning up {len(tables)} temp tables from {temp_dataset_id}:")
            for table in tables:
                table_id = f"{bigquery_project}.{temp_dataset_id}.{table.table_id}"
                print(f"  - Deleting {table.table_id}")
                client.delete_table(table_id, not_found_ok=True)
            print(f"Successfully cleaned up all temp tables\n")
    except Exception as e:
        print(f"Warning: Could not check/clean temp tables from {temp_dataset_id}: {e}")
        print("Proceeding with pipeline execution...\n")
    
    # Truncate target table BEFORE starting the pipeline
    print(f"Truncating target table: {output_table}")
    try:
        from google.cloud import bigquery as bq_client
        client = bq_client.Client(project=bigquery_project)
        
        # Truncate table using TRUNCATE TABLE statement
        truncate_query = f"TRUNCATE TABLE `{output_table}`"
        query_job = client.query(truncate_query)
        query_job.result()  # Wait for completion
        print(f"Successfully truncated table: {output_table}\n")
    except Exception as e:
        print(f"Warning: Could not truncate table {output_table}: {e}")
        print("Proceeding with pipeline execution...\n")

    with beam.Pipeline(options=options) as p:
        # Use BigQuery project for table references and queries
        input_table = f"{bigquery_project}.{config['dataset']['input']}.{config['tables']['source']['name']}"
        select_fields = config['processing']['selected_fields']
        condition = config['processing']['condition']
        dataset_ref = bigquery.DatasetReference()
        dataset_ref.projectId = bigquery_project
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
            import json
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
            import datetime
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

        # Use EXPORT method to avoid temp table conflicts
        # EXPORT is more reliable for Dataflow, though slightly slower than DIRECT_READ
        bigquery_data = p | "Read from BigQuery Table" >> beam.io.ReadFromBigQuery(
            query=input_query,
            use_standard_sql=True,
            project=bigquery_project,
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
            print(f"{count} records inserted into BigQuery.")
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
