from pydantic import BaseModel


class SlideModification(BaseModel):
    slide_index: int
    action: str
    data: dict
