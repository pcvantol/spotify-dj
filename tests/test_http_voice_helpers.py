from __future__ import annotations

import importlib
import asyncio
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]


def install_http_stubs() -> None:
    if "homeassistant.components.http" in sys.modules:
        return

    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))

    homeassistant = sys.modules.setdefault(
        "homeassistant", types.ModuleType("homeassistant")
    )
    components = types.ModuleType("homeassistant.components")
    http = types.ModuleType("homeassistant.components.http")
    core = types.ModuleType("homeassistant.core")
    helpers = types.ModuleType("homeassistant.helpers")
    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")

    class HomeAssistantView:
        def json(self, payload, status_code=200):
            return {"payload": payload, "status_code": status_code}

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class Response:
        def __init__(self, *, status=200, text=None, body=None, content_type=None, headers=None):
            self.status = status
            self.text = text
            self.body = body
            self.content_type = content_type
            self.headers = headers or {}

    class Context:
        pass

    http.HomeAssistantView = HomeAssistantView
    core.Context = Context
    core.HomeAssistant = object
    aiohttp.ClientTimeout = ClientTimeout
    aiohttp.web = types.SimpleNamespace(Response=Response)
    aiohttp_client.async_get_clientsession = lambda hass: None

    homeassistant.components = components
    sys.modules["homeassistant.components"] = components
    sys.modules["homeassistant.components.http"] = http
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

    package = types.ModuleType("custom_components.djconnect")
    package.__path__ = [str(ROOT / "custom_components" / "djconnect")]
    sys.modules.setdefault("custom_components.djconnect", package)


class VoiceHttpHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_http_stubs()
        cls.http = importlib.import_module("custom_components.djconnect.http")

    def test_text_from_header_takes_precedence(self) -> None:
        text = self.http._text_from_payload(
            {"X-DJConnect-Text": " Speel Pearl Jam "},
            {"text": "Speel Nirvana"},
        )

        self.assertEqual(text, "Speel Pearl Jam")

    def test_text_from_json_payload(self) -> None:
        text = self.http._text_from_payload({}, {"text": " Speel Nirvana "})

        self.assertEqual(text, "Speel Nirvana")

    def test_missing_text_response_documents_assist_flow(self) -> None:
        response = self.http._missing_text_response(self.http.DJConnectVoiceView(None))

        self.assertEqual(response["status_code"], 400)
        self.assertEqual(response["payload"]["error"], "missing_text")
        self.assertIn("X-DJConnect-Text", response["payload"]["message"])
        self.assertIn("WAV audio", response["payload"]["message"])

    def test_command_failed_text_uses_device_language(self) -> None:
        nl_runtime = types.SimpleNamespace(device_language=lambda: "nl")
        en_runtime = types.SimpleNamespace(device_language=lambda: "en")
        unknown_runtime = types.SimpleNamespace()

        self.assertIn(
            "Spotify niet starten",
            self.http._command_failed_text(
                nl_runtime,
                RuntimeError("Spotify playback device unavailable"),
            ),
        )
        self.assertIn(
            "could not start Spotify playback",
            self.http._command_failed_text(
                en_runtime,
                RuntimeError("media_player.play_media failed"),
            ),
        )
        self.assertIn(
            "Assist pipeline",
            self.http._command_failed_text(
                en_runtime,
                RuntimeError("HA Assist pipeline failed"),
            ),
        )
        self.assertIn(
            "something went wrong",
            self.http._command_failed_text(unknown_runtime),
        )

    def test_voice_view_text_request_runs_direct_dj_response_test(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            config = {}

            def authorize_device_request(self, headers, body_device_id=None):
                return True

            def device_language(self):
                return "nl"

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()
        hass = types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})

        async def fail_command(hass, runtime, user_text, play=True):
            raise AssertionError("text-only voice test must not run command parser")

        async def dj_response(hass, runtime, text):
            return {"success": True, "spoken": False}

        original_command = self.http.process_text_command
        original_dj_response = self.http.async_send_dj_response_best_effort
        self.http.process_text_command = fail_command
        self.http.async_send_dj_response_best_effort = dj_response

        class Request:
            headers = {
                "X-DJConnect-Text": "Test",
                "X-DJConnect-Device-ID": "djconnect-lilygo-90B70990A994",
            }
            app = {"hass": hass}

            async def read(self):
                return b""

        try:
            response = asyncio.run(self.http.DJConnectVoiceView(None).post(Request()))
        finally:
            self.http.process_text_command = original_command
            self.http.async_send_dj_response_best_effort = original_dj_response

        self.assertEqual(response["status_code"], 200)
        self.assertTrue(response["payload"]["success"])
        self.assertEqual(
            response["payload"]["dj_text"],
            "DJConnect is klaar voor je volgende verzoek.",
        )
        self.assertEqual(response["payload"]["recognized_text"], "Test")
        self.assertEqual(response["payload"]["dj_response"], {"success": True, "spoken": False})
        self.assertIsNone(runtime.last_update["last_error"])

    def test_voice_view_json_text_request_runs_direct_dj_response_test(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            config = {}

            def authorize_device_request(self, headers, body_device_id=None):
                return True

            def device_language(self):
                return "en"

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()
        hass = types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})

        async def fail_command(hass, runtime, user_text, play=True):
            raise AssertionError("JSON text test must not run command parser")

        async def dj_response(hass, runtime, text):
            return {
                "success": True,
                "spoken": True,
                "audio_url_value": "http://ha/api/djconnect/tts/test.mp3",
            }

        original_command = self.http.process_text_command
        original_dj_response = self.http.async_send_dj_response_best_effort
        self.http.process_text_command = fail_command
        self.http.async_send_dj_response_best_effort = dj_response

        class Request:
            headers = {
                "Authorization": "Bearer device-token",
                "X-DJConnect-Device-ID": "djconnect-lilygo-90B70990A994",
                "Content-Type": "application/json",
            }
            app = {"hass": hass}

            async def json(self):
                return {"text": "Test"}

        try:
            response = asyncio.run(self.http.DJConnectVoiceView(None).post(Request()))
        finally:
            self.http.process_text_command = original_command
            self.http.async_send_dj_response_best_effort = original_dj_response

        self.assertEqual(response["status_code"], 200)
        self.assertTrue(response["payload"]["success"])
        self.assertEqual(
            response["payload"]["dj_text"],
            "DJConnect is ready for your next request.",
        )
        self.assertEqual(
            response["payload"]["audio_url"],
            "http://ha/api/djconnect/tts/test.mp3",
        )
        self.assertEqual(response["payload"]["audio_type"], "mp3")

    def test_voice_view_accepts_wav_upload_and_returns_audio_url(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            config = {const.CONF_MAX_AUDIO_BYTES: 100}
            device_status = {"device_id": "djconnect-lilygo-90B70990A994"}
            device_token = "device-token"

            def authorize_device_request(self, headers, body_device_id=None):
                return (
                    headers.get("Authorization") == "Bearer device-token"
                    and body_device_id == "djconnect-lilygo-90B70990A994"
                )

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()
        hass = types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})

        async def transcribe(hass, wav, conf):
            self.assertEqual(wav, b"RIFFxxxxWAVEdata")
            return "Speel Pearl Jam"

        async def command(hass, runtime, user_text, play=True):
            return {
                "text": user_text,
                "dj_text": "Daar gaan we",
                "intent": {},
                "playback": None,
            }

        async def dj_response(hass, runtime, text):
            return {
                "success": True,
                "spoken": True,
                "audio_url_value": "http://ha/api/djconnect/tts/token.mp3",
            }

        original_transcribe = self.http.transcribe_wav_with_assist
        original_command = self.http.process_text_command
        original_dj_response = self.http.async_send_dj_response_best_effort
        self.http.transcribe_wav_with_assist = transcribe
        self.http.process_text_command = command
        self.http.async_send_dj_response_best_effort = dj_response

        class Request:
            headers = {
                "Authorization": "Bearer device-token",
                "X-DJConnect-Device-ID": "djconnect-lilygo-90B70990A994",
                "Content-Type": "audio/wav",
            }
            app = {"hass": hass}

            async def read(self):
                return b"RIFFxxxxWAVEdata"

        try:
            with self.assertLogs(self.http._LOGGER, level="DEBUG") as captured:
                response = asyncio.run(self.http.DJConnectVoiceView(None).post(Request()))
        finally:
            self.http.transcribe_wav_with_assist = original_transcribe
            self.http.process_text_command = original_command
            self.http.async_send_dj_response_best_effort = original_dj_response

        log_output = "\n".join(captured.output)
        self.assertIn("audio_url=True", log_output)
        self.assertNotIn("http://ha/api/djconnect/tts/token.mp3", log_output)
        self.assertEqual(response["status_code"], 200)
        self.assertTrue(response["payload"]["success"])
        self.assertEqual(response["payload"]["recognized_text"], "Speel Pearl Jam")
        self.assertEqual(response["payload"]["text"], "Daar gaan we")
        self.assertEqual(
            response["payload"]["audio_url"],
            "http://ha/api/djconnect/tts/token.mp3",
        )
        self.assertEqual(response["payload"]["audio_type"], "mp3")

    def test_voice_view_wav_command_failure_returns_friendly_200(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            config = {const.CONF_MAX_AUDIO_BYTES: 100}
            device_status = {"device_id": "djconnect-lilygo-90B70990A994"}

            def authorize_device_request(self, headers, body_device_id=None):
                return True

            def device_language(self):
                return "nl"

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()
        hass = types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})

        async def transcribe(hass, wav, conf):
            return "Test"

        async def fail_command(hass, runtime, user_text, play=True):
            raise RuntimeError("Sorry, ik kan geen apparaat vinden met de naam Test")

        async def dj_response(hass, runtime, text):
            return {"success": True, "spoken": False}

        original_transcribe = self.http.transcribe_wav_with_assist
        original_command = self.http.process_text_command
        original_dj_response = self.http.async_send_dj_response_best_effort
        self.http.transcribe_wav_with_assist = transcribe
        self.http.process_text_command = fail_command
        self.http.async_send_dj_response_best_effort = dj_response

        class Request:
            headers = {
                "Authorization": "Bearer device-token",
                "X-DJConnect-Device-ID": "djconnect-lilygo-90B70990A994",
                "Content-Type": "audio/wav",
            }
            app = {"hass": hass}

            async def read(self):
                return b"RIFFxxxxWAVEdata"

        try:
            response = asyncio.run(self.http.DJConnectVoiceView(None).post(Request()))
        finally:
            self.http.transcribe_wav_with_assist = original_transcribe
            self.http.process_text_command = original_command
            self.http.async_send_dj_response_best_effort = original_dj_response

        self.assertEqual(response["status_code"], 200)
        self.assertTrue(response["payload"]["success"])
        self.assertEqual(response["payload"]["error"], "command_failed")
        self.assertIn("Spotify niet starten", response["payload"]["dj_text"])
        self.assertEqual(response["payload"]["recognized_text"], "Test")
        self.assertEqual(response["payload"]["dj_response"], {"success": True, "spoken": False})

    def test_voice_view_rejects_oversized_wav_upload(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            config = {const.CONF_MAX_AUDIO_BYTES: 4}
            device_status = {"device_id": "djconnect-lilygo-90B70990A994"}

            def authorize_device_request(self, headers, body_device_id=None):
                return True

        hass = types.SimpleNamespace(data={const.DOMAIN: {"runtime": Runtime()}})

        class Request:
            headers = {
                "Authorization": "Bearer device-token",
                "X-DJConnect-Device-ID": "djconnect-lilygo-90B70990A994",
                "Content-Type": "audio/x-wav",
            }
            app = {"hass": hass}

            async def read(self):
                return b"RIFFxxxxWAVEdata"

        response = asyncio.run(self.http.DJConnectVoiceView(None).post(Request()))

        self.assertEqual(response["status_code"], 413)
        self.assertEqual(response["payload"]["error"], "audio_too_large")

    def test_voice_view_reports_stt_failure(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            config = {const.CONF_MAX_AUDIO_BYTES: 100}
            device_status = {"device_id": "djconnect-lilygo-90B70990A994"}

            def authorize_device_request(self, headers, body_device_id=None):
                return True

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()
        hass = types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})

        async def fail_stt(hass, wav, conf):
            raise RuntimeError("STT unavailable")

        original_transcribe = self.http.transcribe_wav_with_assist
        self.http.transcribe_wav_with_assist = fail_stt

        class Request:
            headers = {
                "Authorization": "Bearer device-token",
                "X-DJConnect-Device-ID": "djconnect-lilygo-90B70990A994",
                "Content-Type": "application/octet-stream",
            }
            app = {"hass": hass}

            async def read(self):
                return b"RIFFxxxxWAVEdata"

        try:
            response = asyncio.run(self.http.DJConnectVoiceView(None).post(Request()))
        finally:
            self.http.transcribe_wav_with_assist = original_transcribe

        self.assertEqual(response["status_code"], 500)
        self.assertEqual(response["payload"]["error"], "stt_failed")
        self.assertIn("STT unavailable", response["payload"]["message"])

    def test_voice_view_reports_no_stt_provider_as_503(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")
        assist_stt = importlib.import_module("custom_components.djconnect.assist_stt")

        class Runtime:
            config = {const.CONF_MAX_AUDIO_BYTES: 100}
            device_status = {"device_id": "djconnect-lilygo-90B70990A994"}

            def authorize_device_request(self, headers, body_device_id=None):
                return True

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()
        hass = types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})

        async def no_provider(hass, wav, conf):
            raise assist_stt.DJConnectNoSttProviderError(
                assist_stt.NO_STT_PROVIDER + "stt_engine"
            )

        original_transcribe = self.http.transcribe_wav_with_assist
        self.http.transcribe_wav_with_assist = no_provider

        class Request:
            headers = {
                "Authorization": "Bearer device-token",
                "X-DJConnect-Device-ID": "djconnect-lilygo-90B70990A994",
                "Content-Type": "audio/wav",
            }
            app = {"hass": hass}

            async def read(self):
                return b"RIFFxxxxWAVEdata"

        try:
            response = asyncio.run(self.http.DJConnectVoiceView(None).post(Request()))
        finally:
            self.http.transcribe_wav_with_assist = original_transcribe

        self.assertEqual(response["status_code"], 503)
        self.assertEqual(response["payload"]["error"], "stt_failed")
        self.assertIn(assist_stt.NO_STT_PROVIDER, response["payload"]["message"])
        self.assertIn("stt_engine", response["payload"]["message"])

    def test_transcribe_wav_uses_home_assistant_stt_helper(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")
        assist_stt = importlib.import_module("custom_components.djconnect.assist_stt")
        stt_module = types.ModuleType("homeassistant.components.stt")
        assist_pkg = types.ModuleType("homeassistant.components.assist_pipeline")
        pipeline_module = types.ModuleType(
            "homeassistant.components.assist_pipeline.pipeline"
        )

        class SpeechMetadata:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class AudioFormats:
            WAV = "wav"

        class AudioCodecs:
            PCM = "pcm"

        async def async_process_audio_stream(hass, metadata, stream, engine=None):
            chunks = []
            async for chunk in stream:
                chunks.append(chunk)
            self.assertEqual(engine, "mock_stt")
            self.assertEqual(b"".join(chunks), b"RIFFxxxxWAVEdata")
            self.assertEqual(metadata.kwargs["format"], "wav")
            return types.SimpleNamespace(text="Speel Pearl Jam")

        class Pipelines:
            def async_get_pipeline(self, pipeline_id):
                self.pipeline_id = pipeline_id
                return types.SimpleNamespace(
                    id=pipeline_id,
                    stt_engine="mock_stt",
                    stt_language="nl-NL",
                )

        stt_module.SpeechMetadata = SpeechMetadata
        stt_module.AudioFormats = AudioFormats
        stt_module.AudioCodecs = AudioCodecs
        stt_module.async_process_audio_stream = async_process_audio_stream
        pipeline_module.async_get_pipelines = lambda hass: Pipelines()

        originals = {
            name: sys.modules.get(name)
            for name in (
                "homeassistant.components.stt",
                "homeassistant.components.assist_pipeline",
                "homeassistant.components.assist_pipeline.pipeline",
            )
        }
        sys.modules["homeassistant.components.stt"] = stt_module
        sys.modules["homeassistant.components.assist_pipeline"] = assist_pkg
        sys.modules[
            "homeassistant.components.assist_pipeline.pipeline"
        ] = pipeline_module

        try:
            text = asyncio.run(
                assist_stt.transcribe_wav_with_assist(
                    types.SimpleNamespace(data={}),
                    b"RIFFxxxxWAVEdata",
                    {const.CONF_ASSIST_PIPELINE_ID: "preferred"},
                )
            )
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

        self.assertEqual(text, "Speel Pearl Jam")

    def test_transcribe_wav_uses_configured_openai_stt_option(self) -> None:
        assist_stt = importlib.import_module("custom_components.djconnect.assist_stt")
        stt_module = types.ModuleType("homeassistant.components.stt")
        pipeline_module = types.ModuleType(
            "homeassistant.components.assist_pipeline.pipeline"
        )
        calls = []

        class SpeechMetadata:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class AudioFormats:
            WAV = "wav"

        class AudioCodecs:
            PCM = "pcm"

        async def async_process_audio_stream(hass, metadata, stream, engine=None):
            calls.append(engine)
            async for _chunk in stream:
                pass
            return {"text": "Speel via OpenAI"}

        stt_module.SpeechMetadata = SpeechMetadata
        stt_module.AudioFormats = AudioFormats
        stt_module.AudioCodecs = AudioCodecs
        stt_module.async_process_audio_stream = async_process_audio_stream

        def fail_pipeline_lookup(hass):
            raise AssertionError("explicit STT option must not check Assist pipeline first")

        pipeline_module.async_get_pipelines = fail_pipeline_lookup
        originals = self._install_stt_modules(stt_module, pipeline_module)
        try:
            text = asyncio.run(
                assist_stt.transcribe_wav_with_assist(
                    types.SimpleNamespace(data={}),
                    b"RIFFxxxxWAVEdata",
                    {"stt_engine": "openai"},
                )
            )
        finally:
            self._restore_modules(originals)

        self.assertEqual(text, "Speel via OpenAI")
        self.assertEqual(calls, ["openai"])

    def test_transcribe_wav_uses_real_ha_stt_engine_provider_pattern(self) -> None:
        assist_stt = importlib.import_module("custom_components.djconnect.assist_stt")
        stt_module = types.ModuleType("homeassistant.components.stt")
        pipeline_module = types.ModuleType(
            "homeassistant.components.assist_pipeline.pipeline"
        )
        calls = []

        class SpeechMetadata:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class AudioFormats:
            WAV = "wav"

        class AudioCodecs:
            PCM = "pcm"

        class Provider:
            def check_metadata(self, metadata):
                return metadata.kwargs["format"] == "wav"

            async def internal_async_process_audio_stream(self, metadata, stream):
                chunks = []
                async for chunk in stream:
                    chunks.append(chunk)
                calls.append((metadata.kwargs["language"], b"".join(chunks)))
                return types.SimpleNamespace(text="Real HA provider text")

        stt_module.SpeechMetadata = SpeechMetadata
        stt_module.AudioFormats = AudioFormats
        stt_module.AudioCodecs = AudioCodecs
        stt_module.async_get_speech_to_text_engine = (
            lambda hass, engine: Provider() if engine == "stt.openai_stt" else None
        )
        pipeline_module.async_get_pipelines = lambda hass: []
        originals = self._install_stt_modules(stt_module, pipeline_module)
        try:
            text = asyncio.run(
                assist_stt.transcribe_wav_with_assist(
                    types.SimpleNamespace(data={}),
                    b"RIFFxxxxWAVEdata",
                    {"stt_engine": "stt.openai_stt"},
                )
            )
        finally:
            self._restore_modules(originals)

        self.assertEqual(text, "Real HA provider text")
        self.assertEqual(calls, [("nl-NL", b"RIFFxxxxWAVEdata")])

    def test_transcribe_wav_falls_back_to_first_stt_entity(self) -> None:
        assist_stt = importlib.import_module("custom_components.djconnect.assist_stt")
        stt_module = types.ModuleType("homeassistant.components.stt")
        pipeline_module = types.ModuleType(
            "homeassistant.components.assist_pipeline.pipeline"
        )
        calls = []

        class SpeechMetadata:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class AudioFormats:
            WAV = "wav"

        class AudioCodecs:
            PCM = "pcm"

        class States:
            def async_entity_ids(self, domain):
                self.domain = domain
                return ["stt.openai_stt"]

        async def async_process_audio_stream(hass, metadata, stream, engine=None):
            calls.append(engine)
            async for _chunk in stream:
                pass
            return {"text": "OpenAI entity fallback"}

        stt_module.SpeechMetadata = SpeechMetadata
        stt_module.AudioFormats = AudioFormats
        stt_module.AudioCodecs = AudioCodecs
        stt_module.async_process_audio_stream = async_process_audio_stream
        pipeline_module.async_get_pipelines = lambda hass: []
        originals = self._install_stt_modules(stt_module, pipeline_module)
        try:
            text = asyncio.run(
                assist_stt.transcribe_wav_with_assist(
                    types.SimpleNamespace(data={}, states=States()),
                    b"RIFFxxxxWAVEdata",
                    {},
                )
            )
        finally:
            self._restore_modules(originals)

        self.assertEqual(text, "OpenAI entity fallback")
        self.assertEqual(calls, ["stt.openai_stt"])

    def test_transcribe_wav_uses_assist_pipeline_helper_when_no_engine_resolved(self) -> None:
        assist_stt = importlib.import_module("custom_components.djconnect.assist_stt")
        stt_module = types.ModuleType("homeassistant.components.stt")
        assist_pkg = types.ModuleType("homeassistant.components.assist_pipeline")
        pipeline_module = types.ModuleType(
            "homeassistant.components.assist_pipeline.pipeline"
        )
        calls = []

        class SpeechMetadata:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class AudioFormats:
            WAV = "wav"

        class AudioCodecs:
            PCM = "pcm"

        class PipelineStage:
            STT = "stt"

        async def async_pipeline_from_audio_stream(*args, **kwargs):
            calls.append({"args": args, **kwargs})
            chunks = []
            async for chunk in kwargs["stt_stream"]:
                chunks.append(chunk)
            await kwargs["event_callback"](
                {"type": "stt-end", "data": {"stt_output": {"text": "Pipeline text"}}}
            )

        stt_module.SpeechMetadata = SpeechMetadata
        stt_module.AudioFormats = AudioFormats
        stt_module.AudioCodecs = AudioCodecs
        assist_pkg.async_pipeline_from_audio_stream = async_pipeline_from_audio_stream
        pipeline_module.PipelineStage = PipelineStage
        pipeline_module.async_get_pipelines = lambda hass: []

        originals = self._install_stt_modules(stt_module, pipeline_module)
        original_assist = sys.modules.get("homeassistant.components.assist_pipeline")
        sys.modules["homeassistant.components.assist_pipeline"] = assist_pkg
        try:
            text = asyncio.run(
                assist_stt.transcribe_wav_with_assist(
                    types.SimpleNamespace(data={}),
                    b"RIFFxxxxWAVEdata",
                    {},
                )
            )
        finally:
            if original_assist is None:
                sys.modules.pop("homeassistant.components.assist_pipeline", None)
            else:
                sys.modules["homeassistant.components.assist_pipeline"] = original_assist
            self._restore_modules(originals)

        self.assertEqual(text, "Pipeline text")
        self.assertEqual(calls[0]["start_stage"], "stt")
        self.assertEqual(calls[0]["end_stage"], "stt")

    def test_stt_diagnostic_helpers_do_not_log_text(self) -> None:
        assist_stt = importlib.import_module("custom_components.djconnect.assist_stt")

        events = [
            {"type": "stt-start", "data": {}},
            {"type": "stt-end", "data": {"stt_output": {"text": "secret words"}}},
        ]
        result = types.SimpleNamespace(state="success", text="secret words")

        self.assertEqual(assist_stt._event_types(events), ["stt-start", "stt-end"])
        self.assertEqual(assist_stt._result_state(result), "success")
        self.assertNotIn("secret words", repr(assist_stt._event_types(events)))
        self.assertNotIn("secret words", str(assist_stt._result_state(result)))

    def test_stt_metadata_uses_bits_per_sample_not_stream_bitrate(self) -> None:
        assist_stt = importlib.import_module("custom_components.djconnect.assist_stt")

        class SpeechMetadata:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        stt_module = types.SimpleNamespace(
            SpeechMetadata=SpeechMetadata,
            AudioFormats=types.SimpleNamespace(WAV="wav"),
            AudioCodecs=types.SimpleNamespace(PCM="pcm"),
        )
        info = assist_stt.SttInfo(
            ha_version="test",
            pipeline_id=None,
            pipeline_name=None,
            engine="stt.google_ai_stt",
            language="nl-NL",
            audio_format="wav",
            sample_rate=16000,
            channels=1,
            sample_width=2,
            byte_length=6700,
        )

        metadata = assist_stt._speech_metadata(stt_module, info)

        self.assertEqual(metadata.kwargs["bit_rate"], 16)
        self.assertNotEqual(metadata.kwargs["bit_rate"], 256000)

    def test_transcribe_wav_finds_default_cloud_stt_pipeline(self) -> None:
        assist_stt = importlib.import_module("custom_components.djconnect.assist_stt")
        stt_module = types.ModuleType("homeassistant.components.stt")
        pipeline_module = types.ModuleType(
            "homeassistant.components.assist_pipeline.pipeline"
        )
        calls = []

        class SpeechMetadata:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class AudioFormats:
            WAV = "wav"

        class AudioCodecs:
            PCM = "pcm"

        async def async_process_audio_stream(hass, metadata, stream, engine=None):
            calls.append(
                {
                    "engine": engine,
                    "language": metadata.kwargs["language"],
                    "audio": b"".join([chunk async for chunk in stream]),
                }
            )
            return {"text": "Speel Eefje de Visser"}

        stt_module.SpeechMetadata = SpeechMetadata
        stt_module.AudioFormats = AudioFormats
        stt_module.AudioCodecs = AudioCodecs
        stt_module.async_process_audio_stream = async_process_audio_stream
        pipeline_module.async_get_pipelines = lambda hass: [
            types.SimpleNamespace(
                id="default",
                name="Home Assistant Cloud",
                stt_engine="cloud",
                stt_language="nl-NL",
            )
        ]

        originals = self._install_stt_modules(stt_module, pipeline_module)
        try:
            text = asyncio.run(
                assist_stt.transcribe_wav_with_assist(
                    types.SimpleNamespace(data={}),
                    b"RIFFxxxxWAVEdata",
                    {},
                )
            )
        finally:
            self._restore_modules(originals)

        self.assertEqual(text, "Speel Eefje de Visser")
        self.assertEqual(calls[0]["engine"], "cloud")
        self.assertEqual(calls[0]["language"], "nl-NL")
        self.assertEqual(calls[0]["audio"], b"RIFFxxxxWAVEdata")

    def test_transcribe_wav_missing_stored_pipeline_falls_back_to_default(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")
        assist_stt = importlib.import_module("custom_components.djconnect.assist_stt")
        stt_module = types.ModuleType("homeassistant.components.stt")
        pipeline_module = types.ModuleType(
            "homeassistant.components.assist_pipeline.pipeline"
        )

        class SpeechMetadata:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class AudioFormats:
            WAV = "wav"

        class AudioCodecs:
            PCM = "pcm"

        async def async_process_audio_stream(hass, metadata, stream, engine=None):
            return types.SimpleNamespace(text=f"engine={engine}")

        class Pipelines:
            def __init__(self):
                self.default = types.SimpleNamespace(
                    id="default",
                    name="Default Assist",
                    stt_engine="cloud",
                    stt_language="nl-NL",
                )

            def async_get_pipeline(self, pipeline_id):
                return None

            def async_get_preferred_pipeline(self):
                return self.default

        stt_module.SpeechMetadata = SpeechMetadata
        stt_module.AudioFormats = AudioFormats
        stt_module.AudioCodecs = AudioCodecs
        stt_module.async_process_audio_stream = async_process_audio_stream
        pipeline_module.async_get_pipelines = lambda hass: Pipelines()

        originals = self._install_stt_modules(stt_module, pipeline_module)
        try:
            text = asyncio.run(
                assist_stt.transcribe_wav_with_assist(
                    types.SimpleNamespace(data={}),
                    b"RIFFxxxxWAVEdata",
                    {const.CONF_ASSIST_PIPELINE_ID: "deleted-pipeline"},
                )
            )
        finally:
            self._restore_modules(originals)

        self.assertEqual(text, "engine=cloud")

    def test_transcribe_wav_pipeline_without_stt_returns_no_provider(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")
        assist_stt = importlib.import_module("custom_components.djconnect.assist_stt")
        stt_module = types.ModuleType("homeassistant.components.stt")
        pipeline_module = types.ModuleType(
            "homeassistant.components.assist_pipeline.pipeline"
        )

        class Pipelines:
            def async_get_pipeline(self, pipeline_id):
                return types.SimpleNamespace(id=pipeline_id, name="No STT")

        stt_module.async_process_audio_stream = object()
        pipeline_module.async_get_pipelines = lambda hass: Pipelines()
        originals = self._install_stt_modules(stt_module, pipeline_module)
        try:
            with self.assertRaises(assist_stt.DJConnectNoSttProviderError) as raised:
                asyncio.run(
                    assist_stt.transcribe_wav_with_assist(
                        types.SimpleNamespace(data={}),
                        b"RIFFxxxxWAVEdata",
                        {const.CONF_ASSIST_PIPELINE_ID: "no-stt"},
                    )
                )
        finally:
            self._restore_modules(originals)

        self.assertIn(assist_stt.NO_STT_PROVIDER, str(raised.exception))
        self.assertIn("stt_engine", str(raised.exception))

    def test_transcribe_wav_no_stt_provider_error(self) -> None:
        assist_stt = importlib.import_module("custom_components.djconnect.assist_stt")
        originals = {
            name: sys.modules.get(name)
            for name in (
                "homeassistant.components.stt",
                "homeassistant.components.assist_pipeline.pipeline",
            )
        }
        sys.modules.pop("homeassistant.components.stt", None)
        sys.modules.pop("homeassistant.components.assist_pipeline.pipeline", None)

        try:
            with self.assertRaises(assist_stt.DJConnectNoSttProviderError) as raised:
                asyncio.run(
                    assist_stt.transcribe_wav_with_assist(
                        types.SimpleNamespace(data={}),
                        b"RIFFxxxxWAVEdata",
                        {},
                    )
                )
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

        self.assertIn(assist_stt.NO_STT_PROVIDER, str(raised.exception))
        self.assertIn("stt_engine", str(raised.exception))

    def _install_stt_modules(self, stt_module, pipeline_module):
        assist_pkg = types.ModuleType("homeassistant.components.assist_pipeline")
        originals = {
            name: sys.modules.get(name)
            for name in (
                "homeassistant.components.stt",
                "homeassistant.components.assist_pipeline",
                "homeassistant.components.assist_pipeline.pipeline",
            )
        }
        sys.modules["homeassistant.components.stt"] = stt_module
        sys.modules["homeassistant.components.assist_pipeline"] = assist_pkg
        sys.modules[
            "homeassistant.components.assist_pipeline.pipeline"
        ] = pipeline_module
        return originals

    def _restore_modules(self, originals):
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    def test_pair_view_rejects_wrong_pair_code(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            config = {const.CONF_PAIR_CODE: "123456"}

            def update(self, **kwargs):
                self.last_update = kwargs

        class Request:
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": Runtime()}})}

            async def json(self):
                return {"device_id": "djconnect-device", "pair_code": "654321"}

        response = asyncio.run(self.http.DJConnectPairView(None).post(Request()))

        self.assertEqual(response["status_code"], 401)
        self.assertEqual(response["payload"]["error"], "invalid_pair_code")
        self.assertIn("does not match", response["payload"]["message"])

    def test_pair_view_does_not_include_spotify_oauth_secrets(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            config = {
                const.CONF_PAIR_CODE: "123456",
                const.CONF_HA_EXTERNAL_URL: "https://example.ui.nabu.casa",
            }
            device_status = {}

            def ensure_device_token(self):
                self.device_token = "device-token"
                return self.device_token


            def spotify_payload(self):
                return {
                    "client_id": "client-id",
                    "refresh_token": "refresh-token",
                    "spotify_client_id": "client-id",
                    "spotify_refresh_token": "refresh-token",
                    "market": "NL",
                    "scopes": ["scope-a"],
                }

            def device_language(self):
                return "nl"

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()

        class Request:
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})}

            async def json(self):
                return {
                    "device_id": "djconnect-device",
                    "pair_code": "123456",
                    "local_url": "http://djconnect.local",
                }

        response = asyncio.run(self.http.DJConnectPairView(None).post(Request()))

        self.assertEqual(response["status_code"], 200)
        self.assertEqual(
            response["payload"]["ha_local_url"],
            "https://example.ui.nabu.casa",
        )
        self.assertEqual(
            response["payload"]["ha_remote_url"],
            "https://example.ui.nabu.casa",
        )
        self.assertNotIn("ha_url", response["payload"])
        self.assertNotIn("spotify", response["payload"])
        self.assertNotIn("refresh_token", response["payload"])
        self.assertNotIn("spotify_refresh_token", response["payload"])
        self.assertNotIn("client_id", response["payload"])
        self.assertNotIn("spotify_client_id", response["payload"])
        self.assertEqual(response["payload"]["device_language"], "nl")
        self.assertEqual(response["payload"]["language"], "nl")
        self.assertEqual(runtime.device_status["ha_pairing_status"], "pending")
        self.assertNotEqual(runtime.device_status.get("ha_pairing_status"), "paired")

    def test_status_view_reprovisions_when_spotify_configured_false(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            device_token = "device-token"
            device_status = {}
            ota_in_progress = False
            ota_last_error = None
            config = {
                const.CONF_ASSIST_PIPELINE_ID: "pipeline",
                const.CONF_HA_EXTERNAL_URL: "https://ha.example",
            }

            def authorize_device_request(self, headers, body_device_id=None):
                return True


            def spotify_payload(self):
                return {
                    "client_id": "client-id",
                    "refresh_token": "refresh-token",
                    "spotify_client_id": "client-id",
                    "spotify_refresh_token": "refresh-token",
                }

            def device_language(self):
                return "en"

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()

        class Request:
            headers = {"Authorization": "Bearer device-token"}
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})}

            async def json(self):
                return {
                    "device_id": "djconnect-device",
                    "spotify_configured": False,
                }

        response = asyncio.run(self.http.DJConnectStatusView(None).post(Request()))

        self.assertEqual(response["status_code"], 200)
        self.assertEqual(response["payload"]["ha_local_url"], "https://ha.example")
        self.assertEqual(response["payload"]["ha_remote_url"], "https://ha.example")
        self.assertNotIn("ha_url", response["payload"])
        self.assertTrue(response["payload"]["backend_available"])
        self.assertNotIn("refresh_token", response["payload"])
        self.assertNotIn("spotify_refresh_token", response["payload"])
        self.assertNotIn("spotify", response["payload"])

    def test_status_view_persists_reported_device_identity_and_local_url(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")
        entry = types.SimpleNamespace(data={const.CONF_PAIR_CODE: "981032"})

        class ConfigEntries:
            def __init__(self):
                self.updates = []

            def async_update_entry(self, entry, *, data):
                self.updates.append(data)
                entry.data = data

        config_entries = ConfigEntries()

        class Runtime:
            device_token = "device-token"
            device_status = {}
            ota_in_progress = False
            ota_last_error = None
            config = {}

            def authorize_device_request(self, headers, body_device_id=None):
                return True


            def spotify_payload(self):
                return {}

            def device_language(self):
                return "en"

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()
        runtime.entry = entry

        class Request:
            headers = {"Authorization": "Bearer device-token"}
            app = {
                "hass": types.SimpleNamespace(
                    data={const.DOMAIN: {"runtime": runtime}},
                    config_entries=config_entries,
                )
            }

            async def json(self):
                return {
                    "device_id": "djconnect-lilygo-90B70990A994",
                    "local_url": "http://djconnect-lilygo-90B70990A994.local",
                    "spotify_configured": True,
                }

        response = asyncio.run(self.http.DJConnectStatusView(None).post(Request()))

        self.assertEqual(response["status_code"], 200)
        self.assertEqual(
            config_entries.updates[0][const.CONF_DEVICE_ID],
            "djconnect-lilygo-90B70990A994",
        )
        self.assertEqual(config_entries.updates[0][const.CONF_DEVICE_TOKEN], "device-token")
        self.assertEqual(
            config_entries.updates[0][const.CONF_LOCAL_URL],
            "http://djconnect-lilygo-90B70990A994.local",
        )

    def test_status_view_accepts_lilygo_device_id_and_flattens_device_settings(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            device_token = "device-token"
            device_status = {"device_id": "djconnect-981032"}
            ota_in_progress = True
            ota_last_error = None
            config = {}
            pairing_device_id = "djconnect-981032"

            def authorize_device_request(self, headers, body_device_id=None):
                return headers.get("Authorization") == "Bearer device-token"

            def get_current_spotify_credentials(self):
                return {}

            def device_language(self):
                return "nl"

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()

        class Request:
            headers = {
                "Authorization": "Bearer device-token",
                "X-DJConnect-Device-ID": "djconnect-lilygo-90B70990A994",
            }
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})}

            async def json(self):
                return {
                    "device_id": "djconnect-lilygo-90B70990A994",
                    "update_state": "idle",
                    "firmware": "3.0.5",
                    "settings": {
                        "screen_brightness_percent": 91,
                        "screen_off_timeout_ms": 60000,
                        "turn_off_after_ms": 300000,
                        "speaker_volume_percent": 45,
                        "language": "nl",
                        "theme": "dark",
                        "log_level": "info",
                    },
                    "screen": {"state": "on", "brightness_level": 88},
                    "led": {"state": "off"},
                }

        response = asyncio.run(self.http.DJConnectStatusView(None).post(Request()))

        self.assertEqual(response["status_code"], 200)
        self.assertFalse(runtime.ota_in_progress)
        self.assertEqual(runtime.device_status["device_id"], "djconnect-lilygo-90B70990A994")
        self.assertEqual(runtime.device_status["screen_brightness"], 91)
        self.assertEqual(runtime.device_status["screen_timeout_ms"], 60000)
        self.assertEqual(runtime.device_status["turn_off_after_ms"], 300000)
        self.assertEqual(runtime.device_status["speaker_volume"], 45)
        self.assertEqual(runtime.device_status["screen_state"], "on")
        self.assertEqual(runtime.device_status["screen_brightness_level"], 88)
        self.assertEqual(runtime.device_status["led_state"], "off")
        self.assertNotIn("device_token", response["payload"])

    def test_status_view_accepts_same_major_minor_firmware(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            device_token = "device-token"
            device_status = {}
            ota_in_progress = False
            ota_last_error = None
            config = {}

            def authorize_device_request(self, headers, body_device_id=None):
                return True

            def get_current_spotify_credentials(self):
                return {}

            def device_language(self):
                return "nl"

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()

        class Request:
            headers = {"Authorization": "Bearer device-token"}
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})}

            async def json(self):
                return {
                    "device_id": "djconnect-lilygo-90B70990A994",
                    "firmware": "v3.0.99",
                }

        response = asyncio.run(self.http.DJConnectStatusView(None).post(Request()))

        self.assertEqual(response["status_code"], 200)
        self.assertEqual(runtime.device_status["firmware"], "v3.0.99")

    def test_status_view_rejects_different_major_minor_firmware(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            device_token = "device-token"
            device_status = {}
            ota_in_progress = False
            ota_last_error = None
            config = {}

            def authorize_device_request(self, headers, body_device_id=None):
                return True

            def get_current_spotify_credentials(self):
                return {}

            def device_language(self):
                return "nl"

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()

        class Request:
            headers = {"Authorization": "Bearer device-token"}
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})}

            async def json(self):
                return {
                    "device_id": "djconnect-lilygo-90B70990A994",
                    "firmware": "3.1.0",
                }

        response = asyncio.run(self.http.DJConnectStatusView(None).post(Request()))

        self.assertEqual(response["status_code"], 426)
        self.assertEqual(response["payload"]["error"], "version_mismatch")
        self.assertEqual(response["payload"]["ha_major_minor"], "3.0")
        self.assertEqual(response["payload"]["firmware_major_minor"], "3.1")

    def test_command_view_rejects_known_different_major_minor_firmware(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            device_token = "device-token"
            device_status = {
                "device_id": "djconnect-lilygo-90B70990A994",
                "firmware": "4.0.0",
            }
            config = {}

            def authorize_device_request(self, headers, body_device_id=None):
                return True

        runtime = Runtime()

        class Request:
            headers = {
                "Authorization": "Bearer device-token",
                "X-DJConnect-Device-ID": "djconnect-lilygo-90B70990A994",
            }
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})}

            async def json(self):
                return {
                    "device_id": "djconnect-lilygo-90B70990A994",
                    "command": "status",
                }

        response = asyncio.run(self.http.DJConnectCommandView(None).post(Request()))

        self.assertEqual(response["status_code"], 426)
        self.assertEqual(response["payload"]["error"], "version_mismatch")
        self.assertEqual(response["payload"]["firmware"], "4.0.0")

    def test_status_view_prefers_current_spotify_credentials(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            device_token = "device-token"
            device_status = {}
            ota_in_progress = False
            ota_last_error = None
            config = {}

            def authorize_device_request(self, headers, body_device_id=None):
                return True


            def spotify_payload(self):
                return {
                    "client_id": "client-id",
                    "refresh_token": "stale-token",
                    "spotify_refresh_token": "stale-token",
                }

            def get_current_spotify_credentials(self):
                return {
                    "client_id": "client-id",
                    "refresh_token": "rotated-token",
                    "spotify_client_id": "client-id",
                    "spotify_refresh_token": "rotated-token",
                }

            def device_language(self):
                return "en"

            def update(self, **kwargs):
                self.last_update = kwargs

        class Request:
            headers = {"Authorization": "Bearer device-token"}
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": Runtime()}})}

            async def json(self):
                return {
                    "device_id": "djconnect-device",
                    "spotify_configured": False,
                }

        response = asyncio.run(self.http.DJConnectStatusView(None).post(Request()))

        self.assertEqual(response["status_code"], 200)
        self.assertTrue(response["payload"]["backend_available"])
        self.assertNotIn("refresh_token", response["payload"])
        self.assertNotIn("spotify_refresh_token", response["payload"])

    def test_status_view_reprovision_log_does_not_include_token(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            device_token = "device-token"
            device_status = {}
            ota_in_progress = False
            ota_last_error = None
            config = {}

            def authorize_device_request(self, headers, body_device_id=None):
                return True


            def get_current_spotify_credentials(self):
                return {
                    "client_id": "client-id",
                    "refresh_token": "secret-refresh-token",
                    "spotify_client_id": "client-id",
                    "spotify_refresh_token": "secret-refresh-token",
                }

            def device_language(self):
                return "en"

            def update(self, **kwargs):
                self.last_update = kwargs

        class Request:
            headers = {"Authorization": "Bearer device-token"}
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": Runtime()}})}

            async def json(self):
                return {
                    "device_id": "djconnect-device",
                    "spotify_configured": False,
                }

        with self.assertLogs(self.http._LOGGER, level="DEBUG") as captured:
            response = asyncio.run(self.http.DJConnectStatusView(None).post(Request()))

        log_output = "\n".join(captured.output)
        self.assertEqual(response["status_code"], 200)
        self.assertIn("spotify_configured=False", log_output)
        self.assertIn("backend_available=True", log_output)
        self.assertNotIn("secret-refresh-token", log_output)

    def test_status_view_omits_spotify_when_configured_true(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            device_token = "device-token"
            device_status = {}
            ota_in_progress = False
            ota_last_error = None
            config = {}

            def authorize_device_request(self, headers, body_device_id=None):
                return True


            def spotify_payload(self):
                return {
                    "client_id": "client-id",
                    "refresh_token": "refresh-token",
                    "spotify_client_id": "client-id",
                    "spotify_refresh_token": "refresh-token",
                }

            def device_language(self):
                return "en"

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()

        class Request:
            headers = {"Authorization": "Bearer device-token"}
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})}

            async def json(self):
                return {
                    "device_id": "djconnect-device",
                    "spotify_configured": True,
                }

        response = asyncio.run(self.http.DJConnectStatusView(None).post(Request()))

        self.assertEqual(response["status_code"], 200)
        self.assertNotIn("spotify", response["payload"])
        self.assertNotIn("spotify_refresh_token", response["payload"])

    def test_status_view_handles_missing_spotify_config_without_empty_tokens(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            device_token = "device-token"
            device_status = {}
            ota_in_progress = False
            ota_last_error = None
            config = {}

            def authorize_device_request(self, headers, body_device_id=None):
                return True


            def spotify_payload(self):
                return {}

            def device_language(self):
                return "en"

            def update(self, **kwargs):
                self.last_update = kwargs

        class Request:
            headers = {"Authorization": "Bearer device-token"}
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": Runtime()}})}

            async def json(self):
                return {
                    "device_id": "djconnect-device",
                    "spotify_configured": False,
                }

        response = asyncio.run(self.http.DJConnectStatusView(None).post(Request()))

        self.assertEqual(response["status_code"], 200)
        self.assertNotIn("spotify", response["payload"])
        self.assertNotIn("spotify_refresh_token", response["payload"])

    def test_command_view_dispatches_backend_command(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")
        calls = []

        class Runtime:
            device_token = "device-token"
            device_status = {"device_id": "djconnect-lilygo-90B70990A994"}
            config = {}

            def authorize_device_request(self, headers, body_device_id=None):
                return headers.get("Authorization") == "Bearer device-token"

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()

        async def command_handler(hass, runtime, command, value=None, *, play=None):
            calls.append((command, value, play))
            return {"success": True, "devices": [{"name": "iPhone"}]}

        class Request:
            headers = {
                "Authorization": "Bearer device-token",
                "X-DJConnect-Device-ID": "djconnect-lilygo-90B70990A994",
            }
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})}

            async def json(self):
                return {
                    "device_id": "djconnect-lilygo-90B70990A994",
                    "command": "devices",
                    "value": "",
                    "play": False,
                }

        original = self.http.handle_spotify_command
        self.http.handle_spotify_command = command_handler
        try:
            response = asyncio.run(self.http.DJConnectCommandView(None).post(Request()))
        finally:
            self.http.handle_spotify_command = original

        self.assertEqual(response["status_code"], 200)
        self.assertTrue(response["payload"]["success"])
        self.assertEqual(response["payload"]["devices"][0]["name"], "iPhone")
        self.assertEqual(calls, [("devices", "", False)])

    def test_command_view_returns_backend_unavailable_json(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            device_token = "device-token"
            device_status = {}
            config = {}

            def authorize_device_request(self, headers, body_device_id=None):
                return True

            def update(self, **kwargs):
                self.last_update = kwargs

        async def command_handler(hass, runtime, command, value=None, *, play=None):
            raise self.http.SpotifyBackendError("Spotify OAuth is not configured")

        class Request:
            headers = {"Authorization": "Bearer device-token"}
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": Runtime()}})}

            async def json(self):
                return {"device_id": "djconnect-lilygo-90B70990A994", "command": "status"}

        original = self.http.handle_spotify_command
        self.http.handle_spotify_command = command_handler
        try:
            response = asyncio.run(self.http.DJConnectCommandView(None).post(Request()))
        finally:
            self.http.handle_spotify_command = original

        self.assertEqual(response["status_code"], 200)
        self.assertFalse(response["payload"]["success"])
        self.assertEqual(response["payload"]["error"], "backend_unavailable")
        self.assertFalse(response["payload"]["backend_available"])
        self.assertIn("Spotify OAuth", response["payload"]["message"])

    def test_command_view_returns_200_for_generic_backend_failure(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            device_token = "device-token"
            device_status = {}
            last_playback = {"has_playback": False}
            config = {}

            def authorize_device_request(self, headers, body_device_id=None):
                return True

            def update(self, **kwargs):
                self.last_update = kwargs

        async def command_handler(hass, runtime, command, value=None, *, play=None):
            raise RuntimeError("Temporary backend timeout")

        class Request:
            headers = {"Authorization": "Bearer device-token"}
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": Runtime()}})}

            async def json(self):
                return {"device_id": "djconnect-lilygo-90B70990A994", "command": "status"}

        original = self.http.handle_spotify_command
        self.http.handle_spotify_command = command_handler
        try:
            response = asyncio.run(self.http.DJConnectCommandView(None).post(Request()))
        finally:
            self.http.handle_spotify_command = original

        self.assertEqual(response["status_code"], 200)
        self.assertFalse(response["payload"]["success"])
        self.assertEqual(response["payload"]["error"], "backend_unavailable")
        self.assertFalse(response["payload"]["backend_available"])
        self.assertEqual(response["payload"]["playback"], {"has_playback": False})

    def test_command_view_does_not_repair_device_during_normal_command(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class Runtime:
            device_token = "device-token"
            device_status = {"ha_pairing_status": "paired"}
            config = {}
            pair_called = False

            def authorize_device_request(self, headers, body_device_id=None):
                return True

            async def pair_device(self, hass):
                self.pair_called = True

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()

        async def command_handler(hass, runtime, command, value=None, *, play=None):
            return {"success": True, "playback": {"has_playback": True}}

        class Request:
            headers = {"Authorization": "Bearer device-token"}
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})}

            async def json(self):
                return {"device_id": "djconnect-lilygo-90B70990A994", "command": "next"}

        original = self.http.handle_spotify_command
        self.http.handle_spotify_command = command_handler
        try:
            response = asyncio.run(self.http.DJConnectCommandView(None).post(Request()))
        finally:
            self.http.handle_spotify_command = original

        self.assertEqual(response["status_code"], 200)
        self.assertTrue(response["payload"]["success"])
        self.assertFalse(runtime.pair_called)

    def test_store_rotated_spotify_refresh_token_persists_without_logging_secret(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")
        updates = []

        class ConfigEntries:
            def async_update_entry(self, entry, *, data):
                updates.append(data)
                entry.data = data

        class Runtime:
            latest_spotify_refresh_token = "old-token"

            def update_spotify_refresh_token(self, token):
                self.latest_spotify_refresh_token = token
                return True

        entry = types.SimpleNamespace(
            data={const.CONF_SPOTIFY_REFRESH_TOKEN: "old-token"}
        )
        hass = types.SimpleNamespace(config_entries=ConfigEntries())

        with self.assertLogs(self.http._LOGGER, level="DEBUG") as captured:
            changed = self.http._store_rotated_spotify_refresh_token(
                hass,
                entry,
                Runtime(),
                "new-secret-token",
            )

        self.assertTrue(changed)
        self.assertEqual(updates[0][const.CONF_SPOTIFY_REFRESH_TOKEN], "new-secret-token")
        self.assertIn("refresh_token=rotated", "\n".join(captured.output))
        self.assertNotIn("new-secret-token", "\n".join(captured.output))

    def test_spotify_callback_succeeds_when_options_flow_is_closed(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")

        class ConfigFlow:
            async def async_configure(self, flow_id, user_input):
                raise RuntimeError()

        class ConfigEntries:
            flow = ConfigFlow()

            def __init__(self, entry):
                self.entry = entry
                self.updated = None
                self.reloaded = None

            def async_get_entry(self, entry_id):
                return self.entry

            def async_update_entry(self, entry, *, data):
                self.updated = data
                entry.data = data

            async def async_reload(self, entry_id):
                self.reloaded = entry_id

        class Query:
            def get(self, key):
                return {"state": "state-1", "code": "code-1"}.get(key)

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                const.CONF_SPOTIFY_CLIENT_ID: "client-id",
                const.CONF_HA_EXTERNAL_URL: "https://example.ui.nabu.casa",
            },
            options={},
        )
        config_entries = ConfigEntries(entry)
        hass = types.SimpleNamespace(
            data={
                const.DOMAIN: {
                    "spotify_oauth_pending": {
                        "state-1": {
                            "flow_id": "closed-flow",
                            "entry_id": "entry-1",
                            "client_id": "client-id",
                            "code_verifier": "verifier",
                            "redirect_uri": "https://example.ui.nabu.casa/api/djconnect/spotify/callback",
                            "market": "NL",
                            "scopes": "scope",
                        }
                    }
                }
            },
            config_entries=config_entries,
        )
        request = types.SimpleNamespace(app={"hass": hass}, query=Query())

        async def exchange(*args, **kwargs):
            return {"refresh_token": "new-refresh-token"}

        original_exchange = self.http.exchange_code_for_refresh_token
        self.http.exchange_code_for_refresh_token = exchange
        try:
            response = asyncio.run(self.http.DJConnectSpotifyCallbackView(None).get(request))
        finally:
            self.http.exchange_code_for_refresh_token = original_exchange

        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "text/html")
        self.assertIn("DJConnect is opnieuw geautoriseerd", response.text)
        self.assertIn("De refresh token is opgeslagen in Home Assistant", response.text)
        self.assertIn(
            "https://example.ui.nabu.casa/config/integrations/integration/djconnect",
            response.text,
        )
        self.assertIn("data:image/png;base64,", response.text)
        self.assertEqual(entry.data[const.CONF_SPOTIFY_REFRESH_TOKEN], "new-refresh-token")
        self.assertEqual(config_entries.reloaded, "entry-1")

    def test_tts_view_returns_audio_for_valid_token(self) -> None:
        const = importlib.import_module("custom_components.djconnect.const")
        dj_response = importlib.import_module("custom_components.djconnect.dj_response")
        hass = types.SimpleNamespace(data={})
        token = dj_response.store_tts_audio(
            hass,
            b"ID3 mp3 data",
            120,
            content_type="audio/mpeg",
            extension="mp3",
        )
        request = types.SimpleNamespace(app={"hass": hass})

        response = asyncio.run(
            self.http.DJConnectTtsView(None).get(request, token, "mp3")
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "audio/mpeg")
        self.assertEqual(response.body, b"ID3 mp3 data")
        self.assertEqual(response.headers["Content-Length"], "12")
        self.assertIn("tts_audio", hass.data[const.DOMAIN])

    def test_tts_view_returns_410_for_expired_token(self) -> None:
        dj_response = importlib.import_module("custom_components.djconnect.dj_response")
        hass = types.SimpleNamespace(data={})
        token = dj_response.store_tts_audio(hass, b"RIFFxxxxWAVEdata", 120)
        dj_response._store(hass)[token].expires_at = 0
        request = types.SimpleNamespace(app={"hass": hass})

        response = asyncio.run(self.http.DJConnectTtsView(None).get(request, token))

        self.assertEqual(response.status, 410)

    def test_tts_view_returns_404_for_unknown_token(self) -> None:
        request = types.SimpleNamespace(app={"hass": types.SimpleNamespace(data={})})

        response = asyncio.run(self.http.DJConnectTtsView(None).get(request, "unknown"))

        self.assertEqual(response.status, 404)


if __name__ == "__main__":
    unittest.main()
