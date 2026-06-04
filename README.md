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

---

Next, I will add the following stages of the project as the pipeline evolved and improved.
