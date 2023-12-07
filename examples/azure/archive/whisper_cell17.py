# download sample audio file
import requests

sample_audio_url = "https://github.com/Azure-Samples/cognitive-services-speech-sdk/raw/master/sampledata/audiofiles/wikipediaOcelot.wav"
audio_file = requests.get(sample_audio_url)
with open("wikipediaOcelot.wav", "wb") as f:
    f.write(audio_file.content)