# Sports Broadcast Audio Remixer

## Project Overview

Sports Broadcast Audio Remixer is a speech processing system that separates commentator voices from crowd noise in sports broadcast audio using deep learning-based source separation.

The goal is to let users remix sports audio based on their preference:

- Mute commentary for a stadium-only experience
- Amplify crowd atmosphere while keeping light commentary
- Keep a balanced mix between crowd and commentary

## Project Journey

This README documents the project from start to finish. This is the first stage.

### Stage 1: Initial Python Module-Based Audio Splitting (Baseline Attempt)

I began by trying a direct module-based approach in Python for source separation.

- Notebook used: `InitialSpiltter/basicAudioSpliiter.ipynb`
- Core idea: split incoming sports audio into two stems
	- Commentary (vocal-like component)
	- Crowd/background (instrumental-like component)
- Then remix these stems based on user preference (`mute_commentary`, `amplify_crowd`, `balanced`)

#### What this stage included

- Installing and testing `audio-separator` with supporting libraries
- Implementing audio validation and stem identification logic
- Building a remix pipeline for different listening preferences
- Extending the same logic to video by:
	- Extracting audio via `ffmpeg`
	- Processing/remixing audio
	- Reattaching remixed audio back to the original video

#### Outcome

This initial notebook-based approach worked as a prototype, but the separation quality and overall output consistency were not good enough for the final goal.

### Stage 2: Demucs Research, Better Separation, and Flask UI

After the baseline attempt, I studied a few papers on Demucs (stored in the `Papers/` folder) to understand why neural source separation models perform better for complex broadcast audio.

Based on that research, I moved to a Demucs-based pipeline and built a basic Flask UI so the system could be tested interactively on real sports videos.

#### What this stage included

- Reading Demucs-related papers and using those ideas to redesign the separation approach
- Switching from the initial module-based split to a Demucs-driven two-stem workflow (`vocals` and `no_vocals`)
- Building an end-to-end processing backend in Flask
	- Upload sports video
	- Analyze audio characteristics for guidance
	- Extract audio with `ffmpeg`
	- Run Demucs separation
	- Remix commentary/crowd levels
	- Attach remixed audio back to the video
- Creating a simple browser-based UI for upload, controls, and processed output download/playback

#### Outcome

This stage gave much stronger separation quality than the initial prototype and made the project easier to demonstrate through a user-friendly web interface.
