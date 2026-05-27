import eel

@eel.expose
def voicer_synthesize_speech(text, voice_model="default"):
    # TODO: Implement TTS logic later
    print(f"Voicer: Synthesizing speech for text: {text[:20]}...")
    return {"status": "success", "message": "Synthesis logic not implemented yet."}

@eel.expose
def voicer_transcribe_audio(file_path):
    # TODO: Implement STT (Whisper/Deepgram) logic later
    print(f"Voicer: Transcribing audio file: {file_path}")
    return {"status": "success", "message": "Transcription logic not implemented yet."}
