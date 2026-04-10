import json
import pytest
from unittest.mock import patch, MagicMock
from temporalio.testing import ActivityEnvironment

from src.activities.emotion_detection import detect_emotion_activity
from src.activities.scenario_generation import generate_scenario_activity


@pytest.fixture
def activity_env():
    return ActivityEnvironment()


class TestDetectEmotionActivity:

    @pytest.mark.asyncio
    async def test_returns_valid_state(self, activity_env):
        bedrock_response = json.dumps({
            "estado": "ANSIOSO",
            "confianca": 0.91,
            "justificativa": "Usuário expressa medo de errar",
        })

        with patch("src.activities.emotion_detection.invoke_model", return_value=bedrock_response):
            result = await activity_env.run(
                detect_emotion_activity,
                "Quero refinanciar mas tenho medo de errar",
            )

        assert result["estado"] == "ANSIOSO"
        assert result["confianca"] == 0.91
        assert "justificativa" in result

    @pytest.mark.asyncio
    async def test_all_valid_states(self, activity_env):
        for estado in ["ANSIOSO", "CONFUSO", "CONFIANTE", "FRUSTRADO"]:
            payload = json.dumps({"estado": estado, "confianca": 0.8, "justificativa": "ok"})
            with patch("src.activities.emotion_detection.invoke_model", return_value=payload):
                result = await activity_env.run(
                    detect_emotion_activity, "qualquer mensagem"
                )
            assert result["estado"] == estado

    @pytest.mark.asyncio
    async def test_invalid_state_raises(self, activity_env):
        payload = json.dumps({"estado": "FELIZ", "confianca": 0.5, "justificativa": ""})
        with patch("src.activities.emotion_detection.invoke_model", return_value=payload):
            with pytest.raises(Exception):
                await activity_env.run(detect_emotion_activity, "mensagem")

    @pytest.mark.asyncio
    async def test_extracts_json_from_noisy_response(self, activity_env):
        noisy = 'Aqui está o resultado: {"estado": "CONFUSO", "confianca": 0.7, "justificativa": "perdido"}'
        with patch("src.activities.emotion_detection.invoke_model", return_value=noisy):
            result = await activity_env.run(detect_emotion_activity, "não entendo nada")
        assert result["estado"] == "CONFUSO"


class TestGenerateScenarioActivity:

    @pytest.mark.asyncio
    async def test_returns_scenario_string(self, activity_env):
        expected = "Cenário Conservador: ...\nCenário Otimizado: ..."

        with patch("src.activities.scenario_generation.invoke_model", return_value=expected):
            result = await activity_env.run(
                generate_scenario_activity,
                {"mensagem": "Quero refinanciar", "estado": "ANSIOSO", "contexto_anterior": ""},
            )

        assert result == expected

    @pytest.mark.asyncio
    async def test_passes_context_to_prompt(self, activity_env):
        captured_prompt = []

        def fake_invoke(prompt: str) -> str:
            captured_prompt.append(prompt)
            return "cenário gerado"

        with patch("src.activities.scenario_generation.invoke_model", side_effect=fake_invoke):
            await activity_env.run(
                generate_scenario_activity,
                {
                    "mensagem": "minha situação",
                    "estado": "FRUSTRADO",
                    "contexto_anterior": "Cenário anterior: X\nAvaliação: 2/5",
                },
            )

        prompt = captured_prompt[0]
        assert "FRUSTRADO" in prompt
        assert "Cenário anterior: X" in prompt
        assert "minha situação" in prompt
