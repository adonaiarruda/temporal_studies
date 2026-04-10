import logging
from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn(name="notify_activity")
async def notify_activity(params: dict) -> None:
    workflow_id = params.get("workflow_id", "unknown")
    estado = params.get("estado_emocional", "unknown")
    logger.info(
        "Workflow completed",
        extra={"workflow_id": workflow_id, "estado_emocional": estado},
    )
