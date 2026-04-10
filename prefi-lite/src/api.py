import os
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

from src.workflows.analysis_workflow import AnalysisInput, AnalysisResult, AnalysisWorkflow
from src.workflows.refinement_workflow import RefinementInput, RefinementResult, RefinementWorkflow

load_dotenv()

app = FastAPI(title="PreFi Lite")

_temporal_client: Client | None = None


async def get_client() -> Client:
    global _temporal_client
    if _temporal_client is None:
        _temporal_client = await Client.connect(
            os.environ.get("TEMPORAL_HOST", "localhost:7233")
        )
    return _temporal_client


TASK_QUEUE = os.environ.get("TEMPORAL_TASK_QUEUE", "prefi-lite")


# --- Schemas ---

class AnalysisRequest(BaseModel):
    mensagem: str


class RefinementRequest(BaseModel):
    analysis_id: str
    nota: int
    feedback: str


def _raise_if_not_found(e: RPCError, detail: str) -> None:
    if e.status == RPCStatusCode.NOT_FOUND:
        raise HTTPException(status_code=404, detail=detail)
    raise e


# --- Endpoints ---

@app.post("/analysis/start")
async def start_analysis(body: AnalysisRequest):
    client = await get_client()
    workflow_id = f"analysis-{uuid.uuid4().hex[:8]}"

    await client.start_workflow(
        AnalysisWorkflow.run,
        AnalysisInput(mensagem=body.mensagem),
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    return {"workflow_id": workflow_id, "status": "running"}


@app.get("/analysis/{workflow_id}/result")
async def get_analysis_result(workflow_id: str):
    client = await get_client()

    try:
        handle = client.get_workflow_handle(workflow_id)
        result: AnalysisResult = await handle.result()
    except RPCError as e:
        _raise_if_not_found(e, "Workflow not found")

    return {
        "workflow_id": workflow_id,
        "estado_emocional": result.estado_emocional,
        "confianca_emocao": result.confianca_emocao,
        "cenario": result.cenario,
        "status": "completed",
    }


@app.post("/refinement/start")
async def start_refinement(body: RefinementRequest):
    client = await get_client()

    try:
        analysis_handle = client.get_workflow_handle(body.analysis_id)
        analysis_result: AnalysisResult = await analysis_handle.result()
    except RPCError as e:
        _raise_if_not_found(e, f"Analysis workflow '{body.analysis_id}' not found")

    workflow_id = f"refinement-{uuid.uuid4().hex[:8]}"

    await client.start_workflow(
        RefinementWorkflow.run,
        RefinementInput(
            analysis_id=body.analysis_id,
            mensagem_original=analysis_result.mensagem,
            cenario_anterior=analysis_result.cenario,
            estado_emocional=analysis_result.estado_emocional,
            nota=body.nota,
            feedback=body.feedback,
        ),
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    return {"workflow_id": workflow_id, "status": "running"}


@app.get("/refinement/{workflow_id}/result")
async def get_refinement_result(workflow_id: str):
    client = await get_client()

    try:
        handle = client.get_workflow_handle(workflow_id)
        result: RefinementResult = await handle.result()
    except RPCError as e:
        _raise_if_not_found(e, "Workflow not found")

    return {
        "workflow_id": workflow_id,
        "analysis_id": result.analysis_id,
        "cenario_refinado": result.cenario_refinado,
        "status": "completed",
    }
