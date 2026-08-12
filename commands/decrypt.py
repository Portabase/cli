from pathlib import Path
from typing import Optional

import typer

from core.crypto import (
    ENC_SUFFIX,
    DecryptionError,
    decrypt_enc_file,
    default_output_for,
    load_master_key,
)
from core.utils import console


def _looks_like_dir(path: Path) -> bool:
    """True when ``path`` is an existing directory or clearly names one."""
    if path.exists():
        return path.is_dir()
    # A trailing separator or no suffix is treated as a directory hint.
    return str(path).endswith(("/", "\\")) or path.suffix == ""


def decrypt(
    input_path: Path = typer.Argument(
        ...,
        help="A .enc file, or a folder containing .enc files.",
    ),
    output_path: Optional[Path] = typer.Argument(
        None,
        help="Output file or folder (must match the input type). "
        "Defaults to the same directory as the input.",
    ),
    key: Optional[Path] = typer.Option(
        None,
        "--key",
        "-k",
        help="Path to the master key file. Defaults to 'master_key.bin' in the "
        "current directory.",
    ),
):
    """Decrypt Portabase AES-256-GCM ``.enc`` backup files."""
    input_path = input_path.resolve()

    if not input_path.exists():
        console.print(f"[danger]✖ Input path not found: {input_path}[/danger]")
        raise typer.Exit(1)

    try:
        master_key = load_master_key(key.resolve() if key else None)
    except DecryptionError as exc:
        console.print(f"[danger]✖ {exc}[/danger]")
        raise typer.Exit(1)

    if input_path.is_dir():
        _decrypt_folder(input_path, output_path, master_key)
    else:
        _decrypt_single(input_path, output_path, master_key)


def _decrypt_single(
    enc_path: Path, output_path: Optional[Path], master_key: bytes
) -> None:
    if enc_path.suffix != ENC_SUFFIX:
        console.print(
            f"[warning]⚠ {enc_path.name} does not end with {ENC_SUFFIX}; "
            "decrypting anyway.[/warning]"
        )

    if output_path is None:
        out_path = enc_path.parent / default_output_for(enc_path)
    elif _looks_like_dir(output_path):
        out_path = output_path.resolve() / default_output_for(enc_path)
    else:
        out_path = output_path.resolve()

    try:
        decrypt_enc_file(enc_path, out_path, master_key)
    except DecryptionError as exc:
        console.print(f"[danger]✖ Failed to decrypt {enc_path.name}: {exc}[/danger]")
        raise typer.Exit(1)
    except OSError as exc:
        console.print(f"[danger]✖ I/O error on {enc_path.name}: {exc}[/danger]")
        raise typer.Exit(1)

    console.print(f"[success]✔ Decrypted[/success] {enc_path.name} → {out_path}")


def _decrypt_folder(
    in_dir: Path, output_path: Optional[Path], master_key: bytes
) -> None:
    enc_files = sorted(p for p in in_dir.iterdir() if p.is_file() and p.suffix == ENC_SUFFIX)

    if not enc_files:
        console.print(f"[warning]No {ENC_SUFFIX} files found in {in_dir}.[/warning]")
        raise typer.Exit()

    if output_path is None:
        out_dir = in_dir
    elif _looks_like_dir(output_path):
        out_dir = output_path.resolve()
    else:
        console.print(
            "[danger]✖ Input is a folder, so the output must be a folder too.[/danger]"
        )
        raise typer.Exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    succeeded = 0
    failures: list[tuple[str, str]] = []

    with console.status(f"[bold magenta]Decrypting {len(enc_files)} file(s)...[/bold magenta]"):
        for enc_path in enc_files:
            out_path = out_dir / default_output_for(enc_path)
            try:
                decrypt_enc_file(enc_path, out_path, master_key)
            except (DecryptionError, OSError) as exc:
                failures.append((enc_path.name, str(exc)))
                console.print(f"[danger]✖ {enc_path.name}: {exc}[/danger]")
                continue
            succeeded += 1
            console.print(f"[success]✔[/success] {enc_path.name} → {out_path.name}")

    console.print(
        f"\n[info]Done: {succeeded} succeeded, {len(failures)} failed "
        f"of {len(enc_files)} file(s).[/info]"
    )
    if failures:
        console.print("[warning]Failed files:[/warning]")
        for name, reason in failures:
            console.print(f"  [danger]•[/danger] {name}: {reason}")
        raise typer.Exit(1)
