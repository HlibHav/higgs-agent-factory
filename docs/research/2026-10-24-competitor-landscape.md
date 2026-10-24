# Competitor landscape: who owns which part of the voice stack (2026-10-24)

Glib's outside-in comparison of Boson and six companies, from public sources only, as of
2026-10-24. Kept here as the evidence for one CLAIMS row (the demo film's market line). Facts about
competitors change fast: ElevenLabs gained speech-to-speech four days before this date.

Boson's own benchmark numbers and Artificial Analysis rankings from the same analysis are not
copied here; in [CLAIMS.md](../CLAIMS.md) they are `conversation-only`.

## Who builds what

| | Layer | Own speech-to-speech | Own TTS | Own real-time avatar | Rents voice from |
|---|---|---|---|---|---|
| **Boson** | model + platform | yes (Higgs Realtime) | yes (Higgs TTS 3) | yes (Higgs Avatar) | — |
| **ElevenLabs** | all three | yes, since 2026-10-20 | yes | no, through HeyGen LiveAvatar | — |
| **Fish Audio** | model + API | no, announced as the next step | yes, open weights | no | — |
| **Fin** (Salesforce) | app | not as an API; an in-product voice model (Apex Flash) | not disclosed | no | not disclosed |
| **HeyGen** | app + platform | no | no | yes (LiveAvatar) | ElevenLabs, Fish |
| **Synthesia** | app | no | partly | only in its own player | ElevenLabs (clones) |
| **Beyond Presence** | model + platform | no | no | yes (Genesis 2.0) | OpenAI, ElevenLabs, Cartesia, Hume |

Reading: of these six, none has its own speech-to-speech model, TTS and real-time avatar together.
The two cells that need care when phrasing a claim: Fin's voice model exists only inside its
product, and Synthesia's TTS is partial.

## Sources

- Boson: [Higgs Realtime launch](https://www.boson.ai/blog/higgs-realtime), [Higgs TTS 3](https://www.boson.ai/blog/higgs-tts-3), [Avatar streaming](https://www.boson.ai/blog/higgs-avatar-streaming)
- ElevenLabs: [Eleven Realtime](https://elevenlabs.io/blog/realtime)
- Fish Audio: [seed round and roadmap](https://fish.audio/blog/fish-audio-52m-seed-funding/)
- Fin: [Fin Voice 2](https://www.comparethecloud.net/news/fin-voice-2-ships-with-a-purpose-built-model-as-phone-ai-moves-past-general-purpose-foundations), [Salesforce acquisition](https://www.salesforce.com/news/press-releases/2026/09/10/salesforce-completes-acquisition-of-fin/)
- HeyGen: [voice models](https://www.heygen.com/academy/voice/what-are-voice-models), [LiveAvatar](https://docs.liveavatar.com/docs/credits-and-subscriptions)
- Synthesia: [voice cloning technology](https://help.synthesia.io/en/articles/10180028-what-technology-does-synthesia-use-for-voice-cloning)
- Beyond Presence: [pricing and voice providers](https://www.beyondpresence.ai/pricing)
