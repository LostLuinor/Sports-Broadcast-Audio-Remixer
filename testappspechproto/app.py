from __future__ import annotations

import glob
import subprocess
import shutil
import sys
import uuid
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
PROCESSED_DIR = BASE_DIR / "processed"
WORK_DIR = BASE_DIR / "work"
ALLOWED_EXTENSIONS = {"mp4", "mov", "mkv", "avi", "webm"}

for folder in (UPLOAD_DIR, PROCESSED_DIR, WORK_DIR):
    folder.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1GB


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def find_uploaded_video(video_id: str) -> Path | None:
    candidates = glob.glob(str(UPLOAD_DIR / f"{video_id}_*"))
    return Path(candidates[0]) if candidates else None


def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _safe_ratio(value: float, total: float) -> float:
    if total <= 1e-12:
        return 0.0
    return float(value / total)


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values)
    exps = np.exp(shifted)
    total = np.sum(exps)
    if total <= 1e-12:
        return np.ones_like(values) / float(values.size)
    return exps / total


def _component_model(features: np.ndarray) -> dict[str, int]:
    """A compact prototype model over spectral features for common sports-video audio types."""
    labels = ["commentary", "music", "stadium", "ambient_noise", "effects"]

    # Feature vector: [bass, mid, treble, flatness, zcr, transientness]
    prototypes = np.array(
        [
            [0.18, 0.62, 0.24, 0.18, 0.20, 0.15],
            [0.38, 0.30, 0.34, 0.30, 0.22, 0.28],
            [0.28, 0.36, 0.31, 0.42, 0.36, 0.46],
            [0.22, 0.24, 0.35, 0.72, 0.60, 0.24],
            [0.19, 0.28, 0.42, 0.36, 0.30, 0.68],
        ],
        dtype=np.float32,
    )

    # Similarity by negative squared distance, then softmax as probabilities.
    d2 = np.sum((prototypes - features[None, :]) ** 2, axis=1)
    logits = -6.5 * d2
    probs = _softmax(logits)
    percents = [int(round(float(p) * 100)) for p in probs]

    # Keep total at 100 after rounding drift.
    drift = 100 - sum(percents)
    if drift != 0:
        idx = int(np.argmax(probs))
        percents[idx] += drift

    return {label: max(0, pct) for label, pct in zip(labels, percents)}


def _clamp_percent(value: float) -> float:
    return float(max(0.0, min(100.0, value)))


def build_mix_recommendations(components: dict[str, int]) -> dict[str, object]:
    commentary = int(components.get("commentary", 0))
    stadium = int(components.get("stadium", 0))

    commentary_reduction = int(np.clip(round(commentary * 0.9), 0, 90))
    stadium_reduction = int(np.clip(round(60 - stadium * 0.5), 0, 60))

    return {
        "commentary_reduction": commentary_reduction,
        "stadium_reduction": stadium_reduction,
        "note": (
            "High commentary suggests reducing vocals. Strong stadium presence suggests keeping crowd volume up."
        ),
    }


