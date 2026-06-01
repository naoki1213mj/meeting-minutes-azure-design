import azure.functions as func

from meeting_minutes_backend.entrypoints import get_minutes


def main(req: func.HttpRequest) -> func.HttpResponse:
    jobid = req.route_params.get("jobId") or req.route_params["jobid"]
    return get_minutes(req, jobid)
