from src.db import _ConnectionWrapper


class _BaseConnection:
    def __init__(self):
        self.cursor_args = []

    def cursor(self, *args, **kwargs):
        self.cursor_args.append((args, kwargs))
        return object()


class _BeginConnection(_BaseConnection):
    def __init__(self):
        super().__init__()
        self.begin_called = False

    def begin(self):
        self.begin_called = True


class _NativeTransactionConnection(_BaseConnection):
    def __init__(self):
        super().__init__()
        self.calls = []

    def start_transaction(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def test_connection_wrapper_start_transaction_uses_begin_fallback():
    native = _BeginConnection()
    wrapper = _ConnectionWrapper(native)

    wrapper.start_transaction()

    assert native.begin_called is True


def test_connection_wrapper_start_transaction_uses_native_method_when_available():
    native = _NativeTransactionConnection()
    wrapper = _ConnectionWrapper(native)

    wrapper.start_transaction(consistent_snapshot=True)

    assert native.calls == [((), {"consistent_snapshot": True})]
