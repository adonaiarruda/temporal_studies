from dataclasses import dataclass
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy


@dataclass
class AnalysisInput:
    mensagem: str


@dataclass
class AnalysisResult:
    mensagem: str
    estado_emocional: str
    confianca_emocao: float
    cenario: str


@workflow.defn
class AnalysisWorkflow:

    @workflow.run
    async def run(self, input: AnalysisInput) -> AnalysisResult:
        retry = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_attempts=3,
        )
        timeout = timedelta(minutes=2)

        emocao: dict = await workflow.execute_activity(
            "detect_emotion_activity",
            input.mensagem,
            schedule_to_close_timeout=timeout,
            retry_policy=retry,
        )

        cenario: str = await workflow.execute_activity(
            "generate_scenario_activity",
            {
                "mensagem": input.mensagem,
                "estado": emocao["estado"],
                "contexto_anterior": "",
            },
            schedule_to_close_timeout=timeout,
            retry_policy=retry,
        )

        return AnalysisResult(
            mensagem=input.mensagem,
            estado_emocional=emocao["estado"],
            confianca_emocao=emocao["confianca"],
            cenario=cenario,
        )
