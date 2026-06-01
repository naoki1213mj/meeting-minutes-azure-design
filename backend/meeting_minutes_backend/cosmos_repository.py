from __future__ import annotations

from azure.core.credentials import TokenCredential
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceExistsError, CosmosResourceNotFoundError

from meeting_minutes_backend.models import JobRecord
from meeting_minutes_backend.repositories import JobRepository


class CosmosJobRepository(JobRepository):
    """Cosmos DB repository using data-plane RBAC.

    The Functions managed identity requires a Cosmos DB data-plane role such as
    Cosmos DB Built-in Data Contributor scoped to the account/database/container.
    """

    def __init__(
        self,
        endpoint: str,
        database_name: str,
        jobs_container_name: str,
        credential: TokenCredential,
    ) -> None:
        client = CosmosClient(url=endpoint, credential=credential)
        database = client.get_database_client(database_name)
        self._container = database.get_container_client(jobs_container_name)

    def create(self, record: JobRecord) -> JobRecord:
        item = _record_to_item(record)
        try:
            self._container.create_item(item)
        except CosmosResourceExistsError:
            self._container.upsert_item(item)
        return record

    def get(self, tenant_id: str, job_id: str) -> JobRecord | None:
        try:
            item = self._container.read_item(item=job_id, partition_key=tenant_id)
        except CosmosResourceNotFoundError:
            return None
        return _item_to_record(item)

    def save(self, record: JobRecord) -> JobRecord:
        self._container.upsert_item(_record_to_item(record))
        return record


def _record_to_item(record: JobRecord) -> dict[str, object]:
    item = record.model_dump(mode="json")
    item["id"] = record.jobId
    return item


def _item_to_record(item: dict[str, object]) -> JobRecord:
    record_item = {key: value for key, value in item.items() if not key.startswith("_")}
    record_item.pop("id", None)
    return JobRecord.model_validate(record_item)
