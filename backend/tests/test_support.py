import pathlib
import sys
import types


SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


if "boto3" not in sys.modules:
    boto3 = types.ModuleType("boto3")

    class _DummyTable:
        def get_item(self, *args, **kwargs):
            return {}

        def put_item(self, *args, **kwargs):
            return {}

        def update_item(self, *args, **kwargs):
            return {}

        def query(self, *args, **kwargs):
            return {}

    class _DummyResource:
        def Table(self, name):
            return _DummyTable()

    class _DummyClient:
        def __getattr__(self, name):
            def _fn(*args, **kwargs):
                return {}
            return _fn

    def _resource(name):
        return _DummyResource()

    def _client(name, region_name=None):
        return _DummyClient()

    boto3.resource = _resource
    boto3.client = _client

    conditions = types.ModuleType("boto3.dynamodb.conditions")

    class _DummyKey:
        def __init__(self, name):
            self.name = name

        def eq(self, value):
            return (self.name, value)

    conditions.Key = _DummyKey

    dynamodb = types.ModuleType("boto3.dynamodb")
    dynamodb.conditions = conditions
    boto3.dynamodb = dynamodb

    sys.modules["boto3"] = boto3
    sys.modules["boto3.dynamodb"] = dynamodb
    sys.modules["boto3.dynamodb.conditions"] = conditions


if "postal.parser" not in sys.modules:
    postal = types.ModuleType("postal")
    parser = types.ModuleType("postal.parser")

    def _parse_address(raw_address):
        return []

    parser.parse_address = _parse_address
    postal.parser = parser
    sys.modules["postal"] = postal
    sys.modules["postal.parser"] = parser
