from singular.azazel import AzazelParseError, AzazelRuntime
from singular.azazel.cli import _parser
from singular.jarvis.runtime import JarvisParseError, JarvisRuntime


def test_azazel_is_the_canonical_runtime_identity() -> None:
    assert AzazelRuntime.__name__ == "AzazelRuntime"
    assert JarvisRuntime is AzazelRuntime
    assert JarvisParseError is AzazelParseError


def test_azazel_cli_is_the_public_front_door() -> None:
    parser = _parser()
    assert parser.prog == "azazel"


def test_legacy_module_remains_only_as_import_compatibility() -> None:
    assert JarvisRuntime.__module__ == "singular.jarvis.runtime"
    assert AzazelRuntime.__module__ == "singular.jarvis.runtime"
