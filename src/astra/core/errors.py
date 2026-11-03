"""Исключения адаптера ядра. Все сообщения — на русском языке."""


class AstraError(Exception):
    """Базовая ошибка Astra."""


class InputError(AstraError, ValueError):
    """Некорректные исходные данные (обнаружено до вызова ядра)."""


class CoreError(AstraError, RuntimeError):
    """Ядро NASA CEA сообщило об ошибке, не связанной со сходимостью."""