def analyze_audio_types(video_path: Path) -> dict:
    """Analyze first 25s audio and infer component mix + stem slider guidance."""
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "22050",
        "-t",
        "25",
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-",
    ]
    proc = run_ffmpeg(cmd)
    if proc.returncode != 0:
        fallback_scores = {
            "commentary": 25,
            "music": 20,
            "stadium": 25,
            "ambient_noise": 20,
            "effects": 10,
        }
        return {
            "components": fallback_scores,
            "mix_recommendations": build_mix_recommendations(fallback_scores),
            "note": "Analysis failed; using safe defaults.",
        }

    samples = np.frombuffer(proc.stdout, dtype=np.float32)
    if samples.size < 4096:
        fallback_scores = {
            "commentary": 24,
            "music": 22,
            "stadium": 24,
            "ambient_noise": 20,
            "effects": 10,
        }
        return {
            "components": fallback_scores,
            "mix_recommendations": build_mix_recommendations(fallback_scores),
            "note": "Audio too short for deep analysis; using defaults.",
        }

    frame = 2048
    hop = 1024
    sr = 22050
    window = np.hanning(frame)
    frames = []

    for i in range(0, samples.size - frame, hop):
        chunk = samples[i : i + frame] * window
        spec = np.abs(np.fft.rfft(chunk))
        frames.append(spec**2)

    if not frames:
        fallback_scores = {
            "commentary": 24,
            "music": 22,
            "stadium": 24,
            "ambient_noise": 20,
            "effects": 10,
        }
        return {
            "components": fallback_scores,
            "mix_recommendations": build_mix_recommendations(fallback_scores),
            "note": "Could not compute spectral frames; using defaults.",
        }

    spectrum = np.mean(np.stack(frames, axis=0), axis=0)
    freqs = np.fft.rfftfreq(frame, d=1.0 / sr)

    def band_energy(low: float, high: float) -> float:
        mask = (freqs >= low) & (freqs < high)
        if not np.any(mask):
            return 0.0
        return float(np.sum(spectrum[mask]))

    total = float(np.sum(spectrum)) + 1e-12
    bass = _safe_ratio(band_energy(20, 250), total)
    treble = _safe_ratio(band_energy(4000, 12000), total)
    mid = _safe_ratio(band_energy(400, 2500), total)

    flatness = float(np.exp(np.mean(np.log(spectrum + 1e-12))) / (np.mean(spectrum) + 1e-12))
    zcr = float(np.mean(np.abs(np.diff(np.sign(samples))))) / 2.0

    energy_flux = np.mean(np.abs(np.diff(np.stack(frames, axis=0), axis=0)))
    transientness = float(np.clip(energy_flux / (np.mean(spectrum) + 1e-12), 0.0, 1.0))

    feature_vec = np.array(
        [
            float(np.clip(bass, 0.0, 1.0)),
            float(np.clip(mid, 0.0, 1.0)),
            float(np.clip(treble, 0.0, 1.0)),
            float(np.clip(flatness, 0.0, 1.0)),
            float(np.clip(zcr, 0.0, 1.0)),
            transientness,
        ],
        dtype=np.float32,
    )
    components = _component_model(feature_vec)

    return {
        "components": components,
        "mix_recommendations": build_mix_recommendations(components),
        "note": "Model inference complete. Components detected for stem-mix guidance.",
    }


def extract_audio(video_path: Path, work_dir: Path) -> tuple[Path | None, str | None]:
    audio_path = work_dir / "audio.wav"
    if audio_path.exists():
        return audio_path, None

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "2",
        "-ar",
        "44100",
        "-c:a",
        "pcm_s16le",
        str(audio_path),
    ]
    proc = run_ffmpeg(cmd)
    if proc.returncode != 0 or not audio_path.exists():
        details = proc.stderr.decode("utf-8", errors="ignore")[-1200:]
        return None, f"Audio extraction failed. {details}"

    return audio_path, None


def separate_stems(audio_path: Path, work_dir: Path) -> tuple[Path | None, Path | None, str | None]:
    demucs_root = work_dir / "demucs"
    stems_dir = demucs_root / "htdemucs" / audio_path.stem
    vocals_path = stems_dir / "vocals.wav"
    background_path = stems_dir / "no_vocals.wav"

    if vocals_path.exists() and background_path.exists():
        return vocals_path, background_path, None

    def run_demucs_with_python(python_cmd: str) -> subprocess.CompletedProcess[bytes]:
        cmd = [
            python_cmd,
            "-m",
            "demucs",
            "-n",
            "htdemucs",
            "--two-stems=vocals",
            "-o",
            str(demucs_root),
            str(audio_path),
        ]
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def run_demucs_cli(demucs_cmd: str) -> subprocess.CompletedProcess[bytes]:
        cmd = [
            demucs_cmd,
            "-n",
            "htdemucs",
            "--two-stems=vocals",
            "-o",
            str(demucs_root),
            str(audio_path),
        ]
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    demucs_root.mkdir(parents=True, exist_ok=True)

    try:
        proc = run_demucs_with_python(sys.executable)
    except FileNotFoundError:
        return (
            None,
            None,
            "Python executable not found for Demucs run. Ensure your virtual environment is active.",
        )

    stderr_text = proc.stderr.decode("utf-8", errors="ignore")

    if proc.returncode != 0 and "No module named" in stderr_text and "demucs" in stderr_text:
        if sys.platform == "win32":
            venv_python = BASE_DIR / ".venv" / "Scripts" / "python.exe"
        else:
            venv_python = BASE_DIR / ".venv" / "bin" / "python"

        if venv_python.exists() and str(venv_python) != sys.executable:
            proc = run_demucs_with_python(str(venv_python))
            stderr_text = proc.stderr.decode("utf-8", errors="ignore")

        if proc.returncode != 0 and ("No module named" in stderr_text and "demucs" in stderr_text):
            demucs_bin = shutil.which("demucs")
            if demucs_bin:
                proc = run_demucs_cli(demucs_bin)
                stderr_text = proc.stderr.decode("utf-8", errors="ignore")

    if proc.returncode != 0:
        details = stderr_text[-1200:]
        return (
            None,
            None,
            "Demucs failed. "
            f"Python used: {sys.executable}. "
            f"Details: {details}",
        )

    if not vocals_path.exists() or not background_path.exists():
        return None, None, "Demucs ran but did not output the expected stems."

    return vocals_path, background_path, None


