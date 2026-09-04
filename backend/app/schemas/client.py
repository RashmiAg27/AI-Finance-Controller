from datetime import datetime

from pydantic import BaseModel


class ClientCreateRequest(BaseModel):
    code: str
    name: str


class ClientResponse(BaseModel):
    id: str
    code: str
    name: str
    status: str
    display_timezone: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConfigVersionCreateRequest(BaseModel):
    raw_yaml: str


class ConfigVersionResponse(BaseModel):
    id: str
    client_id: str
    version: int
    config_hash: str
    status: str
    created_at: datetime
    activated_at: datetime | None

    model_config = {"from_attributes": True}
