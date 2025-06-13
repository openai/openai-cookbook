/**
 * Raw wav audio file contents
 * @typedef {Object} WavPackerAudioType
 * @property {Blob} blob
 * @property {string} url
 * @property {number} channelCount
 * @property {number} sampleRate
 * @property {number} duration
 */
/**
 * Utility class for assembling PCM16 "audio/wav" data
 * @class
 */
export class WavPacker {
    /**
     * Converts Float32Array of amplitude data to ArrayBuffer in Int16Array format
     * @param {Float32Array} float32Array
     * @returns {ArrayBuffer}
     */
    static floatTo16BitPCM(float32Array: Float32Array): ArrayBuffer;
    /**
     * Concatenates two ArrayBuffers
     * @param {ArrayBuffer} leftBuffer
     * @param {ArrayBuffer} rightBuffer
     * @returns {ArrayBuffer}
     */
    static mergeBuffers(leftBuffer: ArrayBuffer, rightBuffer: ArrayBuffer): ArrayBuffer;
    /**
     * Packs data into an Int16 format
     * @private
     * @param {number} size 0 = 1x Int16, 1 = 2x Int16
     * @param {number} arg value to pack
     * @returns
     */
    private _packData;
    /**
     * Packs audio into "audio/wav" Blob
     * @param {number} sampleRate
     * @param {{bitsPerSample: number, channels: Array<Float32Array>, data: Int16Array}} audio
     * @returns {WavPackerAudioType}
     */
    pack(sampleRate: number, audio: {
        bitsPerSample: number;
        channels: Array<Float32Array>;
        data: Int16Array;
    }): WavPackerAudioType;
}
/**
 * Raw wav audio file contents
 */
export type WavPackerAudioType = {
    blob: Blob;
    url: string;
    channelCount: number;
    sampleRate: number;
    duration: number;
};
//# sourceMappingURL=wav_packer.d.ts.map