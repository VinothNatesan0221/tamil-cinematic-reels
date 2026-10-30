INSTALLATION

Add these three files to your GitHub repository:
1. assemble_final_reel.py (repository root)
2. .github/workflows/assemble-final-reel.yml
3. story.json (repository root; paste the complete Raw JSON from Google Sheet column M)

Every scene in story.json needs duration_seconds, speaker_gender (male/female), tamil_narration and english_subtitle.

Then open Actions > Assemble Final Tamil Reel > Run workflow.
Enter source run ID: 41075747811
Keep artifact name: cinematic-reel
Run it. Download the final-tamil-reel artifact when complete.

This reuses your existing video, mutes its original audio, adds Tamil narration and burns in English subtitles. It does not generate new images or video. No background music is added.
