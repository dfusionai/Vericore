from dataclasses import asdict, dataclass
from datetime import time
from enum import Enum
import json
import logging

class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class LoggerType(Enum):
    Validator = "VALIDATOR"
    Miner = "MINER"

@dataclass
class LogEntry():
    timestamp: float
    logger: str
    level: str
    message: str
    module: str
    filename: str
    lineno: int
    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "logger": self.logger,
            "level": self.level,
            "message": self.message,
            "module": self.module,
            "filename": self.filename,
            "lineno": self.lineno
        }

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = LogEntry(
            timestamp = record.created,
            logger = record.name,
            level = record.levelname,
            message = record.getMessage(),
            module = record.module,
            filename = record.filename,
            lineno = record.lineno
        )
        return json.dumps(log_entry.to_dict())  # Convert to JSON string
