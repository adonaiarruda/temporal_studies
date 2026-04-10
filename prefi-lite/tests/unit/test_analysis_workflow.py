import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.workflows.analysis_workflow import AnalysisWorkflow, AnalysisInput, AnalysisResult


FAKE_EMOCAO = {"estado": "ANSIOSO", "confianca": 0.88, "justificativa": "medo"}
FAKE_CENARIO = "Cenário Conservador: ...\nCenário Otimizado: ..."


@activity.defn(name="detect_emotion_activity")
async def fake_detect_emotion(mensagem: str) -> dict:
    return FAKE_EMOCAO


@activity.defn(name="generate_scenario_activity")
async def fake_generate_scenario(params: dict) -> str:
    return FAKE_CENARIO


@pytest.mark.asyncio
async def test_analysis_workflow_run():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[AnalysisWorkflow],
            activities=[fake_detect_emotion, fake_generate_scenario],
        ):
            result: AnalysisResult = await env.client.execute_workflow(
                AnalysisWorkflow.run,
                AnalysisInput(mensagem="Quero refinanciar mas tenho medo"),
                id="test-analysis-1",
                task_queue="test-queue",
            )

    assert result.estado_emocional == "ANSIOSO"
    assert result.confianca_emocao == 0.88
    assert result.cenario == FAKE_CENARIO
    assert result.mensagem == "Quero refinanciar mas tenho medo"
