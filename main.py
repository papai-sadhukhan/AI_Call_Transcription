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
    StatefulPasswordRecognizer,
    StatefulPhoneNumberRecognizer
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
        
        # Load deny_list, validation config, detection scores, and number_words from YAML
        # Single unified configuration for all recognizers
        yaml_config = self._load_deny_list_config(config_path)
        self.deny_list = yaml_config['deny_list']
        self.person_validation_config = yaml_config['validation']
        self.detection_scores = yaml_config['detection_scores']
        
        # deny_list serves dual purpose:
        # 1. Exact match: if detected text exactly matches a word in deny_list, skip it
        # 2. Conversational validation: use words to calculate ratio for PERSON entity validation
        self.conversational_words = self.deny_list  # Same list, dual purpose
        
        # Get context indicators from JSON config
        context_indicators = self.config.get('context_indicators', {})
        
        # Add shared configuration to context_indicators for recognizers
        context_indicators['conversational_words'] = list(self.conversational_words)
        context_indicators['detection_scores'] = self.detection_scores
        context_indicators['number_words'] = yaml_config.get('number_words', [])
        
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
            logging.info("Stateful EntityRecognizers registered (using context_tracker, context_indicators, and detection_scores from config)")
        except Exception as e:
            logging.warning("Could not register recognizer: %s", e)

    def _load_deny_list_config(self, config_path):
        """
        Load deny_list, validation config, detection scores, and number_words from YAML.
        
        Returns a dict with:
          - deny_list: Set of uppercase words for exact matching and validation
          - validation: Dict with person_entity validation settings
          - detection_scores: Dict with score thresholds for detection filtering
          - number_words: List of spoken number words (shared across recognizers)
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
                
                # Load detection score settings
                detection_scores = config.get('detection_scores', {})
                scores_config = {
                    'min_score_threshold': detection_scores.get('min_score_threshold', 0.7),
                    'recognizer_scores': detection_scores.get('recognizer_scores', {
                        'high_confidence': 0.95,
                        'very_high_confidence': 0.98,
                        'medium_high_confidence': 0.92,
                        'medium_confidence': 0.90,
                        'low_confidence': 0.80
                    })
                }
                
                # Load number words (shared across all recognizers)
                number_words = config.get('number_words', [])
                # Convert to uppercase for consistency
                number_words_list = [word.upper() for word in number_words]
                
                return {
                    'deny_list': deny_list_set,
                    'validation': person_validation,
                    'detection_scores': scores_config,
                    'number_words': number_words_list
                }
        except Exception as e:
            logging.warning(f"Could not load config from YAML: {e}")
            # Fallback defaults
            return {
                'deny_list': set(),
                'validation': {'enabled': True, 'max_conversational_ratio': 0.5},
                'detection_scores': {
                    'min_score_threshold': 0.7,
                    'recognizer_scores': {
                        'high_confidence': 0.95,
                        'very_high_confidence': 0.98,
                        'medium_high_confidence': 0.92,
                        'medium_confidence': 0.90,
                        'low_confidence': 0.80
                    }
                },
                'number_words': ['ZERO', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE',
                               'TEN', 'ELEVEN', 'TWELVE', 'THIRTEEN', 'FOURTEEN', 'FIFTEEN', 'SIXTEEN',
                               'SEVENTEEN', 'EIGHTEEN', 'NINETEEN', 'TWENTY', 'THIRTY', 'FORTY', 'FIFTY',
                               'SIXTY', 'SEVENTY', 'EIGHTY', 'NINETY', 'HUNDRED', 'OH', 'DOUBLE', 'TRIPLE']
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
                # Remove false positives using deny_list from YAML and intelligent validation
                filtered_results = []
                for r in analyzer_result:
                    matched_text = content[r.start:r.end].upper()
                    
                    # Debug: Log all detections before filtering
                    logging.debug(f"Detected {r.entity_type}: '{matched_text}' (score: {r.score:.2f})")
                    
                    # Skip if text is in deny_list (exact match or contains deny_list word)
                    # BUT: Don't apply deny_list filter to explicitly structured entities like PHONE_NUMBER
                    if r.entity_type not in ["PHONE_NUMBER", "EMAIL_ADDRESS", "CREDIT_CARD", "IBAN_CODE"]:
                        if matched_text in self.deny_list:
                            logging.debug(f"Filtered by deny_list (exact match): '{matched_text}'")
                            continue
                        
                        # Also skip if ANY word in matched_text is in deny_list
                        words_in_match = matched_text.split()
                        if any(word in self.deny_list for word in words_in_match):
                            logging.debug(f"Filtered by deny_list (word match): '{matched_text}'")
                            continue
                    
                    # Skip if score is too low (configurable threshold)
                    min_score = self.detection_scores.get('min_score_threshold', 0.7)
                    if r.score <= min_score:
                        continue
                    
                    # SMART FILTER: For PERSON entities, validate them when NOT expecting a name
                    # This catches false positives from default recognizers (SpacyRecognizer, etc.)
                    # If we ARE expecting a name, trust all recognizers (custom + default)
                    if r.entity_type == "PERSON" and not self.context_tracker.expecting_name:
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
    
    # Add dataflow service options if specified in config
    if 'dataflow_service_options' in config.get('dataflow', {}):
        for option in config['dataflow']['dataflow_service_options']:
            pipeline_args.append(f'--dataflow_service_options={option}')
    
    # Add worker service account if specified in config
    if 'worker_service_account' in config.get('project', {}):
        pipeline_args.append(f'--service_account_email={config["project"]["worker_service_account"]}')
        print(f"Using worker service account: {config['project']['worker_service_account']}")

    options = PipelineOptions(pipeline_args)

    print(f"Running STATEFUL ENTITY RECOGNIZER approach with config: {args.config_path}")
    # Set Dataflow job project
    if not options.get_all_options().get('runner') or options.get_all_options().get('runner') == 'DataflowRunner':
        options.view_as(StandardOptions).runner = 'DataflowRunner'
        google_cloud_options = options.view_as(GoogleCloudOptions)
        google_cloud_options.project = config['project']['dataflow_project_id']
        google_cloud_options.region = config['project']['region']
        google_cloud_options.staging_location = config['project']['staging_location']
        google_cloud_options.job_name = config['project']['job_name']
        
        # Set service account if provided in config
        if 'service_account' in config['project']:
            google_cloud_options.service_account_email = config['project']['service_account']
            print(f"Using service account: {config['project']['service_account']}")

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
