/**
 * STTController - Modular Speech-to-Text Engine
 * Handles microphone capture, speech recognition, live interim transcripts,
 * and modular fallback to backend speech transcription services.
 */
class STTController {
  constructor() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition || null;
    this.recognition = SpeechRecognition ? new SpeechRecognition() : null;
    this.isRecording = false;
    this.finalTranscript = "";
    this.interimTranscript = "";

    this.onTranscriptUpdateCallback = null;
    this.onStateChangeCallback = null;
    this.onErrorCallback = null;

    if (this.recognition) {
      this.recognition.continuous = true;
      this.recognition.interimResults = true;
      this.recognition.lang = "en-US";

      this.recognition.onstart = () => {
        this.isRecording = true;
        this.finalTranscript = "";
        this.interimTranscript = "";
        this._emitState("RECORDING");
      };

      this.recognition.onresult = (event) => {
        this.interimTranscript = "";
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            this.finalTranscript += (this.finalTranscript ? " " : "") + event.results[i][0].transcript.trim();
          } else {
            this.interimTranscript += event.results[i][0].transcript;
          }
        }

        const fullText = (this.finalTranscript + (this.interimTranscript ? " " + this.interimTranscript : "")).trim();
        if (this.onTranscriptUpdateCallback) {
          this.onTranscriptUpdateCallback(fullText, this.finalTranscript, this.interimTranscript);
        }
      };

      this.recognition.onerror = (event) => {
        console.warn("STT recognition error:", event.error);
        if (this.onErrorCallback) {
          let userMsg = "Speech recognition error.";
          if (event.error === "not-allowed") {
            userMsg = "Microphone permission denied. Please allow microphone access in your browser settings.";
          } else if (event.error === "no-speech") {
            userMsg = "No speech detected. Please try speaking again.";
          }
          this.onErrorCallback(userMsg, event.error);
        }
        this.stop();
      };

      this.recognition.onend = () => {
        this.isRecording = false;
        this._emitState("IDLE");
      };
    }
  }

  isSupported() {
    return !!this.recognition;
  }

  onTranscriptUpdate(cb) {
    this.onTranscriptUpdateCallback = cb;
  }

  onStateChange(cb) {
    this.onStateChangeCallback = cb;
  }

  onError(cb) {
    this.onErrorCallback = cb;
  }

  _emitState(state) {
    if (this.onStateChangeCallback) {
      this.onStateChangeCallback(state, { isRecording: this.isRecording });
    }
  }

  start() {
    if (!this.recognition) {
      if (this.onErrorCallback) {
        this.onErrorCallback("Speech recognition is not supported in this browser. Please use Google Chrome or Edge.");
      }
      return false;
    }

    if (this.isRecording) return true;

    try {
      this.finalTranscript = "";
      this.interimTranscript = "";
      this.recognition.start();
      return true;
    } catch (err) {
      console.error("Failed to start speech recognition:", err);
      return false;
    }
  }

  stop() {
    if (!this.recognition || !this.isRecording) return;
    try {
      this.recognition.stop();
    } catch (e) {
      // Ignored
    }
    this.isRecording = false;
    this._emitState("IDLE");
  }

  toggle() {
    if (this.isRecording) {
      this.stop();
    } else {
      this.start();
    }
  }

  /**
   * Modular backend speechToText fallback
   * Useful when browser STT is not available or when backend STT (Whisper) is preferred.
   */
  async speechToText(audioBlob) {
    const formData = new FormData();
    formData.append("file", audioBlob, "recording.wav");

    const response = await fetch("/api/interview/audio", {
      method: "POST",
      body: formData
    });

    if (!response.ok) {
      throw new Error(`Backend transcription failed: ${response.statusText}`);
    }

    const data = await response.json();
    return data.text;
  }
}

window.sttController = new STTController();
