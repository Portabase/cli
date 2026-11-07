import pytest

import main

CASES = [
    ([], 0),
    (["--version"], 0),
    (["no-such-command"], 2),
    (["db"], 2),
    (["agent", "--bogus"], 2),
]


@pytest.mark.parametrize(
    ("argv", "exit_code"), CASES, ids=[" ".join(argv) or "no-args" for argv, _ in CASES]
)
def cli_errors_map_to_exit_codes(monkeypatch, tmp_path, argv, exit_code):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["portabase", *argv])
    with pytest.raises(SystemExit) as raised:
        main.main()
    assert raised.value.code == exit_code
