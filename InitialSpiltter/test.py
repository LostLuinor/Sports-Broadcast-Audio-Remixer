import os
import sys
from pathlib import Path
from audio_separator.separator import Separator
from pydub import AudioSegment


SUPPORTED_FORMATS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}


def validate_input(input_path: str) -> Path:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")
    if path.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format '{path.suffix}'. Supported: {SUPPORTED_FORMATS}")
    return path


def identify_stems(output_files: list, output_dir: str) -> tuple[str, str]:
    """
    Auto-detect which output file is vocals (commentary) and which is crowd.
    audio-separator names files with '(Vocals)' and '(Instrumental)' suffixes.
    Falls back to index-based if naming is unexpected.
    """
    vocals_path, crowd_path = None, None

    for f in output_files:
        full = os.path.join(output_dir, f)
        lower = f.lower()
        if "vocal" in lower:
            vocals_path = full
        elif "instrumental" in lower or "no_vocal" in lower:
            crowd_path = full

    # Fallback to index order if naming didn't match
    if not vocals_path or not crowd_path:
        print("  [Warning] Could not auto-detect stems by name. Falling back to index order.")
        print(f"  Files found: {output_files}")
        crowd_path  = os.path.join(output_dir, output_files[0])
        vocals_path = os.path.join(output_dir, output_files[1])

    return vocals_path, crowd_path


def print_audio_info(label: str, segment: AudioSegment):
    duration = len(segment) / 1000
    print(f"  {label}: {duration:.1f}s | {segment.channels}ch | {segment.frame_rate}Hz")


def process_sports_audio(
    input_path: str,
    preference: str = "mute_commentary",
    crowd_boost_db: float = 10.0,
    commentary_reduce_db: float = 15.0,
    output_dir: str = "./output",
    model_name: str = "UVR-MDX-NET-Voc_FT",
):
    """
    Separate and remix sports broadcast audio.

    Args:
        input_path:           Path to input audio file.
        preference:           "mute_commentary" | "amplify_crowd" | "balanced"
        crowd_boost_db:       dB boost applied to crowd in 'amplify_crowd' mode.
        commentary_reduce_db: dB reduction on commentary in 'amplify_crowd' mode.
        output_dir:           Folder to store intermediate and final files.
        model_name:           audio-separator model to use.
    """

    # --- Validate ---
    input_file = validate_input(input_path)
    os.makedirs(output_dir, exist_ok=True)
    print(f"\n{'='*50}")
    print(f"  Input : {input_file.name}")
    print(f"  Mode  : {preference}")
    print(f"  Model : {model_name}")
    print(f"{'='*50}\n")

    # --- Step 1: Separate ---
    print("[1/3] Running source separation...")
    separator = Separator(
        output_dir=output_dir,
        output_format="WAV",
    )
    separator.load_model(model_filename=model_name)
    output_files = separator.separate(str(input_file))
    print(f"  Stems produced: {output_files}")

    # --- Step 2: Load stems ---
    print("\n[2/3] Loading stems...")
    commentary_path, crowd_path = identify_stems(output_files, output_dir)

    crowd       = AudioSegment.from_wav(crowd_path)
    commentary  = AudioSegment.from_wav(commentary_path)

    print_audio_info("Crowd stem      ", crowd)
    print_audio_info("Commentary stem ", commentary)

    # --- Step 3: Apply preference ---
    print(f"\n[3/3] Applying preference: '{preference}'...")

    if preference == "mute_commentary":
        final_output = crowd
        print("  → Commentators muted. Pure crowd audio.")

    elif preference == "amplify_crowd":
        boosted_crowd      = crowd + crowd_boost_db
        reduced_commentary = commentary - commentary_reduce_db
        final_output       = boosted_crowd.overlay(reduced_commentary)
        print(f"  → Crowd +{crowd_boost_db}dB | Commentary -{commentary_reduce_db}dB")

    elif preference == "balanced":
        # Slight crowd boost, keep commentary at normal
        final_output = (crowd + 5).overlay(commentary)
        print("  → Balanced mix: slight crowd boost, commentary unchanged.")

    else:
        raise ValueError(f"Unknown preference '{preference}'. Choose: mute_commentary | amplify_crowd | balanced")

    # --- Export ---
    result_name = f"sports_{preference}_{input_file.stem}.wav"
    final_output.export(result_name, format="wav")

    size_mb = os.path.getsize(result_name) / (1024 * 1024)
    print(f"\n✅ Done! Saved as '{result_name}' ({size_mb:.1f} MB)\n")
    return result_name


# ── CLI Usage ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sports Audio Commentary Separator")
    parser.add_argument("input",       help="Path to input audio file (mp3, wav, etc.)")
    parser.add_argument(
        "--mode", "-m",
        default="mute_commentary",
        choices=["mute_commentary", "amplify_crowd", "balanced"],
        help="How to remix the audio (default: mute_commentary)"
    )
    parser.add_argument("--crowd-boost",      type=float, default=10.0,  help="dB boost for crowd (amplify_crowd mode)")
    parser.add_argument("--commentary-reduce",type=float, default=15.0,  help="dB cut for commentary (amplify_crowd mode)")
    parser.add_argument("--output-dir",       default="./output",        help="Directory for intermediate files")

    args = parser.parse_args()

    try:
        result = process_sports_audio(
            input_path=args.input,
            preference=args.mode,
            crowd_boost_db=args.crowd_boost,
            commentary_reduce_db=args.commentary_reduce,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)