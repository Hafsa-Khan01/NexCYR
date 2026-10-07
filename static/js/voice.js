// NexCYR AI Voice — browser speechSynthesis only. Never depends on an external AI API.

const state = {
  enabled: true,
  rate: 1.0,
  volume: 1.0,
  voiceName: null,
  language: null,
  current: null,
  onStateChange: null,
};

function supported() {
  return "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
}

function pickVoice() {
  if (!supported()) return null;
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;
  if (state.voiceName) {
    const v = voices.find((x) => x.name === state.voiceName);
    if (v) return v;
  }
  if (state.language) {
    const v = voices.find((x) => x.lang && x.lang.toLowerCase().startsWith(state.language.toLowerCase()));
    if (v) return v;
  }
  return voices.find((x) => /en[-_]?(US|GB|IN)/i.test(x.lang || "")) || voices[0] || null;
}

export function configureVoice(settings = {}) {
  if (typeof settings.voice_enabled === "boolean") state.enabled = settings.voice_enabled;
  if (settings.voice_rate != null) state.rate = Number(settings.voice_rate) || 1.0;
  if (settings.voice_volume != null) state.volume = Number(settings.voice_volume);
  if (Number.isNaN(state.volume)) state.volume = 1.0;
  if (settings.voice_name) state.voiceName = settings.voice_name;
  if (settings.voice_language) state.language = settings.voice_language;
}

export function setVoiceEnabled(on) {
  state.enabled = !!on;
  if (!state.enabled) stopSpeaking();
  notify();
}
export function isVoiceEnabled() { return state.enabled; }

function notify() {
  if (typeof state.onStateChange === "function") state.onStateChange(state);
}
export function onVoiceState(cb) { state.onStateChange = cb; }

export function speak(text) {
  if (!state.enabled) return false;
  if (!supported()) {
    notify();
    return false;
  }
  stopSpeaking();
  const utter = new SpeechSynthesisUtterance(String(text || "").slice(0, 4000));
  const v = pickVoice();
  if (v) utter.voice = v;
  utter.rate = state.rate;
  utter.volume = state.volume;
  utter.onend = () => { state.current = null; notify(); };
  utter.onerror = () => { state.current = null; notify(); };
  state.current = utter;
  notify();
  window.speechSynthesis.speak(utter);
  return true;
}

export function stopSpeaking() {
  if (supported()) window.speechSynthesis.cancel();
  state.current = null;
  notify();
}

export function isSpeaking() {
  return supported() && window.speechSynthesis.speaking;
}

export function voiceSupported() { return supported(); }

// preload voices (Chrome fires asynchronously)
if (supported()) {
  window.speechSynthesis.onvoiceschanged = () => {};
  window.speechSynthesis.getVoices();
}
