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
        address_pattern = Pattern(
            "address_pattern",
            r"\b\d{1,5}\s+([A-Za-z]+\s){1,4}(road|street|avenue|drive|lane|rd|st|ave|blvd)\b.*",
            0.6,
        )
        class SpokenAddressRecognizer(PatternRecognizer):
            def __init__(self):
                super().__init__(
                    supported_entity="ADDRESS",
                    supported_language="en",
                    name="SpokenAddressRecognizer",
                    patterns=[address_pattern],
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

        # Create custom account number recognizer for spoken/written numbers
        account_number_recognizer = PatternRecognizer(
            supported_entity="ACCOUNT_NUMBER",
            supported_language="en",
            patterns=[
                # Pattern for spoken digits like "ONE ZERO ZERO SIX NINE THREE SIX"
                Pattern(
                    name="spoken_account_number",
                    regex=r"\b(?:ZERO|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE)(?:\s+(?:ZERO|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE)){3,}\b",
                    score=0.7
                ),
                # Pattern for numeric account numbers like "1006936"
                Pattern(
                    name="numeric_account_number",
                    regex=r"\b\d{4,12}\b",
                    score=0.5
                )
            ],
            context=["ACCOUNT", "CUSTOMER", "NUMBER", "ID", "REFERENCE"]
        )

        # Create analyzer and anonymizer
        # Create a registry that only loads English recognizers
        self.analyzer = AnalyzerEngine(nlp_engine=provider.create_engine())
        self.anonymizer = AnonymizerEngine()

        # Register the custom recognizers on the analyzer registry
        try:
            self.analyzer.registry.add_recognizer(account_number_recognizer)
            self.analyzer.registry.add_recognizer(SpokenAddressRecognizer())
        except Exception:
            try:
                self.analyzer._registry.add_recognizer(account_number_recognizer)
                self.analyzer._registry.add_recognizer(SpokenAddressRecognizer())
            except Exception as e:
                logging.warning("Could not register custom recognizer: %s", e)

    def spoken_to_numeric(self, text: str) -> str:
        """
        Convert spoken numbers (e.g., 'FIFTY TWO') to numeric digits ('50 2' simplified),
        and also merge single-letter sequences like 'C F' -> 'CF'.
        This is a heuristic approach — adapt to your needs.
        """
        import re

        number_words = {
            'ZERO': '0', 'ONE': '1', 'TWO': '2', 'THREE': '3', 'FOUR': '4', 'FIVE': '5',
            'SIX': '6', 'SEVEN': '7', 'EIGHT': '8', 'NINE': '9', 'TEN': '10',
            'ELEVEN': '11', 'TWELVE': '12', 'THIRTEEN': '13', 'FOURTEEN': '14', 'FIFTEEN': '15',
            'SIXTEEN': '16', 'SEVENTEEN': '17', 'EIGHTEEN': '18', 'NINETEEN': '19', 'TWENTY': '20',
            'THIRTY': '30', 'FORTY': '40', 'FIFTY': '50', 'SIXTY': '60', 'SEVENTY': '70',
            'EIGHTY': '80', 'NINETY': '90', 'HUNDRED': '100', 'THOUSAND': '1000'
        }

        # Convert to upper for matching but keep original letter-case variants handled by returning lower at the end
        original_text = text
        text_up = text.upper()

        # Replace sequences of spelled numbers with joined digits/values
        # This approach: for contiguous number words, replace with the concatenated numeric tokens separated by space
        def replace_spoken(match):
            words = match.group(0).split()
            digits = []
            for word in words:
                if word in number_words:
                    digits.append(number_words[word])
                else:
                    digits.append(word)
            return " ".join(digits)

        num_pattern = re.compile(
            r'\b(?:ZERO|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|TWENTY|THIRTY|FORTY|FIFTY|SIXTY|SEVENTY|EIGHTY|NINETY|HUNDRED|THOUSAND)(?:\s+(?:ZERO|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|TWENTY|THIRTY|FORTY|FIFTY|SIXTY|SEVENTY|EIGHTY|NINETY|HUNDRED|THOUSAND))*\b',
            re.IGNORECASE
        )

        converted = num_pattern.sub(lambda m: replace_spoken(m), text_up)

        # Merge groups of spaced single letters (like "H A W" -> "HAW")
        # We only merge groups of 2+ letters to avoid merging single isolated letters
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
                anonymizer_result = self.anonymizer.anonymize(
                    text=converted_content,
                    analyzer_results=analyzer_result,
                    operators=self.operators,
                )
                # Create redacted turn
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
        yield element


def run(argv=None):

    # Argument parsing for input source
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', choices=['Bigquery', 'Local'], default='Bigquery', help='Input source: Bigquery or Local')
    parser.add_argument('--local_file', default='local_test/sample_transcript_data.xlsx', help='Local Excel file path')
    parser.add_argument('--output_file', default='local_test/output_redacted_data.xlsx', help='Output Excel file path for local mode')
    known_args, pipeline_args = parser.parse_known_args(argv)

    config = load_config()
    options = PipelineOptions(pipeline_args)

    if known_args.input == 'Local':
        # Local file mode
        print(f"🔄 Running in LOCAL FILE mode")
        print(f"📥 Input: {known_args.local_file}")
        print(f"📤 Output: {known_args.output_file}")
        df = pd.read_excel(known_args.local_file)
        results = []
        pii_transform = DirectPIITransform(config)
        pii_transform.setup()
        for idx, row in df.iterrows():
            conversation_json = json.loads(row['transcript'])
            element = {
                'transaction_id': row['transaction_id'],
                'transcript': row['transcript'],
                'conversation_transcript': conversation_json.get('turns', [])
            }
            redacted_elements = list(pii_transform.process(element))
            redacted_element = redacted_elements[0] if redacted_elements else element
            # Prepare output
            redacted_conversation = {'turns': redacted_element['conversation_transcript']}
            results.append({
                'transaction_id': redacted_element['transaction_id'],
                'transcription_file_dt': row.get('file_date'),
                'original_transcript': row['transcript'],
                'redacted_transcript': json.dumps(redacted_conversation)
            })
        output_df = pd.DataFrame(results)
        output_df.to_excel(known_args.output_file, index=False)
        print(f"✅ Local file processing complete! Output saved to {known_args.output_file}")
        return

    # BigQuery mode (default)
    print(f"🔄 Running in BIGQUERY mode")
    # Set default values for cloud execution if not running locally
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
        current_timestamp = datetime.datetime.now().isoformat()
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
            row[config['tables']['target']['columns']['conversation_transcript_json']] = json.dumps(row["conversation_transcript"])
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
            # Add load_datetime with current datetime
            output_row['load_datetime'] = datetime.datetime.now().isoformat()
            return output_row

        bigquery_data = p | "Read from BigQuery Table" >> beam.io.ReadFromBigQuery(
            query=input_query,
            method="DIRECT_READ",
            use_standard_sql=True,
            temp_dataset=dataset_ref,
        )

        (
            bigquery_data
            | "Parse Conversation" >> beam.Map(process_row)
            | "Direct PII Redaction" >> beam.ParDo(DirectPIITransform(config))
            | "Prepare Output" >> beam.Map(prepare_output_row)
            | "Write to BigQuery"
            >> beam.io.WriteToBigQuery(
                output_table,
                schema=config['tables']['target']['schema'],
                write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
                create_disposition=beam.io.BigQueryDisposition.CREATE_IF_NEEDED,
                method=config['dataflow'].get('write_method', None),
                batch_size=config['processing'].get('batch_size', None),
            )
        )

if __name__ == "__main__":
    run()
