// Downsamples the captured tab audio to mono PCM16 at targetSampleRate,
// then posts each ~250ms chunk to the main thread as a transferable ArrayBuffer.
class DownsampleProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetRate = (options.processorOptions && options.processorOptions.targetSampleRate) || 16000;
    this.chunkDurationSec = 0.25;
    this.outputChunkSamples = Math.round(this.targetRate * this.chunkDurationSec);
    this.inputSegments = [];
    this.inputTotal = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (input && input.length && input[0] && input[0].length) {
      let mono = input[0];
      if (input.length > 1 && input[1]) {
        mono = new Float32Array(input[0].length);
        for (let i = 0; i < mono.length; i++) {
          mono[i] = (input[0][i] + input[1][i]) / 2;
        }
      } else {
        mono = mono.slice();
      }
      this.inputSegments.push(mono);
      this.inputTotal += mono.length;
    }

    const ratio = sampleRate / this.targetRate;
    const neededInput = Math.ceil(this.outputChunkSamples * ratio);

    if (this.inputTotal >= neededInput) {
      const flat = new Float32Array(this.inputTotal);
      let offset = 0;
      for (const seg of this.inputSegments) {
        flat.set(seg, offset);
        offset += seg.length;
      }

      const outSamples = Math.floor(flat.length / ratio);
      const out = new Int16Array(outSamples);
      for (let i = 0; i < outSamples; i++) {
        const srcIndex = i * ratio;
        const idx0 = Math.floor(srcIndex);
        const idx1 = Math.min(idx0 + 1, flat.length - 1);
        const frac = srcIndex - idx0;
        const sample = flat[idx0] * (1 - frac) + flat[idx1] * frac;
        out[i] = Math.max(-32768, Math.min(32767, Math.round(sample * 32767)));
      }

      this.port.postMessage(out.buffer, [out.buffer]);
      this.inputSegments = [];
      this.inputTotal = 0;
    }

    return true;
  }
}

registerProcessor("downsample-processor", DownsampleProcessor);
