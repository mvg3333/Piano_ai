# Model and audio attribution

## Piano transcription CRNN

The optional piano model is the unmodified checkpoint released by **Qiuqiang Kong, Bochen Li, Xuchen Song, Yuan Wan, and Yuxuan Wang**, authors of *High-resolution Piano Transcription with Pedals by Regressing Onset and Offset Times* (2021).

- Paper: https://arxiv.org/abs/2010.01815
- Original checkpoint and license metadata: https://zenodo.org/records/4034264
- Weights license: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
- Original file: `CRNN_note_F1=0.9677_pedal_F1=0.9186.pth`
- SHA-256: `c3fa9730725bf4a762f1c14bc80cd5986eacda01b026f5a4a2525cd607876141`
- The app renames the downloaded file to `piano-crnn.pth`. Model weights are unchanged. The application adapts decoded events to its practice format.

The [piano-transcription-inference Python distribution](https://pypi.org/project/piano-transcription-inference/) declares MIT in its package metadata. Its [inference source](https://github.com/qiuqiangkong/piano_transcription_inference) and the [original training repository](https://github.com/bytedance/piano_transcription), which declares Apache-2.0, document the implementation. These packages and weights are downloaded during optional local setup; they are not included in browser assets.

## Basic Pitch

The optional fallback is [Spotify Basic Pitch](https://github.com/spotify/basic-pitch), distributed under [Apache License 2.0](https://github.com/spotify/basic-pitch/blob/main/LICENSE), with its packaged ICASSP 2022 pretrained model.

## Piano playback samples

The bundled sample recordings and their CC BY 3.0 attribution are listed in [the sample attribution file](frontend/public/samples/ATTRIBUTION.txt). Other installed dependencies retain their licenses in their distributions.
