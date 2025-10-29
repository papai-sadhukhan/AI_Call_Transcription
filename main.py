import logging
logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)
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
from text2digits import text2digits

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
        from presidio_analyzer import PatternRecognizer, Pattern
        # Add custom address recognizer
        # More generic UK address pattern: number, street, optional region/postcode
        
        address_pattern = Pattern(
            "address_pattern",
            r"\b(?:flat\s*(?:number|no)?\s*\d{1,5}|\d{1,5})\s+(?:[A-Za-z0-9]+\s+)?(?:street|road|lane|avenue|drive|close|way|place|square|court|crescent|terrace|boulevard|highway|hill|gardens|walk|view|grove|park)(?:\s+(?:[A-Z]{1,2}\s*\d{1,2}\s*[A-Z]{1,2}))?\b",
            0.8,
        )

        class SpokenAddressRecognizer(PatternRecognizer):
            def __init__(self):
                super().__init__(
                    supported_entity="ADDRESS",
                    supported_language="en",
                    name="SpokenAddressRecognizer",
                    patterns=[address_pattern],
                )
        
        
        verification_code_pattern = Pattern(
            name="verification_code_pattern",
            regex=r"\b(?:verification\s*code\s*(is|:)?\s*)?\d{4,6}\b",
            score=0.85
        )

        class VerificationCodeRecognizer(PatternRecognizer):
            def __init__(self):
                super().__init__(
                    supported_entity="VERIFICATION_CODE",
                    supported_language="en",
                    name="VerificationCodeRecognizer",
                    patterns=[verification_code_pattern]
                )
        
        bank_digits_pattern = Pattern(
            name="bank_last_digits_pattern",
            regex=r"\b(?:last\s*(two|2)\s*digits\s*(of\s*(your)?\s*(bank\s*account)?)?\s*)?\d{2}\b",
            score=0.85
        )

        class BankLastDigitsRecognizer(PatternRecognizer):
            def __init__(self):
                super().__init__(
                    supported_entity="BANK_ACCOUNT_LAST_DIGITS",
                    supported_language="en",
                    name="BankLastDigitsRecognizer",
                    patterns=[bank_digits_pattern]
                )


        # Build operators from config
        for entity_type, replacement in self.config.get('pii_entities', {}).items():
            # OperatorConfig(operation_name, params)
            self.operators[entity_type] = OperatorConfig("replace", {
                "new_value": replacement
            })
        
        # Use config file from parent directory for the NLP engine provider if present
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "redactConfig.yaml")
        provider = NlpEngineProvider(conf_file=config_path)

        # Create analyzer and anonymizer
        self.analyzer = AnalyzerEngine(nlp_engine=provider.create_engine())
        self.anonymizer = AnonymizerEngine()

        # Register the custom address recognizer on the analyzer registry
        try:
            self.analyzer.registry.add_recognizer(SpokenAddressRecognizer())
            self.analyzer.registry.add_recognizer(VerificationCodeRecognizer())
            self.analyzer.registry.add_recognizer(BankLastDigitsRecognizer())
        except Exception as e:
                logging.warning("Could not register custom recognizer: %s", e)

    def spoken_to_numeric(self, text: str) -> str:
        """
        Convert spoken cardinal numbers to digits, but avoid converting ordinal words
        and spoken numbers when used with units like 'pounds', 'minutes', etc.
        Also merge single-letter sequences like 'C F' -> 'CF'.
        """
        from text2digits import text2digits
        import re

        # List of ordinal words to exclude from conversion
        ordinals = [
            "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
            "eighth", "ninth", "tenth", "eleventh", "twelfth", "thirteenth",
            "fourteenth", "fifteenth", "sixteenth", "seventeenth", "eighteenth",
            "nineteenth", "twentieth"
        ]

        # List of units where spoken numbers should be preserved
        preserve_units = ["pounds", "minutes", "days", "hours", "weeks", "months"]

        # Mask ordinal words
        for word in ordinals:
            pattern = rf"\b{word}\b"
            token = f"__{word.upper()}__"
            text = re.sub(pattern, token, text, flags=re.IGNORECASE)

        # Mask spoken numbers followed by units
        for unit in preserve_units:
            pattern = rf"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\s+{unit}\b"
            text = re.sub(
                pattern,
                lambda m: f"__{m.group(0).upper().replace(' ', '_')}__",
                text,
                flags=re.IGNORECASE
            )

        # Convert remaining spoken numbers
        t2d = text2digits.Text2Digits()
        converted = t2d.convert(text)

        # Restore masked ordinal words
        for word in ordinals:
            token = f"__{word.upper()}__"
            converted = re.sub(token, word, converted, flags=re.IGNORECASE)

        # Restore masked unit phrases
        for unit in preserve_units:
            for num in [
                "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
                "eighteen", "nineteen", "twenty"
            ]:
                phrase = f"{num} {unit}"
                token = f"__{phrase.upper().replace(' ', '_')}__"
                converted = re.sub(token, phrase, converted, flags=re.IGNORECASE)

        # Merge groups of spaced single letters (like "W A" -> "WA")
        converted = re.sub(r'\b(?:[A-Z]\s+){1,}[A-Z]\b', lambda m: m.group(0).replace(" ", ""), converted)

        return converted

    def process(self, element):
        """Process each conversation turn directly for PII redaction"""
        # element expected to be a dict with "conversation_transcript": [...]
        conversation = element.get("conversation_transcript", [])
        redacted_conversation = []
        for turn in conversation:
            if isinstance(turn, dict) and 'content' in turn:
                content = turn.get('content', '')
                role = turn.get('role', '')
                # Convert spelled numbers and merge spelled letters
                converted_content = self.spoken_to_numeric(content)
                # Analyze and redact PII in this turn's content
                analyzer_result = self.analyzer.analyze(text=converted_content, language="en")
                # Filter entities by score > 0.7
                filtered_results = [r for r in analyzer_result if r.score > 0.7]
                # Collect debug info for matched entities
                debug_info = []
                for result in filtered_results:
                    matched_text = converted_content[result.start:result.end]
                    debug_info.append(f"Matched entity: {result.entity_type}, text: {matched_text}, score: {result.score}")

                anonymizer_result = self.anonymizer.anonymize(
                    text=converted_content,
                    analyzer_results=filtered_results,
                    operators=self.operators,
                )
                # Create redacted turn with debug field
                redacted_turn = {
                    'role': role,
                    'content': anonymizer_result.text,
                    'debug': debug_info
                }
                redacted_conversation.append(redacted_turn)
            else:
                # Preserve non-dict elements as-is
                redacted_conversation.append(turn)

        # Update the element with redacted conversation
        element["conversation_transcript"] = redacted_conversation
        # Also create a flattened redacted transcript for compatibility
        element["redacted_transcript"] = deconstruct_transcript(redacted_conversation)
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
        google_cloud_options.temp_location = config['project']['temp_location']
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
        dataset_ref.datasetId = config['dataset']['temp']
        input_query = f"""
        SELECT {', '.join(select_fields)}
        FROM {input_table}
        WHERE {condition}
        LIMIT {config['processing']['limit']}
        """
        print("Input Query for BigQuery:")
        print(input_query)

        def process_row(row):
            transcript_col = config['tables']['source']['columns']['conversation_transcript_json']
            conversation_json = row[transcript_col]
            if isinstance(conversation_json, str):
                conversation_transcript = json.loads(conversation_json)
            else:
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
            output_row['load_datetime'] = datetime.datetime.now().isoformat()
            # Aggregate debug info from all turns
            debug_rows = []
            for turn in row.get("conversation_transcript", []):
                if isinstance(turn, dict) and "debug" in turn:
                    debug_rows.extend(turn["debug"])
            output_row['debug'] = "; ".join(debug_rows)
            #print("Test Output Row:", output_row)
            return output_row

        bigquery_data = p | "Read from BigQuery Table" >> beam.io.ReadFromBigQuery(
            query=input_query,
            method="DIRECT_READ",
            use_standard_sql=True,
            temp_dataset=dataset_ref,
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

        result | "Write to BigQuery" >> beam.io.WriteToBigQuery(
            output_table,
            schema=config['tables']['target']['schema'],
            write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
            create_disposition=beam.io.BigQueryDisposition.CREATE_IF_NEEDED,
            method=config['dataflow'].get('write_method', None),
            batch_size=config['processing'].get('batch_size', None),
        )

if __name__ == "__main__":
    run()
