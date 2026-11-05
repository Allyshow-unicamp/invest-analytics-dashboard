"""Configuração idempotente de logs JSON para execução local ou hospedada."""

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Serializa eventos em uma linha para coleta e consulta automatizada."""

    def format(self, record: logging.LogRecord) -> str:
        """Converte nível, horário UTC, origem e mensagem em JSON."""
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """Instala um handler apenas uma vez, inclusive nos reruns do Streamlit."""
    root = logging.getLogger()
    if any(handler.name == "invest_analytics" for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.name = "invest_analytics"
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