def mix_stems(
    vocals_path: Path,
    background_path: Path,
    vocals_gain: float,
    background_gain: float,
    output_path: Path,
) -> tuple[bool, str | None]:
    filter_complex = (
        f"[0:a]volume={vocals_gain:.3f}[v];"
        f"[1:a]volume={background_gain:.3f}[b];"
        "[v][b]amix=inputs=2:dropout_transition=2,alimiter=limit=0.98"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(vocals_path),
        "-i",
        str(background_path),
        "-filter_complex",
        filter_complex,
        "-ac",
        "2",
        "-ar",
        "44100",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    proc = run_ffmpeg(cmd)
    if proc.returncode != 0 or not output_path.exists():
        details = proc.stderr.decode("utf-8", errors="ignore")[-1200:]
        return False, f"Stem mix failed. {details}"

    return True, None


def attach_audio_to_video(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
) -> tuple[bool, str | None]:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output_path),
    ]
    proc = run_ffmpeg(cmd)
    if proc.returncode != 0:
        details = proc.stderr.decode("utf-8", errors="ignore")[-1200:]
        return False, f"Video mux failed. {details}"

    return True, None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_video():
    if "video" not in request.files:
        return jsonify({"error": "No file provided."}), 400

    file = request.files["video"]
    if not file or file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type."}), 400

    video_id = uuid.uuid4().hex[:12]
    safe_name = secure_filename(file.filename)
    save_path = UPLOAD_DIR / f"{video_id}_{safe_name}"
    file.save(save_path)

    analysis = analyze_audio_types(save_path)

    return jsonify(
        {
            "video_id": video_id,
            "video_url": f"/media/uploads/{save_path.name}",
            "analysis": analysis,
            "filename": safe_name,
        }
    )


@app.route("/process", methods=["POST"])
def process_video():
    payload = request.get_json(silent=True) or {}
    video_id = payload.get("video_id")
    reductions = payload.get("reductions") or {}

    if not video_id:
        return jsonify({"error": "video_id is required."}), 400

    input_path = find_uploaded_video(video_id)
    if input_path is None or not input_path.exists():
        return jsonify({"error": "Video not found. Upload again."}), 404

    output_name = f"{video_id}_mixed.mp4"
    output_path = PROCESSED_DIR / output_name

    work_dir = WORK_DIR / video_id
    work_dir.mkdir(parents=True, exist_ok=True)

    audio_path, error = extract_audio(input_path, work_dir)
    if error:
        return jsonify({"error": error}), 500

    vocals_path, background_path, error = separate_stems(audio_path, work_dir)
    if error:
        return jsonify({"error": error}), 500

    commentary_reduction = _clamp_percent(float(reductions.get("commentary", 0)))
    stadium_reduction = _clamp_percent(float(reductions.get("stadium", 0)))
    vocals_gain = 1.0 - commentary_reduction / 100.0
    background_gain = 1.0 - stadium_reduction / 100.0

    mixed_audio_path = work_dir / "mixed.wav"
    ok, error = mix_stems(
        vocals_path,
        background_path,
        vocals_gain,
        background_gain,
        mixed_audio_path,
    )
    if not ok:
        return jsonify({"error": error}), 500

    ok, error = attach_audio_to_video(input_path, mixed_audio_path, output_path)
    if not ok:
        return jsonify({"error": error}), 500

    return jsonify({"output_url": f"/media/processed/{output_name}"})


@app.route("/media/uploads/<path:filename>")
def media_uploads(filename: str):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/media/processed/<path:filename>")
def media_processed(filename: str):
    return send_from_directory(PROCESSED_DIR, filename)


if __name__ == "__main__":
    app.run(debug=True)
