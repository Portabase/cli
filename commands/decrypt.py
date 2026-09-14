from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from commands.base import Command
from core.crypto import (
    ENC_SUFFIX,
    DecryptionError,
    decrypt_enc_file,
    default_output_for,
    load_master_key,
)
from core.errors import ConfigError, ValidationError


def _looks_like_dir(path: Path) -> bool:
    if path.exists():
        return path.is_dir()
    return str(path).endswith(("/", "\\")) or path.suffix == ""


class DecryptCommand(Command):
    name = "decrypt"
    help = "Decrypt Portabase .enc backup files (single file or folder)."
    panel = "Configuration"
    no_args_is_help = True

    def run(
        self,
        input_path: Annotated[
            Path,
            typer.Argument(help="A .enc file, or a folder containing .enc files."),
        ],
        output_path: Annotated[
            Path | None,
            typer.Argument(
                help="Output file or folder (must match the input type). "
                "Defaults to the input directory."
            ),
        ] = None,
        key: Annotated[
            Path | None,
            typer.Option(
                "--key", "-k", help="Master key file. Defaults to ./master_key.bin"
            ),
        ] = None,
    ) -> None:
        input_path = input_path.resolve()
        if not input_path.exists():
            raise ConfigError(f"Input path not found: {input_path}")
        master_key = load_master_key(key.resolve() if key else None)
        if input_path.is_dir():
            self._folder(input_path, output_path, master_key)
        else:
            self._single(input_path, output_path, master_key)

    def _single(
        self, enc_path: Path, output_path: Path | None, master_key: bytes
    ) -> None:
        if enc_path.suffix != ENC_SUFFIX:
            self.ui.warning(
                f"{enc_path.name} does not end with {ENC_SUFFIX}; decrypting anyway."
            )
        if output_path is None:
            out = enc_path.parent / default_output_for(enc_path)
        elif _looks_like_dir(output_path):
            out = output_path.resolve() / default_output_for(enc_path)
        else:
            out = output_path.resolve()
        try:
            decrypt_enc_file(enc_path, out, master_key)
        except OSError as error:
            raise DecryptionError(
                f"I/O error on {enc_path.name}: {error}", cause=error
            ) from error
        self.ui.success(f"Decrypted {enc_path.name} → {out}")

    def _folder(
        self, in_dir: Path, output_path: Path | None, master_key: bytes
    ) -> None:
        enc_files = sorted(
            path
            for path in in_dir.iterdir()
            if path.is_file() and path.suffix == ENC_SUFFIX
        )
        if not enc_files:
            self.ui.warning(f"No {ENC_SUFFIX} files found in {in_dir}.")
            return
        if output_path is None:
            out_dir = in_dir
        elif _looks_like_dir(output_path):
            out_dir = output_path.resolve()
        else:
            raise ValidationError(
                "Input is a folder, so the output must be a folder too."
            )
        out_dir.mkdir(parents=True, exist_ok=True)

        failures: list[tuple[str, str]] = []
        with self.ui.status(f"Decrypting {len(enc_files)} file(s)..."):
            for enc_path in enc_files:
                out = out_dir / default_output_for(enc_path)
                try:
                    decrypt_enc_file(enc_path, out, master_key)
                except (DecryptionError, OSError) as error:
                    failures.append((enc_path.name, str(error)))
        succeeded = len(enc_files) - len(failures)
        self.ui.info(
            f"Done: {succeeded} succeeded, {len(failures)} failed "
            f"of {len(enc_files)} file(s)."
        )
        if failures:
            for name, reason in failures:
                self.ui.print(f"  [danger]•[/danger] {name}: {reason}")
            raise DecryptionError(f"{len(failures)} file(s) failed to decrypt.")
