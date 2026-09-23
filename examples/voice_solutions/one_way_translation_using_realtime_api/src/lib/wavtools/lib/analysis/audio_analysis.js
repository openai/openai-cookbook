import {
  noteFrequencies,
  noteFrequencyLabels,
  voiceFrequencies,
  voiceFrequencyLabels,
} from './constants.js';

/**
 * Output of AudioAnalysis for the frequency domain of the audio
 * @typedef {Object} AudioAnalysisOutputType
 * @property {Float32Array} values Amplitude of this frequency between {0, 1} inclusive
 * @property {number[]} frequencies Raw frequency bucket values
 * @property {string[]} labels Labels for the frequency bucket values
 */

/**
 * Analyzes audio for visual output
 * @class
 */
export class AudioAnalysis {
  /**
   * Retrieves frequency domain data from an AnalyserNode adjusted to a decibel range
   * returns human-readable formatting and labels
   * @param {AnalyserNode} analyser
   * @param {number} sampleRate
   * @param {Float32Array} [fftResult]
   * @param {"frequency"|"music"|"voice"} [analysisType]
   * @param {number} [minDecibels] default -100
   * @param {number} [maxDecibels] default -30
   * @returns {AudioAnalysisOutputType}
   */
  static getFrequencies(
    analyser,
    sampleRate,
    fftResult,
    analysisType = 'frequency',
    minDecibels = -100,
    maxDecibels = -30,
  ) {
    if (!fftResult) {
      fftResult = new Float32Array(analyser.frequencyBinCount);
      analyser.getFloatFrequencyData(fftResult);
    }
    const nyquistFrequency = sampleRate / 2;
    const frequencyStep = (1 / fftResult.length) * nyquistFrequency;
    let outputValues;
    let frequencies;
    let labels;
    if (analysisType === 'music' || analysisType === 'voice') {
      const useFrequencies =
        analysisType === 'voice' ? voiceFrequencies : noteFrequencies;
      const aggregateOutput = Array(useFrequencies.length).fill(minDecibels);
      for (let i = 0; i < fftResult.length; i++) {
        const frequency = i * frequencyStep;
        const amplitude = fftResult[i];
        for (let n = useFrequencies.length - 1; n >= 0; n--) {
          if (frequency > useFrequencies[n]) {
            aggregateOutput[n] = Math.max(aggregateOutput[n], amplitude);
            break;
          }
        }
      }
      outputValues = aggregateOutput;
      frequencies =
        analysisType === 'voice' ? voiceFrequencies : noteFrequencies;
      labels =
        analysisType === 'voice' ? voiceFrequencyLabels : noteFrequencyLabels;
    } else {
      outputValues = Array.from(fftResult);
      frequencies = outputValues.map((_, i) => frequencyStep * i);
      labels = frequencies.map((f) => `${f.toFixed(2)} Hz`);
    }
    // We normalize to {0, 1}
    const normalizedOutput = outputValues.map((v) => {
      return Math.max(
        0,
        Math.min((v - minDecibels) / (maxDecibels - minDecibels), 1),
      );
    });
    const values = new Float32Array(normalizedOutput);
    return {
      values,
      frequencies,
      labels,
    };
  }

  /**
   * Creates a new AudioAnalysis instance for an HTMLAudioElement
   * @param {HTMLAudioElement} audioElement
   * @param {AudioBuffer|null} [audioBuffer] If provided, will cache all frequency domain data from the buffer
   * @returns {AudioAnalysis}
   */
  constructor(audioElement, audioBuffer = null) {
    this.fftResults = [];
    if (audioBuffer) {
      /**
       * Modified from
       * https://stackoverflow.com/questions/75063715/using-the-web-audio-api-to-analyze-a-song-without-playing
       *
       * We do this to populate FFT values for the audio if provided an `audioBuffer`
       * The reason to do this is that Safari fails when using `createMediaElementSource`
       * This has a non-zero RAM cost so we only opt-in to run it on Safari, Chrome is better
       */
      const { length, sampleRate } = audioBuffer;
      const offlineAudioContext = new OfflineAudioContext({
        length,
        sampleRate,
      });
      const source = offlineAudioContext.createBufferSource();
      source.buffer = audioBuffer;
      const analyser = offlineAudioContext.createAnalyser();
      analyser.fftSize = 8192;
      analyser.smoothingTimeConstant = 0.1;
      source.connect(analyser);
      // limit is :: 128 / sampleRate;
      // but we just want 60fps - cuts ~1s from 6MB to 1MB of RAM
      const renderQuantumInSeconds = 1 / 60;
      const durationInSeconds = length / sampleRate;
      const analyze = (index) => {
        const suspendTime = renderQuantumInSeconds * index;
        if (suspendTime < durationInSeconds) {
          offlineAudioContext.suspend(suspendTime).then(() => {
            const fftResult = new Float32Array(analyser.frequencyBinCount);
            analyser.getFloatFrequencyData(fftResult);
            this.fftResults.push(fftResult);
            analyze(index + 1);
          });
        }
        if (index === 1) {
          offlineAudioContext.startRendering();
        } else {
          offlineAudioContext.resume();
        }
      };
      source.start(0);
      analyze(1);
      this.audio = audioElement;
      this.context = offlineAudioContext;
      this.analyser = analyser;
      this.sampleRate = sampleRate;
      this.audioBuffer = audioBuffer;
    } else {
      const audioContext = new AudioContext();
      const track = audioContext.createMediaElementSource(audioElement);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 8192;
      analyser.smoothingTimeConstant = 0.1;
      track.connect(analyser);
      analyser.connect(audioContext.destination);
      this.audio = audioElement;
      this.context = audioContext;
      this.analyser = analyser;
      this.sampleRate = this.context.sampleRate;
      this.audioBuffer = null;
    }
  }

  /**
   * Gets the current frequency domain data from the playing audio track
   * @param {"frequency"|"music"|"voice"} [analysisType]
   * @param {number} [minDecibels] default -100
   * @param {number} [maxDecibels] default -30
   * @returns {AudioAnalysisOutputType}
   */
  getFrequencies(
    analysisType = 'frequency',
    minDecibels = -100,
    maxDecibels = -30,
  ) {
    let fftResult = null;
    if (this.audioBuffer && this.fftResults.length) {
      const pct = this.audio.currentTime / this.audio.duration;
      const index = Math.min(
        (pct * this.fftResults.length) | 0,
        this.fftResults.length - 1,
      );
      fftResult = this.fftResults[index];
    }
    return AudioAnalysis.getFrequencies(
      this.analyser,
      this.sampleRate,
      fftResult,
      analysisType,
      minDecibels,
      maxDecibels,
    );
  }

  /**
   * Resume the internal AudioContext if it was suspended due to the lack of
   * user interaction when the AudioAnalysis was instantiated.
   * @returns {Promise<true>}
   */
  async resumeIfSuspended() {
    if (this.context.state === 'suspended') {
      await this.context.resume();
    }
    return true;
  }
}

globalThis.AudioAnalysis = AudioAnalysis;
