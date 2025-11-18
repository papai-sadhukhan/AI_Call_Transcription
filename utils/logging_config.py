"""
Logging configuration for the entity redaction pipeline.
Supports both local file logging (DirectRunner) and GCP Cloud Logging (DataflowRunner).
"""
import logging
import os
import sys
from pathlib import Path


def setup_logging(runner: str = "DirectRunner", log_level: str = "INFO"):
    """
    Configure logging based on the runner type.
    
    Args:
        runner: Pipeline runner type - "DirectRunner" for local or "DataflowRunner" for GCP
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger("entity_redaction")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    if runner == "DirectRunner":
        # Local file logging
        setup_file_logging(logger, formatter)
    else:
        # GCP Cloud Logging for DataflowRunner
        setup_gcp_logging(logger, formatter)
    
    # Suppress verbose third-party loggers
    logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)
    logging.getLogger("apache_beam.io.gcp.bigquery").setLevel(logging.ERROR)
    logging.getLogger("google.auth").setLevel(logging.WARNING)
    logging.getLogger("google.cloud").setLevel(logging.WARNING)
    
    return logger


def setup_file_logging(logger, formatter):
    """
    Setup local file logging with rotation.
    Creates log directory if it doesn't exist.
    """
    # Create log directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / "app.log"
    
    # File handler with rotation
    try:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
    except Exception:
        # Fallback to basic file handler if rotation not available
        file_handler = logging.FileHandler(log_file)
    
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler for local development
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    logger.info(f"Local file logging initialized: {log_file.absolute()}")


def setup_gcp_logging(logger, formatter):
    """
    Setup GCP Cloud Logging for Dataflow.
    Uses google-cloud-logging with resource labels for easy filtering.
    """
    try:
        from google.cloud import logging as cloud_logging
        
        # Initialize GCP logging client
        logging_client = cloud_logging.Client()
        
        # Create a Cloud Logging handler with structured logging
        # Using log name for easy filtering in GCP Console
        cloud_handler = logging_client.get_default_handler(
            labels={
                "application": "entity-redaction-pipeline",
                "component": "pii-anonymization",
                "environment": "production"
            }
        )
        
        # Set formatter for cloud handler
        cloud_handler.setFormatter(formatter)
        logger.addHandler(cloud_handler)
        
        # Also add console handler for Dataflow worker logs
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        logger.info("GCP Cloud Logging initialized for Dataflow with label: application=entity-redaction-pipeline")
        
    except ImportError:
        # Fallback to console logging if google-cloud-logging not available
        logger.warning("google-cloud-logging not available, falling back to console logging")
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    except Exception as e:
        # Fallback to console logging on any error
        logger.warning(f"Failed to setup GCP logging: {e}, falling back to console logging")
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)


def get_logger(name: str = "entity_redaction"):
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (default: entity_redaction)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)
