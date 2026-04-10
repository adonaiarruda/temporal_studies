from dataclasses import dataclass
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy


@dataclass
class RefinementInput:
    analysis_id: str
    mensagem_original: str
    cenario_anterior: str
    estado_emocional: str
    nota: int
    feedback: str


@dataclass
class RefinementResult:
    analysis_id: str
    cenario_refinado: str


@workflow.defn
class RefinementWorkflow:

    @workflow.run
    async def run(self, input: RefinementInput) -> RefinementResult:
        retry = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_attempts=3,
        )

        contexto = (
            f"Cenário anterior gerado:\n{input.cenario_anterior}\n\n"
            f"Avaliação do usuário: {input.nota}/5\n"
            f"Feedback: {input.feedback}"
        )

        cenario_refinado: str = await workflow.execute_activity(
            "generate_scenario_activity",
            {
                "mensagem": input.mensagem_original,
                "estado": input.estado_emocional,
                "contexto_anterior": contexto,
            },
            schedule_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry,
        )

        return RefinementResult(
            analysis_id=input.analysis_id,
            cenario_refinado=cenario_refinado,
        )
