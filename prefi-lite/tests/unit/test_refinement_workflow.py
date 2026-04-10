import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.workflows.refinement_workflow import RefinementWorkflow, RefinementInput, RefinementResult


FAKE_CENARIO_REFINADO = "Cenário Refinado: mais simples e direto"


@activity.defn(name="generate_scenario_activity")
async def fake_generate_scenario(params: dict) -> str:
    # Verifica que o contexto anterior foi passado
    assert "contexto_anterior" in params
    assert params["contexto_anterior"] != ""
    return FAKE_CENARIO_REFINADO


@pytest.mark.asyncio
async def test_refinement_workflow_run():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[RefinementWorkflow],
            activities=[fake_generate_scenario],
        ):
            result: RefinementResult = await env.client.execute_workflow(
                RefinementWorkflow.run,
                RefinementInput(
                    analysis_id="analysis-abc123",
                    mensagem_original="Quero refinanciar",
                    cenario_anterior="Cenário anterior gerado...",
                    estado_emocional="CONFUSO",
                    nota=2,
                    feedback="Muito técnico",
                ),
                id="test-refinement-1",
                task_queue="test-queue",
            )

    assert result.analysis_id == "analysis-abc123"
    assert result.cenario_refinado == FAKE_CENARIO_REFINADO


class CapturingActivity:
    def __init__(self):
        self.captured: list[dict] = []

    @activity.defn(name="generate_scenario_activity")
    async def generate_scenario_activity(self, params: dict) -> str:
        self.captured.append(params)
        return "cenário"


@pytest.mark.asyncio
async def test_refinement_builds_context_correctly():
    capturer = CapturingActivity()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-queue-2",
            workflows=[RefinementWorkflow],
            activities=[capturer.generate_scenario_activity],
        ):
            await env.client.execute_workflow(
                RefinementWorkflow.run,
                RefinementInput(
                    analysis_id="analysis-xyz",
                    mensagem_original="minha situação",
                    cenario_anterior="Cenário A",
                    estado_emocional="FRUSTRADO",
                    nota=1,
                    feedback="não ajudou",
                ),
                id="test-refinement-2",
                task_queue="test-queue-2",
            )

    params = capturer.captured[0]
    assert "Cenário A" in params["contexto_anterior"]
    assert "1/5" in params["contexto_anterior"]
    assert "não ajudou" in params["contexto_anterior"]
    assert params["estado"] == "FRUSTRADO"
    assert params["mensagem"] == "minha situação"
