import azure.functions as func

from meeting_minutes_backend.entrypoints import (
    complete_upload as handle_complete_upload,
)
from meeting_minutes_backend.entrypoints import (
    create_job as handle_create_job,
)
from meeting_minutes_backend.entrypoints import (
    get_job as handle_get_job,
)
from meeting_minutes_backend.entrypoints import (
    get_minutes as handle_get_minutes,
)
from meeting_minutes_backend.entrypoints import (
    get_transcript as handle_get_transcript,
)
from meeting_minutes_backend.entrypoints import (
    health as handle_health,
)

# Local/test entrypoint only. Azure deployment uses function.json wrappers and
# excludes this file via .funcignore because Python v2 indexing was unstable in
# the validated Python 3.13 Functions environment.
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.function_name(name="health")
@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return handle_health(req)


@app.function_name(name="create_job")
@app.route(route="jobs", methods=["POST"])
def create_job(req: func.HttpRequest) -> func.HttpResponse:
    return handle_create_job(req)


@app.function_name(name="get_job")
@app.route(route="jobs/{jobId}", methods=["GET"])
def get_job(req: func.HttpRequest, jobId: str) -> func.HttpResponse:
    return handle_get_job(req, jobId)


@app.function_name(name="get_transcript")
@app.route(route="jobs/{jobId}/transcript", methods=["GET"])
def get_transcript(req: func.HttpRequest, jobId: str) -> func.HttpResponse:
    return handle_get_transcript(req, jobId)


@app.function_name(name="get_minutes")
@app.route(route="jobs/{jobId}/minutes", methods=["GET"])
def get_minutes(req: func.HttpRequest, jobId: str) -> func.HttpResponse:
    return handle_get_minutes(req, jobId)


@app.function_name(name="complete_upload")
@app.route(route="jobs/{jobId}/upload-complete", methods=["POST"])
def complete_upload(req: func.HttpRequest, jobId: str) -> func.HttpResponse:
    return handle_complete_upload(req, jobId)
