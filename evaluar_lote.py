import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from agent.pipeline import run_pipeline
from agent.schemas import ProcesadoItem, SalidaJSON


CARACAS = ZoneInfo("America/Caracas")
SUPPORTED_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".xlsx"}


def _git_value(*args: str, cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _proposal_files(input_dir: Path) -> list[Path]:
    proposals_dir = input_dir / "propuestas"
    if not proposals_dir.is_dir():
        return []
    return sorted(
        (path for path in proposals_dir.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_EXTS),
        key=lambda path: path.relative_to(proposals_dir).as_posix().casefold(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audita propuestas del lote de forma reproducible.")
    parser.add_argument("--input", required=True, help="Directorio del lote con proyecto.pdf y propuestas/.")
    parser.add_argument("--output", required=True, help="Ruta del archivo JSON de salida.")
    args = parser.parse_args()

    input_dir = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    if not input_dir.is_dir():
        parser.error(f"No existe el directorio de entrada: {input_dir}")

    repo_root = Path(__file__).resolve().parent
    started = datetime.now(CARACAS)
    files = _proposal_files(input_dir)
    audits, ranking = run_pipeline(str(input_dir))
    finished = datetime.now(CARACAS)
    proposal_root = input_dir / "propuestas"
    processed_at = {audit.propuesta.archivo: finished.isoformat(timespec="seconds") for audit in audits}
    processed = [
        ProcesadoItem(
            archivo=path.relative_to(proposal_root).as_posix(),
            hora=processed_at.get(
                path.relative_to(proposal_root).as_posix(),
                finished.isoformat(timespec="seconds"),
            ),
        )
        for path in files
    ]

    repository = os.environ.get("REPOSITORY_URL") or _git_value("remote", "get-url", "origin", cwd=repo_root)
    if not repository:
        repository = repo_root.name
    commit = _git_value("rev-parse", "HEAD", cwd=repo_root)
    output = SalidaJSON(
        repositorio=repository,
        commit=commit,
        inicio=started.isoformat(timespec="seconds"),
        fin=finished.isoformat(timespec="seconds"),
        procesados=processed,
        ranking=ranking,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    discarded = sum(audit.descartada for audit in audits)
    print(f"Lote procesado: {len(files)} archivo(s), {len(audits) - discarded} válido(s), {discarded} descartado(s).")
    print(f"Salida: {output_path}")
    if not commit:
        print("Aviso: no se pudo determinar el commit (el directorio no tiene HEAD Git).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
