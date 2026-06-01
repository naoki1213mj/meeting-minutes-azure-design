import azure.durable_functions as df
import azure.functions as func

from meeting_minutes_backend.auth import resolve_auth_context
from meeting_minutes_backend.entrypoints import complete_upload_with_instance_id
from meeting_minutes_backend.services import get_job_service


async def main(req: func.HttpRequest, starter: str) -> func.HttpResponse:
    jobid = req.route_params.get("jobId") or req.route_params["jobid"]
    auth = resolve_auth_context(req.headers)
    existing_instance_id = get_job_service().get_orchestration_instance_id(auth, jobid)
    if existing_instance_id:
        return complete_upload_with_instance_id(req, jobid, existing_instance_id)

    client = df.DurableOrchestrationClient(starter)
    instance_id = await client.start_new(
        "MeetingMinutesOrchestrator",
        instance_id=jobid,
        client_input={
            "tenantId": auth.tenant_id,
            "jobId": jobid,
            "userId": auth.user_id,
        },
    )
    return complete_upload_with_instance_id(req, jobid, instance_id)
