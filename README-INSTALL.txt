MANUAL FINAL ASSEMBLY

The manual retry workflow is .github/workflows/assemble-final-reel.yml.

1. Open GitHub → Actions → Generate cinematic Reel.
2. Select the successful source render run and copy its numeric run ID.
3. Open GitHub → Actions → Assemble Final Tamil Reel (manual retry).
4. Run the workflow with that source_run_id and artifact_name=cinematic-reel.
5. Download final-tamil-reel-review-package after success.

Important:
- The workflow downloads cinematic_reel.mp4, ambience.wav, sfx.wav and the exact story.json from the same source artifact.
- It must not copy the repository-root sample story.json over the downloaded story.
- The output is a review package only. It does not publish to Instagram.
