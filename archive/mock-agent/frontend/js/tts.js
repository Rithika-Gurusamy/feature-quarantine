/**
 * TTSController - Modular Text-to-Speech Engine
 * Isolates SpeechSynthesis logic with reliable Pause, Resume, Stop, and Mute support.
 */
class TTSController {
  constructor() {
    this.synth = window.speechSynthesis || null;
    this.isSpeaking = false;
    this.isPaused = false;
    this.ttsEnabled = true;
    this.currentText = "";
    this.utterance = null;
    this.selectedVoice = null;
    this.onStateChangeCallback = null;

    if (this.synth) {
      this._initVoices();
      if (this.synth.onvoiceschanged !== undefined) {
        this.synth.onvoiceschanged = () => this._initVoices();
      }
    }
  }

  _initVoices() {
    if (!this.synth) return;
    const voices = this.synth.getVoices();
    // Prefer natural English voices (Google, Microsoft, Natural, Samantha)
    this.selectedVoice =
      voices.find((v) => v.lang.startsWith("en") && (v.name.includes("Google") || v.name.includes("Natural") || v.name.includes("Neural"))) ||
      voices.find((v) => v.lang.startsWith("en")) ||
      voices[0] ||
      null;
  }

  onStateChange(cb) {
    this.onStateChangeCallback = cb;
  }

  _emitState(state) {
    if (this.onStateChangeCallback) {
      this.onStateChangeCallback(state, {
        isSpeaking: this.isSpeaking,
        isPaused: this.isPaused,
        ttsEnabled: this.ttsEnabled
      });
    }
  }

  speak(text) {
    if (!this.synth || !this.ttsEnabled || !text) {
      this._emitState("READY");
      return;
    }

    // Stop any active or paused speech before starting a new one
    this.stopSpeech();

    this.currentText = text;
    this.utterance = new SpeechSynthesisUtterance(text);
    if (this.selectedVoice) {
      this.utterance.voice = this.selectedVoice;
    }
    this.utterance.rate = 1.0;
    this.utterance.pitch = 1.0;

    this.utterance.onstart = () => {
      this.isSpeaking = true;
      this.isPaused = false;
      this._emitState("SPEAKING");
    };

    this.utterance.onpause = () => {
      this.isSpeaking = true;
      this.isPaused = true;
      this._emitState("PAUSED");
    };

    this.utterance.onresume = () => {
      this.isSpeaking = true;
      this.isPaused = false;
      this._emitState("SPEAKING");
    };

    this.utterance.onend = () => {
      this.isSpeaking = false;
      this.isPaused = false;
      this.currentText = "";
      this.utterance = null;
      this._emitState("READY");
    };

    this.utterance.onerror = (e) => {
      console.warn("TTS Utterance event:", e.error || e);
      this.isSpeaking = false;
      this.isPaused = false;
      this._emitState("READY");
    };

    this.synth.speak(this.utterance);
  }

  pauseSpeech() {
    if (!this.synth || !this.isSpeaking || this.isPaused) return;
    this.synth.pause();
    this.isPaused = true;
    this._emitState("PAUSED");
  }

  resumeSpeech() {
    if (!this.synth || !this.isPaused) return;
    this.synth.resume();
    this.isPaused = false;
    this._emitState("SPEAKING");
  }

  togglePauseResume() {
    if (this.isPaused) {
      this.resumeSpeech();
    } else if (this.isSpeaking) {
      this.pauseSpeech();
    }
  }

  stopSpeech() {
    if (!this.synth) return;
    this.synth.cancel();
    this.isSpeaking = false;
    this.isPaused = false;
    this.currentText = "";
    this.utterance = null;
    this._emitState("READY");
  }

  toggleMute() {
    this.ttsEnabled = !this.ttsEnabled;
    if (!this.ttsEnabled && this.isSpeaking) {
      this.stopSpeech();
    }
    this._emitState(this.isSpeaking ? (this.isPaused ? "PAUSED" : "SPEAKING") : "READY");
    return this.ttsEnabled;
  }
}

window.ttsController = new TTSController();
