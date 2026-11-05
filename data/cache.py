"""Cache TTL limitado em memória, sem executar arquivos pickle do legado."""

import copy
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Copia resultados para isolar mutações; exceções nunca são armazenadas."""

    def __init__(self, ttl: float = 3600, max_entries: int = 16) -> None:
        if ttl <= 0 or max_entries < 1:
            raise ValueError("TTL e limite devem ser positivos.")
        self.ttl = ttl
        self.max_entries = max_entries
        self._values: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self._lock = threading.RLock()

    def get_or_load(self, key: str, loader: Callable[[], T]) -> T:
        """Reutiliza resultados frescos e substitui a entrada menos recente."""
        with self._lock:
            item = self._values.get(key)
            if item is not None and time.monotonic() - item[0] < self.ttl:
                self._values.move_to_end(key)
                return copy.deepcopy(item[1])
            self._values.pop(key, None)
            value = loader()
            self._values[key] = (time.monotonic(), copy.deepcopy(value))
            while len(self._values) > self.max_entries:
                self._values.popitem(last=False)
            return copy.deepcopy(value)

    def clear(self) -> None:
        """Invalida o cache para atualização explícita do usuário."""
        with self._lock:
            self._values.clear()
